"""KPI 聚合服务（P7.1）。

对照：
- BUILD_ORDER §P7.1：`app/situation/kpi_aggregator.py`：KPI 聚合服务,1Hz 写缓存,WS 推送
- API_SPEC §6 GET /situation/kpi 200 字段
- WS_EVENTS §7 kpi.snapshot（1Hz commander 房间）
- DATA_CONTRACTS §1.5 robots / §1.6 robot_states / §1.8 tasks / §1.14 alerts

聚合口径：
- online_robots：robot_states 中 fsm_state ≠ FAULT 且 recorded_at >= now-15s 的不同
  robot_id 数（与 BUSINESS_RULES §2.2.2「连续 15 秒未上报心跳 → comm_lost」对齐）。
- total_robots：robots.is_active = TRUE 的总数。
- completion_rate：tasks 中近 24h 内 COMPLETED / (COMPLETED+FAILED+CANCELLED) × 100。
  分母 0 时返回 0。
- avg_response_sec：近 24h 内已 COMPLETED 任务的 (started_at - created_at).total_seconds()
  平均；分母 0 返回 0。
- battery_distribution：每个机器人取最新一条 robot_state 的 battery，分桶 high>=60 /
  30<=mid<60 / low<30。无最新状态的机器人不计入。
- active_alerts：alerts 中 acknowledged_at IS NULL AND is_ignored = FALSE。
- active_tasks：tasks 中 status IN (PENDING, ASSIGNED, EXECUTING)。

设计：
- **最近一次快照缓存** + 1Hz 协程推送：REST GET /situation/kpi 命中缓存即返回，避免
  每次请求都全表扫；缓存为 None 时同步聚合一次。
- **fresh session per tick**：和其他后台扫描器同款，避免长事务卡连接池。
- **失败容错**：单轮聚合 fail → logger.exception，缓存保留上一个版本；不会推送 WS。
- **room='commander'**：与 WS_EVENTS §7 一致；admin 房间不重复推送（admin 订阅
  alert.* / intervention.recorded 已够用）。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_maker
from app.models.alert import Alert
from app.models.robot import Robot, RobotState
from app.models.task import Task
from app.schemas.situation import BatteryDistribution, KPISnapshot
from app.ws.events import push_event

logger = logging.getLogger(__name__)


HEARTBEAT_TIMEOUT_SEC = 15  # BUSINESS_RULES §2.2.2
COMPLETION_WINDOW_HOURS = 24

BATTERY_HIGH_THRESHOLD = 60.0
BATTERY_MID_THRESHOLD = 30.0


async def _aggregate_once(session: AsyncSession) -> KPISnapshot:
    """在给定 session 内一次性聚合 KPI；不修改数据，纯读。"""
    now = datetime.now(timezone.utc)
    heartbeat_cutoff = now - timedelta(seconds=HEARTBEAT_TIMEOUT_SEC)
    completion_cutoff = now - timedelta(hours=COMPLETION_WINDOW_HOURS)

    # total_robots：is_active=TRUE
    total_robots = int(
        (
            await session.execute(
                select(func.count()).select_from(Robot).where(Robot.is_active.is_(True))
            )
        ).scalar_one()
    )

    # online_robots：心跳 < cutoff 且 fsm ≠ FAULT 的不同 robot_id 数
    online_stmt = (
        select(func.count(func.distinct(RobotState.robot_id)))
        .select_from(RobotState)
        .where(
            RobotState.recorded_at >= heartbeat_cutoff,
            RobotState.fsm_state != "FAULT",
        )
    )
    online_robots = int((await session.execute(online_stmt)).scalar_one())

    # completion_rate：近 24h 内已结束的任务（COMPLETED/FAILED/CANCELLED）作分母
    completion_buckets_stmt = (
        select(Task.status, func.count())
        .where(
            Task.created_at >= completion_cutoff,
            Task.status.in_(("COMPLETED", "FAILED", "CANCELLED")),
        )
        .group_by(Task.status)
    )
    rows = (await session.execute(completion_buckets_stmt)).all()
    finished_total = sum(int(c) for _, c in rows)
    completed = sum(int(c) for s, c in rows if s == "COMPLETED")
    completion_rate = (
        round(completed / finished_total * 100.0, 1) if finished_total > 0 else 0.0
    )

    # avg_response_sec：started_at - created_at（COMPLETED 内）平均
    resp_stmt = (
        select(
            func.avg(
                func.extract("epoch", Task.started_at - Task.created_at)
            )
        )
        .where(
            Task.status == "COMPLETED",
            Task.created_at >= completion_cutoff,
            Task.started_at.is_not(None),
        )
    )
    avg_resp_val = (await session.execute(resp_stmt)).scalar_one_or_none()
    avg_response_sec = round(float(avg_resp_val), 1) if avg_resp_val is not None else 0.0

    # 电量分布：每个 robot 最新一条 state；用窗口函数 row_number=1 取 latest
    distribution = await _battery_distribution(session)

    # active_alerts：未确认且未忽略
    active_alerts = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Alert)
                .where(Alert.acknowledged_at.is_(None), Alert.is_ignored.is_(False))
            )
        ).scalar_one()
    )

    # active_tasks
    active_tasks = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Task)
                .where(Task.status.in_(("PENDING", "ASSIGNED", "EXECUTING")))
            )
        ).scalar_one()
    )

    return KPISnapshot(
        online_robots=online_robots,
        total_robots=total_robots,
        completion_rate=completion_rate,
        avg_response_sec=avg_response_sec,
        battery_distribution=distribution,
        active_alerts=active_alerts,
        active_tasks=active_tasks,
    )


async def _battery_distribution(session: AsyncSession) -> BatteryDistribution:
    """对每个 robot 取最新 state.battery，按 60/30 阈值分桶。

    实现：用 row_number() OVER (PARTITION BY robot_id ORDER BY recorded_at DESC) = 1
    选最新行，再 GROUP BY 桶。
    """
    from sqlalchemy import case, literal_column

    rn = func.row_number().over(
        partition_by=RobotState.robot_id,
        order_by=RobotState.recorded_at.desc(),
    ).label("rn")
    sub = (
        select(RobotState.battery.label("battery"), rn)
        .subquery()
    )
    bucket = case(
        (sub.c.battery >= BATTERY_HIGH_THRESHOLD, "high"),
        (sub.c.battery >= BATTERY_MID_THRESHOLD, "mid"),
        else_="low",
    ).label("bucket")
    stmt = (
        select(bucket, func.count())
        .select_from(sub)
        .where(sub.c.rn == 1)
        .group_by(bucket)
    )
    rows = (await session.execute(stmt)).all()
    counts = {"high": 0, "mid": 0, "low": 0}
    for b, c in rows:
        counts[str(b)] = int(c)
    return BatteryDistribution(**counts)


# ============== Aggregator ==============


class KPIAggregator:
    """1Hz 协程：聚合 → 缓存 → push_event('kpi.snapshot')。"""

    def __init__(self, *, interval_sec: float = 1.0) -> None:
        self.interval_sec = float(interval_sec)
        self._task: asyncio.Task[None] | None = None
        self._stop: asyncio.Event | None = None
        self._started: bool = False
        self._last_snapshot: KPISnapshot | None = None
        self._last_at: datetime | None = None

    @property
    def started(self) -> bool:
        return self._started

    @property
    def last_snapshot(self) -> KPISnapshot | None:
        return self._last_snapshot

    async def start(self) -> None:
        if self._started:
            logger.warning("kpi_aggregator_already_started")
            return
        if self.interval_sec <= 0:
            logger.info(
                "kpi_aggregator_disabled_zero_interval",
                extra={"interval_sec": self.interval_sec},
            )
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop(), name="kpi_aggregator")
        self._started = True
        logger.info("kpi_aggregator_started", extra={"interval_sec": self.interval_sec})

    async def stop(self, *, timeout_sec: float = 5.0) -> None:
        if not self._started or self._task is None or self._stop is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=timeout_sec)
        except asyncio.TimeoutError:
            logger.warning("kpi_aggregator_stop_timeout, cancelling")
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, BaseException):  # noqa: BLE001
                pass
        self._task = None
        self._stop = None
        self._started = False
        logger.info("kpi_aggregator_stopped")

    async def _run_loop(self) -> None:
        assert self._stop is not None
        try:
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=self.interval_sec
                    )
                    return
                except asyncio.TimeoutError:
                    pass
                await self.tick_once()
        except asyncio.CancelledError:
            raise

    async def tick_once(self) -> KPISnapshot | None:
        """单轮：聚合 → 缓存 → push_event。失败仅记录不重抛。"""
        try:
            async with async_session_maker() as session:
                snap = await _aggregate_once(session)
        except Exception:
            logger.exception("kpi_aggregator_tick_failed")
            return None
        self._last_snapshot = snap
        self._last_at = datetime.now(timezone.utc)
        try:
            await push_event(
                "kpi.snapshot",
                snap.model_dump(),
                room="commander",
            )
        except Exception:
            logger.exception("kpi_snapshot_push_failed")
        return snap

    async def get_or_refresh(self) -> KPISnapshot:
        """REST 入口：若缓存为空 → 同步聚合一次再返回；否则返回缓存。"""
        if self._last_snapshot is not None:
            return self._last_snapshot
        async with async_session_maker() as session:
            snap = await _aggregate_once(session)
        self._last_snapshot = snap
        self._last_at = datetime.now(timezone.utc)
        return snap


# 进程单例
_aggregator_singleton: KPIAggregator | None = None


def get_kpi_aggregator(*, interval_sec: float = 1.0) -> KPIAggregator:
    global _aggregator_singleton
    if _aggregator_singleton is None:
        _aggregator_singleton = KPIAggregator(interval_sec=interval_sec)
    return _aggregator_singleton


def reset_for_tests() -> None:
    global _aggregator_singleton
    _aggregator_singleton = None


# 兼容性导出（避免后续脚本误用）
__all__: Sequence[str] = (
    "KPIAggregator",
    "get_kpi_aggregator",
    "reset_for_tests",
)
