"""机器人 REST 路由。

对照：
- API_SPEC §2（/robots/* 7 个核心路由）
- BUSINESS_RULES §6.2 / §6.5（错误码）+ §4（HITL 召回）
- DATA_CONTRACTS §5（RobotRead / RobotStateRead / RobotDetailRead）+ §1.12 + §4.8（intervention）

权限模型：
- 读类（GET）：robot:read
- 写类（POST / PUT / DELETE）：robot:manage
- HITL 召回（POST /{id}/recall）：robot:recall

显式不在本文件实现（按 BUILD_ORDER 字面）：
- GET /robots/{id}/faults —— BUILD_ORDER P3 全程未列，按字面跳过

显式不实现的 query 参数：
- status（=fsm_state）—— 来自 robot_states 时序表的最新一行；P3.5 WS 上线后
  用 service 内存缓存做更顺手，本任务先支持 type / group_id / search
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.db.session import get_db
from app.schemas.intervention import RecallRequest, RecallResponse
from app.schemas.pagination import Page
from app.schemas.robot import (
    RobotCreate,
    RobotDetailRead,
    RobotRead,
    RobotStateRead,
    RobotUpdate,
)
from app.services.recall_service import RecallService
from app.services.robot_service import RobotService

router = APIRouter(prefix="/robots", tags=["robots"])


@router.get("", response_model=Page[RobotRead])
async def list_robots(
    type: str | None = Query(None, description="机器人类型: uav | ugv | usv"),
    group_id: UUID | None = Query(None, description="编队 ID"),
    search: str | None = Query(None, description="对 code / name 模糊匹配"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_inactive: bool = Query(
        False, description="是否包含已注销（is_active=FALSE）的机器人"
    ),
    _current=Depends(require_permission("robot:read")),
    db: AsyncSession = Depends(get_db),
) -> Page[RobotRead]:
    items, total = await RobotService(db).list_paginated(
        type_=type,
        group_id=group_id,
        search=search,
        page=page,
        page_size=page_size,
        only_active=not include_inactive,
    )
    return Page[RobotRead](
        items=[RobotRead.model_validate(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{robot_id}", response_model=RobotDetailRead)
async def get_robot(
    robot_id: UUID,
    _current=Depends(require_permission("robot:read")),
    db: AsyncSession = Depends(get_db),
) -> RobotDetailRead:
    robot, latest = await RobotService(db).get_with_latest_state(robot_id)
    return RobotDetailRead(
        **RobotRead.model_validate(robot).model_dump(),
        latest_state=(RobotStateRead.model_validate(latest) if latest else None),
    )


@router.post(
    "",
    response_model=RobotRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_robot(
    payload: RobotCreate,
    _current=Depends(require_permission("robot:manage")),
    db: AsyncSession = Depends(get_db),
) -> RobotRead:
    robot = await RobotService(db).create(payload)
    return RobotRead.model_validate(robot)


@router.put("/{robot_id}", response_model=RobotRead)
async def update_robot(
    robot_id: UUID,
    payload: RobotUpdate,
    _current=Depends(require_permission("robot:manage")),
    db: AsyncSession = Depends(get_db),
) -> RobotRead:
    robot = await RobotService(db).update(robot_id, payload)
    return RobotRead.model_validate(robot)


@router.delete(
    "/{robot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_robot(
    robot_id: UUID,
    _current=Depends(require_permission("robot:manage")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """软删除：设置 is_active=FALSE，不真正删数据库行。

    409 触发条件：该机器人在 task_assignments 中存在 is_active=TRUE 的记录。
    """
    await RobotService(db).soft_delete(robot_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{robot_id}/states", response_model=list[RobotStateRead])
async def list_robot_states(
    robot_id: UUID,
    start_time: datetime | None = Query(None, description="ISO 8601，含时区"),
    end_time: datetime | None = Query(None, description="ISO 8601，含时区"),
    limit: int = Query(100, ge=1, le=1000, description="单次返回条数上限 1000"),
    _current=Depends(require_permission("robot:read")),
    db: AsyncSession = Depends(get_db),
) -> list[RobotStateRead]:
    states = await RobotService(db).list_states(
        robot_id, start_time=start_time, end_time=end_time, limit=limit
    )
    return [RobotStateRead.model_validate(s) for s in states]


@router.post(
    "/{robot_id}/recall",
    response_model=RecallResponse,
    status_code=status.HTTP_200_OK,
)
async def recall_robot(
    robot_id: UUID,
    payload: RecallRequest,
    current=Depends(require_permission("robot:recall")),
    db: AsyncSession = Depends(get_db),
) -> RecallResponse:
    """HITL 紧急召回（API_SPEC §2 + BUSINESS_RULES §4）。

    错误码：
    - 422_INTERVENTION_REASON_INVALID_001：reason < 5 个非空白字符
    - 404_ROBOT_NOT_FOUND_001
    - 503_AGENT_NOT_RUNNING_001：AgentManager 未启动或该 robot 无 Agent
    - 409_ROBOT_ALREADY_FAULT_001
    - 409_ROBOT_NOT_RECALLABLE_001：当前 FSM 不可召回（IDLE 等）
    """
    return await RecallService(db).execute_recall(
        robot_id=robot_id,
        user_id=current.id,
        reason=payload.reason,
    )
