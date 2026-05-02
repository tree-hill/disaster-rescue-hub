"""错误响应 Pydantic Schemas。

严格对照 DATA_CONTRACTS §5 / API_SPEC §0.3 错误响应格式。
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    field: str | None = None
    code: str
    message: str


class ErrorResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "code": "404_TASK_NOT_FOUND_001",
            "message": "任务不存在或已被删除",
            "details": [],
            "request_id": "req-20260425-143218-abc123",
            "timestamp": "2026-04-25T14:32:18Z",
        }
    })

    code: str
    message: str
    details: list[ErrorDetail] = []
    request_id: str
    timestamp: datetime
