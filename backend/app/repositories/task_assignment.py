"""TaskAssignment 数据访问层。

对照 BUILD_ORDER §P4.4（GET /tasks/{id}/assignments + POST /tasks/{id}/cancel
释放 assignment）+ DATA_CONTRACTS §1.9。

事务边界：与其他 repo 一致 —— add+flush，commit / rollback 由调用方控制。
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import TaskAssignment


class TaskAssignmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, assignment: TaskAssignment) -> TaskAssignment:
        self.session.add(assignment)
        await self.session.flush()
        return assignment

    async def find_by_task(
        self, task_id: UUID, *, only_active: bool = False
    ) -> list[TaskAssignment]:
        """按任务查询全部 assignment，默认含历史；only_active=True 仅 is_active=TRUE。

        排序：assigned_at DESC（与 API_SPEC §3 GET /tasks/{id}/assignments
        「按时间倒序」一致）。
        """
        stmt = select(TaskAssignment).where(TaskAssignment.task_id == task_id)
        if only_active:
            stmt = stmt.where(TaskAssignment.is_active.is_(True))
        stmt = stmt.order_by(TaskAssignment.assigned_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_active_by_robot_bulk(
        self, robot_ids: Iterable[UUID]
    ) -> dict[UUID, int]:
        """批量统计每个机器人的当前 active 任务数（is_active=TRUE）。

        BUSINESS_RULES §3.2 R8（load_limit < 3）+ §1.2.4 L(r) 都需要此值。本方法
        一次性 GROUP BY 查询，避免 dispatch_service 在 N 个机器人上循环各 1 次
        SELECT。

        返回字典：robot_id → count；输入列表中没出现 active 行的 robot_id 显式
        填 0，调用方无需自行兜底 KeyError。
        """
        ids = list(robot_ids)
        if not ids:
            return {}
        stmt = (
            select(TaskAssignment.robot_id, func.count(TaskAssignment.id))
            .where(
                TaskAssignment.robot_id.in_(ids),
                TaskAssignment.is_active.is_(True),
            )
            .group_by(TaskAssignment.robot_id)
        )
        rows = (await self.session.execute(stmt)).all()
        result: dict[UUID, int] = {rid: 0 for rid in ids}
        for rid, cnt in rows:
            result[rid] = int(cnt)
        return result

    async def release_active_for_task(
        self, task_id: UUID, *, released_at: datetime
    ) -> int:
        """批量将该任务下 is_active=TRUE 的 assignment 标记为已释放。

        返回受影响行数；调用方常用于 cancel / 任务完成时统一释放，再写
        intervention（HITL 路径）。同事务，不在此 commit。
        """
        stmt = (
            update(TaskAssignment)
            .where(
                TaskAssignment.task_id == task_id,
                TaskAssignment.is_active.is_(True),
            )
            .values(is_active=False, released_at=released_at)
            .execution_options(synchronize_session=False)
        )
        res = await self.session.execute(stmt)
        return int(res.rowcount or 0)
