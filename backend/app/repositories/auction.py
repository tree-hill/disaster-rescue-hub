"""Auction 数据访问层。

对照 BUILD_ORDER §P5.4 + DATA_CONTRACTS §1.10（auctions 表）+ API_SPEC §4
（GET /dispatch/auctions[/{id}]）。

事务边界：与本项目其他 repo 一致 — add+flush，commit / rollback 由调用方控制；
本任务（P5.4）的调用方是 dispatch_service.start_auction，单事务串起 auction +
bids + assignments 原子写入。

P5.4 仅实现 save / find_by_id（dispatch_service 闭环够用）；P5.5 GET 列表 / 详
情接口落地时再追加 find_paginated 与 find_by_id_with_bids。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dispatch import Auction


class AuctionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, auction: Auction) -> Auction:
        """新增或附加已存在的 Auction 对象（不在此 commit）。"""
        self.session.add(auction)
        await self.session.flush()
        return auction

    async def find_by_id(self, auction_id: UUID) -> Auction | None:
        return await self.session.get(Auction, auction_id)
