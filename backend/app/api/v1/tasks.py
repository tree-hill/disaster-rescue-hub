"""任务 REST 路由（P4.3：仅 POST /tasks）。

对照：
- API_SPEC §3 POST /tasks
- BUSINESS_RULES §6.3（任务类错误码）
- WS_EVENTS §4 task.created

权限模型：
- 创建：task:create

后续 P4.4 会在本 router 追加 GET / PUT / cancel / assignments 等。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.task import TaskCreate, TaskRead
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


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
