"""Auction 数据访问层。

对照 BUILD_ORDER §P5.4 / §P5.5 + DATA_CONTRACTS §1.10（auctions 表）+ API_SPEC
§4（GET /dispatch/auctions[/{id}]）。

事务边界：与本项目其他 repo 一致 — add+flush，commit / rollback 由调用方控制。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
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

    async def find_paginated(
        self,
        *,
        task_id: UUID | None = None,
        algorithm: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Auction], int]:
        """GET /dispatch/auctions（API_SPEC §4）。

        按 started_at DESC 排序（与 idx_auctions_task 索引同向）。返回 (items, total)，
        total 为过滤后总数（前端分页器使用）。
        """
        filters = []
        if task_id is not None:
            filters.append(Auction.task_id == task_id)
        if algorithm is not None:
            filters.append(Auction.algorithm == algorithm)
        if start_time is not None:
            filters.append(Auction.started_at >= start_time)
        if end_time is not None:
            filters.append(Auction.started_at <= end_time)

        count_stmt = select(func.count()).select_from(Auction)
        for f in filters:
            count_stmt = count_stmt.where(f)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = select(Auction)
        for f in filters:
            stmt = stmt.where(f)
        stmt = (
            stmt.order_by(Auction.started_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await self.session.execute(stmt)).scalars().all())
        return items, int(total)
