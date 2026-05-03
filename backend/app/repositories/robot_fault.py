"""robot_faults 数据访问层。

对照 DATA_CONTRACTS §1.7。

P3.6 范围：append 一条故障记录（low_battery / sensor_error / comm_lost / unknown）。
resolved_at / resolved_by 由后续故障管理模块写入（P3 不做）。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.robot import RobotFault


class RobotFaultRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, fault: RobotFault) -> RobotFault:
        """新增故障记录；不在此 commit。"""
        self.session.add(fault)
        await self.session.flush()
        return fault

    async def find_latest_by_robot(
        self, robot_id: UUID, *, limit: int = 50
    ) -> list[RobotFault]:
        stmt = (
            select(RobotFault)
            .where(RobotFault.robot_id == robot_id)
            .order_by(desc(RobotFault.occurred_at))
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())
