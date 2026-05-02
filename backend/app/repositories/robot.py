"""Robot 数据访问层。

对照 BUILD_ORDER P3.1（save / find_by_id / find_all / find_by_group）+ 补充
find_by_code（seed 数据使用 UAV-001 / UGV-001 这类业务 code，后续 P3.2 接口
查询、调试与测试都会用到）。

事务边界：本仓库只 add + flush，不 commit / rollback；事务由调用方（service / 测试）控制。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.robot import Robot


class RobotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, robot: Robot) -> Robot:
        """新增或附加已存在的对象（不在此 commit，由调用方控制事务边界）。"""
        self.session.add(robot)
        await self.session.flush()
        return robot

    async def find_by_id(self, robot_id: UUID) -> Robot | None:
        return await self.session.get(Robot, robot_id)

    async def find_by_code(self, code: str) -> Robot | None:
        """按业务 code（如 'UAV-001'）查询。code 是 robots 表的 UNIQUE 列。"""
        stmt = select(Robot).where(Robot.code == code)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def find_all(self, *, only_active: bool = True) -> list[Robot]:
        """返回机器人列表。only_active=True 时仅返回 is_active=TRUE 的（默认）。

        排序按 code 升序，便于稳定调试 / 测试断言。
        """
        stmt = select(Robot)
        if only_active:
            stmt = stmt.where(Robot.is_active.is_(True))
        stmt = stmt.order_by(Robot.code.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def find_by_group(self, group_id: UUID) -> list[Robot]:
        """按编队 group_id 查询，返回该编队下的全部机器人（含 inactive）。

        is_active 过滤逻辑由 service / API 层视场景决定，不在 repo 内部硬编码。
        """
        stmt = select(Robot).where(Robot.group_id == group_id).order_by(Robot.code.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def find_paginated(
        self,
        *,
        type_: str | None = None,
        group_id: UUID | None = None,
        search: str | None = None,
        only_active: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Robot], int]:
        """分页查询，支持 type / group_id / search 过滤。

        - search:对 code 与 name 做 ILIKE '%search%' 模糊匹配
        - only_active=True 仅返回 is_active=TRUE
        - 返回 (items, total)；total 是过滤条件下的总数（用于前端分页器）
        - 排序：created_at DESC（与 API_SPEC §0.6 默认一致）
        """
        filters = []
        if only_active:
            filters.append(Robot.is_active.is_(True))
        if type_ is not None:
            filters.append(Robot.type == type_)
        if group_id is not None:
            filters.append(Robot.group_id == group_id)
        if search:
            pattern = f"%{search}%"
            filters.append(or_(Robot.code.ilike(pattern), Robot.name.ilike(pattern)))

        # total
        count_stmt = select(func.count()).select_from(Robot)
        for f in filters:
            count_stmt = count_stmt.where(f)
        total = (await self.session.execute(count_stmt)).scalar_one()

        # items
        stmt = select(Robot)
        for f in filters:
            stmt = stmt.where(f)
        stmt = (
            stmt.order_by(Robot.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await self.session.execute(stmt)).scalars().all())
        return items, total
