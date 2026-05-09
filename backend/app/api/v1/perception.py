"""视觉感知 REST 路由（P6.6）。

对照：
- API_SPEC §5：POST /perception/infer 请求 {robot_id, image_base64, position}，
  响应 {detections, inference_time_ms}，权限 system:test，副作用 = 写黑板 +
  可能触发告警
- BUSINESS_RULES §5.2：process_image 主链路

实现：P6.6 不加载真实 YOLO 模型（best.pt 由 P6.5 用户在 Colab 训练），本路由是
**Mock 接口**：detections 始终为空 list，inference_time_ms=0；走 PerceptionService
.process_image 的链路（detections 为空时早返回，不写黑板/不推 WS），仅验证
endpoint 契约可用。

P6.6 之后接入真实模型时只需把 `_mock_infer(...)` 换成 `model(image, conf=0.5,
iou=0.45)`，schema 不变。
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.exceptions import BusinessError
from app.db.session import get_db
from app.perception.service import PerceptionService
from app.repositories.robot import RobotRepository
from app.schemas.auth import CurrentUser
from app.schemas.common import Detection
from app.schemas.perception import InferRequest, InferResponse

router = APIRouter(prefix="/perception", tags=["perception"])


def _mock_infer(image_base64: str) -> tuple[list[Detection], int]:
    """P6.6 占位：返回空 detections。

    P6.5 best.pt 落地后替换为 `model(image, conf=0.5, iou=0.45)` → 解析为
    Detection 列表 + 计算 inference_time_ms。
    """
    return [], 0


@router.post("/infer", response_model=InferResponse)
async def infer(
    payload: InferRequest,
    _current: CurrentUser = Depends(require_permission("system:test")),
    db: AsyncSession = Depends(get_db),
) -> InferResponse:
    """Mock 推理接口。副作用：（detections 非空时）写黑板 + WS perception.detection
    + 可能 perception.high_confidence_alert + 自动救援任务（survivor conf≥0.8）。
    """
    robot = await RobotRepository(db).find_by_id(payload.robot_id)
    if robot is None:
        raise BusinessError(
            code="404_ROBOT_NOT_FOUND_001",
            message=f"机器人 '{payload.robot_id}' 不存在",
            http_status=404,
        )

    t0 = time.perf_counter()
    detections, _ = _mock_infer(payload.image_base64)
    inference_time_ms = int((time.perf_counter() - t0) * 1000)

    frame_id = f"{robot.code}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-mock"
    await PerceptionService(db).process_image(
        robot_id=robot.id,
        robot_code=robot.code,
        position=payload.position,
        detections=detections,
        frame_id=frame_id,
        inference_time_ms=inference_time_ms,
    )

    return InferResponse(detections=detections, inference_time_ms=inference_time_ms)
