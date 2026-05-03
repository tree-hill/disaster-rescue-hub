"""HITL 召回服务（POST /robots/{id}/recall）。

对照：
- API_SPEC §2 POST /robots/{id}/recall
- BUSINESS_RULES §4（HITL 通用流程）+ §4.4（召回特殊规则）+ §6.2/§6.5（错误码）
- DATA_CONTRACTS §1.12 + §4.8（before/after_state JSONB schema）
- WS_EVENTS §3 robot.recall_initiated
- INV-G：intervention 与业务状态变更必须同事务

流程（严格按 BUSINESS_RULES §4.2 七步）：
  1. 校验 reason（≥5 字符，非纯空白）
  2. 校验机器人存在（404）
  3. 校验 Agent 在线 + FSM 可召回（503 / 409）
  4. before_state 快照
  5. 计算 recall_eta_sec（haversine 近似 + capability.max_speed_mps）
  6. 调用 agent.request_recall（内存状态变更：transit RETURNING + target=BASE）
  7. 写 human_interventions（同事务）+ commit
  8. 事务外 emit `robot.recall_initiated`（commander 房间）

设计取舍：
- agent 内存态在 commit 之前修改：若 commit 失败需回滚 agent 状态。本任务接受
  「写库失败但 agent 已转 RETURNING」的极小概率窗口（mock 环境数据库稳定），
  P5 接入真实 dispatch 时再加 try/except 回滚补偿
- intervention.recorded（admin 房间审计事件）按 P3.5 决策推迟到 P5 一并实现
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.manager import get_agent_manager
from app.core.constants import (
    BASE_LAT,
    BASE_LNG,
    METERS_PER_DEGREE,
    RECALL_REASON_MIN_LEN,
)
from app.core.exceptions import BusinessError
from app.models.intervention import HumanIntervention
from app.repositories.intervention import InterventionRepository
from app.repositories.robot import RobotRepository
from app.schemas.intervention import RecallResponse
from app.ws.events import push_event

logger = logging.getLogger(__name__)


class RecallService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def execute_recall(
        self,
        *,
        robot_id: UUID,
        user_id: UUID,
        reason: str,
    ) -> RecallResponse:
        # 1) reason 校验（特化错误码优先于通用 422_VALIDATION_FAILED_001）
        self._validate_reason(reason)

        # 2) 机器人存在性
        robot = await RobotRepository(self.session).find_by_id(robot_id)
        if robot is None:
            raise BusinessError(
                code="404_ROBOT_NOT_FOUND_001",
                message="机器人不存在",
                http_status=404,
                details=[
                    {
                        "field": "robot_id",
                        "code": "not_found",
                        "message": str(robot_id),
                    }
                ],
            )

        # 3) Agent 在线 + FSM 可召回
        manager = get_agent_manager()
        agent = manager.get(robot_id)
        if not manager.started or agent is None:
            raise BusinessError(
                code="503_AGENT_NOT_RUNNING_001",
                message="机器人 Agent 未运行（mock_agents_enabled=False 或未启动）",
                http_status=503,
            )
        if agent.fsm_state == "FAULT":
            raise BusinessError(
                code="409_ROBOT_ALREADY_FAULT_001",
                message="机器人已是 FAULT 状态，不能召回",
                http_status=409,
                details=[
                    {
                        "field": "robot.fsm_state",
                        "code": "current_state",
                        "message": "FAULT",
                    }
                ],
            )
        if agent.fsm_state not in {"EXECUTING", "BIDDING", "RETURNING"}:
            raise BusinessError(
                code="409_ROBOT_NOT_RECALLABLE_001",
                message="当前 FSM 状态不可召回（仅 EXECUTING/BIDDING/RETURNING 可召回）",
                http_status=409,
                details=[
                    {
                        "field": "robot.fsm_state",
                        "code": "current_state",
                        "message": agent.fsm_state,
                    }
                ],
            )

        # 4) before_state 快照（DATA_CONTRACTS §4.8）
        before_state: dict[str, Any] = {
            "robot_id": str(robot.id),
            "robot_code": robot.code,
            "robot_state": agent.fsm_state,
            "current_task_id": (
                str(agent.current_task_id) if agent.current_task_id else None
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # 5) recall_eta_sec：haversine 近似 + capability.max_speed_mps
        eta_sec = self._compute_eta_sec(agent)

        # 6) 内存状态变更（agent 转 RETURNING + target=BASE）
        ok = agent.request_recall(user_id=user_id, reason=reason)
        if not ok:
            # 理论上前面已经校验过；防御性兜底
            raise BusinessError(
                code="409_ROBOT_NOT_RECALLABLE_001",
                message="Agent 拒绝召回请求",
                http_status=409,
            )

        # 7) 写 intervention（同事务）
        after_state: dict[str, Any] = {
            "robot_id": str(robot.id),
            "robot_code": robot.code,
            "robot_state": "RETURNING",
            # 任务侧解绑（current_task_id=None）留 P4 task 模块联动；本任务保留原 task_id
            "current_task_id": before_state["current_task_id"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        intervention = HumanIntervention(
            user_id=user_id,
            intervention_type="recall",
            target_robot_id=robot.id,
            target_task_id=agent.current_task_id,
            before_state=before_state,
            after_state=after_state,
            reason=reason,
        )
        await InterventionRepository(self.session).save(intervention)
        await self.session.commit()

        # 把 intervention_id 灌回 agent，供后续 recall_completed 引用
        agent._recall_intervention_id = intervention.id

        # 8) emit `robot.recall_initiated`（commander 房间；admin 房间留 P5 intervention.recorded）
        await push_event(
            "robot.recall_initiated",
            {
                "robot_id": str(robot.id),
                "robot_code": robot.code,
                "initiated_by_user_id": str(user_id),
                "reason": reason,
                "intervention_id": str(intervention.id),
            },
        )

        logger.info(
            "robot_recall_initiated",
            extra={
                "robot_id": str(robot.id),
                "code": robot.code,
                "user_id": str(user_id),
                "intervention_id": str(intervention.id),
                "recall_eta_sec": eta_sec,
            },
        )

        return RecallResponse(
            intervention_id=intervention.id,
            recall_eta_sec=eta_sec,
        )

    # ---------- helpers ----------
    @staticmethod
    def _validate_reason(reason: str) -> None:
        """BUSINESS_RULES §4.3.1 + §6.5：reason ≥ 5 字符且非纯空白。

        失败抛 422_INTERVENTION_REASON_INVALID_001（特化错误码，优先于通用 422_VALIDATION_FAILED_001）。
        """
        if not isinstance(reason, str) or len(reason.strip()) < RECALL_REASON_MIN_LEN:
            raise BusinessError(
                code="422_INTERVENTION_REASON_INVALID_001",
                message=f"reason 至少 {RECALL_REASON_MIN_LEN} 个非空白字符",
                http_status=422,
                details=[
                    {
                        "field": "reason",
                        "code": "too_short_or_blank",
                        "message": f"strip 后长度 {len(reason.strip()) if isinstance(reason, str) else 0}",
                    }
                ],
            )

    @staticmethod
    def _compute_eta_sec(agent: Any) -> int:
        """从当前位置到基地的 ETA（秒）。

        简化：用 1° = METERS_PER_DEGREE 近似（与 Agent 内部移动模型一致），
        速度取 capability.max_speed_mps；速度 ≤ 0 兜底 1 m/s。
        最小返回 1 秒（避免 0 让前端误判已到达）。
        """
        cur_lat = float(agent.position["lat"])
        cur_lng = float(agent.position["lng"])
        dist_m = math.hypot(cur_lat - BASE_LAT, cur_lng - BASE_LNG) * METERS_PER_DEGREE
        max_speed = float(agent.capability.get("max_speed_mps", 1.0))
        if max_speed <= 0:
            max_speed = 1.0
        return max(1, int(dist_m / max_speed))
