"""复盘 Pydantic v2 Schemas（P8.1）。

对照：
- API_SPEC §7 GET /replay/sessions /sessions/{id} /sessions/{id}/snapshots /key-events
- DATA_CONTRACTS §4.12 replay_sessions.summary（P8.1 扩展加 snapshots / key_events
  两个数组字段；前 7 个聚合字段保留契约不变）

体积说明：
- snapshots 按 1Hz × N 任务期录帧，单 session 上限 replay_session_max_frames（默认 1800
  即 30 分钟）。Snapshot 内 blackboard 仅落统计计数，不落全量 entries，避免 MB 级膨胀。
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Position


# ============== 单帧 / 单事件 ==============


class RobotFrame(BaseModel):
    robot_id: UUID
    code: str
    fsm_state: str
    position: Position | None = None
    battery: float = Field(ge=0.0, le=100.0)
    current_task_id: UUID | None = None


class TaskFrame(BaseModel):
    task_id: UUID
    code: str
    status: str
    progress: float = Field(ge=0.0, le=100.0)
    assigned_robot_ids: list[UUID] = Field(default_factory=list)


class BlackboardFrame(BaseModel):
    """仅统计；避免 entries 全量进 summary 导致 JSONB 爆炸。"""

    total_entries: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)


class Snapshot(BaseModel):
    ts: datetime
    robots: list[RobotFrame] = Field(default_factory=list)
    tasks: list[TaskFrame] = Field(default_factory=list)
    blackboard: BlackboardFrame = Field(default_factory=BlackboardFrame)


KeyEventType = Literal[
    "task_completed",
    "task_failed",
    "task_cancelled",
    "task_reassigned",
    "intervention",
    "alert",
    "auction_completed",
    "recall",
]


class KeyEvent(BaseModel):
    ts: datetime
    type: KeyEventType
    description: str
    related_id: UUID | None = None


# ============== ReplaySession 汇总 ==============


class YoloDetectionsSummary(BaseModel):
    """对应 §4.12 yolo_detections_summary 字面字段。"""

    survivor: int = 0
    fire: int = 0
    smoke: int = 0
    collapsed_building: int = 0


class ReplaySummary(BaseModel):
    """§4.12 原 7 字段 + P8.1 扩展 snapshots / key_events。"""

    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_robots_used: int = 0
    total_interventions: int = 0
    total_alerts: int = 0
    yolo_detections_summary: YoloDetectionsSummary = Field(
        default_factory=YoloDetectionsSummary
    )
    snapshots: list[Snapshot] = Field(default_factory=list)
    key_events: list[KeyEvent] = Field(default_factory=list)


class ReplaySessionRead(BaseModel):
    """列表行 + 详情通用：summary 始终返回完整结构。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    scenario_id: UUID | None = None
    algorithm: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_sec: int | None = None
    completion_rate: float | None = None
    summary: ReplaySummary = Field(default_factory=ReplaySummary)
    created_by: UUID
    created_at: datetime
