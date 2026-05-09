"""调度算法测试夹具（对照 ALGORITHM_TESTCASES.md §0.2）。

设计取舍：
- 直接构造 RuleEngine / 算法所需的视图 dataclass（RobotEvalInput / TaskEvalInput），
  而不是构造 ORM Robot / Task —— TC-1~TC-10 是纯函数测试，不需要 DB。
- 为方便测试断言追踪某个机器人，给 RobotEvalInput 包一层带 `code` 的 namedtuple
  风格映射；fixture 返回 (robot_view, code) 列表，测试用 by_code(...) 取。
- "blackboard" 在 P5 阶段还没建（属于 P6.1）；本文件按 BUILD_ORDER 现状用
  `nearby_survivor_count`（int）模拟黑板查询结果，与 compute_full_bid 入参对齐。
"""
from __future__ import annotations

import uuid

import pytest

from app.dispatch.rule_engine import RobotEvalInput, TaskEvalInput
from app.schemas.common import Position, RobotCapability
from app.schemas.task import TargetArea, TaskRequiredCapabilities


# ---------- 助手 ----------


def _r(
    *,
    code: str,
    type_: str,
    sensors: list[str],
    payloads: list[str],
    max_speed_mps: float,
    max_battery_min: int,
    max_range_km: float,
    has_yolo: bool,
    weight_kg: float,
    lat: float,
    lng: float,
    battery: float,
    fsm_state: str = "IDLE",
    is_active: bool = True,
    active_count: int = 0,
) -> RobotEvalInput:
    """构造一个 RobotEvalInput；id 用 UUID5 from code，保证测试稳定可读。"""
    cap = RobotCapability(
        sensors=sensors,
        payloads=payloads,
        max_speed_mps=max_speed_mps,
        max_battery_min=max_battery_min,
        max_range_km=max_range_km,
        has_yolo=has_yolo,
        weight_kg=weight_kg,
    )
    return RobotEvalInput(
        id=uuid.uuid5(uuid.NAMESPACE_DNS, f"robot:{code}"),
        is_active=is_active,
        type=type_,  # type: ignore[arg-type]
        fsm_state=fsm_state,  # type: ignore[arg-type]
        battery=battery,
        position=Position(lat=lat, lng=lng),
        capability=cap,
        active_assignments_count=active_count,
    )


def _t(
    *,
    code: str,
    sensors: list[str] | None = None,
    payloads: list[str] | None = None,
    min_battery_pct: float = 20.0,
    robot_type: list[str] | None = None,
    center_lat: float,
    center_lng: float,
    radius_m: float = 200.0,
    area_km2: float = 0.13,
    priority: int = 2,
) -> TaskEvalInput:
    """构造一个 TaskEvalInput（默认 circle 区域）。"""
    center = Position(lat=center_lat, lng=center_lng)
    target_area = TargetArea(
        type="circle",
        bounds=None,
        vertices=None,
        center=center,
        radius_m=radius_m,
        area_km2=area_km2,
        center_point=center,
    )
    required = TaskRequiredCapabilities(
        sensors=sensors or [],
        payloads=payloads or [],
        min_battery_pct=min_battery_pct,
        robot_type=robot_type,  # type: ignore[arg-type]
    )
    return TaskEvalInput(
        id=uuid.uuid5(uuid.NAMESPACE_DNS, f"task:{code}"),
        required_capabilities=required,
        target_area=target_area,
        priority=priority,
    )


def by_code(views: list[RobotEvalInput], code: str) -> RobotEvalInput:
    """从 views 列表里按 code 找回 RobotEvalInput；测试断言用。"""
    target = uuid.uuid5(uuid.NAMESPACE_DNS, f"robot:{code}")
    for v in views:
        if v.id == target:
            return v
    raise KeyError(f"no robot view with code {code!r}")


# ---------- fixtures（ALGORITHM_TESTCASES §0.2 字面） ----------


@pytest.fixture
def base_robots() -> list[RobotEvalInput]:
    """4 台机器人，覆盖 uav / ugv / usv 三种类型 + USV 电量不足。"""
    return [
        _r(
            code="UAV-001",
            type_="uav",
            sensors=["camera_4k", "thermal"],
            payloads=[],
            max_speed_mps=23.0,
            max_battery_min=55,
            max_range_km=8.0,
            has_yolo=True,
            weight_kg=6.3,
            lat=30.20,
            lng=120.50,
            battery=80.0,
        ),
        _r(
            code="UAV-002",
            type_="uav",
            sensors=["camera_4k"],
            payloads=[],
            max_speed_mps=20.0,
            max_battery_min=45,
            max_range_km=6.0,
            has_yolo=True,
            weight_kg=5.8,
            lat=30.22,
            lng=120.52,
            battery=60.0,
        ),
        _r(
            code="UGV-001",
            type_="ugv",
            sensors=["camera_4k", "lidar"],
            payloads=["rescue_kit"],
            max_speed_mps=5.0,
            max_battery_min=120,
            max_range_km=4.0,
            has_yolo=False,
            weight_kg=180,
            lat=30.21,
            lng=120.51,
            battery=92.0,
        ),
        _r(
            code="USV-001",
            type_="usv",
            sensors=["sonar"],
            payloads=["winch"],
            max_speed_mps=8.0,
            max_battery_min=180,
            max_range_km=10.0,
            has_yolo=False,
            weight_kg=350,
            lat=30.30,
            lng=120.60,
            battery=15.0,  # < 20，被 R3 过滤
        ),
    ]


@pytest.fixture
def empty_blackboard() -> int:
    """空黑板：nearby_survivor_count=0，不触发视觉加成。"""
    return 0


@pytest.fixture
def blackboard_with_survivor() -> int:
    """黑板有高置信度幸存者：count >= 1 即触发 vision_boost（has_yolo=True 时）。"""
    return 1


# ---------- generators（ALGORITHM_TESTCASES §4） ----------


def generate_robot(i: int) -> RobotEvalInput:
    """生成第 i 个 UAV 测试机器人（5×5 网格分布，能力一致）。

    与 ALGORITHM_TESTCASES.md §4.1 对应；位置散布在 (30.20+0~0.04, 120.50+0~0.04)
    的 0.04°×0.04° 区域内（约 4×4 km），与生成的 task 区域吻合。
    """
    return _r(
        code=f"UAV-{i + 1:03d}",
        type_="uav",
        sensors=["camera_4k", "thermal"],
        payloads=[],
        max_speed_mps=20.0,
        max_battery_min=50,
        max_range_km=8.0,
        has_yolo=True,
        weight_kg=6.0,
        lat=30.20 + (i % 5) * 0.01,
        lng=120.50 + (i // 5) * 0.01,
        battery=80.0,
    )


def generate_task(i: int) -> TaskEvalInput:
    """生成第 i 个测试任务（与 generate_robot 网格对齐）。"""
    return _t(
        code=f"T-{i + 1:03d}",
        sensors=["camera_4k"],
        center_lat=30.20 + (i % 5) * 0.015,
        center_lng=120.50 + (i // 5) * 0.015,
        radius_m=200.0,
        area_km2=0.13,
        priority=2,
    )


__all__ = [
    "base_robots",
    "blackboard_with_survivor",
    "by_code",
    "empty_blackboard",
    "generate_robot",
    "generate_task",
]
