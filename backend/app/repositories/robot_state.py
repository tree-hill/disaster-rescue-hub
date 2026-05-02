"""RobotState 时序数据访问层（高频写入表 robot_states，BIGSERIAL 主键）。

对照 BUILD_ORDER P3.1 + DATA_CONTRACTS §1.6 / §4.3 / §4.4。

事务边界：append 只 add + flush，不 commit / rollback；由 RobotAgent / service 在
1Hz 上报循环里按批控制提交。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.robot import RobotState


class RobotStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(self, state: RobotState) -> RobotState:
        """追加一条状态记录（不在此 commit，由调用方控制事务边界）。

        BIGSERIAL 主键由数据库分配，flush 后 state.id / recorded_at 可被读取。
        """
        self.session.add(state)
        await self.session.flush()
        return state

    async def find_latest_by_robot(self, robot_id: UUID) -> RobotState | None:
        """取该机器人最新的一条状态。配合索引 idx_robot_states_robot_time DESC。"""
        stmt = (
            select(RobotState)
            .where(RobotState.robot_id == robot_id)
            .order_by(RobotState.recorded_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def find_by_robot_in_window(
        self,
        robot_id: UUID,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[RobotState]:
        """时间窗内查询某机器人的状态序列，按时间倒序，最多返回 limit 条。

        limit 上限的业务校验（API_SPEC §2 GET /robots/{id}/states 规定 ≤ 1000）
        留给 service / API 层；本层只忠实地把参数传给 SQL。
        """
        stmt = select(RobotState).where(RobotState.robot_id == robot_id)
        if start_time is not None:
            stmt = stmt.where(RobotState.recorded_at >= start_time)
        if end_time is not None:
            stmt = stmt.where(RobotState.recorded_at <= end_time)
        stmt = stmt.order_by(RobotState.recorded_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())
