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


async def _relay_auction_started(payload: dict[str, Any]) -> None:
    await push_event("auction.started", payload, room="commander")


async def _relay_auction_bid_submitted(payload: dict[str, Any]) -> None:
    await push_event("auction.bid_submitted", payload, room="commander")


async def _relay_auction_completed(payload: dict[str, Any]) -> None:
    await push_event("auction.completed", payload, room="commander")


async def _relay_auction_failed(payload: dict[str, Any]) -> None:
    await push_event("auction.failed", payload, room="commander")


async def _relay_dispatch_algorithm_changed(payload: dict[str, Any]) -> None:
    """HITL 算法切换 → commander + admin 两房间（WS_EVENTS §5）。

    push_event 每次注入新的 event_id / timestamp；前端通常只在 commander 或 admin
    单房间订阅，重复推送是双房间的契约本身（不是同房间重发，无去重压力）。
    """
    await push_event("dispatch.algorithm_changed", payload, room="commander")
    await push_event("dispatch.algorithm_changed", payload, room="admin")


async def _relay_task_reassigned(payload: dict[str, Any]) -> None:
    """HITL 改派业务事件 → commander 房间（WS_EVENTS §4）。"""
    await push_event("task.reassigned", payload, room="commander")


async def _relay_intervention_recorded(payload: dict[str, Any]) -> None:
    """HITL 通用审计事件 → admin 房间（WS_EVENTS §8）。

    与 task.reassigned / robot.recall_initiated 等业务事件并发触发；区别在于
    本事件只发 admin 审计页，业务面板（commander）订阅业务事件。
    """
    await push_event("intervention.recorded", payload, room="admin")


def register_ws_relays(bus: EventBus) -> None:
    """订阅本任务范围内的 WS 转推 handler。subscribe 自带去重，幂等。"""
    bus.subscribe("task.created", _relay_task_created)
    bus.subscribe("task.cancelled", _relay_task_cancelled)
    # P5.4 调度模块事件（commander 房间，对照 WS_EVENTS §5）
    bus.subscribe("auction.started", _relay_auction_started)
    bus.subscribe("auction.bid_submitted", _relay_auction_bid_submitted)
    bus.subscribe("auction.completed", _relay_auction_completed)
    bus.subscribe("auction.failed", _relay_auction_failed)
    # P5.5 HITL 算法切换（commander + admin 两房间）
    bus.subscribe("dispatch.algorithm_changed", _relay_dispatch_algorithm_changed)
    # P5.6 HITL 改派（commander 业务 + admin 审计）
    bus.subscribe("task.reassigned", _relay_task_reassigned)
    bus.subscribe("intervention.recorded", _relay_intervention_recorded)
