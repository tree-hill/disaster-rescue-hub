"""机器人相关 Pydantic v2 Schemas。

严格对照 DATA_CONTRACTS §5（Robot Schemas）和 API_SPEC §2（/robots/* 接口）。
字段、类型、约束与 DATA_CONTRACTS §1.4（robots 表）/ §1.6（robot_states 表）一一对应。
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Position, RobotCapability, SensorData


class RobotBase(BaseModel):
    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=100)
    type: Literal["uav", "ugv", "usv"]
    model: str | None = Field(None, max_length=100)
    capability: RobotCapability
    group_id: UUID | None = None


class RobotCreate(RobotBase):
    """注册新机器人。对照 API_SPEC §2 POST /robots。"""


class RobotUpdate(BaseModel):
    """更新机器人配置。对照 API_SPEC §2 PUT /robots/{id}。

    所有字段可选；is_active=False 等价于软删除（DELETE /robots/{id}）。
    code 与 type 不可变（数据库唯一键 + CHECK 约束）。
    """

    name: str | None = Field(None, max_length=100)
    capability: RobotCapability | None = None
    group_id: UUID | None = None
    is_active: bool | None = None


class RobotRead(RobotBase):
    """机器人详情。对照 API_SPEC §2 GET /robots/{id}。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RobotStateRead(BaseModel):
    """单条机器人状态记录。对照 API_SPEC §2 GET /robots/{id}/states。

    主键来自 BIGSERIAL，因此为 int；其他字段由 JSONB 反序列化为对应 Pydantic 模型。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    robot_id: UUID
    recorded_at: datetime
    fsm_state: Literal["IDLE", "BIDDING", "EXECUTING", "RETURNING", "FAULT"]
    position: Position
    battery: float = Field(..., ge=0, le=100)
    sensor_data: SensorData
    current_task_id: UUID | None = None


class RobotDetailRead(RobotRead):
    """GET /robots/{id} 的扩展响应：在 RobotRead 基础上嵌入最新状态。

    对照 API_SPEC §2：「200 响应：RobotRead + 嵌入最新 RobotStateRead」。
    若该机器人尚未上报过状态（robot_states 表无记录），latest_state 为 null。
    """

    latest_state: RobotStateRead | None = None
