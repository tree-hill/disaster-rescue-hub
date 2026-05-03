"""WS 事件推送统一入口。

设计：
- 任何 service / agent 想推送 WS 事件 → 调用 `await push_event(name, payload, room=...)`
- 自动注入 `event_id`（uuid4）+ `timestamp`（ISO 8601 UTC），对照 WS_EVENTS §0.6
  通用约定与 BUSINESS_RULES §8 INV-F「每个 WS 事件必须有 event_id 和 timestamp」
- room 默认 `commander`；admin 房间需显式指定（如 robot.recall_initiated 同时发到
  commander+admin 时，由调用方两次 push_event）

为什么独立成模块：
- handlers.py 处理客户端入站事件，broadcaster.py 处理 1Hz pull-model 批量推送，
  其余事件型推送（fault_occurred / recall_initiated / state_changed 等）需要一个
  统一出口；放在 ws/ 子包下保持 WS 关注点收敛
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.ws.server import sio


async def push_event(
    name: str,
    payload: dict[str, Any],
    *,
    room: str = "commander",
) -> None:
    """统一 WS 事件推送（自动加 event_id + timestamp）。"""
    enriched: dict[str, Any] = {
        "event_id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    await sio.emit(name, enriched, room=room)
