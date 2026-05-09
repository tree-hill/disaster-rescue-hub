"""黑板 TTL 清理后台扫描器（P6.1）。

对照 BUILD_ORDER §P6.1：「TTL 清理:定时任务每分钟清理过期条目」。

设计：与 services/dispatch_trigger.PendingAuctionScanner 一致风格 ——
- asyncio.Event + wait_for(timeout=interval) 优雅停（停止信号 1 个 tick 内响应）
- 重复 start / stop 是 no-op
- interval <= 0 视为禁用扫描器（lifespan 不启）
- 单轮失败仅 logger.exception，不退出循环，保持长生命周期协程稳定

DB / 内存清理逻辑都在 Blackboard.cleanup_expired() 内；本模块只提供调度时序。
"""
from __future__ import annotations

import asyncio
import logging

from app.communication.blackboard import get_blackboard

logger = logging.getLogger(__name__)


class BlackboardCleanupScanner:
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
            logger.warning("blackboard_cleanup_scanner_already_started")
            return
        if self.interval_sec <= 0:
            logger.info(
                "blackboard_cleanup_scanner_disabled_zero_interval",
                extra={"interval_sec": self.interval_sec},
            )
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(
            self._run_loop(), name="blackboard_cleanup_scanner"
        )
        self._started = True
        logger.info(
            "blackboard_cleanup_scanner_started",
            extra={"interval_sec": self.interval_sec},
        )

    async def stop(self, *, timeout_sec: float = 5.0) -> None:
        if not self._started or self._task is None or self._stop is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=timeout_sec)
        except asyncio.TimeoutError:
            logger.warning("blackboard_cleanup_scanner_stop_timeout, cancelling")
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, BaseException):  # noqa: BLE001
                pass
        self._task = None
        self._stop = None
        self._started = False
        logger.info("blackboard_cleanup_scanner_stopped")

    async def _run_loop(self) -> None:
        assert self._stop is not None
        try:
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=self.interval_sec
                    )
                    return  # 收到停止信号
                except asyncio.TimeoutError:
                    pass  # 正常一轮过去
                try:
                    await get_blackboard().cleanup_expired()
                except Exception:
                    logger.exception("blackboard_cleanup_tick_failed")
        except asyncio.CancelledError:
            raise


# ---------- 进程单例 ----------


_scanner_singleton: BlackboardCleanupScanner | None = None


def get_blackboard_cleanup_scanner(*, interval_sec: float) -> BlackboardCleanupScanner:
    """单例访问器：复用同一个 scanner。interval_sec 仅在首次创建时生效。"""
    global _scanner_singleton
    if _scanner_singleton is None:
        _scanner_singleton = BlackboardCleanupScanner(interval_sec=interval_sec)
    return _scanner_singleton


def reset_scanner_for_tests() -> None:
    """仅测试用：清空单例。"""
    global _scanner_singleton
    _scanner_singleton = None
