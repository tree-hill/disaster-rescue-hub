"""告警相关 Pydantic v2 Schemas（P7.1）。

严格对照 DATA_CONTRACTS §5（Alert Schemas）+ §1.14（alerts 表）+ §4.11
（alerts.payload 载荷）；REST 形态对照 API_SPEC §6（/alerts /situation/kpi）。

注意：
- payload 是自由扩展 JSONB；Schema 用 dict 不锁字段，避免与 §4.11 的 yolo_detection /
  battery_alert / sla_alert 三类（任选一种）冲突。
- AlertAcknowledgeRequest 在 DATA_CONTRACTS §5 字面带 `alert_id`；POST
  /alerts/{id}/acknowledge 的请求体只需要 `note`，{id} 走 path param，本文件提供
  `AlertNoteRequest` 供 REST 层使用。
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


AlertSeverity = Literal["info", "warn", "critical"]


class AlertRead(BaseModel):
    """对照 DATA_CONTRACTS §5 AlertRead。"""

    id: UUID
    code: str
    type: str
    severity: AlertSeverity
    source: str
    message: str
    payload: dict
    related_task_id: UUID | None = None
    related_robot_id: UUID | None = None
    raised_at: datetime
    acknowledged_at: datetime | None = None
    acknowledged_by: UUID | None = None
    is_ignored: bool

    model_config = ConfigDict(from_attributes=True)


class AlertNoteRequest(BaseModel):
    """POST /alerts/{id}/acknowledge 请求体（API_SPEC §6）。"""

    note: str | None = Field(None, max_length=500)


class AlertIgnoreRequest(BaseModel):
    """POST /alerts/{id}/ignore 请求体（API_SPEC §6）。"""

    reason: str = Field(..., min_length=1, max_length=500)


class AlertBatchAcknowledgeRequest(BaseModel):
    """POST /alerts/batch-acknowledge 请求体（API_SPEC §6）。"""

    alert_ids: list[UUID] = Field(..., min_length=1, max_length=100)


class AlertBatchAcknowledgeResponse(BaseModel):
    acknowledged: int
    failed: int
