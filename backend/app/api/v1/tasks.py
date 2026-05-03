"""任务 REST 路由（P4.3 + P4.4）。

对照：
- API_SPEC §3（/tasks 完整 6 个接口；本任务实现 5 个，auctions 摘要按字面跳过 → P5）
- BUSINESS_RULES §6.3 / §6.5（错误码）+ §2.1（状态机）+ §4（HITL cancel_task 流程）
- WS_EVENTS §4 task.created / task.cancelled

权限模型：
- 读类（GET）：task:read
- 创建：task:create
- 更新：task:update
- 取消：task:cancel
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.pagination import Page
from app.schemas.task import (
    TaskAssignmentRead,
    TaskCancelRequest,
    TaskCreate,
    TaskDetailRead,
    TaskRead,
    TaskUpdate,
)
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=Page[TaskRead])
async def list_tasks(
    status_: list[str] | None = Query(
        None, alias="status", description="可多选；不传则不限定状态"
    ),
    priority: int | None = Query(None, ge=1, le=3),
    type: str | None = Query(None, description="search_rescue / recon / transport / patrol"),
    created_by: UUID | None = Query(None),
    search: str | None = Query(None, description="对 code / name 模糊匹配"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _current: CurrentUser = Depends(require_permission("task:read")),
    db: AsyncSession = Depends(get_db),
) -> Page[TaskRead]:
    items, total = await TaskService(db).list_paginated(
        status_in=status_,
        priority=priority,
        type_=type,
        created_by=created_by,
        search=search,
        page=page,
        page_size=page_size,
    )
    return Page[TaskRead](
        items=[TaskRead.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{task_id}", response_model=TaskDetailRead)
async def get_task(
    task_id: UUID,
    _current: CurrentUser = Depends(require_permission("task:read")),
    db: AsyncSession = Depends(get_db),
) -> TaskDetailRead:
    """GET /tasks/{id}：含 assignments；auctions 摘要留 P5。"""
    task, assignments = await TaskService(db).get_with_assignments(task_id)
    detail = TaskDetailRead.model_validate(task)
    detail.assignments = [TaskAssignmentRead.model_validate(a) for a in assignments]
    detail.auctions = []  # P5 dispatch 模块接入
    return detail


@router.get("/{task_id}/assignments", response_model=list[TaskAssignmentRead])
async def list_task_assignments(
    task_id: UUID,
    _current: CurrentUser = Depends(require_permission("task:read")),
    db: AsyncSession = Depends(get_db),
) -> list[TaskAssignmentRead]:
    rows = await TaskService(db).list_assignments(task_id)
    return [TaskAssignmentRead.model_validate(r) for r in rows]


@router.post(
    "",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    payload: TaskCreate,
    current: CurrentUser = Depends(require_permission("task:create")),
    db: AsyncSession = Depends(get_db),
) -> TaskRead:
    """创建任务，自动分配 code（T-YYYY-NNN）；area_km2 > 1 时同事务写子任务。

    成功后向 commander 房间广播 `task.created`。
    错误码：
    - 422_TASK_INVALID_AREA_001：area_km2 ≤ 0 / 几何字段不一致
    - 403_AUTH_PERMISSION_DENIED_001：缺 task:create
    """
    parent = await TaskService(db).create(payload, created_by=current.id)
    return TaskRead.model_validate(parent)


@router.put("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    _current: CurrentUser = Depends(require_permission("task:update")),
    db: AsyncSession = Depends(get_db),
) -> TaskRead:
    """PUT /tasks/{id}：仅 name/priority/sla_deadline，且非终态。

    错误码：
    - 404_TASK_NOT_FOUND_001
    - 409_TASK_STATUS_CONFLICT_001（任务为 COMPLETED / FAILED / CANCELLED）
    """
    task = await TaskService(db).update(task_id, payload)
    return TaskRead.model_validate(task)


@router.post("/{task_id}/cancel", response_model=TaskRead)
async def cancel_task(
    task_id: UUID,
    payload: TaskCancelRequest,
    current: CurrentUser = Depends(require_permission("task:cancel")),
    db: AsyncSession = Depends(get_db),
) -> TaskRead:
    """POST /tasks/{id}/cancel：HITL 取消任务（BUSINESS_RULES §4.1 cancel_task）。

    错误码：
    - 422_INTERVENTION_REASON_INVALID_001
    - 404_TASK_NOT_FOUND_001
    - 409_TASK_ALREADY_CANCELLED_001
    - 409_TASK_STATUS_CONFLICT_001（COMPLETED / FAILED）

    成功副作用：状态 → CANCELLED；释放所有 active assignment；写 intervention；
    commander 房间广播 `task.cancelled`。
    """
    task = await TaskService(db).cancel(
        task_id, user_id=current.id, reason=payload.reason
    )
    return TaskRead.model_validate(task)
