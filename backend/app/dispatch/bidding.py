"""出价计算：5 个分量 + 视觉加成 + 主入口 compute_full_bid。

对照 BUSINESS_RULES §1（调度出价公式）：

    bid(r, t) = base_score(r, t) × vision_boost(r, t)
    base_score = w₁·D(r,t) + w₂·B(r) + w₃·C(r,t) − w₄·L(r)
    w₁=0.40 (距离) / w₂=0.20 (电量) / w₃=0.30 (能力) / w₄=0.10 (负载惩罚)

设计边界（与 P5.1 rule_engine 同款风格，保证模块零 IO + 可测）：
- 5 个 leaf 函数（compute_distance_score / compute_battery_score / compute_
  capability_match / compute_load_score / compute_vision_boost）按 BUSINESS_RULES
  §1.2 伪代码签名取**原始参数**（Position / float / RobotCapability / int / bool +
  int），便于单元测试与论文复现。
- compute_full_bid 复用 rule_engine 的 RobotEvalInput / TaskEvalInput 冻结
  dataclass 作为视图入参，与「过滤 → 出价」同一份输入，避免再造一套类型。
- vision_boost **不直接依赖 Blackboard**：用 nearby_survivor_count 整数注入。
  P6.1 黑板基础设施落地后，dispatch_service 通过 blackboard.query_by_proximity
  (center=task.center, radius_m=200, type_filter='survivor', min_confidence=0.8)
  得到数量再传进来；本模块零修改。这一注入模式与 P5.1 R8 active_assignments_count
  完全一致，是「调用方查询、引擎纯计算」的 N+1 安全设计。
"""
from __future__ import annotations

import math

from app.dispatch.rule_engine import (
    RobotEvalInput,
    TaskEvalInput,
    haversine_km,
)
from app.schemas.common import Position, RobotCapability
from app.schemas.dispatch import BidBreakdown, BidBreakdownComponent
from app.schemas.task import TaskRequiredCapabilities

# === 出价权重（BUSINESS_RULES §1.1 + §7 阈值表）===
W_DISTANCE = 0.40
W_BATTERY = 0.20
W_CAPABILITY = 0.30
W_LOAD = 0.10  # 注：进入 base_score 时取负号（−w₄·L）

# === 距离归一化阈值（BUSINESS_RULES §1.2.1）===
# 与 R7（rule_engine.py 中的 max_range_km）相互独立：R7 按机种 max_range 过滤；
# 而出价分数始终用固定 10 km 归一化（论文公式不变）。
DISTANCE_CAP_KM = 10.0

# === 电量底线（BUSINESS_RULES §1.2.2）===
# 进入此函数前已经过 R3 过滤（>= max(20, task.min_battery_pct)），但保留 <=20 → 0.0
# 兜底，与公式严格一致；不应在线上触发。
BATTERY_FLOOR_PCT = 20.0

# === 负载上限（BUSINESS_RULES §1.2.4 + §3.2 R8）===
MAX_LOAD = 3

# === 视觉加成（BUSINESS_RULES §1.3）===
VISION_BOOST_FACTOR = 1.5
# 以下两个常量供 dispatch_service 调 blackboard.query_by_proximity 时引用，
# 本模块只需要计数，不直接消费这俩；写在此处便于「公式与查询参数」同源审阅。
VISION_PROXIMITY_RADIUS_M = 200.0
VISION_CONFIDENCE_THRESHOLD = 0.8

# 出价分量字典的键名（写入 bids.breakdown.components / DATA_CONTRACTS §4.7）。
COMPONENT_DISTANCE = "distance"
COMPONENT_BATTERY = "battery"
COMPONENT_CAPABILITY = "capability"
COMPONENT_LOAD = "load"


# ---------- 5 个分量函数（BUSINESS_RULES §1.2 伪代码签名）----------


def compute_distance_score(robot_pos: Position, task_center: Position) -> float:
    """距离分量 D(r, t)。距离越近得分越高，线性归一化到 [0, 1]。

    BUSINESS_RULES §1.2.1：
    - 用 Haversine 球面距离（不是欧氏距离），单位 km。
    - 上限 10 km：dist >= 10.0 即 0；dist=0 即 1。
    - 不在此处做范围硬过滤（那是 R7 在 rule_engine 的事）。
    """
    dist_km = haversine_km(
        robot_pos.lat, robot_pos.lng, task_center.lat, task_center.lng
    )
    if dist_km >= DISTANCE_CAP_KM:
        return 0.0
    return 1.0 - (dist_km / DISTANCE_CAP_KM)


def compute_battery_score(battery_pct: float) -> float:
    """电量分量 B(r)。BUSINESS_RULES §1.2.2 的平方根函数。

    用 sqrt 而非线性，使 50% 比 25% 显著更优；25% 是 R3 下限，进入此函数的最小
    实际值是 21（含义：业务底线 20 < 实际 < 21 这个开区间已被 R3 排除）。
    battery_pct <= 20 时返回 0.0（公式兜底，线上不应触发）。
    """
    if battery_pct <= BATTERY_FLOOR_PCT:
        return 0.0
    return math.sqrt(battery_pct / 100.0)


def compute_capability_match(
    robot_capability: RobotCapability,
    task_required: TaskRequiredCapabilities,
) -> float:
    """能力匹配度 C(r, t)。BUSINESS_RULES §1.2.3。

    硬约束（必备 sensor / payload 缺失）由 R5/R6 在规则引擎过滤；本函数计算「软
    匹配度」=（命中 sensor 数 + 命中 payload 数）/（要求 sensor 数 + 要求 payload 数）。
    任务无能力要求时返回 1.0（默认满分），与 §1.2.3 注释一致。
    """
    required_sensors = set(task_required.sensors)
    required_payloads = set(task_required.payloads)
    total_required = len(required_sensors) + len(required_payloads)
    if total_required == 0:
        return 1.0
    has_sensors = set(robot_capability.sensors)
    has_payloads = set(robot_capability.payloads)
    matched = len(required_sensors & has_sensors) + len(required_payloads & has_payloads)
    return matched / total_required


def compute_load_score(current_active_assignments: int) -> float:
    """负载分量 L(r)。BUSINESS_RULES §1.2.4。

    `current_active_assignments` 来自 `task_assignments WHERE robot_id=r AND
    is_active=TRUE` 的计数（由调用方提供，本模块不查库）。
    L(r) = min(count / MAX_LOAD, 1.0)；L 越大代表越忙，进入 base_score 时取负权
    `-w₄·L`，因此 L 越大 base_score 越小（惩罚）。
    """
    if current_active_assignments <= 0:
        return 0.0
    return min(current_active_assignments / MAX_LOAD, 1.0)


def compute_vision_boost(has_yolo: bool, nearby_survivor_count: int) -> float:
    """视觉加成 vision_boost(r, t)。BUSINESS_RULES §1.3。

    决策规则：
    - 仅 has_yolo=True 的机器人享受加成（设计理由：有视觉能力的机器人，在已识别
      幸存者的区域有更强适配性；这是论文核心创新点）；
    - 任务目标区域附近 < 200 m 内若存在 conf ≥ 0.8 的幸存者条目（黑板查询结果由
      调用方传入 nearby_survivor_count），则返回 1.5；否则返回 1.0。

    `nearby_survivor_count` 由 dispatch_service 在 P5.4 / P6.1 联通后通过
    `blackboard.query_by_proximity(center=task.center, radius_m=200,
    type_filter='survivor', min_confidence=0.8)` 得到。当前 P5.2 阶段 Blackboard
    尚未实现，本参数默认 0（无加成），与 has_yolo=False 表现一致。
    """
    if not has_yolo:
        return 1.0
    if nearby_survivor_count > 0:
        return VISION_BOOST_FACTOR
    return 1.0


# ---------- 主入口 ----------


def compute_full_bid(
    robot: RobotEvalInput,
    task: TaskEvalInput,
    *,
    nearby_survivor_count: int = 0,
) -> BidBreakdown:
    """计算单个 (robot, task) 对的完整出价并返回审计 BidBreakdown。

    参数:
        robot / task: 与 P5.1 RuleEngine 同款冻结 dataclass 视图（dispatch_service
            将合并 robots 表 + agent 快照 + task_assignments active 计数后构造）。
        nearby_survivor_count: 任务区域 200 m 内 conf≥0.8 幸存者数量（黑板查询结
            果，由调用方注入；P5.4 之前 / 无黑板时传 0）。

    返回:
        BidBreakdown:
        - base_score = w₁·D + w₂·B + w₃·C − w₄·L
        - components = {distance, battery, capability, load} 四条，每条带原始 value
          与加权后值 weighted（distance/battery/capability 取 +w，load 取 -w₄）
        - vision_boosted: True 当且仅当本次实际享受 1.5 倍加成
        - final_bid = base_score × vision_boost

    本函数纯计算，零 IO；不修改输入 dataclass。
    """
    distance_value = compute_distance_score(
        robot.position, task.target_area.center_point
    )
    battery_value = compute_battery_score(robot.battery)
    capability_value = compute_capability_match(
        robot.capability, task.required_capabilities
    )
    load_value = compute_load_score(robot.active_assignments_count)

    distance_weighted = W_DISTANCE * distance_value
    battery_weighted = W_BATTERY * battery_value
    capability_weighted = W_CAPABILITY * capability_value
    # 负载是惩罚项：写入 weighted 时取负号（−w₄·L），加总时直接相加即可。
    load_weighted = -W_LOAD * load_value

    base_score = (
        distance_weighted + battery_weighted + capability_weighted + load_weighted
    )

    boost = compute_vision_boost(robot.capability.has_yolo, nearby_survivor_count)
    vision_boosted = boost > 1.0
    final_bid = base_score * boost

    return BidBreakdown(
        base_score=base_score,
        components={
            COMPONENT_DISTANCE: BidBreakdownComponent(
                value=distance_value, weighted=distance_weighted
            ),
            COMPONENT_BATTERY: BidBreakdownComponent(
                value=battery_value, weighted=battery_weighted
            ),
            COMPONENT_CAPABILITY: BidBreakdownComponent(
                value=capability_value, weighted=capability_weighted
            ),
            COMPONENT_LOAD: BidBreakdownComponent(
                value=load_value, weighted=load_weighted
            ),
        },
        vision_boosted=vision_boosted,
        final_bid=final_bid,
    )
