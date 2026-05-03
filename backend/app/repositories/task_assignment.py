"""TaskAssignment 数据访问层。

对照 BUILD_ORDER §P4.4（GET /tasks/{id}/assignments + POST /tasks/{id}/cancel
释放 assignment）+ DATA_CONTRACTS §1.9。

事务边界：与其他 repo 一致 —— add+flush，commit / rollback 由调用方控制。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
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
