"""规则引擎：拍卖前的硬约束过滤。

对照 BUSINESS_RULES §3（Rule Engine）：
- §3.2 列出 8 条硬约束（R1~R8），任一失败即过滤；失败标记字符串字面一致
  （inactive / not_idle / low_battery / wrong_type / missing_sensor /
  missing_payload / out_of_range / overloaded）。
- §3.3 给出 RuleEngine.check / RuleEngine.filter 的伪代码。
- §3.4：filter 后若 eligible == 0，由调用方关闭拍卖；本模块只负责过滤本身。

设计边界（与 task_status_machine 同一思路，保证可测性 + 避免与 ORM 耦合）：
- 本模块零 IO、无 DB session、无 Agent 引用；所有依赖通过 RobotEvalInput /
  TaskEvalInput 显式输入。
- R8 `active_assignments_count < 3` 由调用方（P5.4 dispatch_service）从
  task_assignments 表查得后注入；规则引擎不查库，避免「过滤一次扫一次表」的
  N+1 风险，并使本模块 100% 单元测试可覆盖。
- R7 用内置球面 haversine（R=6371 km，BUSINESS_RULES §1 默认地球半径）；
  P5.2 出价的 distance_score 也是球面距离，未来若需要在 dispatch/geo.py
  统一抽出再说，本任务不预抽（避免 YAGNI）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.schemas.common import Position, RobotCapability
from app.schemas.task import TargetArea, TaskRequiredCapabilities

# === 失败原因常量（BUSINESS_RULES §3.2 字面） ===
REASON_OK = "ok"
REASON_INACTIVE = "inactive"
REASON_NOT_IDLE = "not_idle"
REASON_LOW_BATTERY = "low_battery"
REASON_WRONG_TYPE = "wrong_type"
REASON_MISSING_SENSOR = "missing_sensor"
REASON_MISSING_PAYLOAD = "missing_payload"
REASON_OUT_OF_RANGE = "out_of_range"
REASON_OVERLOADED = "overloaded"

# R3 业务底线：min_battery_pct < 20.0 时按 20.0 兜底（BUSINESS_RULES §3.2 R3）。
MIN_BATTERY_FLOOR_PCT = 20.0
# R8 单机活跃任务上限（BUSINESS_RULES §3.2 R8）。
MAX_ACTIVE_ASSIGNMENTS = 3
# 地球半径（km），与 BUSINESS_RULES §1 距离计算一致。
EARTH_RADIUS_KM = 6371.0

# 允许参与拍卖的运行时状态集合（R2，BUSINESS_RULES §3.2）。
ELIGIBLE_FSM_STATES: frozenset[str] = frozenset({"IDLE", "RETURNING"})


@dataclass(frozen=True)
class RobotEvalInput:
    """RuleEngine 评估机器人所需的输入快照。

    由 dispatch_service 在拍卖时合并三处来源构造：
    1. robots 表（is_active / type / capability）
    2. AgentManager 运行时快照（fsm_state / position / battery）
    3. task_assignments 表的 active 计数（active_assignments_count）

    冻结 dataclass 保证不可变，避免在过滤过程中被意外改写。
    """

    id: UUID
    is_active: bool
    type: Literal["uav", "ugv", "usv"]
    fsm_state: Literal["IDLE", "BIDDING", "EXECUTING", "RETURNING", "FAULT"]
    battery: float
    position: Position
    capability: RobotCapability
    active_assignments_count: int


@dataclass(frozen=True)
class TaskEvalInput:
    """RuleEngine 评估任务所需的输入快照。

    由 dispatch_service 从 tasks 表读出后构造；只用到 required_capabilities 与
    target_area.center_point，其余字段（status / priority / sla 等）跟硬约束无关。
    """

    id: UUID
    required_capabilities: TaskRequiredCapabilities
    target_area: TargetArea


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """球面 haversine 距离（km）。

    R=6371。对接 BUSINESS_RULES §1 / §3.2 R7。导出供 P5.2 出价计算复用。
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmd = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmd / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


class RuleEngine:
    """硬约束过滤器（无状态）。

    使用方式：
        engine = RuleEngine()
        ok, reason = engine.check(robot_view, task_view)
        eligible, stats = engine.filter(robot_views, task_view)

    约束顺序与 BUSINESS_RULES §3.2 表格一致，任一失败立即返回（短路），
    后续约束不再求值；这一点对统计语义重要：filter 的 stats 反映的是「首个
    命中的失败原因」，并非「所有失败原因」。
    """

    def check(
        self, robot: RobotEvalInput, task: TaskEvalInput
    ) -> tuple[bool, str]:
        """单机硬约束检测。返回 (是否通过, 首个失败原因 | 'ok')。"""
        # R1: is_active
        if not robot.is_active:
            return False, REASON_INACTIVE

        # R2: state_idle —— 仅 IDLE / RETURNING 可参与拍卖
        if robot.fsm_state not in ELIGIBLE_FSM_STATES:
            return False, REASON_NOT_IDLE

        # R3: min_battery —— 取业务底线 20% 与任务自身要求中的更高者
        battery_threshold = max(
            MIN_BATTERY_FLOOR_PCT,
            task.required_capabilities.min_battery_pct,
        )
        if robot.battery < battery_threshold:
            return False, REASON_LOW_BATTERY

        # R4: robot_type —— None 或空 list 表示「不限定」（schema 默认 None）
        allowed_types = task.required_capabilities.robot_type
        if allowed_types and robot.type not in allowed_types:
            return False, REASON_WRONG_TYPE

        # R5: required_sensors —— 任务要求集合 ⊆ 机器人具备集合
        required_sensors = set(task.required_capabilities.sensors)
        if required_sensors and not required_sensors.issubset(set(robot.capability.sensors)):
            return False, REASON_MISSING_SENSOR

        # R6: required_payloads
        required_payloads = set(task.required_capabilities.payloads)
        if required_payloads and not required_payloads.issubset(set(robot.capability.payloads)):
            return False, REASON_MISSING_PAYLOAD

        # R7: range_check —— 球面距离 ≤ 机器人最大航程（km）
        dist_km = haversine_km(
            robot.position.lat,
            robot.position.lng,
            task.target_area.center_point.lat,
            task.target_area.center_point.lng,
        )
        if dist_km > robot.capability.max_range_km:
            return False, REASON_OUT_OF_RANGE

        # R8: load_limit
        if robot.active_assignments_count >= MAX_ACTIVE_ASSIGNMENTS:
            return False, REASON_OVERLOADED

        return True, REASON_OK

    def filter(
        self,
        robots: list[RobotEvalInput],
        task: TaskEvalInput,
    ) -> tuple[list[RobotEvalInput], dict[str, int]]:
        """批量过滤。返回 (合格机器人列表, {失败原因: 计数})。

        合格列表保持输入顺序（稳定），便于上层算法在相同输入下产出可重放结果；
        统计 dict 仅包含实际出现的失败原因，避免给上层造成「所有 8 项均参与
        统计」的错觉。
        """
        eligible: list[RobotEvalInput] = []
        stats: dict[str, int] = {}
        for r in robots:
            ok, reason = self.check(r, task)
            if ok:
                eligible.append(r)
            else:
                stats[reason] = stats.get(reason, 0) + 1
        return eligible, stats
