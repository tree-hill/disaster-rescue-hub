from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.exceptions import BusinessError
from app.core.middleware import REQUEST_ID_HEADER, RequestIdMiddleware

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Disaster Rescue Hub API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
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
