"""调度（拍卖 / 出价 / HITL）相关 Pydantic v2 Schemas。

严格对照 DATA_CONTRACTS §4.7（BidBreakdown）+ §5（Auction / Bid Schemas）+
API_SPEC §4（POST /dispatch/auction、GET/POST /dispatch/algorithm、GET
/dispatch/auctions[/{id}]、POST /dispatch/reassign）。

按 BUILD_ORDER 增量补充原则：
- P5.2 出价计算落地了 BidBreakdownComponent / BidBreakdown
- P5.5 REST 接口在此追加 BidRead / AuctionRead / AuctionTriggerRequest /
  AlgorithmSwitchRequest / AlgorithmSwitchResponse / AlgorithmInfoResponse
- P5.6 HITL 改派将追加 ReassignRequest 等
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# === BidBreakdown（P5.2 已落地，P5.5 不动） =================================

class BidBreakdownComponent(BaseModel):
    """出价单个分量的审计条目。

    对照 DATA_CONTRACTS §4.7 / §5：每个 base_score 加权分量必须可追溯，因此同时
    存原始 value（[0,1] 归一化得分，可能是负权惩罚分量的正值）与 weighted（权重相
    乘后实际进入 base_score 的有符号值，正负权由调用方决定）。
    """

    value: float
    weighted: float


class BidBreakdown(BaseModel):
    """出价分解。对照 DATA_CONTRACTS §4.7 + BUSINESS_RULES §1.1 / §1.5。

    components 的键固定为 `distance / battery / capability / load` 四个；vision_boost
    不进 components（它是 base_score 之外的乘法加成）。`vision_boosted` 反映的是本
    次出价是否实际享受了 1.5 倍加成；`final_bid = base_score × (1.5 if vision_boosted
    else 1.0)`。
    """

    base_score: float
    components: dict[str, BidBreakdownComponent]
    vision_boosted: bool
    final_bid: float


# === REST 请求 / 响应（P5.5） ==============================================

# 算法名 Literal — 与 DATA_CONTRACTS §5 auctions.algorithm + dispatch.algorithms
# 模块的 KNOWN_ALGORITHMS 一一对应。
AlgorithmName = Literal["AUCTION_HUNGARIAN", "GREEDY", "RANDOM"]


class AuctionTriggerRequest(BaseModel):
    """POST /dispatch/auction 请求体。对照 API_SPEC §4。"""

    task_id: UUID


class AlgorithmInfoResponse(BaseModel):
    """GET /dispatch/algorithm 响应。"""

    current: AlgorithmName
    available: list[AlgorithmName]


class AlgorithmSwitchRequest(BaseModel):
    """POST /dispatch/algorithm 请求体。对照 BUSINESS_RULES §4.1 algorithm_switch。

    reason 长度 5–500 字符（max 由 schema 拦截，min 在 service 层抛特化错误码
    422_INTERVENTION_REASON_INVALID_001，与 cancel_task / recall 同款模式）。
    algorithm 用 Literal，schema 层即可挡住未知名（→ 422_VALIDATION_FAILED_001）。
    """

    algorithm: AlgorithmName
    reason: str = Field(..., max_length=500)


class AlgorithmSwitchResponse(BaseModel):
    """POST /dispatch/algorithm 响应。对照 API_SPEC §4。"""

    previous: AlgorithmName
    current: AlgorithmName
    intervention_id: UUID


class BidRead(BaseModel):
    """单条出价审计。对照 DATA_CONTRACTS §5 BidRead。

    `vision_boost` 字段为出价时实际生效的乘数（1.0 / 1.5），与 breakdown.
    vision_boosted 一致；这里冗余存值便于前端展示而无需解 breakdown。
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    auction_id: UUID
    robot_id: UUID
    bid_value: float
    breakdown: BidBreakdown
    vision_boost: float
    submitted_at: datetime

    @field_validator("bid_value", "vision_boost", mode="before")
    @classmethod
    def _decimal_to_float(cls, v: object) -> object:
        """Bid.bid_value / vision_boost 数据库为 Numeric → Pydantic 接收 Decimal。"""
        # asyncpg 返回 Decimal；Pydantic v2 不会自动转 float，在此显式转。
        if v is None:
            return v
        try:
            return float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return v


class AuctionRead(BaseModel):
    """拍卖会话。对照 DATA_CONTRACTS §5 AuctionRead + API_SPEC §4。

    `bids` 字段：列表接口（GET /dispatch/auctions）返回 []，详情接口（GET
    /dispatch/auctions/{id}）返回完整列表。这与 DATA_CONTRACTS 字面一致。
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    algorithm: AlgorithmName
    status: Literal["OPEN", "CLOSED", "FAILED"]
    started_at: datetime
    closed_at: datetime | None = None
    winner_robot_id: UUID | None = None
    decision_latency_ms: int | None = None
    bids: list[BidRead] = []


# === HITL 改派（P5.6） ====================================================


class ReassignRequest(BaseModel):
    """POST /dispatch/reassign 请求体。对照 DATA_CONTRACTS §5 ReassignRequest +
    API_SPEC §4 + BUSINESS_RULES §4.3.3。

    reason min_length 业务校验由 service 层统一抛 422_INTERVENTION_REASON_INVALID_001
    （与 cancel_task / recall / algorithm_switch 同款），此处仅 max_length 拦截。
    """

    task_id: UUID
    new_robot_id: UUID
    reason: str = Field(..., max_length=500)


class ReassignResponse(BaseModel):
    """POST /dispatch/reassign 响应。

    API_SPEC §4 写「`{task: TaskRead, intervention_id: UUID}`」。这里直接引用
    TaskRead；为避免循环 import，用 lazy 字符串注解 + model_rebuild 在模块底部装配。
    """

    model_config = ConfigDict(from_attributes=True)

    task: "TaskRead"
    intervention_id: UUID


from app.schemas.task import TaskRead  # noqa: E402  解决 ReassignResponse 前向引用

ReassignResponse.model_rebuild()
