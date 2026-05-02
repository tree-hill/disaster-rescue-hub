"""跨领域共用的 Pydantic v2 Schemas。

严格对照 DATA_CONTRACTS §5（Common Schemas）。
P3 / P4 / P5 / P6 多个领域复用本文件，因此**只放与领域无关、稳定的基础类型**。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Position(BaseModel):
    """通用地理位置。对照 DATA_CONTRACTS §4.3。"""

    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    altitude_m: float | None = None
    heading_deg: float | None = Field(None, ge=0, lt=360)


class RobotCapability(BaseModel):
    """机器人能力（写入 robots.capability JSONB）。对照 DATA_CONTRACTS §4.2。"""

    sensors: list[str] = Field(default_factory=list)
    payloads: list[str] = Field(default_factory=list)
    max_speed_mps: float
    max_battery_min: int
    max_range_km: float
    has_yolo: bool = False
    weight_kg: float


class Detection(BaseModel):
    """单条 YOLO 检测结果。对照 DATA_CONTRACTS §4.4 vision.detections[]。"""

    class_id: int = Field(..., ge=0, le=3)
    class_name: Literal["survivor", "collapsed_building", "smoke", "fire"]
    confidence: float = Field(..., ge=0, le=1)
    bbox: list[float] = Field(..., min_length=4, max_length=4)
    world_position: Position | None = None


class VisionData(BaseModel):
    """单帧视觉推理输出。对照 DATA_CONTRACTS §4.4 sensor_data.vision。"""

    frame_id: str
    inference_time_ms: int
    detections: list[Detection]


class SensorData(BaseModel):
    """传感器数据载荷（写入 robot_states.sensor_data JSONB）。

    对照 DATA_CONTRACTS §4.4。允许扩展字段，避免不同机型扩展数据被 Pydantic 截断。
    """

    model_config = ConfigDict(extra="allow")

    temperature_c: float | None = None
    humidity_pct: float | None = None
    signal_dbm: float | None = None
    vision: VisionData | None = None
