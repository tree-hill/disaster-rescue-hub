"""事件总线 → WebSocket 转推桥。

对照 BUILD_ORDER §P4.5：「与 WS 集成：某些事件 (`task.created` 等) 自动转推 WS」。

设计：
- 总线只负责领域事件分发；WS 协议字段（event_id / timestamp）由 push_event 注入
- 本桥接器把领域事件类型直接复用为 WS 事件名（task.created / task.cancelled）
- 房间默认 commander；admin 房间的转推（如 intervention.recorded）留给后续任务
- register_ws_relays 可重复调用：EventBus.subscribe 内部去重保证幂等

显式不在本任务接入：
- robot.recall_initiated / recall_completed / fault_occurred / state_changed
  这些事件目前由 RobotAgent / RecallService 直接 push_event，避免在 P3 已上线
  的协程上做大改造；P5 dispatch 落地时一并迁到 bus.publish 风格
"""
from __future__ import annotations

from typing import Any

from app.core.event_bus import EventBus
from app.ws.events import push_event


async def _relay_task_created(payload: dict[str, Any]) -> None:
    await push_event("task.created", payload, room="commander")


async def _relay_task_cancelled(payload: dict[str, Any]) -> None:
    await push_event("task.cancelled", payload, room="commander")


def register_ws_relays(bus: EventBus) -> None:
    """订阅本任务范围内的 WS 转推 handler。subscribe 自带去重，幂等。"""
    bus.subscribe("task.created", _relay_task_created)
    bus.subscribe("task.cancelled", _relay_task_cancelled)
