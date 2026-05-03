"""WebSocket 连接生命周期事件：connect / subscribe / unsubscribe / disconnect。

严格对照 WS_EVENTS §0.2（认证）+ §0.4（房间）+ §2（welcome / subscribed / auth_error）。

设计：
- JWT 校验：query 参数 ?token=<access JWT>（WS_EVENTS §0.2 规范），同时也兼容
  socket.io-client 推荐的 auth dict {token: ...}
- 房间访问规则：
    commander 房间 = commander 或 admin 角色
    admin 房间    = 仅 admin 角色
    observer       = 仅可连接但不可订阅任何房间（收不到推送）
- 连接成功立即 emit `welcome`；失败 emit `auth_error` 并 raise ConnectionRefusedError
  让 socketio 在握手期拒绝
- subscribe 部分成功也算成功：通过的房间一并写入 `subscribed.rooms`，被拒的逐条
  emit `subscribe_error`
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs
from uuid import UUID, uuid4

import socketio
from jose import ExpiredSignatureError, JWTError

from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.db.session import async_session_maker
from app.repositories.user import UserRepository
from app.ws.server import sio

logger = logging.getLogger(__name__)


# 房间访问规则（WS_EVENTS §0.4 + 项目角色矩阵 commander/admin/observer）
ROOM_ROLE_REQUIREMENTS: dict[str, set[str]] = {
    "commander": {"commander", "admin"},
    "admin": {"admin"},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_token(environ: dict[str, Any], auth: Any) -> str | None:
    """优先 auth dict（Socket.IO 推荐方式），回退 query string ?token=（WS_EVENTS §0.2）。"""
    if isinstance(auth, dict):
        token = auth.get("token")
        if token:
            return str(token)
    qs = environ.get("QUERY_STRING", "")
    if qs:
        params = parse_qs(qs)
        vals = params.get("token", [])
        if vals:
            return vals[0]
    return None


class _AuthFailed(Exception):
    """内部异常：携带 WS_EVENTS §2 auth_error.reason 字段值。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def _resolve_user(token: str) -> dict[str, Any]:
    """解析 JWT + 加载用户角色，返回写入 socketio session 的最小字段。

    - 过期 → reason='token_expired'
    - 任何其他失效（签名错 / type≠access / sub 非 UUID / 用户不存在或停用）→ reason='invalid'
      不暴露具体原因（防探测，对齐 deps.py 设计）
    """
    try:
        payload = decode_token(token)
    except ExpiredSignatureError as exc:
        raise _AuthFailed("token_expired") from exc
    except JWTError as exc:
        raise _AuthFailed("invalid") from exc

    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise _AuthFailed("invalid")

    sub = payload.get("sub")
    if not sub:
        raise _AuthFailed("invalid")
    try:
        user_id = UUID(str(sub))
    except (TypeError, ValueError) as exc:
        raise _AuthFailed("invalid") from exc

    async with async_session_maker() as session:
        users = UserRepository(session)
        user = await users.find_by_id(user_id)
        if user is None or not user.is_active:
            raise _AuthFailed("invalid")
        roles, _perms = await users.get_roles_and_permissions(user.id)

    return {
        "user_id": str(user.id),
        "username": user.username,
        "display_name": user.display_name,
        "roles": roles,
    }


async def connect(sid: str, environ: dict[str, Any], auth: Any = None) -> None:
    """握手事件。校验 JWT，成功 → emit welcome；失败 → emit auth_error + disconnect。

    重要：不 raise ConnectionRefusedError —— 那会让 Socket.IO 在 namespace 握手期
    直接拒绝，先前 emit 的 auth_error 包来不及送达客户端。改为：
      让握手成功 → emit auth_error → 主动 disconnect。
    这样客户端能正常收到 auth_error 事件（WS_EVENTS §0.2 字面要求）。
    """
    token = _extract_token(environ, auth)
    reason: str | None = None
    user_session: dict[str, Any] | None = None

    if not token:
        reason = "invalid"
    else:
        try:
            user_session = await _resolve_user(token)
        except _AuthFailed as exc:
            reason = exc.reason

    if reason is not None:
        await sio.emit("auth_error", {"reason": reason}, to=sid)
        # 主动断开：让 emit 落地后再断（asyncio 串行 await 保证顺序）
        await sio.disconnect(sid)
        return

    assert user_session is not None  # mypy 提示
    await sio.save_session(sid, user_session)
    await sio.emit(
        "welcome",
        {
            "event_id": str(uuid4()),
            "timestamp": _now_iso(),
            "session_id": sid,
            "user": {
                "id": user_session["user_id"],
                "username": user_session["username"],
                "roles": user_session["roles"],
            },
            "server_time": _now_iso(),
        },
        to=sid,
    )
    logger.info(
        "ws_connected",
        extra={"sid": sid, "user_id": user_session["user_id"]},
    )


async def subscribe(sid: str, data: Any) -> None:
    """加入房间。按 ROOM_ROLE_REQUIREMENTS 守卫角色。"""
    rooms = data.get("rooms") if isinstance(data, dict) else None
    if not isinstance(rooms, list) or not rooms:
        await sio.emit(
            "subscribe_error",
            {"room": None, "reason": "invalid_payload"},
            to=sid,
        )
        return

    user_session = await sio.get_session(sid)
    user_roles: set[str] = set(user_session.get("roles", []))
    granted: list[str] = []
    for room in rooms:
        if not isinstance(room, str):
            await sio.emit(
                "subscribe_error",
                {"room": str(room), "reason": "invalid_room"},
                to=sid,
            )
            continue
        required = ROOM_ROLE_REQUIREMENTS.get(room)
        if required is None:
            await sio.emit(
                "subscribe_error",
                {"room": room, "reason": "unknown_room"},
                to=sid,
            )
            continue
        if not (user_roles & required):
            await sio.emit(
                "subscribe_error",
                {"room": room, "reason": "permission_denied"},
                to=sid,
            )
            continue
        await sio.enter_room(sid, room)
        granted.append(room)

    if granted:
        await sio.emit(
            "subscribed",
            {
                "event_id": str(uuid4()),
                "timestamp": _now_iso(),
                "rooms": granted,
            },
            to=sid,
        )
        logger.info("ws_subscribed", extra={"sid": sid, "rooms": granted})


async def unsubscribe(sid: str, data: Any) -> None:
    """离开房间（无错误响应；幂等）。"""
    rooms = data.get("rooms") if isinstance(data, dict) else None
    if not isinstance(rooms, list):
        return
    for room in rooms:
        if isinstance(room, str):
            await sio.leave_room(sid, room)


async def disconnect(sid: str) -> None:
    """断开连接。socketio 自动清理房间归属，本处仅记录日志。"""
    logger.info("ws_disconnected", extra={"sid": sid})


def register_handlers(server: socketio.AsyncServer) -> None:
    """显式注册所有事件 handler。

    main.py 在创建 ASGIApp 之前调用一次。不使用 @sio.event 装饰器以避免 import
    side effect（让 handler 注册时机由调用方控制）。
    """
    server.on("connect", connect)
    server.on("subscribe", subscribe)
    server.on("unsubscribe", unsubscribe)
    server.on("disconnect", disconnect)
