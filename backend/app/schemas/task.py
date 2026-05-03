"""任务相关 Pydantic v2 Schemas。

严格对照 DATA_CONTRACTS §1.8（tasks 表）+ §4.5（target_area）+ §4.6
（required_capabilities）+ §5 草案；REST 形态对照 API_SPEC §3。

业务校验（area_km2 > 0、target_area 几何字段一致性、状态机等）放在 service
层，schema 层只做静态字段约束，与 robot/intervention 风格一致。
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Position


class TargetArea(BaseModel):
    """任务目标区域。对照 DATA_CONTRACTS §4.5。

    几何形状由 type 决定：
    - rectangle：使用 bounds={sw, ne}
    - polygon：使用 vertices[]
    - circle：使用 center + radius_m

    area_km2 / center_point 为预计算字段，方便排序与拍卖；几何字段一致性校验
    （type=rectangle 必有 bounds 等）+ area_km2 / radius_m 必须 > 0 的业务校验放
    在 service 层，统一抛特化错误码 422_TASK_INVALID_AREA_001（BUSINESS_RULES §6.3
    字面）；schema 层不再做 gt=0，避免 Pydantic 422_VALIDATION_FAILED_001 抢先返回
    通用错误码。
    """

    type: Literal["rectangle", "polygon", "circle"]
    bounds: dict | None = None
    vertices: list[Position] | None = None
    center: Position | None = None
    radius_m: float | None = None
    area_km2: float
    center_point: Position


class TaskRequiredCapabilities(BaseModel):
    """任务所需能力。对照 DATA_CONTRACTS §4.6。

    min_battery_pct 默认 20.0；robot_type 为空时不限定机器人类型（拍卖时所有 active
    机器人均可参与），由调度算法在 P5 中按 sensors / payloads 过滤可行解。
    """

    sensors: list[str] = Field(default_factory=list)
    payloads: list[str] = Field(default_factory=list)
    min_battery_pct: float = Field(20.0, ge=0, le=100)
    robot_type: list[Literal["uav", "ugv", "usv"]] | None = None


class TaskBase(BaseModel):
    name: str = Field(..., max_length=200)
    type: Literal["search_rescue", "recon", "transport", "patrol"]
    priority: Literal[1, 2, 3] = 2
    target_area: TargetArea
    required_capabilities: TaskRequiredCapabilities
    sla_deadline: datetime | None = None


class TaskCreate(TaskBase):
    """创建任务请求体。对照 API_SPEC §3 POST /tasks。

    code / status / created_by / 自动分解的 parent_id 等由 service 层补全。
    """


class TaskUpdate(BaseModel):
    """更新任务请求体。对照 API_SPEC §3 PUT /tasks/{id}。

    仅允许修改 name / priority / sla_deadline；非 COMPLETED/CANCELLED 状态校验由
    service 层在 P4.4 实现，错误码 409_TASK_STATUS_CONFLICT_001。
    """

    name: str | None = Field(None, max_length=200)
    priority: Literal[1, 2, 3] | None = None
    sla_deadline: datetime | None = None


class TaskRead(BaseModel):
    """任务详情。对照 API_SPEC §3 GET /tasks/{id} + DATA_CONTRACTS §5。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    type: str
    priority: int
    status: str
    target_area: TargetArea
    required_capabilities: TaskRequiredCapabilities
    parent_id: UUID | None = None
    progress: float
    sla_deadline: datetime | None = None
    created_by: UUID
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class TaskAssignmentRead(BaseModel):
    """任务-机器人分配记录。对照 DATA_CONTRACTS §1.9 + API_SPEC §3 GET /tasks/{id}/assignments。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    robot_id: UUID
    auction_id: UUID | None = None
    assigned_at: datetime
    released_at: datetime | None = None
    is_active: bool


class TaskDetailRead(TaskRead):
    """GET /tasks/{id} 扩展响应。

    `assignments`：当前任务的所有分配记录（含已释放的历史，按 assigned_at DESC）。
    `auctions`：API_SPEC §3 写「auctions: AuctionRead[](摘要)」，但 AuctionRead /
    auctions 表的 service 写入路径属于 P5 调度模块；本任务暂返回空列表占位，P5
    实装时再具体化为 list[AuctionRead]，前端契约保留键不破坏。
    """

    assignments: list[TaskAssignmentRead] = []
    auctions: list[dict] = []


class TaskCancelRequest(BaseModel):
    """POST /tasks/{id}/cancel 请求体。

    reason 长度 5–500 字符；与 RecallRequest 同模式：max 由 schema 拦截，min 在
    service 层抛 422_INTERVENTION_REASON_INVALID_001（BUSINESS_RULES §4.3.1）。
    """

    reason: str = Field(..., max_length=500)
