from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

import socketio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agents.manager import get_agent_manager
from app.api.router import api_router
from app.core.config import settings
from app.core.event_bus import get_event_bus
from app.core.exceptions import BusinessError
from app.core.middleware import REQUEST_ID_HEADER, RequestIdMiddleware
from app.ws import handlers as ws_handlers
from app.ws.broadcaster import get_broadcaster
from app.ws.event_bridge import register_ws_relays
from app.ws.server import SOCKETIO_PATH, sio

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """启动时按需拉起 25 个 RobotAgent + WS 推送器；关闭时优雅停止。

    由 settings.mock_agents_enabled 控制（默认 False）：
    - 自检脚本 / pytest 不会自动起后台协程
    - 本地开发想看 Agent 跑：在 backend/.env 显式 MOCK_AGENTS_ENABLED=true

    顺序：
    - startup：EventBus（注册 WS 转推 handler）→ AgentManager → PositionBroadcaster
    - shutdown：先停 broadcaster（不再读 Agent），再停 AgentManager，最后停 EventBus
      （让 service 层晚发布的最后一波 task.* 事件能被 dispatch loop 消费完）
    """
    bus = get_event_bus()
    register_ws_relays(bus)
    await bus.start()
    if settings.mock_agents_enabled:
        await get_agent_manager().start_all()
        await get_broadcaster().start()
    try:
        yield
    finally:
        if settings.mock_agents_enabled:
            await get_broadcaster().stop()
            await get_agent_manager().stop_all()
        await bus.stop()


app = FastAPI(
    title="Disaster Rescue Hub API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# 中间件按 add_middleware 顺序：先加的在内层。这里我们希望
# X-Request-Id 在最外层（让所有响应都带 header），所以最后 add。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER],
)
app.add_middleware(RequestIdMiddleware)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "req-unknown")


def _error_payload(
    *,
    code: str,
    message: str,
    request_id: str,
    details: list[dict] | None = None,
) -> dict:
    return {
        "code": code,
        "message": message,
        "details": details or [],
        "request_id": request_id,
        "timestamp": _now_iso(),
    }


@app.exception_handler(BusinessError)
async def business_error_handler(
    request: Request, exc: BusinessError
) -> JSONResponse:
    rid = _request_id(request)
    return JSONResponse(
        status_code=exc.http_status,
        headers={REQUEST_ID_HEADER: rid},
        content=_error_payload(
            code=exc.code,
            message=exc.message,
            request_id=rid,
            details=exc.details,
        ),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Pydantic 请求体/查询参数校验失败 → 422_VALIDATION_FAILED_001。

    对照 BUSINESS_RULES §6.7 通用错误码。
    """
    rid = _request_id(request)
    details: list[dict] = []
    for err in exc.errors():
        # err.loc 形如 ("body", "username")；取除 body 外部分作 field
        loc = err.get("loc", ())
        field = ".".join(str(p) for p in loc[1:]) if len(loc) > 1 else None
        details.append(
            {
                "field": field,
                "code": str(err.get("type", "validation_error")),
                "message": str(err.get("msg", "")),
            }
        )
    return JSONResponse(
        status_code=422,
        headers={REQUEST_ID_HEADER: rid},
        content=_error_payload(
            code="422_VALIDATION_FAILED_001",
            message="入参校验失败",
            request_id=rid,
            details=details,
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """兜底：未捕获异常 → 500_INTERNAL_ERROR_001，不暴露内部细节。"""
    rid = _request_id(request)
    logger.exception(
        "unhandled_exception",
        extra={"request_id": rid, "error_type": type(exc).__name__},
    )
    return JSONResponse(
        status_code=500,
        headers={REQUEST_ID_HEADER: rid},
        content=_error_payload(
            code="500_INTERNAL_ERROR_001",
            message="服务器内部错误",
            request_id=rid,
        ),
    )


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router)


# === WebSocket（python-socketio + ASGI mount）===
# 注册 handlers 后，用 socketio.ASGIApp 把 sio 与 FastAPI app 组合为一个 ASGI app。
# 真实入口请用 `uvicorn app.main:asgi_app`，httpx ASGITransport 测试 REST 仍可直接用 `app`。
ws_handlers.register_handlers(sio)
asgi_app = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path=SOCKETIO_PATH)
