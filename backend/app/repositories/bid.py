"""Bid 数据访问层。

对照 BUILD_ORDER §P5.4 / §P5.5 + DATA_CONTRACTS §1.11（bids 表）+ BUSINESS_RULES
§1.5（每次拍卖 N 条 bid，每个候选机器人 1 条）。

事务边界：add 不 commit，由 dispatch_service 在 start_auction 同事务中提交。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dispatch import Bid


class BidRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_many(self, bids: list[Bid]) -> list[Bid]:
        """批量写入 bid 行（同事务，不 commit）。

        SQLAlchemy add_all 注册到 unit-of-work 后，session.flush 一次写入所有；
        各自的 id / submitted_at server_default 会在 flush 后通过 RETURNING
        回填到 ORM 对象（INSERT ... RETURNING id, submitted_at）。
        """
        if not bids:
            return []
        self.session.add_all(bids)
        await self.session.flush()
        return bids

    async def find_by_auction(self, auction_id: UUID) -> list[Bid]:
        """GET /dispatch/auctions/{id} 含 bids 详情。

        排序：bid_value DESC（与 idx_bids_auction 索引同向，前端默认按出价高低
        渲染）。
        """
        stmt = (
            select(Bid)
            .where(Bid.auction_id == auction_id)
            .order_by(Bid.bid_value.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())
