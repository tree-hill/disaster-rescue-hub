"""感知模块 Schemas（P6.6）。

对照 API_SPEC §5：POST /perception/infer
- 请求：{robot_id: UUID, image_base64: str, position: Position}
- 响应：{detections: Detection[], inference_time_ms: int}

复用 schemas/common.py 的 Detection 定义（class_name 限定 4 类 + bbox 4 浮点数 +
world_position 可选）。
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Detection, Position


class InferRequest(BaseModel):
    """POST /perception/infer 请求体（API_SPEC §5）。"""

    robot_id: UUID
    image_base64: str = Field(..., description="Base64 编码图像；P6.6 Mock 路径忽略内容")
    position: Position


class InferResponse(BaseModel):
    """POST /perception/infer 响应。"""

    detections: list[Detection] = Field(default_factory=list)
    inference_time_ms: int = 0
