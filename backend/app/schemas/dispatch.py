"""调度（拍卖 / 出价 / HITL 改派）相关 Pydantic v2 Schemas。

严格对照 DATA_CONTRACTS §4.7（BidBreakdown）+ §5（Auction / Bid Schemas）。

按 BUILD_ORDER 增量补充原则，本任务（P5.2 出价计算）只放 `BidBreakdownComponent`
与 `BidBreakdown` 两个出价审计结构；`AuctionRead / BidRead / ReassignRequest` 等
等到 P5.4 / P5.5 / P5.6 拍卖编排与 REST 接口落地时再追加，避免空 schema 过早入库。
"""
from __future__ import annotations

from pydantic import BaseModel


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
