"""视觉感知服务（P6.6）。

对照：
- BUSINESS_RULES §5.2：推理结果处理流程（filter conf≥0.5 → 写黑板 → WS push →
  高置信度告警）
- BUSINESS_RULES §5.3：高置信度幸存者自动派任务（500 m 邻域去重 → 否则系统用户创建）
- WS_EVENTS §6：perception.detection（一帧一推送，含整 detections 数组）
  + perception.high_confidence_alert
- API_SPEC §5：POST /perception/infer 副作用 = 写黑板 + 可能触发告警

设计边界：
- **不在本模块加载真实 YOLO 模型**：P6.4 / P6.5 由用户在 Colab 完成；本模块的
  `process_image` 接受调用方预先算好的 `detections: list[Detection]`，model_path
  字段只挂在 `__init__` 上做未来扩展占位。这样 backend 链路完全跑通，best.pt 落地
  时只需新增一个 `_infer_yolo(image)` 适配方法。
- **fuse 而非 set**：BUSINESS_RULES §5.2 字面调 `blackboard.fuse(key=...)` —
  同一 (class, lat100, lng100) 网格内多机器人/多帧观测要走 P6.2 加权融合。
- **session 由调用方注入**（FastAPI route / mock agent / self-check），与
  TaskService 同款风格；本模块不开新 session。
- **TaskService.create 内部 commit + publish task.created**：自动救援任务的
  task.created 由 P5.7 dispatch_trigger.register_auto_trigger 监听到 → 自动
  start_auction，构成「视觉发现 → 自动派任务 → 自动拍卖」端到端链。
- **fire 告警 P6.6 仅推 WS perception.high_confidence_alert**（class_name=fire）；
  写 alerts 表 / alert.raised 业务事件留给 P7 告警模块。
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.communication.blackboard import get_blackboard
from app.core.event_bus import get_event_bus
from app.repositories.task import TaskRepository
from app.repositories.user import UserRepository
from app.schemas.common import Detection, Position
from app.schemas.task import TargetArea, TaskCreate, TaskRequiredCapabilities
from app.services.task_service import TaskService
from app.ws.events import push_event

logger = logging.getLogger(__name__)

# BUSINESS_RULES §7：写黑板 conf 下限（与 INV-5 对齐）+ 视觉数据 TTL 5 min
WRITE_CONFIDENCE_FLOOR = 0.5
PERCEPTION_TTL_SEC = 300.0

# §5.2 高置信度告警阈值
SURVIVOR_HIGH_CONF = 0.8
FIRE_HIGH_CONF = 0.7

# §5.3 幸存者去重半径（km）+ 自动救援任务参数
SURVIVOR_DEDUP_RADIUS_KM = 0.5
AUTO_RESCUE_RADIUS_M = 200.0
AUTO_RESCUE_AREA_KM2 = 0.126  # π × 0.2² ≈ 0.126
AUTO_RESCUE_MIN_BATTERY_PCT = 30.0
AUTO_RESCUE_REQUIRED_SENSORS = ["camera_4k"]

SYSTEM_USERNAME = "system"


class PerceptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def process_image(
        self,
        *,
        robot_id: UUID,
        robot_code: str,
        position: Position,
        detections: list[Detection],
        frame_id: str,
        inference_time_ms: int,
    ) -> dict[str, Any]:
        """处理一帧推理结果（BUSINESS_RULES §5.2）。

        Returns: {valid_count, written_keys, auto_task_ids, alerts_pushed}.
        """
        valid = [d for d in detections if d.confidence >= WRITE_CONFIDENCE_FLOOR]
        result: dict[str, Any] = {
            "valid_count": len(valid),
            "written_keys": [],
            "auto_task_ids": [],
            "alerts_pushed": 0,
        }
        if not valid:
            return result

        bb = get_blackboard()

        # 1) 写黑板（每条 detection 一条 fuse；P6.2 信息融合自动按 confidence 加权）
        for d in valid:
            world_pos = d.world_position or position
            key = self._make_key(d.class_name, world_pos)
            await bb.fuse(
                key=key,
                value={
                    "type": d.class_name,
                    "position": {"lat": world_pos.lat, "lng": world_pos.lng},
                    "bbox": list(d.bbox),
                },
                confidence=float(d.confidence),
                source_robot_id=robot_id,
                ttl_sec=PERCEPTION_TTL_SEC,
            )
            result["written_keys"].append(key)

        # 2) WS perception.detection（一帧一推送，整 detections 数组）
        await push_event(
            "perception.detection",
            {
                "source_robot_id": str(robot_id),
                "source_robot_code": robot_code,
                "frame_id": frame_id,
                "inference_time_ms": int(inference_time_ms),
                "detections": [self._serialize_detection(d, position) for d in valid],
            },
            room="commander",
        )

        # 3) 高置信度处理（survivor → 自动派任务；fire → 告警）
        for d in valid:
            world_pos = d.world_position or position
            if d.class_name == "survivor" and d.confidence >= SURVIVOR_HIGH_CONF:
                task_id = await self._handle_high_confidence_survivor(
                    confidence=float(d.confidence),
                    position=world_pos,
                    robot_code=robot_code,
                )
                result["auto_task_ids"].append(str(task_id) if task_id else None)
                result["alerts_pushed"] += 1
            elif d.class_name == "fire" and d.confidence >= FIRE_HIGH_CONF:
                await self._push_high_confidence_alert(
                    class_name="fire",
                    confidence=float(d.confidence),
                    position=world_pos,
                    robot_code=robot_code,
                    auto_task_triggered=False,
                    task_id=None,
                )
                result["alerts_pushed"] += 1

        return result

    # ---------- 内部 ----------

    @staticmethod
    def _make_key(class_name: str, pos: Position) -> str:
        """与 BUSINESS_RULES §5.2 的 key 公式一致（int(lat*100)_int(lng*100)）。"""
        return f"{class_name}:{int(pos.lat * 100)}_{int(pos.lng * 100)}"

    @staticmethod
    def _serialize_detection(d: Detection, fallback_pos: Position) -> dict[str, Any]:
        wp = d.world_position or fallback_pos
        return {
            "class_name": d.class_name,
            "confidence": float(d.confidence),
            "bbox": list(d.bbox),
            "world_position": {"lat": wp.lat, "lng": wp.lng} if wp else None,
        }

    async def _handle_high_confidence_survivor(
        self,
        *,
        confidence: float,
        position: Position,
        robot_code: str,
    ) -> UUID | None:
        """500 m 内已有救援任务 → 提优先级；否则系统用户创建救援任务。"""
        repo = TaskRepository(self.session)
        nearby = await repo.find_active_near(
            position.lat,
            position.lng,
            radius_km=SURVIVOR_DEDUP_RADIUS_KM,
            types=["search_rescue"],
        )

        if nearby:
            bumped = False
            for t in nearby:
                if t.priority > 1:
                    t.priority = 1
                    bumped = True
            if bumped:
                await self.session.commit()
            await self._push_high_confidence_alert(
                class_name="survivor",
                confidence=confidence,
                position=position,
                robot_code=robot_code,
                auto_task_triggered=False,
                task_id=None,
            )
            return None

        # 系统用户创建任务
        sys_user = await UserRepository(self.session).get_by_username(SYSTEM_USERNAME)
        if sys_user is None:
            logger.error(
                "perception_auto_create_skipped_no_system_user",
                extra={"robot_code": robot_code},
            )
            await self._push_high_confidence_alert(
                class_name="survivor",
                confidence=confidence,
                position=position,
                robot_code=robot_code,
                auto_task_triggered=False,
                task_id=None,
            )
            return None

        target_area = TargetArea(
            type="circle",
            center=position,
            radius_m=AUTO_RESCUE_RADIUS_M,
            area_km2=AUTO_RESCUE_AREA_KM2,
            center_point=position,
        )
        payload = TaskCreate(
            name=f"自动救援：发现幸存者（置信度 {confidence:.2f}）",
            type="search_rescue",
            priority=1,
            target_area=target_area,
            required_capabilities=TaskRequiredCapabilities(
                sensors=AUTO_RESCUE_REQUIRED_SENSORS,
                payloads=[],
                min_battery_pct=AUTO_RESCUE_MIN_BATTERY_PCT,
            ),
        )
        # TaskService.create 内部 commit + publish task.created（→ P5.7 自动 start_auction）
        task = await TaskService(self.session).create(payload, created_by=sys_user.id)

        await self._push_high_confidence_alert(
            class_name="survivor",
            confidence=confidence,
            position=position,
            robot_code=robot_code,
            auto_task_triggered=True,
            task_id=str(task.id),
        )
        return task.id

    @staticmethod
    async def _push_high_confidence_alert(
        *,
        class_name: str,
        confidence: float,
        position: Position,
        robot_code: str,
        auto_task_triggered: bool,
        task_id: str | None,
    ) -> None:
        payload = {
            "class_name": class_name,
            "confidence": float(confidence),
            "position": {"lat": position.lat, "lng": position.lng},
            "source_robot_code": robot_code,
            "auto_task_triggered": bool(auto_task_triggered),
            "task_id": task_id,
        }
        await push_event(
            "perception.high_confidence_alert",
            payload,
            room="commander",
        )
        # P7.1：双发到 EventBus，AlertEngine 据此触发 fire_detected /
        # survivor_high_confidence 规则；publish 失败仅日志，不阻塞 WS 链路。
        try:
            await get_event_bus().publish("perception.high_confidence_alert", payload)
        except Exception:
            logger.exception(
                "perception_alert_publish_failed",
                extra={"class_name": class_name, "robot_code": robot_code},
            )
