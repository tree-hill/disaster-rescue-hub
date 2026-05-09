"""Task 数据访问层（含 task_assignments 协助过滤的分页查询）。

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

from sqlalchemy import func, or_, select
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

    async def find_by_parent(self, parent_id: UUID) -> list[Task]:
        """按 parent_id 查询子任务（P4.3 网格分解后的 tile 任务）。

        排序：code ASC（T-YYYY-NNN-CC 后缀按字面顺序，便于稳定枚举）。
        P5.7 自动触发拍卖在父任务有子任务时不拍父，转拍子任务列表。
        """
        stmt = select(Task).where(Task.parent_id == parent_id).order_by(Task.code.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def find_pending_leaves(self) -> list[Task]:
        """返回所有「叶子级」PENDING 任务（即不是其他任务的父）。

        语义：跳过被网格分解的父任务（其 area_km2 通常 > 1 km²，单机器人航程 R7
        几乎必定 out_of_range）。这是 P5.7 PENDING 30s 扫描的主入口；与
        `find_pending` 不同点仅在 NOT IN 过滤掉 parent_id 不为空的任务的父集合。
        排序与 find_pending 一致：priority ASC + created_at ASC。
        """
        # 子任务父集合：所有 parent_id 不为空的 task 的 parent_id
        parents_subq = (
            select(Task.parent_id)
            .where(Task.parent_id.isnot(None))
            .distinct()
            .subquery()
        )
        stmt = (
            select(Task)
            .where(
                Task.status == "PENDING",
                Task.id.notin_(select(parents_subq.c.parent_id)),
            )
            .order_by(Task.priority.asc(), Task.created_at.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def find_active_near(
        self,
        center_lat: float,
        center_lng: float,
        *,
        radius_km: float,
        types: Sequence[str] | None = None,
    ) -> list[Task]:
        """查询「活跃」(status NOT IN 终态) 且 target_area.center_point 距 center
        ≤ radius_km 的任务。

        BUSINESS_RULES §5.3：高置信度幸存者自动派任务用 0.5 km 邻域去重判定。
        实现：先按 status / type 过滤拉出活跃集合（量级 ≤ 数百），再 Python
        haversine 过滤；target_area JSONB 没有几何索引，硬要 SQL 算地理距离需
        PostGIS，毕设规模不引入。
        """
        from app.dispatch.rule_engine import haversine_km

        stmt = select(Task).where(
            Task.status.in_(("PENDING", "ASSIGNED", "EXECUTING"))
        )
        if types is not None:
            stmt = stmt.where(Task.type.in_(list(types)))
        rows = list((await self.session.execute(stmt)).scalars().all())

        out: list[Task] = []
        for t in rows:
            ta = t.target_area or {}
            cp = ta.get("center_point") if isinstance(ta, dict) else None
            if not isinstance(cp, dict):
                continue
            try:
                dist_km = haversine_km(
                    center_lat, center_lng, float(cp["lat"]), float(cp["lng"])
                )
            except (KeyError, TypeError, ValueError):
                continue
            if dist_km <= radius_km:
                out.append(t)
        return out

    async def find_paginated(
        self,
        *,
        status_in: Sequence[str] | None = None,
        priority: int | None = None,
        type_: str | None = None,
        created_by: UUID | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Task], int]:
        """分页查询，支持多条件过滤。

        - status_in：可多选（API_SPEC §3 GET /tasks 写 `status (可多选)`）；空序列短路 → ([], 0)
        - priority：1/2/3 精确匹配
        - type_：search_rescue / recon / transport / patrol
        - created_by：按用户过滤
        - search：对 code / name 做 ILIKE '%search%'
        - 排序：created_at DESC（API_SPEC §0.6 默认；sort 自定义留 P4.4 后续按需扩展）
        """
        if status_in is not None and len(list(status_in)) == 0:
            return [], 0

        filters = []
        if status_in is not None:
            filters.append(Task.status.in_(list(status_in)))
        if priority is not None:
            filters.append(Task.priority == priority)
        if type_ is not None:
            filters.append(Task.type == type_)
        if created_by is not None:
            filters.append(Task.created_by == created_by)
        if search:
            pattern = f"%{search}%"
            filters.append(or_(Task.code.ilike(pattern), Task.name.ilike(pattern)))

        count_stmt = select(func.count()).select_from(Task)
        for f in filters:
            count_stmt = count_stmt.where(f)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = select(Task)
        for f in filters:
            stmt = stmt.where(f)
        stmt = (
            stmt.order_by(Task.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await self.session.execute(stmt)).scalars().all())
        return items, total
