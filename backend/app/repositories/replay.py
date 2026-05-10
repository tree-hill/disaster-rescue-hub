"""ReplaySession 数据访问层（P8.1）。

事务边界：本仓库只 add + flush，不 commit / rollback；调用方控制（与
AlertRepository / TaskRepository 一致）。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.replay import ReplaySession


class ReplaySessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, obj: ReplaySession) -> ReplaySession:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def find_by_id(self, session_id: UUID) -> ReplaySession | None:
        return await self.session.get(ReplaySession, session_id)

    async def find_paginated(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        algorithm: str | None = None,
        scenario_id: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ReplaySession], int]:
        filters = []
        if start_time is not None:
            filters.append(ReplaySession.started_at >= start_time)
        if end_time is not None:
            filters.append(ReplaySession.started_at <= end_time)
        if algorithm is not None:
            filters.append(ReplaySession.algorithm == algorithm)
        if scenario_id is not None:
            filters.append(ReplaySession.scenario_id == scenario_id)

        count_stmt = select(func.count()).select_from(ReplaySession)
        for f in filters:
            count_stmt = count_stmt.where(f)
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = select(ReplaySession)
        for f in filters:
            stmt = stmt.where(f)
        stmt = (
            stmt.order_by(ReplaySession.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await self.session.execute(stmt)).scalars().all())
        return items, total
