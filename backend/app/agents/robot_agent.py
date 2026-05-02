"""单台机器人 Agent —— 1Hz 主循环 + FSM 状态机 + Mock 行为。

对照：
- BUILD_ORDER §P3.3 / §P3.4
- BUSINESS_RULES §2.2（FSM 转移表 + 故障触发条件）
- DATA_CONTRACTS §1.4 / §1.6 / §4.2 / §4.3（robots / robot_states / capability / position）

本任务范围（截至 P3.4）：
- 主循环 1Hz：推 tick_count + 故障检测 + IDLE 不动 / EXECUTING 移动 1m·s + 电量 -0.5%/tick
- 状态机 transit() 守卫（违规抛 FSMTransitionError）
- 故障检测：battery <= 5 + 概率注入（settings.mock_fault_inject_probability）；
  comm_lost / sensor_error 留 P3.5 / P3.6
- **每 tick 写一行 robot_states**（与 P3 验收"每秒新增约 25 条"一致）
- WS 推送钩子 _emit_state_changed：P3.4 仅 logger；P3.5 替换为真实 WS broadcast
- 不响应召回信号（P3.6）
"""
from __future__ import annotations

import asyncio
import logging
import math
import random
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import (
    EXECUTING_BATTERY_DRAIN_PCT,
    FAULT_BATTERY_THRESHOLD,
    METERS_PER_DEGREE,
    MOVE_STEP_METERS,
)
from app.db.session import async_session_maker
from app.models.robot import RobotState
from app.repositories.robot import RobotRepository
from app.repositories.robot_state import RobotStateRepository

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

# P3.3 简化：所有 Agent 启动时位置 = seed CENTER（30.225, 120.525）
# P3.4 再做 scenarios.initial_state 解析 + 真实初始位置加载
DEFAULT_INITIAL_POSITION: dict[str, float] = {
    "lat": 30.225,
    "lng": 120.525,
    "altitude_m": 50.0,
}
DEFAULT_INITIAL_BATTERY: float = 100.0


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

        # 运行控制
        self.tick_hz = tick_hz
        self._tick_interval = 1.0 / tick_hz
        self.tick_count = 0
        self.last_heartbeat_at: datetime | None = None
        self._stop_event = asyncio.Event()
        # 测试钩子：覆盖默认的 _emit_state_changed（仅 P3.4 自检使用，P3.5 直接改 _emit）
        self._emit_override = None  # type: ignore[assignment]

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

    # ---------- WS 推送钩子（P3.5 替换为真实 broadcast） ----------
    def _emit_state_changed(self, state: RobotState) -> None:
        """状态变化推送钩子。P3.4 仅 logger；P3.5 替换为 sio.emit('robot.position_updated', ...)。"""
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
        2. EXECUTING 状态下：移动 + 电量下降（先做行为，再检查故障）
        3. 故障检测（除已 FAULT 外）→ 命中即 transit FAULT
        4. 写 robot_states
        5. emit 钩子
        """
        self.tick_count += 1
        self.last_heartbeat_at = datetime.now(timezone.utc)

        # 2) Mock 行为
        if self.fsm_state == "EXECUTING":
            self._move_toward_target()
            self._drain_battery()

        # 3) 故障检测（行为之后：电量降到阈值的那一 tick 立即触发 FAULT）
        if self.fsm_state != "FAULT":
            fault_type = self._check_faults()
            if fault_type is not None:
                self.transit("FAULT", reason=fault_type)

        # 4) 持久化（写入失败不应让循环死亡 —— 上层 try/except 兜底）
        state = await self._persist_state()

        # 5) 推送
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
