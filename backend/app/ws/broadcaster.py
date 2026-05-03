"""1Hz 批量位置推送（拉模型）。

对照：
- WS_EVENTS §3 robot.position_updated（batch 模式：updates 数组）
- WS_EVENTS §12.2「25 机器人 × 1Hz = 25 events/s,batch 后 = 1 event/s ✓」
- BUILD_ORDER §P3.5「1Hz 批量推送(每秒一次,合并 25 台)」

设计：
- **拉模型**：broadcaster 单协程每秒读 AgentManager 内存快照；不动 RobotAgent 的
  `_emit_state_changed` 钩子（避免 25 个并发 emit 与 broadcaster 双推）
- 房间 commander 无客户端时跳过 emit（节流；服务端 zero-cost when no listeners）
- 单 tick 异常仅 logger.exception，不让循环死亡（与 RobotAgent.run 同款保险丝）
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.agents.manager import get_agent_manager
from app.ws.server import sio

logger = logging.getLogger(__name__)


class PositionBroadcaster:
    """commander 房间的 1Hz 批量 robot.position_updated 推送器。"""

    def __init__(self, *, interval_sec: float = 1.0) -> None:
        if interval_sec <= 0:
            raise ValueError("interval_sec 必须 > 0")
        self.interval_sec = interval_sec
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def started(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.started:
            logger.warning("position_broadcaster_already_started")
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="ws:position_broadcaster")
        logger.info(
            "position_broadcaster_started",
            extra={"interval_sec": self.interval_sec},
        )

    async def stop(self, *, timeout_sec: float = 3.0) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=timeout_sec)
        except asyncio.TimeoutError:
            logger.warning("position_broadcaster_stop_timeout, cancelling")
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("position_broadcaster_stopped")

    async def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    await self._tick()
                except Exception:  # noqa: BLE001
                    logger.exception("position_broadcaster_tick_failed")
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self.interval_sec
                    )
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise

    async def _tick(self) -> None:
        # 房间无人 → 跳过 emit（节流；并不影响后续 tick）
        if not self._has_listeners("commander"):
            return
        agents = get_agent_manager().list_agents()
        if not agents:
            return
        updates = [
            {
                "robot_id": str(a.robot_id),
                "robot_code": a.code,
                "position": dict(a.position),
                "battery": float(a.battery),
                "fsm_state": a.fsm_state,
            }
            for a in agents
        ]
        payload = {
            "event_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "updates": updates,
        }
        await sio.emit("robot.position_updated", payload, room="commander")

    def _has_listeners(self, room: str) -> bool:
        """检查房间是否有客户端。

        socketio.AsyncManager.rooms 结构：dict[namespace, dict[room, dict[sid, ...]]]
        访问失败时保守返回 True，宁可推送也不要漏。
        """
        try:
            ns_rooms = sio.manager.rooms.get("/", {})
            participants = ns_rooms.get(room, {})
            return bool(participants)
        except Exception:  # noqa: BLE001
            return True


_broadcaster: PositionBroadcaster | None = None


def get_broadcaster() -> PositionBroadcaster:
    """模块级单例访问器（与 AgentManager.get_instance 同款）。"""
    global _broadcaster
    if _broadcaster is None:
        _broadcaster = PositionBroadcaster()
    return _broadcaster


def reset_for_tests() -> None:
    global _broadcaster
    _broadcaster = None
