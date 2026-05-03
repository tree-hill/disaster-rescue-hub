"""human_interventions 数据访问层。

对照 DATA_CONTRACTS §1.12 + BUSINESS_RULES §4（HITL 写 intervention 同事务）。

事务边界：与 UserRepository / RobotRepository 同款 —— 只 add+flush，commit/rollback
由 service 控制，保证 INV-G「数据库写操作涉及多表时必须用同一事务」。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intervention import HumanIntervention


class InterventionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, intervention: HumanIntervention) -> HumanIntervention:
        """新增干预记录；不在此 commit。"""
        self.session.add(intervention)
        await self.session.flush()
        return intervention

    async def find_by_id(self, intervention_id: UUID) -> HumanIntervention | None:
        return await self.session.get(HumanIntervention, intervention_id)
