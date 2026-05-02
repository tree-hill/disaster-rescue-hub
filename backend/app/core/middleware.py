"""请求级中间件。

RequestIdMiddleware（纯 ASGI 实现）：
- 每请求生成或透传 `X-Request-Id`（客户端可携带以串联全链路）
- 写入 `scope["state"]["request_id"]` 供 handler 通过 `request.state` 读取
- 通过包装 send 注入响应头 `X-Request-Id`（API_SPEC §0.8 必须）

为什么不用 starlette.middleware.base.BaseHTTPMiddleware：
- 它与 FastAPI `@app.exception_handler(Exception)` 兜底 handler 存在
  已知冲突（Starlette #1996 / FastAPI #4719）：handler 已生成响应但
  exception 仍会被 BaseHTTPMiddleware 重新抛出，导致客户端拿不到响应。
  纯 ASGI 中间件直接包装 send 就没有这个问题。
"""
from __future__ import annotations

import uuid
from typing import Awaitable, Callable, MutableMapping

REQUEST_ID_HEADER = "X-Request-Id"
_REQUEST_ID_HEADER_BYTES = b"x-request-id"

Scope = MutableMapping[str, object]
Message = MutableMapping[str, object]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def generate_request_id() -> str:
    """生成 req-<uuid4-hex32> 形式的请求 ID（API_SPEC §0.8）。"""
    return f"req-{uuid.uuid4().hex}"


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        # 读客户端可能传入的 X-Request-Id
        rid: str | None = None
        for key, value in scope.get("headers", []) or []:
            if key.lower() == _REQUEST_ID_HEADER_BYTES:
                try:
                    rid = value.decode("latin-1") or None
                except Exception:
                    rid = None
                break
        if not rid:
            rid = generate_request_id()

        # 注入 request.state.request_id（Starlette Request.state 读 scope["state"]）
        scope.setdefault("state", {})  # type: ignore[arg-type]
        state = scope["state"]
        if isinstance(state, dict):
            state["request_id"] = rid

        rid_bytes = rid.encode("latin-1")

        async def send_wrapper(message: Message) -> None:
            if message.get("type") == "http.response.start":
                # 移除已存在的同名 header（防御）+ 追加我们的
                headers = [
                    (k, v)
                    for (k, v) in (message.get("headers") or [])
                    if k.lower() != _REQUEST_ID_HEADER_BYTES
                ]
                headers.append((_REQUEST_ID_HEADER_BYTES, rid_bytes))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
