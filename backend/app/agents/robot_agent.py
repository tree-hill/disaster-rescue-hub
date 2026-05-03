"""单台机器人 Agent —— 1Hz 主循环 + FSM 状态机 + Mock 行为 + 召回响应 + 故障写库。

对照：
- BUILD_ORDER §P3.3 / §P3.4 / §P3.6
- BUSINESS_RULES §2.2（FSM 转移表 + 故障触发条件）+ §4（HITL 召回流程）
- DATA_CONTRACTS §1.4 / §1.6 / §1.7 / §4.2 / §4.3（robots / robot_states / robot_faults / capability / position）
- WS_EVENTS §3（robot.fault_occurred / robot.recall_initiated / robot.recall_completed）

本任务范围（截至 P3.6）：
- 主循环 1Hz：tick_count + 心跳 + IDLE 不动 / EXECUTING / RETURNING 朝目标移动 1m·s + 电量 -0.5%/tick
- 状态机 transit() 守卫（违规抛 FSMTransitionError）
- 故障检测：battery <= 5（low_battery） + 概率注入（settings.mock_fault_inject_probability）；
  comm_lost / sensor_error 暂用占位
- 故障触发时：transit FAULT + 写 robot_faults 表 + emit `robot.fault_occurred`
- 召回响应：`request_recall(user_id, reason)` 由 service 调用，转 RETURNING 并把 target=BASE
- RETURNING 阶段：朝基地移动；距基地 < RETURNING_ARRIVAL_THRESHOLD_M 时 transit IDLE
  + emit `robot.recall_completed`（含 eta_actual_sec）
- **每 tick 写一行 robot_states**
- WS 状态推送（高频位置）由 broadcaster.py 拉模型批量；本类只处理事件型推送
"""
from __future__ import annotations

import asyncio
import logging
import math
import random
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import (
    BASE_ALTITUDE_M,
    BASE_LAT,
    BASE_LNG,
    EXECUTING_BATTERY_DRAIN_PCT,
    FAULT_BATTERY_THRESHOLD,
    METERS_PER_DEGREE,
    MOVE_STEP_METERS,
    RETURNING_ARRIVAL_THRESHOLD_M,
)
from app.db.session import async_session_maker
from app.models.robot import RobotFault, RobotState
from app.repositories.robot import RobotRepository
from app.repositories.robot_fault import RobotFaultRepository
from app.repositories.robot_state import RobotStateRepository
from app.ws.events import push_event

logger = logging.getLogger(__name__)


# 严格对照 BUSINESS_RULES.md §2.2.3。修改前必须同步契约文档。
ROBOT_FSM_TRANSITIONS: dict[str, set[str]] = {
    "IDLE": {"BIDDING", "FAULT"},
    "BIDDING": {"EXECUTING", "IDLE", "FAULT"},
    "EXECUTING": {"RETURNING", "FAULT"},
    "RETURNING": {"IDLE", "FAULT"},
    "FAULT": {"IDLE"},  # 仅修复后回到 IDLE
}

VALID_FSM_STATES = frozenset(ROBOT_FSM_TRANSITIONS.keys())

# 所有 Agent 启动时位置 = 基地中心（与 scripts/seed.py CENTER_LAT/LNG 对齐）
# P5+ 再做 scenarios.initial_state 解析 + 真实初始位置加载
DEFAULT_INITIAL_POSITION: dict[str, float] = {
    "lat": BASE_LAT,
    "lng": BASE_LNG,
    "altitude_m": BASE_ALTITUDE_M,
}
DEFAULT_INITIAL_BATTERY: float = 100.0


def _base_position() -> dict[str, float]:
    """基地坐标快照（RETURNING 阶段的目标）。"""
    return {
        "lat": BASE_LAT,
        "lng": BASE_LNG,
        "altitude_m": BASE_ALTITUDE_M,
    }


# 类型别名：事件推送钩子（async (name, payload) -> None）
EventEmitter = Callable[[str, dict[str, Any]], Awaitable[None]]


class FSMTransitionError(ValueError):
    """非法 FSM 转移。"""


class RobotAgent:
    """单台机器人的 asyncio 协程。

    本类不直接写数据库（P3.3 范围），仅在内存中维护状态。
    `run()` 按 tick_hz 节拍循环；`stop()` 通过 cancel 信号让循环优雅退出。
    """

    def __init__(
        self,
        *,
        robot_id: UUID,
        code: str,
        type_: str,
        capability: dict[str, Any],
        position: dict[str, float] | None = None,
        battery: float = DEFAULT_INITIAL_BATTERY,
        fsm_state: str = "IDLE",
        tick_hz: float = 1.0,
    ) -> None:
        if fsm_state not in VALID_FSM_STATES:
            raise FSMTransitionError(f"非法初始 fsm_state: {fsm_state}")
        if tick_hz <= 0:
            raise ValueError("tick_hz 必须 > 0")

        # 静态身份信息（启动后不变）
        self.robot_id = robot_id
        self.code = code
        self.type = type_
        self.capability = capability

        # 动态状态
        self.fsm_state = fsm_state
        self.position = position or dict(DEFAULT_INITIAL_POSITION)
        self.battery = battery
        self.current_task_id: UUID | None = None
        self.target_position: dict[str, float] | None = None  # set_target_position 设置

        # 召回上下文（P3.6）：service 写 intervention 后调 request_recall 时填充，
        # 用于 _complete_recall 时填到 robot.recall_completed payload
        self._recall_user_id: UUID | None = None
        self._recall_reason: str | None = None
        self._recall_intervention_id: UUID | None = None
        self._recall_started_at: datetime | None = None

        # 运行控制
        self.tick_hz = tick_hz
        self._tick_interval = 1.0 / tick_hz
        self.tick_count = 0
        self.last_heartbeat_at: datetime | None = None
        self._stop_event = asyncio.Event()
        # 测试钩子：覆盖默认的 _emit_state_changed（仅 P3.4 自检使用）
        self._emit_override = None  # type: ignore[assignment]
        # 事件型 WS 推送钩子（fault_occurred / recall_completed 等）
        # 默认走 app.ws.events.push_event；测试可覆盖为 mock async fn
        self._event_emit_override: EventEmitter | None = None

    # ---------- 工厂 ----------
    @classmethod
    async def from_db(
        cls,
        session: AsyncSession,
        robot_id: UUID,
        *,
        tick_hz: float = 1.0,
    ) -> "RobotAgent":
        """从 robots 表加载一台机器人，构造 Agent。"""
        robot = await RobotRepository(session).find_by_id(robot_id)
        if robot is None:
            raise LookupError(f"robot_id {robot_id} 不存在")
        return cls(
            robot_id=robot.id,
            code=robot.code,
            type_=robot.type,
            capability=dict(robot.capability),
            tick_hz=tick_hz,
        )

    # ---------- 状态机 ----------
    def transit(self, target: str, *, reason: str = "") -> None:
        """执行一次 FSM 转移。违反 ROBOT_FSM_TRANSITIONS 抛 FSMTransitionError。"""
        if target not in VALID_FSM_STATES:
            raise FSMTransitionError(f"未知目标状态: {target}")
        allowed = ROBOT_FSM_TRANSITIONS[self.fsm_state]
        if target not in allowed:
            raise FSMTransitionError(
                f"非法转移 {self.fsm_state} → {target}（允许集 {sorted(allowed)}）"
            )
        prev = self.fsm_state
        self.fsm_state = target
        logger.info(
            "robot_fsm_transit",
            extra={
                "robot_id": str(self.robot_id),
                "code": self.code,
                "from": prev,
                "to": target,
                "reason": reason,
            },
        )

    # ---------- 目标位置（P5 拍卖完成后由 dispatch_service 调用） ----------
    def set_target_position(
        self, lat: float, lng: float, altitude_m: float | None = None
    ) -> None:
        """设置 EXECUTING 状态的移动目标。"""
        self.target_position = {
            "lat": float(lat),
            "lng": float(lng),
            "altitude_m": altitude_m if altitude_m is not None else self.position.get("altitude_m"),
        }

    def clear_target_position(self) -> None:
        self.target_position = None

    # ---------- 召回（P3.6） ----------
    def request_recall(
        self,
        *,
        user_id: UUID,
        reason: str,
        intervention_id: UUID | None = None,
    ) -> bool:
        """由 RecallService 在写完 human_interventions 后调用。

        - 仅 EXECUTING / BIDDING / RETURNING 可召回（BUSINESS_RULES §4.4）
        - EXECUTING / BIDDING → transit RETURNING，target = 基地
        - RETURNING → 幂等：刷新召回上下文（user_id 可能不同），保留原 target
        - 其他状态 → 返回 False（service 层翻译为 409）

        本方法只做内存状态变更；DB 写入与 WS `robot.recall_initiated` 推送由 service 完成。
        """
        if self.fsm_state not in {"EXECUTING", "BIDDING", "RETURNING"}:
            return False

        # 记录召回上下文（用于 _complete_recall 时拼 recall_completed payload）
        self._recall_user_id = user_id
        self._recall_reason = reason
        self._recall_intervention_id = intervention_id
        self._recall_started_at = datetime.now(timezone.utc)

        if self.fsm_state in {"EXECUTING", "BIDDING"}:
            self.transit("RETURNING", reason=f"hitl_recall:user={user_id}")
            self.target_position = _base_position()
        else:
            # 已 RETURNING：保险地确认 target=基地（之前任务侧可能 set 过其他 target）
            self.target_position = _base_position()
        return True

    def _arrived_at_base(self) -> bool:
        """RETURNING 阶段判定是否到达基地（< RETURNING_ARRIVAL_THRESHOLD_M）。"""
        if self.fsm_state != "RETURNING":
            return False
        dlat = self.position["lat"] - BASE_LAT
        dlng = self.position["lng"] - BASE_LNG
        dist_m = math.hypot(dlat, dlng) * METERS_PER_DEGREE
        return dist_m < RETURNING_ARRIVAL_THRESHOLD_M

    async def _complete_recall(self) -> None:
        """RETURNING → IDLE 收尾：清任务关联 + emit recall_completed。

        WS_EVENTS §3：recall_completed payload = recall_initiated 同字段 + eta_actual_sec。
        """
        eta_actual_sec: int | None = None
        if self._recall_started_at is not None:
            eta_actual_sec = int(
                (datetime.now(timezone.utc) - self._recall_started_at).total_seconds()
            )
        recall_user_id = self._recall_user_id
        recall_reason = self._recall_reason
        recall_intervention_id = self._recall_intervention_id

        # 状态收尾
        self.transit("IDLE", reason="recall_arrived_base")
        self.current_task_id = None
        self.target_position = None
        self._recall_user_id = None
        self._recall_reason = None
        self._recall_intervention_id = None
        self._recall_started_at = None

        await self._emit_event(
            "robot.recall_completed",
            {
                "robot_id": str(self.robot_id),
                "robot_code": self.code,
                "initiated_by_user_id": str(recall_user_id) if recall_user_id else None,
                "reason": recall_reason,
                "intervention_id": (
                    str(recall_intervention_id) if recall_intervention_id else None
                ),
                "eta_actual_sec": eta_actual_sec,
            },
        )

    # ---------- 故障检测 ----------
    def _check_faults(self) -> str | None:
        """检查所有故障条件，返回故障类型或 None。

        P3.4 实现：battery <= 5 + 概率注入；
        P3.5/3.6 补：comm_lost（心跳超时）、sensor_error。
        """
        if self.battery <= FAULT_BATTERY_THRESHOLD:
            return "low_battery"
        # 概率注入（演示用，默认 0.0 关闭）
        if (
            settings.mock_fault_inject_probability > 0
            and random.random() < settings.mock_fault_inject_probability
        ):
            return "unknown"
        return None

    # ---------- Mock 行为 ----------
    def _move_toward_target(self) -> None:
        """EXECUTING 状态下朝 target 移动 1 米（近似 1° = METERS_PER_DEGREE m）。

        无 target 时 no-op。距离 < 1 米直接吸附到 target。
        """
        if self.target_position is None:
            return
        cur_lat = self.position["lat"]
        cur_lng = self.position["lng"]
        tgt_lat = self.target_position["lat"]
        tgt_lng = self.target_position["lng"]

        dlat = tgt_lat - cur_lat
        dlng = tgt_lng - cur_lng
        dist_deg = math.hypot(dlat, dlng)
        if dist_deg < 1e-12:
            return  # 已到达

        step_deg = MOVE_STEP_METERS / METERS_PER_DEGREE
        if dist_deg <= step_deg:
            # 到达：吸附到 target，便于上层判断到达条件
            self.position["lat"] = tgt_lat
            self.position["lng"] = tgt_lng
            tgt_alt = self.target_position.get("altitude_m")
            if tgt_alt is not None:
                self.position["altitude_m"] = tgt_alt
            return

        ratio = step_deg / dist_deg
        self.position["lat"] = cur_lat + dlat * ratio
        self.position["lng"] = cur_lng + dlng * ratio

    def _drain_battery(self) -> None:
        """EXECUTING 状态电量下降 0.5%/tick，下限 0。"""
        self.battery = max(0.0, self.battery - EXECUTING_BATTERY_DRAIN_PCT)

    # ---------- 故障入口（P3.6）：transit + 写库 + WS 推送 ----------
    async def _enter_fault(self, fault_type: str) -> None:
        """触发故障：transit FAULT + 写 robot_faults + emit `robot.fault_occurred`。

        - severity 映射：low_battery → critical；其余 → warn（细化留 P6）
        - message 中文短句，便于前端直接展示（WS_EVENTS §3 fault_occurred.message）
        - 写库失败时仍 transit FAULT 并尝试 emit（with fault_id=None）—— 状态正确性优先
          于审计完整性；失败本身已被外层 try/except 捕获记日志
        """
        severity = "critical" if fault_type == "low_battery" else "warn"
        message = self._format_fault_message(fault_type)

        self.transit("FAULT", reason=fault_type)

        fault_id: UUID | None = None
        try:
            async with async_session_maker() as session:
                fault = RobotFault(
                    robot_id=self.robot_id,
                    fault_type=fault_type,
                    severity=severity,
                    message=message,
                    detail={
                        "battery": float(self.battery),
                        "position": dict(self.position),
                        "fsm_at_fault": "FAULT",
                    },
                )
                await RobotFaultRepository(session).save(fault)
                await session.commit()
                fault_id = fault.id
        except Exception:  # noqa: BLE001
            logger.exception(
                "robot_fault_persist_failed",
                extra={
                    "robot_id": str(self.robot_id),
                    "code": self.code,
                    "fault_type": fault_type,
                },
            )

        await self._emit_event(
            "robot.fault_occurred",
            {
                "robot_id": str(self.robot_id),
                "robot_code": self.code,
                "fault_type": fault_type,
                "severity": severity,
                "message": message,
                "fault_id": str(fault_id) if fault_id else None,
            },
        )

    def _format_fault_message(self, fault_type: str) -> str:
        if fault_type == "low_battery":
            return f"电量降至 {self.battery:.1f}%，无法继续执行任务"
        if fault_type == "comm_lost":
            return "通信中断超过心跳超时阈值"
        if fault_type == "sensor_error":
            return "传感器异常"
        return f"未知故障：{fault_type}"

    # ---------- 事件型 WS 推送（fault / recall_completed） ----------
    async def _emit_event(self, name: str, payload: dict[str, Any]) -> None:
        """统一事件推送出口；测试可通过 _event_emit_override 劫持。

        默认走 `app.ws.events.push_event`（自动注入 event_id + timestamp）。
        """
        if self._event_emit_override is not None:
            await self._event_emit_override(name, payload)
            return
        try:
            await push_event(name, payload)
        except Exception:  # noqa: BLE001
            # WS 推送失败不应让协程死亡（主循环外层也有兜底，本处早收一层日志）
            logger.exception(
                "robot_event_emit_failed",
                extra={
                    "robot_id": str(self.robot_id),
                    "code": self.code,
                    "event_name": name,
                },
            )

    # ---------- 高频位置 emit 钩子（pull-model broadcaster 主推；本钩子保留为 logger/测试） ----------
    def _emit_state_changed(self, state: RobotState) -> None:
        """每 tick 状态钩子（非 WS 推送主路径）。

        高频位置推送由 broadcaster.py 拉模型批量；本钩子仅留 logger 占位 +
        测试钩子 _emit_override（P3.4 自检使用）。
        """
        if self._emit_override is not None:
            self._emit_override(state)
            return
        logger.debug(
            "robot_state_emitted",
            extra={
                "robot_id": str(self.robot_id),
                "code": self.code,
                "fsm_state": state.fsm_state,
                "battery": float(state.battery),
                "position": dict(state.position),
            },
        )

    # ---------- 数据持久化 ----------
    async def _persist_state(self) -> RobotState:
        """写入一行 robot_states，返回带 id 的实例（commit 后可读）。

        每 tick 开独立 session：25 个协程并发，asyncpg 连接池自然管理。
        """
        async with async_session_maker() as session:
            state = RobotState(
                robot_id=self.robot_id,
                fsm_state=self.fsm_state,
                position=dict(self.position),
                # NUMERIC(5,2) → 用 Decimal 控制精度，避免浮点误差
                battery=Decimal(f"{self.battery:.2f}"),
                sensor_data={},
                current_task_id=self.current_task_id,
            )
            await RobotStateRepository(session).append(state)
            await session.commit()
            return state

    # ---------- 主循环 ----------
    async def _tick(self) -> None:
        """单次 tick：

        1. 计数 + 心跳
        2. EXECUTING / RETURNING：朝 target 移动 + 电量下降
        2.5. RETURNING 抵达基地（< 50m）→ IDLE + emit recall_completed
        3. 故障检测（除已 FAULT 外）→ 命中 → _enter_fault（transit + 写 robot_faults + emit fault_occurred）
        4. 写 robot_states
        5. 高频状态钩子（pull-model broadcaster 主推；本钩子仅 logger / 测试劫持）
        """
        self.tick_count += 1
        self.last_heartbeat_at = datetime.now(timezone.utc)

        # 2) Mock 行为：EXECUTING 与 RETURNING 都朝 target 移动 + 电量下降
        if self.fsm_state in {"EXECUTING", "RETURNING"}:
            self._move_toward_target()
            self._drain_battery()

        # 2.5) RETURNING 抵达基地 → IDLE 收尾 + recall_completed
        if self.fsm_state == "RETURNING" and self._arrived_at_base():
            await self._complete_recall()

        # 3) 故障检测（行为之后：电量降到阈值的那一 tick 立即触发 FAULT）
        if self.fsm_state != "FAULT":
            fault_type = self._check_faults()
            if fault_type is not None:
                await self._enter_fault(fault_type)

        # 4) 持久化（写入失败不应让循环死亡 —— 上层 try/except 兜底）
        state = await self._persist_state()

        # 5) 高频位置 emit 钩子（broadcaster 拉模型主推）
        self._emit_state_changed(state)

    async def run(self) -> None:
        """1Hz 主循环。响应 stop()/cancel 优雅退出。"""
        logger.info(
            "robot_agent_started",
            extra={"robot_id": str(self.robot_id), "code": self.code},
        )
        try:
            while not self._stop_event.is_set():
                try:
                    await self._tick()
                except Exception:  # noqa: BLE001
                    # 单次 tick 异常不应让协程整体死亡（毕设场景：
                    # mock 行为以后会引入更多分支，避免一次失败拉宕整个 manager）
                    logger.exception(
                        "robot_agent_tick_failed",
                        extra={"robot_id": str(self.robot_id), "code": self.code},
                    )
                # 用 Event.wait 替代 sleep：stop_event.set() 可立即解除等待
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self._tick_interval
                    )
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            logger.info(
                "robot_agent_cancelled",
                extra={"robot_id": str(self.robot_id), "code": self.code},
            )
            raise
        finally:
            logger.info(
                "robot_agent_stopped",
                extra={
                    "robot_id": str(self.robot_id),
                    "code": self.code,
                    "tick_count": self.tick_count,
                },
            )

    def stop(self) -> None:
        """请求协程退出（优雅停止信号）。"""
        self._stop_event.set()
