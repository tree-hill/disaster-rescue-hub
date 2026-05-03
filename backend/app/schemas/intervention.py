"""HITL 干预相关 Pydantic v2 Schemas。

对照：
- DATA_CONTRACTS §1（human_interventions 表）+ §4.8（before/after_state 格式）
- API_SPEC §2 POST /robots/{id}/recall（请求体 / 响应体）
- BUSINESS_RULES §4（HITL 通用规则）+ §6.5（错误码）

注：
- `RecallRequest.reason` Pydantic 层只校验 max_length（防 DoS）；min_length 业务校验
  由 service 层抛 `422_INTERVENTION_REASON_INVALID_001`，避免被 Pydantic 422_VALIDATION_FAILED_001
  覆盖（特化错误码优先于通用校验错误码）
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import RECALL_REASON_MAX_LEN


class RecallRequest(BaseModel):
    """POST /robots/{id}/recall 请求体。"""

    model_config = ConfigDict(str_strip_whitespace=False)  # 保留原始空白，便于 service 准确判定纯空白

    reason: str = Field(..., max_length=RECALL_REASON_MAX_LEN)


class RecallResponse(BaseModel):
    """POST /robots/{id}/recall 响应体（API_SPEC §2）。"""

    intervention_id: UUID
    recall_eta_sec: int
