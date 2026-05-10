"""复盘录制器（P8.1）。

对照：
- BUILD_ORDER §P8.1：在 EXECUTING 期间每秒录制系统全量状态(robots / tasks /
  blackboard) → 写 `replay_sessions` + 关联快照
- DATA_CONTRACTS §1.15 replay_sessions（17 表内已建）
- DATA_CONTRACTS §4.12 summary 在 P8.1 扩展 snapshots / key_events 字段

设计：
- 1Hz 后台单协程（与 KPIAggregator 同款生命周期）
- **session 边界自动管理**：发现 ASSIGNED/EXECUTING 任务即开 session；session 内
  跟踪过的所有 task 都进入终态（COMPLETED/FAILED/CANCELLED）→ 自动 finalize 落库
- **帧上限**：替换为 finalize 触发器之一，防 summary JSONB 体积爆炸（默认 1800 ≈ 30 min）
- **EventBus 订阅**：collect 关键事件到 in-memory key_events buffer
- **task_completed/failed/cancelled**：通过相邻 tick 的 snapshot diff 判定（不依赖事件
  发布——task_status_machine 没有显式 publish）
- **algorithm 字段**：开 session 时取 `DispatchSettings.current_algorithm`
- **created_by NOT NULL**：开 session 时按 username='system' 查 UUID 缓存
- **失败容错**：单 tick 异常仅 logger.exception，不破坏 session 状态

线程模型：单进程 asyncio，tick 协程与 EventBus handler 都在同一 event loop；
共享 _active 用 asyncio.Lock 串行化（不是性能瓶颈，避免 list/dict 并发改写）。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.communication.blackboard import get_blackboard
from app.core.event_bus import EventBus
from app.db.session import async_session_maker
from app.models.replay import ReplaySession
from app.models.robot import Robot, RobotState
from app.models.task import Task, TaskAssignment
from app.models.user import User
from app.repositories.replay import ReplaySessionRepository

logger = logging.getLogger(__name__)


_ACTIVE_TASK_STATUSES: frozenset[str] = frozenset({"ASSIGNED", "EXECUTING"})
_TERMINAL_TASK_STATUSES: frozenset[str] = frozenset(
    {"COMPLETED", "FAILED", "CANCELLED"}
)
_TERMINAL_TO_KEY_EVENT: dict[str, str] = {
    "COMPLETED": "task_completed",
    "FAILED": "task_failed",
    "CANCELLED": "task_cancelled",
}


class _ActiveSession:
    """In-memory 录制 session（finalize 后落库）。"""

    __slots__ = (
        "started_at",
        "algorithm",
        "scenario_id",
        "snapshots",
        "key_events",
        "task_states",
        "robot_ids_used",
        "yolo_counts",
        "alert_count",
    )

    def __init__(
        self, *, started_at: datetime, algorithm: str, scenario_id: UUID | None
    ) -> None:
        self.started_at: datetime = started_at
        self.algorithm: str = algorithm
        self.scenario_id: UUID | None = scenario_id
        self.snapshots: list[dict[str, Any]] = []
        self.key_events: list[dict[str, Any]] = []
        # task_id → 上一 tick 看到的 status（用于检测终态切换）
        self.task_states: dict[UUID, str] = {}
        self.robot_ids_used: set[UUID] = set()
        self.yolo_counts: dict[str, int] = {
            "survivor": 0,
            "fire": 0,
            "smoke": 0,
            "collapsed_building": 0,
        }
        self.alert_count: int = 0

    @property
    def all_tracked_terminal(self) -> bool:
        if not self.task_states:
            return False
        return all(s in _TERMINAL_TASK_STATUSES for s in self.task_states.values())


class SnapshotRecorder:
    def __init__(
        self,
        *,
        interval_sec: float = 1.0,
        max_frames: int = 1800,
    ) -> None:
        self.interval_sec = float(interval_sec)
        self.max_frames = int(max_frames)
        self._task: asyncio.Task[None] | None = None
        self._stop: asyncio.Event | None = None
        self._started: bool = False
        self._active: _ActiveSession | None = None
        self._lock: asyncio.Lock = asyncio.Lock()
        self._system_user_id: UUID | None = None

    @property
    def started(self) -> bool:
        return self._started

    @property
    def active_session(self) -> _ActiveSession | None:
        return self._active

    # ---------- 生命周期 ----------

    async def start(self) -> None:
        if self._started:
            logger.warning("snapshot_recorder_already_started")
            return
        if self.interval_sec <= 0:
            logger.info(
                "snapshot_recorder_disabled_zero_interval",
                extra={"interval_sec": self.interval_sec},
            )
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop(), name="snapshot_recorder")
        self._started = True
        logger.info(
            "snapshot_recorder_started",
            extra={"interval_sec": self.interval_sec, "max_frames": self.max_frames},
        )

    async def stop(self, *, timeout_sec: float = 5.0) -> None:
        if not self._started or self._task is None or self._stop is None:
            # 即使未起 loop，也尝试 finalize 当前 session（测试 / 手工 tick 场景）
            await self._finalize_if_active(reason="stop")
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=timeout_sec)
        except asyncio.TimeoutError:
            logger.warning("snapshot_recorder_stop_timeout, cancelling")
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, BaseException):  # noqa: BLE001
                pass
        self._task = None
        self._stop = None
        self._started = False
        # 关停时把当前 session 落库（任务还在跑，但服务要停）
        await self._finalize_if_active(reason="stop")
        logger.info("snapshot_recorder_stopped")

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
                try:
                    await self.tick_once()
                except Exception:
                    logger.exception("snapshot_recorder_tick_failed")
        except asyncio.CancelledError:
            raise

    # ---------- 主循环单步 ----------

    async def tick_once(self) -> bool:
        """单轮：read → snapshot → 终态 diff → 必要时 finalize。

        返回 True 表示本轮录入了一帧（或新开/finalize 了 session）。
        """
        async with self._lock:
            now = datetime.now(timezone.utc)
            async with async_session_maker() as session:
                tracked_ids = set(self._active.task_states.keys()) if self._active else set()
                tasks = await self._fetch_relevant_tasks(session, tracked_ids)

                # 边界 1：当前无 active session，但发现活跃任务 → 开 session
                if self._active is None:
                    has_active_task = any(t.status in _ACTIVE_TASK_STATUSES for t in tasks)
                    if not has_active_task:
                        return False
                    await self._open_session(session, started_at=now)

                assert self._active is not None
                # 终态 diff（对所有跟踪过的 task）
                self._detect_terminal_transitions(tasks, ts=now)
                # 把新出现的活跃任务也纳入跟踪
                for t in tasks:
                    if t.status in _ACTIVE_TASK_STATUSES:
                        self._active.task_states.setdefault(t.id, t.status)
                # 录帧
                snapshot = await self._build_snapshot(session, ts=now, tasks=tasks)
                self._active.snapshots.append(snapshot)
                for tf in snapshot["tasks"]:
                    for rid in tf.get("assigned_robot_ids", []) or []:
                        self._active.robot_ids_used.add(_to_uuid(rid))

                # finalize 触发器：1) 全部 tracked task 终态  2) 帧数到上限
                should_finalize = (
                    self._active.all_tracked_terminal
                    or len(self._active.snapshots) >= self.max_frames
                )

            if should_finalize:
                await self._finalize_if_active(reason="auto", ts=now)
            return True

    # ---------- 查询 ----------

    @staticmethod
    async def _fetch_relevant_tasks(
        session: AsyncSession, tracked_ids: set[UUID]
    ) -> list[Task]:
        """活跃任务 + 已被追踪到本 session 的任务（即便已终态）。"""
        from sqlalchemy import or_

        clauses = [Task.status.in_(tuple(_ACTIVE_TASK_STATUSES))]
        if tracked_ids:
            clauses.append(Task.id.in_(tuple(tracked_ids)))
        stmt = select(Task).where(or_(*clauses))
        return list((await session.execute(stmt)).scalars().all())

    async def _build_snapshot(
        self,
        session: AsyncSession,
        *,
        ts: datetime,
        tasks: Sequence[Task],
    ) -> dict[str, Any]:
        """构 1 帧：robots（最新 state）+ tasks + blackboard 统计。"""
        from sqlalchemy import func

        # 每个机器人取 latest state（窗口函数）
        rn = func.row_number().over(
            partition_by=RobotState.robot_id,
            order_by=RobotState.recorded_at.desc(),
        ).label("rn")
        latest_sub = (
            select(
                RobotState.robot_id.label("rid"),
                RobotState.fsm_state.label("fsm"),
                RobotState.position.label("pos"),
                RobotState.battery.label("bat"),
                RobotState.current_task_id.label("ctid"),
                rn,
            ).subquery()
        )
        latest_stmt = (
            select(
                latest_sub.c.rid,
                latest_sub.c.fsm,
                latest_sub.c.pos,
                latest_sub.c.bat,
                latest_sub.c.ctid,
                Robot.code,
            )
            .join(Robot, Robot.id == latest_sub.c.rid)
            .where(latest_sub.c.rn == 1, Robot.is_active.is_(True))
        )
        robot_rows = list((await session.execute(latest_stmt)).all())
        robots_frame: list[dict[str, Any]] = []
        for rid, fsm, pos, bat, ctid, code in robot_rows:
            robots_frame.append(
                {
                    "robot_id": str(rid),
                    "code": code,
                    "fsm_state": fsm,
                    "position": dict(pos) if pos else None,
                    "battery": float(bat) if bat is not None else 0.0,
                    "current_task_id": str(ctid) if ctid else None,
                }
            )

        # tasks: 拉取 active assignments（一次查全 task_assignments）
        task_ids = [t.id for t in tasks]
        assignments_map: dict[UUID, list[UUID]] = {tid: [] for tid in task_ids}
        if task_ids:
            a_stmt = select(TaskAssignment.task_id, TaskAssignment.robot_id).where(
                TaskAssignment.task_id.in_(tuple(task_ids)),
                TaskAssignment.is_active.is_(True),
            )
            for tid, rid in (await session.execute(a_stmt)).all():
                assignments_map.setdefault(tid, []).append(rid)
        tasks_frame: list[dict[str, Any]] = []
        for t in tasks:
            tasks_frame.append(
                {
                    "task_id": str(t.id),
                    "code": t.code,
                    "status": t.status,
                    "progress": float(t.progress) if t.progress is not None else 0.0,
                    "assigned_robot_ids": [
                        str(rid) for rid in assignments_map.get(t.id, [])
                    ],
                }
            )

        # blackboard 统计（仅 by_type 计数，不落 entries 全量）
        bb_stats = get_blackboard().stats()
        blackboard_frame = {
            "total_entries": int(bb_stats.get("total_entries", 0)),
            "by_type": dict(bb_stats.get("by_type", {})),
        }

        return {
            "ts": ts.isoformat(),
            "robots": robots_frame,
            "tasks": tasks_frame,
            "blackboard": blackboard_frame,
        }

    # ---------- session 边界 ----------

    async def _open_session(
        self, session: AsyncSession, *, started_at: datetime
    ) -> None:
        from app.services.dispatch_service import get_dispatch_settings

        algorithm = get_dispatch_settings().current_algorithm
        # system 用户 UUID 缓存（首 session 解析一次）
        if self._system_user_id is None:
            await self._resolve_system_user(session)
        # 即使 system 用户不存在，也用任意可用用户兜底（防 NOT NULL 违反）
        creator = self._system_user_id
        if creator is None:
            stmt = select(User.id).where(User.is_active.is_(True)).limit(1)
            res = (await session.execute(stmt)).scalar_one_or_none()
            if res is None:
                logger.warning("snapshot_recorder_no_user_skip_open")
                return
            creator = res
            self._system_user_id = creator
        self._active = _ActiveSession(
            started_at=started_at,
            algorithm=str(algorithm),
            scenario_id=None,
        )
        # creator 同步缓存到 active session 的隐式属性，落库时取 self._system_user_id
        logger.info(
            "snapshot_recorder_session_opened",
            extra={"algorithm": algorithm, "started_at": started_at.isoformat()},
        )

    async def _resolve_system_user(self, session: AsyncSession) -> None:
        stmt = select(User.id).where(User.username == "system")
        res = (await session.execute(stmt)).scalar_one_or_none()
        if res is not None:
            self._system_user_id = res

    def _detect_terminal_transitions(
        self, tasks: Sequence[Task], *, ts: datetime
    ) -> None:
        """对照 _active.task_states，检测进入终态的 task → 写 key_event。"""
        if self._active is None:
            return
        seen_ids: set[UUID] = set()
        for t in tasks:
            seen_ids.add(t.id)
            prev = self._active.task_states.get(t.id)
            if prev is None:
                # 第一次见且非终态 → 等下一 tick 由 caller 写入 task_states
                continue
            if prev not in _TERMINAL_TASK_STATUSES and t.status in _TERMINAL_TASK_STATUSES:
                ev_type = _TERMINAL_TO_KEY_EVENT[t.status]
                self._active.key_events.append(
                    {
                        "ts": ts.isoformat(),
                        "type": ev_type,
                        "description": f"任务 {t.code} → {t.status}",
                        "related_id": str(t.id),
                    }
                )
            self._active.task_states[t.id] = t.status

    async def _finalize_if_active(
        self, *, reason: str, ts: datetime | None = None
    ) -> UUID | None:
        if self._active is None:
            return None
        active = self._active
        self._active = None  # 立刻置空，避免 finalize 期间 EventBus handler 改写
        ended_at = ts or datetime.now(timezone.utc)
        duration_sec = max(0, int((ended_at - active.started_at).total_seconds()))

        completed = sum(1 for s in active.task_states.values() if s == "COMPLETED")
        failed = sum(1 for s in active.task_states.values() if s == "FAILED")
        cancelled = sum(1 for s in active.task_states.values() if s == "CANCELLED")
        total_tasks = len(active.task_states)
        finished_total = completed + failed + cancelled
        completion_rate = (
            round(completed / finished_total * 100.0, 2) if finished_total > 0 else 0.0
        )

        intervention_count = sum(
            1
            for ev in active.key_events
            if ev.get("type") in {"intervention", "task_reassigned"}
        )

        summary = {
            "total_tasks": total_tasks,
            "completed_tasks": completed,
            "failed_tasks": failed,
            "total_robots_used": len(active.robot_ids_used),
            "total_interventions": intervention_count,
            "total_alerts": active.alert_count,
            "yolo_detections_summary": dict(active.yolo_counts),
            "snapshots": active.snapshots,
            "key_events": active.key_events,
        }

        try:
            async with async_session_maker() as session:
                repo = ReplaySessionRepository(session)
                # 名称：起止时间 + 算法
                name = (
                    f"复盘-{active.started_at.strftime('%Y%m%d-%H%M%S')}-"
                    f"{active.algorithm}"
                )
                obj = ReplaySession(
                    name=name,
                    scenario_id=active.scenario_id,
                    algorithm=active.algorithm,
                    started_at=active.started_at,
                    ended_at=ended_at,
                    duration_sec=duration_sec,
                    completion_rate=completion_rate,
                    summary=summary,
                    created_by=self._system_user_id,
                )
                await repo.save(obj)
                await session.commit()
                await session.refresh(obj)
                new_id = obj.id
        except Exception:
            logger.exception("snapshot_recorder_finalize_failed")
            return None
        logger.info(
            "snapshot_recorder_session_finalized",
            extra={
                "session_id": str(new_id),
                "reason": reason,
                "frames": len(active.snapshots),
                "key_events": len(active.key_events),
                "duration_sec": duration_sec,
            },
        )
        return new_id

    # ---------- EventBus handlers ----------

    async def _on_alert_raised(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            if self._active is None:
                return
            self._active.alert_count += 1
            self._active.key_events.append(
                {
                    "ts": _now_iso(),
                    "type": "alert",
                    "description": str(payload.get("message", "告警")),
                    "related_id": str(payload.get("alert_id"))
                    if payload.get("alert_id")
                    else None,
                }
            )

    async def _on_auction_completed(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            if self._active is None:
                return
            algo = payload.get("algorithm") or "?"
            task_code = payload.get("task_code") or "?"
            self._active.key_events.append(
                {
                    "ts": _now_iso(),
                    "type": "auction_completed",
                    "description": f"拍卖完成（{algo}）→ {task_code}",
                    "related_id": str(payload.get("auction_id"))
                    if payload.get("auction_id")
                    else None,
                }
            )

    async def _on_intervention_recorded(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            if self._active is None:
                return
            self._active.key_events.append(
                {
                    "ts": _now_iso(),
                    "type": "intervention",
                    "description": (
                        f"HITL：{payload.get('intervention_type', 'unknown')}"
                    ),
                    "related_id": str(payload.get("intervention_id"))
                    if payload.get("intervention_id")
                    else None,
                }
            )

    async def _on_task_reassigned(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            if self._active is None:
                return
            self._active.key_events.append(
                {
                    "ts": _now_iso(),
                    "type": "task_reassigned",
                    "description": (
                        f"改派：{payload.get('from_robot_code')} → "
                        f"{payload.get('to_robot_code')}"
                    ),
                    "related_id": str(payload.get("task_id"))
                    if payload.get("task_id")
                    else None,
                }
            )

    async def _on_perception_high_confidence(
        self, payload: dict[str, Any]
    ) -> None:
        cls = str(payload.get("class_name", ""))
        if cls not in self._active_session_yolo_keys():
            return
        async with self._lock:
            if self._active is None:
                return
            if cls in self._active.yolo_counts:
                self._active.yolo_counts[cls] += 1

    @staticmethod
    def _active_session_yolo_keys() -> tuple[str, ...]:
        return ("survivor", "fire", "smoke", "collapsed_building")


# ============== Helpers ==============


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_uuid(v: Any) -> UUID:
    if isinstance(v, UUID):
        return v
    return UUID(str(v))


# ============== EventBus 注册 + 单例 ==============


def register_snapshot_recorder(
    bus: EventBus, recorder: "SnapshotRecorder"
) -> None:
    """订阅与 P8.1 复盘相关的事件类型。"""
    bus.subscribe("alert.raised", recorder._on_alert_raised)
    bus.subscribe("auction.completed", recorder._on_auction_completed)
    bus.subscribe("intervention.recorded", recorder._on_intervention_recorded)
    bus.subscribe("task.reassigned", recorder._on_task_reassigned)
    bus.subscribe(
        "perception.high_confidence_alert", recorder._on_perception_high_confidence
    )


_recorder_singleton: SnapshotRecorder | None = None


def get_snapshot_recorder(
    *,
    interval_sec: float = 1.0,
    max_frames: int = 1800,
) -> SnapshotRecorder:
    global _recorder_singleton
    if _recorder_singleton is None:
        _recorder_singleton = SnapshotRecorder(
            interval_sec=interval_sec, max_frames=max_frames
        )
    return _recorder_singleton


def reset_for_tests() -> None:
    global _recorder_singleton
    _recorder_singleton = None


__all__: Sequence[str] = (
    "SnapshotRecorder",
    "get_snapshot_recorder",
    "register_snapshot_recorder",
    "reset_for_tests",
)
