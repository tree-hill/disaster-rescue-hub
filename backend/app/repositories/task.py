"""Task 数据访问层。

对照 BUILD_ORDER P4.1（save / find_by_id / find_by_status / find_pending）
+ DATA_CONTRACTS §1.8（tasks 表）。

事务边界：本仓库只 add + flush，不 commit / rollback；事务由调用方
（service / 测试 / 拍卖触发器）控制，与 RobotRepository 一致。

排序约定：
- find_by_status：created_at DESC，配合 idx_tasks_status(status, created_at DESC)。
- find_pending：priority ASC，created_at ASC，配合 idx_tasks_priority(priority,
  created_at) WHERE status='PENDING'，使老的高优任务先被拍卖（FIFO within
  priority）。
"""
from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, task: Task) -> Task:
        """新增或附加已存在的对象（不在此 commit，由调用方控制事务边界）。

        flush 后服务端默认值（id / created_at / updated_at / status / progress）
        会被回填到 ORM 对象上，便于 service 层立即返回 TaskRead。
        """
        self.session.add(task)
        await self.session.flush()
        return task

    async def find_by_id(self, task_id: UUID) -> Task | None:
        return await self.session.get(Task, task_id)

    async def find_by_status(self, status: str | Sequence[str]) -> list[Task]:
        """按状态查询任务。status 可以是单个字符串或字符串序列（IN 查询）。

        排序：created_at DESC（与 idx_tasks_status 一致，最近的任务靠前）。
        """
        stmt = select(Task)
        if isinstance(status, str):
            stmt = stmt.where(Task.status == status)
        else:
            statuses = list(status)
            if not statuses:
                return []
            stmt = stmt.where(Task.status.in_(statuses))
        stmt = stmt.order_by(Task.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def find_pending(self) -> list[Task]:
        """返回所有 PENDING 任务，priority ASC + created_at ASC。

        语义：高优先级（priority=1）排在前面；同优先级 FIFO，老任务先被拍卖。
        匹配 idx_tasks_priority 部分索引（status='PENDING'），是 P5 拍卖触发器
        的主入口。
        """
        stmt = (
            select(Task)
            .where(Task.status == "PENDING")
            .order_by(Task.priority.asc(), Task.created_at.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())
