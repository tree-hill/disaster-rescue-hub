"""单台机器人 Agent —— 1Hz 主循环 + FSM 状态机骨架。

对照：
- BUILD_ORDER §P3.3（__init__ / async run / FSM 字典）
- BUSINESS_RULES §2.2（FSM 转移表 + 故障触发条件）
- DATA_CONTRACTS §1.4 / §4.2 / §4.3（robots / capability / position）

本任务范围（严格按 BUILD_ORDER 字面）：
- 主循环 1Hz 推动 tick_count
- 状态机 transit() 守卫（违规抛 ValueError）
- 故障检测：仅 battery <= 5（其余 P3.4 补全）
- 不写 robot_states 表（P3.4 加 Mock 移动逻辑时一并写）
- 不推 WS 事件（P3.5）
- 不响应召回信号（P3.6）
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import FAULT_BATTERY_THRESHOLD
from app.repositories.robot import RobotRepository

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

        # 运行控制
        self.tick_hz = tick_hz
        self._tick_interval = 1.0 / tick_hz
        self.tick_count = 0
        self.last_heartbeat_at: datetime | None = None
        self._stop_event = asyncio.Event()

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

    # ---------- 故障检测（P3.3 仅 battery；P3.4 补 sensor_error / comm_lost） ----------
    def _check_faults(self) -> str | None:
        """检查所有故障条件，返回故障类型（如 'low_battery'）或 None。"""
        if self.battery <= FAULT_BATTERY_THRESHOLD:
            return "low_battery"
        return None

    # ---------- 主循环 ----------
    async def _tick(self) -> None:
        """单次 tick：心跳 + 故障检测。

        P3.3 不做位置移动 / 电量下降（P3.4）和 WS 推送（P3.5）。
        """
        self.tick_count += 1
        self.last_heartbeat_at = datetime.now(timezone.utc)

        # 故障检测：除已 FAULT 外的状态命中条件 → 转 FAULT
        if self.fsm_state != "FAULT":
            fault_type = self._check_faults()
            if fault_type is not None:
                self.transit("FAULT", reason=fault_type)

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
