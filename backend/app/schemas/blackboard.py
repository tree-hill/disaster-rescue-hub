"""黑板协同通信 Schemas（P6.1）。

严格对照 DATA_CONTRACTS §4.9 / §4.10 / §5（Blackboard Schemas）。

设计边界：
- BlackboardValue 用 Pydantic v2 model_config(extra="allow")，允许 §4.9 末尾的「自由扩展」字段
- FusionSource 是 fused_from JSONB 数组的单元；P6.2 信息融合会用到，P6.1 仅落基础结构
- BlackboardEntryRead 即 DATA_CONTRACTS §5 字面定义的 GET /blackboard/entries 响应单元；P6.3
  落 REST 时直接复用，P6.1 仅声明
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Position


class BlackboardValue(BaseModel):
    """黑板条目值（写入 blackboard_entries.value JSONB）。对照 DATA_CONTRACTS §4.9。"""

    model_config = ConfigDict(extra="allow")

    type: Literal["survivor", "fire", "smoke", "collapsed_building", "weather", "custom"]
    position: Optional[Position] = None
    area_m2: Optional[float] = None
    intensity: Optional[Literal["low", "medium", "high"]] = None
    detected_count: Optional[int] = None


class FusionSource(BaseModel):
    """融合来源审计单元（写入 blackboard_entries.fused_from JSONB[]）。

    对照 DATA_CONTRACTS §4.10。所有 weight 之和应为 1（P6.2 信息融合校验）。
    """

    robot_id: UUID
    confidence: float = Field(..., ge=0.0, le=1.0)
    timestamp: datetime
    weight: float = Field(..., ge=0.0, le=1.0)


class BlackboardEntryRead(BaseModel):
    """黑板条目响应（GET /blackboard/entries 列表项）。对照 DATA_CONTRACTS §5。"""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = None  # 内存主路径下，DB 落库回填前可能为 None
    key: str
    value: BlackboardValue
    confidence: float
    source_robot_id: Optional[UUID] = None
    fused_from: list[FusionSource] = Field(default_factory=list)
    expires_at: Optional[datetime] = None
    updated_at: datetime


class BlackboardStats(BaseModel):
    """GET /blackboard/stats 响应。对照 API_SPEC §5。"""

    total_entries: int
    by_type: dict[str, int]
    active_subscribers: int
    avg_fusion_latency_ms: float
    throughput_per_min: float
