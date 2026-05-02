"""机器人业务编排层。

对照：
- API_SPEC §2（/robots/* 路由契约）
- BUSINESS_RULES §6.2（机器人类错误码）
- DATA_CONTRACTS §1.4 / §1.6 / §1.9（robots / robot_states / task_assignments）

事务边界：
- 单写操作（create / update / soft_delete）在 service 内 commit；失败 rollback
- 读操作不 commit；FastAPI 依赖结束后 session 自动 close
- IntegrityError（如 code UNIQUE 冲突）翻译为 BusinessError，保证 API 层只处理业务码
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError
from app.models.robot import Robot, RobotState
from app.models.task import TaskAssignment
from app.repositories.robot import RobotRepository
from app.repositories.robot_state import RobotStateRepository
from app.schemas.robot import RobotCreate, RobotUpdate


def _not_found(robot_id: UUID) -> BusinessError:
    return BusinessError(
        code="404_ROBOT_NOT_FOUND_001",
        message="机器人不存在或已被删除",
        http_status=404,
        details=[{"field": "robot_id", "code": "not_found", "message": str(robot_id)}],
    )


def _code_duplicate(code: str) -> BusinessError:
    return BusinessError(
        code="409_ROBOT_CODE_DUPLICATE_001",
        message=f"机器人编码 '{code}' 已存在",
        http_status=409,
        details=[{"field": "code", "code": "duplicate", "message": code}],
    )


def _has_active_task(robot_id: UUID) -> BusinessError:
    return BusinessError(
        code="409_ROBOT_HAS_ACTIVE_TASK_001",
        message="机器人有进行中的任务，不能注销；请先完成或改派任务",
        http_status=409,
        details=[
            {"field": "robot_id", "code": "has_active_task", "message": str(robot_id)}
        ],
    )


class RobotService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.robots = RobotRepository(session)
        self.states = RobotStateRepository(session)

    # ---------- 读 ----------
    async def list_paginated(
        self,
        *,
        type_: str | None,
        group_id: UUID | None,
        search: str | None,
        page: int,
        page_size: int,
        only_active: bool = True,
    ) -> tuple[list[Robot], int]:
        return await self.robots.find_paginated(
            type_=type_,
            group_id=group_id,
            search=search,
            only_active=only_active,
            page=page,
            page_size=page_size,
        )

    async def get_with_latest_state(
        self, robot_id: UUID
    ) -> tuple[Robot, RobotState | None]:
        robot = await self.robots.find_by_id(robot_id)
        if robot is None:
            raise _not_found(robot_id)
        latest = await self.states.find_latest_by_robot(robot_id)
        return robot, latest

    async def list_states(
        self,
        robot_id: UUID,
        *,
        start_time: datetime | None,
        end_time: datetime | None,
        limit: int,
    ) -> list[RobotState]:
        # 404 守卫：先确认机器人存在
        if await self.robots.find_by_id(robot_id) is None:
            raise _not_found(robot_id)
        return await self.states.find_by_robot_in_window(
            robot_id, start_time=start_time, end_time=end_time, limit=limit
        )

    # ---------- 写 ----------
    async def create(self, payload: RobotCreate) -> Robot:
        robot = Robot(
            code=payload.code,
            name=payload.name,
            type=payload.type,
            model=payload.model,
            capability=payload.capability.model_dump(),
            group_id=payload.group_id,
            is_active=True,
        )
        self.session.add(robot)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            # 唯一冲突最常见于 code；FK 异常（如 group_id 不存在）也走这里
            # 这里以 code 为主要场景翻译，符合 BUSINESS_RULES §6.2 唯一列出的 409
            raise _code_duplicate(payload.code) from exc
        await self.session.refresh(robot)
        return robot

    async def update(self, robot_id: UUID, payload: RobotUpdate) -> Robot:
        robot = await self.robots.find_by_id(robot_id)
        if robot is None:
            raise _not_found(robot_id)

        # PATCH 语义：只更新用户显式传入的字段（model_dump exclude_unset）
        patch = payload.model_dump(exclude_unset=True)
        if "name" in patch:
            robot.name = patch["name"]
        if "capability" in patch:
            # capability 子模型 model_dump 已经递归 dict
            robot.capability = patch["capability"]
        if "group_id" in patch:
            robot.group_id = patch["group_id"]
        if "is_active" in patch:
            robot.is_active = patch["is_active"]

        await self.session.commit()
        await self.session.refresh(robot)
        return robot

    async def soft_delete(self, robot_id: UUID) -> None:
        robot = await self.robots.find_by_id(robot_id)
        if robot is None:
            raise _not_found(robot_id)

        # 409：是否存在进行中任务
        active_count = (
            await self.session.execute(
                select(func.count())
                .select_from(TaskAssignment)
                .where(
                    TaskAssignment.robot_id == robot_id,
                    TaskAssignment.is_active.is_(True),
                )
            )
        ).scalar_one()
        if active_count > 0:
            raise _has_active_task(robot_id)

        robot.is_active = False
        await self.session.commit()
