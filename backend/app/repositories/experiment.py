"""ExperimentRun 数据库仓库（P8.2）。"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.replay import ExperimentRun


class ExperimentRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, run: ExperimentRun) -> ExperimentRun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def find_by_batch(self, batch_id: UUID) -> list[ExperimentRun]:
        stmt = (
            select(ExperimentRun)
            .where(ExperimentRun.batch_id == batch_id)
            .order_by(ExperimentRun.algorithm, ExperimentRun.run_index)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_batch(self, batch_id: UUID) -> int:
        stmt = select(func.count()).where(ExperimentRun.batch_id == batch_id)
        return (await self.session.execute(stmt)).scalar_one()
