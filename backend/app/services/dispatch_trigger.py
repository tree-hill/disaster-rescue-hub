"""任务自动触发拍卖（P5.7）。

对照：
- BUILD_ORDER §P5.7：
  1. 监听 `TaskCreatedEvent`（事件总线上的 `task.created`）→ 自动调用
     `DispatchService.start_auction(task_id)`
  2. PENDING 任务定时扫描（每 30 秒）→ 重新尝试拍卖
- BUSINESS_RULES §3.4：拍卖失败处理 —— 任务保持 PENDING；**不**自动重试，
  由系统每 30 秒扫描重新发起。本模块即 §3.4 的「定时扫描器」。
- DATA_CONTRACTS §1.8：tasks.parent_id 用于 P4.3 网格分解。被分解的父任务
  area_km2 > 1，单机器人航程 R7 几乎一定 out_of_range，没必要参与拍卖；
  本模块通过 TaskRepository.find_pending_leaves / find_by_parent 跳过父。

设计取舍：
- **独立 session per task**：每次 start_auction 都开新 session，原因有二：
  1) DispatchService.start_auction 自己调用 `session.commit()`；如果共享
     session，下一次循环里的查询可能看到「已 commit 但本会话视为脏」的状态；
  2) 后台协程跑长生命周期，长 session 会卡住 connection 池；fresh 短事务对
     连接池更友好。
- **业务异常静默**：start_auction 抛 BusinessError（404 任务消失 / 409 状态
  非 PENDING）属于「期望的竞态」—— 自动 trigger 与 PENDING scanner 可能同时
  尝试同一任务，先到的赢。logger.info 一行即可，不要 logger.error 污染告警。
- **scanner 优雅停**：用 `asyncio.Event` + `wait_for(timeout=interval)`，比
  `sleep(interval)` 退出更快（停止信号 1 个 tick 内响应）；与 EventBus.stop
  的哨兵风格一致。
- **auto_trigger 不强制要求 scanner**：两个能力独立开关；测试场景可只起
  其中一个。lifespan 用 settings.dispatch_auto_trigger_enabled 控制 trigger
  注册；scanner 用 dispatch_pending_scan_interval_sec > 0 控制启动。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from app.core.event_bus import EventBus
from app.core.exceptions import BusinessError
from app.db.session import async_session_maker
from app.repositories.task import TaskRepository
from app.services.dispatch_service import DispatchService

logger = logging.getLogger(__name__)

# task.created 是 EventBus 上的事件类型字面量，与 task_service._emit_created 一致。
EVT_TASK_CREATED = "task.created"


# ---------- 单任务触发（auto_trigger + scanner 共用）----------


async def _try_start_auction(task_id: UUID) -> None:
    """尝试为单个任务发起拍卖；竞态导致的 BusinessError 仅 info 不告警。

    打开新 session（与请求线程完全隔离），在 DispatchService.start_auction 内部
    完成 commit。失败的可能：
    - 任务被并发删除 → 404_TASK_NOT_FOUND_001
    - 任务已被先来的触发拍卖到 ASSIGNED → 409_TASK_STATUS_CONFLICT_001
    - 数据库 / 事件总线连接异常 → 走 except 分支记录 exception
    """
    async with async_session_maker() as session:
        try:
            await DispatchService(session).start_auction(task_id)
            logger.info(
                "auto_auction_triggered",
                extra={"task_id": str(task_id)},
            )
        except BusinessError as exc:
            # 404 / 409 都是预期的并发竞态，info 级即可；其他业务码仍降级 info
            # （拍卖逻辑里目前不会抛其他码，未来如新增也保守静默）。
            logger.info(
                "auto_auction_skipped",
                extra={"task_id": str(task_id), "code": exc.code},
            )
        except Exception:
            # 真实异常（DB 连不上 / 算法库炸 / event bus 未启动）→ exception
            logger.exception(
                "auto_auction_failed",
                extra={"task_id": str(task_id)},
            )


# ---------- 自动触发：订阅 task.created ----------


async def _on_task_created(payload: dict[str, Any]) -> None:
    """task.created EventBus handler。

    payload 字段（task_service._emit_created 字面）：
        - task_id: str
        - task_code, name, type, priority, target_area, created_by, child_count

    分支：
    - child_count > 0：父任务被网格分解；查 children 列表，对每个 child
      调 _try_start_auction；父本身跳过（避免给单机器人派 4 km² 以上的活）。
    - child_count == 0：直接对该任务发起拍卖。
    """
    raw_id = payload.get("task_id")
    if not raw_id:
        logger.warning("task_created_payload_missing_id", extra={"payload": payload})
        return
    try:
        task_id = UUID(str(raw_id))
    except (ValueError, TypeError):
        logger.warning(
            "task_created_payload_bad_id", extra={"task_id": str(raw_id)}
        )
        return

    child_count = int(payload.get("child_count", 0) or 0)

    if child_count > 0:
        # 父任务跳过；查子任务并逐个触发
        async with async_session_maker() as session:
            children = await TaskRepository(session).find_by_parent(task_id)
        if not children:
            logger.warning(
                "task_created_decomposed_but_no_children",
                extra={"task_id": str(task_id)},
            )
            return
        for child in children:
            await _try_start_auction(child.id)
    else:
        await _try_start_auction(task_id)


def register_auto_trigger(bus: EventBus) -> None:
    """订阅 task.created → 自动 start_auction。subscribe 自带去重，幂等。"""
    bus.subscribe(EVT_TASK_CREATED, _on_task_created)


# ---------- PENDING 扫描器：30 秒一轮 ----------


class PendingAuctionScanner:
    """后台协程：周期性扫描 PENDING 叶子任务，重新发起拍卖。

    用例（BUSINESS_RULES §3.4）：拍卖一开始没有 eligible 机器人 → auction
    FAILED + 任务保持 PENDING；30 秒后机器人电量恢复 / 故障修复 / 距离更近
    后再扫描，可能有新的 eligible 集合，拍卖成功。

    生命周期：start() / stop() 与 EventBus / AgentManager 同款；重复 start /
    stop 是 no-op。
    """

    def __init__(self, *, interval_sec: float) -> None:
        self.interval_sec = float(interval_sec)
        self._task: asyncio.Task[None] | None = None
        self._stop: asyncio.Event | None = None
        self._started: bool = False

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        if self._started:
            logger.warning("pending_auction_scanner_already_started")
            return
        if self.interval_sec <= 0:
            logger.info(
                "pending_auction_scanner_disabled_zero_interval",
                extra={"interval_sec": self.interval_sec},
            )
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(
            self._run_loop(), name="pending_auction_scanner"
        )
        self._started = True
        logger.info(
            "pending_auction_scanner_started",
            extra={"interval_sec": self.interval_sec},
        )

    async def stop(self, *, timeout_sec: float = 5.0) -> None:
        if not self._started or self._task is None or self._stop is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=timeout_sec)
        except asyncio.TimeoutError:
            logger.warning("pending_auction_scanner_stop_timeout, cancelling")
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, BaseException):  # noqa: BLE001
                pass
        self._task = None
        self._stop = None
        self._started = False
        logger.info("pending_auction_scanner_stopped")

    async def _run_loop(self) -> None:
        assert self._stop is not None
        # 启动后等待第一个 interval 才开始扫描，避免 cold-start 与
        # auto_trigger 抢同一批 task.created（两者都跑同一任务时第二次必失败）。
        try:
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=self.interval_sec
                    )
                    return  # 收到停止信号
                except asyncio.TimeoutError:
                    pass  # 正常一轮过去
                await self._scan_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("pending_auction_scanner_loop_crashed")
            raise

    async def _scan_once(self) -> None:
        try:
            async with async_session_maker() as session:
                pending = await TaskRepository(session).find_pending_leaves()
        except Exception:
            logger.exception("pending_auction_scanner_query_failed")
            return

        if not pending:
            return
        logger.info(
            "pending_auction_scanner_tick",
            extra={"pending_count": len(pending)},
        )
        for t in pending:
            if self._stop is not None and self._stop.is_set():
                break
            await _try_start_auction(t.id)


# ---------- 全局单例（lifespan 注入用） ----------


_scanner_singleton: PendingAuctionScanner | None = None


def get_pending_auction_scanner(*, interval_sec: float) -> PendingAuctionScanner:
    """单例访问器：复用同一个 scanner。interval_sec 仅在首次创建时生效。"""
    global _scanner_singleton
    if _scanner_singleton is None:
        _scanner_singleton = PendingAuctionScanner(interval_sec=interval_sec)
    return _scanner_singleton


def reset_scanner_for_tests() -> None:
    """仅测试用：清空单例，便于不同 interval 的隔离测试。"""
    global _scanner_singleton
    _scanner_singleton = None
