"""Bid 数据访问层。

对照 BUILD_ORDER §P5.4 + DATA_CONTRACTS §1.11（bids 表）+ BUSINESS_RULES §1.5
（每次拍卖 N 条 bid，每个候选机器人 1 条）。

事务边界：add 不 commit，由 dispatch_service 在 start_auction 同事务中提交。

P5.4 仅实现 save_many（拍卖一次性写入所有候选 bid，避免循环 add+flush 的额
外往返）；P5.5 GET /dispatch/auctions/{id} 含 bids 详情时再追加 find_by_auction。
"""
from __future__ import annotations

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
