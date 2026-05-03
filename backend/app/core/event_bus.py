"""进程内事件总线（asyncio.Queue 发布订阅）。

对照 BUILD_ORDER §P4.5：
- `publish(event_type, payload)`：把领域事件投递给后台 dispatcher
- `subscribe(event_type, handler)`：注册 async handler（事件类型字符串匹配）

设计要点：
- 与 AgentManager 同款单例 + 生命周期模式（start_all / stop_all 风格的 start / stop）
- 后台 dispatch loop 单协程持续 `queue.get()`，按 event_type 找到 handler 列表，
  用 `asyncio.gather` 并发调用；任何 handler 抛错只 logger.exception 不影响 bus
- `publish` 是 fire-and-forget：put 进 queue 后立即返回，调用方不阻塞
  （service 层无需等 WS emit 完成；如果 handler 慢，不会拖累 HTTP 响应）
- 停止：`stop()` 投递哨兵 + wait_for(timeout) + 超时 cancel；与 AgentManager 一致
- 单个 EventBus 实例对应一个 dispatch 协程；测试可用 reset_for_tests 清空单例

事件载荷约定：
- 总线内传递「业务 payload（dict）」，**不含** event_id / timestamp 元数据
- 元数据由 WS bridge（`app/ws/event_bridge.py`）调用 `push_event` 时统一注入
- 这样总线不与 WS 协议耦合，未来可以接入审计 sink / Kafka 中继，handler 改一处即可
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]

# 内部哨兵：stop() 时投递，dispatch loop 见到立即退出
_STOP_SENTINEL: tuple[str, dict[str, Any]] = ("__stop__", {})


class EventBus:
    _instance: "EventBus | None" = None

    def __init__(self) -> None:
        # queue / event 不要在 __init__ 里立刻创建（asyncio 对象绑定 event loop），
        # 改在 start() 中按需构造，与 lifespan / 测试的事件循环对齐。
        self._queue: asyncio.Queue[tuple[str, dict[str, Any]]] | None = None
        self._subs: dict[str, list[EventHandler]] = {}
        self._task: asyncio.Task[None] | None = None
        self._started: bool = False

    # ---------- 单例 ----------
    @classmethod
    def get_instance(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_for_tests(cls) -> None:
        """仅用于测试：清空单例引用 + 订阅。"""
        cls._instance = None

    # ---------- 订阅 ----------
    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """注册事件 handler。同一 (event_type, handler) 不会重复添加（幂等）。"""
        bucket = self._subs.setdefault(event_type, [])
        if handler not in bucket:
            bucket.append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        bucket = self._subs.get(event_type)
        if not bucket:
            return
        try:
            bucket.remove(handler)
        except ValueError:
            pass

    def subscribers(self, event_type: str) -> list[EventHandler]:
        """快照，便于测试断言。"""
        return list(self._subs.get(event_type, []))

    # ---------- 发布 ----------
    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        """投递事件；bus 未启动则丢弃 + 警告（避免静默累积）。"""
        if self._queue is None or not self._started:
            logger.warning(
                "event_bus_not_started_drop",
                extra={"event_type": event_type},
            )
            return
        await self._queue.put((event_type, payload))

    # ---------- 生命周期 ----------
    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        """启动 dispatcher 协程。重复调用是 no-op。"""
        if self._started:
            logger.warning("event_bus_already_started")
            return
        self._queue = asyncio.Queue()
        self._task = asyncio.create_task(self._dispatch_loop(), name="event_bus")
        self._started = True
        logger.info("event_bus_started")

    async def stop(self, *, timeout_sec: float = 5.0) -> None:
        """优雅停止：投哨兵 → wait_for → 超时 cancel。"""
        if not self._started or self._task is None or self._queue is None:
            return
        await self._queue.put(_STOP_SENTINEL)
        try:
            await asyncio.wait_for(self._task, timeout=timeout_sec)
        except asyncio.TimeoutError:
            logger.warning("event_bus_stop_timeout, cancelling dispatcher")
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, BaseException):  # noqa: BLE001
                pass
        self._task = None
        self._queue = None
        self._started = False
        logger.info("event_bus_stopped")

    # ---------- 内部 ----------
    async def _dispatch_loop(self) -> None:
        assert self._queue is not None
        while True:
            event_type, payload = await self._queue.get()
            if event_type == _STOP_SENTINEL[0]:
                return
            handlers = list(self._subs.get(event_type, []))
            if not handlers:
                continue
            await asyncio.gather(
                *(self._safe_call(event_type, h, payload) for h in handlers),
                return_exceptions=False,
            )

    async def _safe_call(
        self,
        event_type: str,
        handler: EventHandler,
        payload: dict[str, Any],
    ) -> None:
        try:
            await handler(payload)
        except Exception:
            logger.exception(
                "event_handler_failed",
                extra={"event_type": event_type, "handler": getattr(handler, "__name__", repr(handler))},
            )


def get_event_bus() -> EventBus:
    """便捷访问器（lifespan / service 注入用）。"""
    return EventBus.get_instance()
