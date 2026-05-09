"""调度算法单元测试 TC-1 ~ TC-10（对照 ALGORITHM_TESTCASES.md §2）。

测试结构（贯穿所有 TC）：
  1. RuleEngine.filter(robots, task) → eligible 列表 + filter_stats
  2. compute_full_bid(robot, task, nearby_survivor_count=...) for r in eligible
  3. algo.solve(eligible, [task], bids) → 分配字典

这个模式严格按 P5.4 dispatch_service.start_auction 内部流水线，但脱掉 DB / 事务 /
WS 层；纯函数行为可在 ms 级跑完。
"""
from __future__ import annotations

import time
import uuid
from statistics import pstdev

import pytest

from app.dispatch.algorithms import (
    GreedyAuction,
    HungarianAuction,
)
from app.dispatch.bidding import VISION_BOOST_FACTOR, compute_full_bid
from app.dispatch.rule_engine import RobotEvalInput, RuleEngine, TaskEvalInput
from app.schemas.dispatch import BidBreakdown, BidBreakdownComponent
from tests.algorithms.conftest import (
    by_code,
    generate_robot,
    generate_task,
)


def _bids_for(
    eligible: list[RobotEvalInput],
    task: TaskEvalInput,
    *,
    survivor_count: int = 0,
) -> dict[tuple[uuid.UUID, uuid.UUID], BidBreakdown]:
    """对每个合格 robot 计算 (r, t) → BidBreakdown 字典。"""
    return {
        (r.id, task.id): compute_full_bid(
            r, task, nearby_survivor_count=survivor_count
        )
        for r in eligible
    }


def _bb_only(bids: dict, code: str, robots: list[RobotEvalInput]) -> BidBreakdown:
    return bids[(by_code(robots, code).id, next(iter(bids))[1])]


# ============================== TC-1 ==============================


def test_tc1_basic_hungarian_single_candidate(base_robots, empty_blackboard):
    """TC-1：1 任务 1 候选，UAV-001 满电应胜出。"""
    robots = [by_code(base_robots, "UAV-001")]
    task = TaskEvalInput.__class__  # placeholder for type checkers
    from tests.algorithms.conftest import _t  # type: ignore[attr-defined]

    task = _t(
        code="T-001",
        sensors=["camera_4k"],
        payloads=[],
        min_battery_pct=20,
        center_lat=30.205,
        center_lng=120.505,
    )

    eligible, stats = RuleEngine().filter(robots, task)
    assert len(eligible) == 1
    assert stats == {}
    bids = _bids_for(eligible, task, survivor_count=empty_blackboard)
    assignments = HungarianAuction().solve(eligible, [task], bids)

    assert assignments == {task.id: by_code(base_robots, "UAV-001").id}
    bid = bids[(by_code(base_robots, "UAV-001").id, task.id)]
    assert bid.final_bid > 0
    assert bid.vision_boosted is False
    assert 0.4 <= bid.final_bid <= 0.95  # ALGORITHM_TESTCASES §TC-1 范围


# ============================== TC-2 ==============================


def test_tc2_rule_engine_low_battery_filter(base_robots):
    """TC-2：USV-001(15%) 唯一有 sonar 但被 R3 过滤 → 拍卖整体无 eligible。"""
    from tests.algorithms.conftest import _t  # type: ignore[attr-defined]

    task = _t(
        code="T-002",
        sensors=["sonar"],
        payloads=["winch"],
        min_battery_pct=20,
        center_lat=30.30,
        center_lng=120.60,
        priority=1,
        area_km2=2.0,
    )

    eligible, stats = RuleEngine().filter(base_robots, task)
    assert eligible == []
    # USV-001 → low_battery；UAV-001 / UAV-002 / UGV-001 → missing_sensor
    assert stats.get("low_battery") == 1
    assert stats.get("missing_sensor") == 3
    # 这是 dispatch_service._fail_no_eligible 路径：写 FAILED + auction.failed
    assignments = HungarianAuction().solve(eligible, [task], {})
    assert assignments == {}


# ============================== TC-3 ==============================


def test_tc3_rule_engine_capability_filter(base_robots):
    """TC-3：要求 rescue_kit payload，仅 UGV-001 满足。"""
    from tests.algorithms.conftest import _t  # type: ignore[attr-defined]

    task = _t(
        code="T-003",
        sensors=["camera_4k"],
        payloads=["rescue_kit"],
        min_battery_pct=30,
        center_lat=30.21,
        center_lng=120.51,
    )

    eligible, stats = RuleEngine().filter(base_robots, task)
    assert len(eligible) == 1
    assert by_code(eligible, "UGV-001").id == eligible[0].id
    # missing_payload 命中 UAV-001 / UAV-002（电量足、UAV-002 sensor 不缺，但 payload 缺）；
    # USV-001 在 R3 / R5 / R6 任一阶段先被命中（短路），命中 low_battery（R3 早于 R5/R6）。
    assert stats.get("missing_payload") == 2
    assert stats.get("low_battery") == 1

    bids = _bids_for(eligible, task)
    assignments = HungarianAuction().solve(eligible, [task], bids)
    assert assignments == {task.id: by_code(base_robots, "UGV-001").id}
    assert len(bids) == 1


# ============================== TC-4 ==============================


def test_tc4_distance_weight(base_robots, empty_blackboard):
    """TC-4：两 UAV 能力一致，距离近的胜出，bid 差距来自 distance 分量。"""
    from tests.algorithms.conftest import _t  # type: ignore[attr-defined]

    robots = [by_code(base_robots, "UAV-001"), by_code(base_robots, "UAV-002")]
    task = _t(
        code="T-004",
        sensors=["camera_4k"],
        payloads=[],
        center_lat=30.205,
        center_lng=120.505,
        radius_m=200.0,
    )

    eligible, _ = RuleEngine().filter(robots, task)
    assert len(eligible) == 2
    bids = _bids_for(eligible, task, survivor_count=empty_blackboard)
    assignments = HungarianAuction().solve(eligible, [task], bids)
    assert assignments[task.id] == by_code(base_robots, "UAV-001").id

    bid_uav1 = bids[(by_code(base_robots, "UAV-001").id, task.id)]
    bid_uav2 = bids[(by_code(base_robots, "UAV-002").id, task.id)]
    assert bid_uav1.final_bid > bid_uav2.final_bid
    # 距离分量是差距主要来源
    assert (
        bid_uav1.components["distance"].weighted
        > bid_uav2.components["distance"].weighted
    )


# ============================== TC-5（论文核心） ==============================


def test_tc5_vision_boost_triggers(base_robots, blackboard_with_survivor):
    """TC-5：UAV-001(has_yolo=True) 在幸存者区域附近，出价被 1.5 倍加成。"""
    from tests.algorithms.conftest import _t  # type: ignore[attr-defined]

    robots = [by_code(base_robots, "UAV-001")]
    task = _t(
        code="T-005",
        sensors=["camera_4k"],
        payloads=[],
        center_lat=30.21,
        center_lng=120.51,
        radius_m=200.0,
        priority=1,
    )

    eligible, _ = RuleEngine().filter(robots, task)
    bids = _bids_for(eligible, task, survivor_count=blackboard_with_survivor)
    assignments = HungarianAuction().solve(eligible, [task], bids)
    assert assignments == {task.id: by_code(base_robots, "UAV-001").id}

    bid = bids[(by_code(base_robots, "UAV-001").id, task.id)]
    assert bid.vision_boosted is True
    assert bid.final_bid == pytest.approx(
        bid.base_score * VISION_BOOST_FACTOR, abs=1e-6
    )


# ============================== TC-6 ==============================


def test_tc6_vision_boost_no_yolo(base_robots, blackboard_with_survivor):
    """TC-6：UGV-001(has_yolo=False) 同位置不享受加成；UAV-001 享受。"""
    from tests.algorithms.conftest import _t  # type: ignore[attr-defined]

    robots = [by_code(base_robots, "UAV-001"), by_code(base_robots, "UGV-001")]
    task = _t(
        code="T-006",
        sensors=["camera_4k"],
        payloads=[],
        center_lat=30.21,
        center_lng=120.51,
    )

    eligible, _ = RuleEngine().filter(robots, task)
    bids = _bids_for(eligible, task, survivor_count=blackboard_with_survivor)

    bid_uav = bids[(by_code(base_robots, "UAV-001").id, task.id)]
    bid_ugv = bids[(by_code(base_robots, "UGV-001").id, task.id)]
    assert bid_uav.vision_boosted is True
    assert bid_ugv.vision_boosted is False

    # 由于 UAV 拿到 1.5x 加成，预期最终中标
    assignments = HungarianAuction().solve(eligible, [task], bids)
    assert assignments[task.id] == by_code(base_robots, "UAV-001").id


# ============================== TC-7 ==============================


def _fake_bid(value: float) -> BidBreakdown:
    """构造一个任意 final_bid 值的 BidBreakdown（其他字段填占位），用于 mock 出价矩阵。"""
    z = BidBreakdownComponent(value=0.0, weighted=0.0)
    return BidBreakdown(
        base_score=value,
        components={"distance": z, "battery": z, "capability": z, "load": z},
        vision_boosted=False,
        final_bid=value,
    )


def test_tc7_hungarian_vs_greedy_global_optimum():
    """TC-7：mock 出价矩阵下 Hungarian 全局最优(28) > Greedy 局部解(22)。

    出价矩阵：
                r1   r2   r3
        t1     10    9    1
        t2      9    2    1
        t3      1    1   10
    Hungarian → t1=r2(9), t2=r1(9), t3=r3(10) = 28（最优）
    Greedy(t1→t2→t3) → t1=r1(10), t2=r2(2), t3=r3(10) = 22
    """
    from tests.algorithms.conftest import _r, _t  # type: ignore[attr-defined]

    r1 = _r(code="R-T7-1", type_="uav", sensors=["camera_4k"], payloads=[],
            max_speed_mps=20, max_battery_min=50, max_range_km=8.0,
            has_yolo=True, weight_kg=6.0, lat=30.20, lng=120.50, battery=80.0)
    r2 = _r(code="R-T7-2", type_="uav", sensors=["camera_4k"], payloads=[],
            max_speed_mps=20, max_battery_min=50, max_range_km=8.0,
            has_yolo=True, weight_kg=6.0, lat=30.20, lng=120.50, battery=80.0)
    r3 = _r(code="R-T7-3", type_="uav", sensors=["camera_4k"], payloads=[],
            max_speed_mps=20, max_battery_min=50, max_range_km=8.0,
            has_yolo=True, weight_kg=6.0, lat=30.20, lng=120.50, battery=80.0)
    robots = [r1, r2, r3]

    t1 = _t(code="T-T7-1", sensors=["camera_4k"], center_lat=30.20, center_lng=120.50, priority=1)
    t2 = _t(code="T-T7-2", sensors=["camera_4k"], center_lat=30.20, center_lng=120.50, priority=2)
    t3 = _t(code="T-T7-3", sensors=["camera_4k"], center_lat=30.20, center_lng=120.50, priority=3)
    tasks = [t1, t2, t3]

    bid_matrix = {
        (r1.id, t1.id): _fake_bid(10), (r2.id, t1.id): _fake_bid(9),  (r3.id, t1.id): _fake_bid(1),
        (r1.id, t2.id): _fake_bid(9),  (r2.id, t2.id): _fake_bid(2),  (r3.id, t2.id): _fake_bid(1),
        (r1.id, t3.id): _fake_bid(1),  (r2.id, t3.id): _fake_bid(1),  (r3.id, t3.id): _fake_bid(10),
    }

    h_result = HungarianAuction().solve(robots, tasks, bid_matrix)
    g_result = GreedyAuction().solve(robots, tasks, bid_matrix)

    h_total = sum(bid_matrix[(rid, tid)].final_bid for tid, rid in h_result.items())
    g_total = sum(bid_matrix[(rid, tid)].final_bid for tid, rid in g_result.items())

    assert h_total == 28
    assert g_total == 22
    assert h_total > g_total
    assert h_result != g_result
    # 字面期望：Hungarian {t1:r2, t2:r1, t3:r3}
    assert h_result == {t1.id: r2.id, t2.id: r1.id, t3.id: r3.id}
    # Greedy 按 priority 升序处理 → {t1:r1, t2:r2, t3:r3}
    assert g_result == {t1.id: r1.id, t2.id: r2.id, t3.id: r3.id}


# ============================== TC-8 ==============================


def test_tc8_auction_failed_no_eligible():
    """TC-8：所有机器人电量 <20，全部被 R3 过滤 → 无 eligible。"""
    from tests.algorithms.conftest import _r, _t  # type: ignore[attr-defined]

    robots = [
        _r(code="UAV-T8-1", type_="uav", sensors=["camera_4k"], payloads=[],
           max_speed_mps=20, max_battery_min=50, max_range_km=8.0,
           has_yolo=True, weight_kg=6.0, lat=30.20, lng=120.50, battery=10.0),
        _r(code="UAV-T8-2", type_="uav", sensors=["camera_4k"], payloads=[],
           max_speed_mps=20, max_battery_min=50, max_range_km=8.0,
           has_yolo=True, weight_kg=6.0, lat=30.20, lng=120.50, battery=15.0),
        _r(code="UAV-T8-3", type_="uav", sensors=["camera_4k"], payloads=[],
           max_speed_mps=20, max_battery_min=50, max_range_km=8.0,
           has_yolo=True, weight_kg=6.0, lat=30.20, lng=120.50, battery=18.0),
    ]
    task = _t(code="T-T8-001", sensors=["camera_4k"], center_lat=30.20, center_lng=120.50)

    eligible, stats = RuleEngine().filter(robots, task)
    assert eligible == []
    assert stats.get("low_battery") == 3
    # 算法返回空 → dispatch_service 进 _fail_no_eligible 分支（auction.status=FAILED）
    assert HungarianAuction().solve(eligible, [task], {}) == {}


# ============================== TC-9 ==============================


def test_tc9_load_balance_hungarian_vs_greedy():
    """TC-9：8 任务 × 8 机器人，Hungarian 负载标准差 ≤ Greedy。

    具体值受出价分布影响（generate_robot/task 网格化均匀），重点验大小关系；
    论文报告的 1.21 vs 3.84 是平均结果，单次可能波动 → 用 ≤（含等号）。
    """
    robots = [generate_robot(i) for i in range(8)]
    tasks = [generate_task(i) for i in range(8)]

    eligible, _ = RuleEngine().filter(robots, tasks[0])
    # generate_robot/task 网格内距离都在 R7 内，全部 eligible
    assert len(eligible) == 8

    # 全任务全机器人的 bids 矩阵（只在 8×8 之间，所有 (r,t) 都计算）
    bids: dict[tuple[uuid.UUID, uuid.UUID], BidBreakdown] = {}
    for r in robots:
        for t in tasks:
            bids[(r.id, t.id)] = compute_full_bid(r, t, nearby_survivor_count=0)

    h_result = HungarianAuction().solve(robots, tasks, bids)
    g_result = GreedyAuction().solve(robots, tasks, bids)

    def _load_per_robot(result: dict) -> list[int]:
        load = {r.id: 0 for r in robots}
        for rid in result.values():
            load[rid] = load.get(rid, 0) + 1
        return list(load.values())

    h_std = pstdev(_load_per_robot(h_result))
    g_std = pstdev(_load_per_robot(g_result))
    # 在 8 任务 8 机器人下，Hungarian 是双向匹配（每机器人最多 1 任务），
    # 负载分布最理想 = 全 1（std=0）；Greedy 在某些 bids 分布下会让一两个机器人
    # 拿多个任务（不重用机器人在我们 P5.3 实现里其实已经做了——每 task 不重复
    # 选机器人）。所以两者大概率都接近最优；这里用 ≤ 容许相等。
    assert h_std <= g_std


# ============================== TC-10 ==============================


def test_tc10_decision_latency_25x10():
    """TC-10：25 机器人 × 10 任务，Hungarian 决策延迟 < 2000 ms。"""
    robots = [generate_robot(i) for i in range(25)]
    tasks = [generate_task(i) for i in range(10)]

    bids: dict[tuple[uuid.UUID, uuid.UUID], BidBreakdown] = {}
    for r in robots:
        for t in tasks:
            bids[(r.id, t.id)] = compute_full_bid(r, t, nearby_survivor_count=0)

    start = time.perf_counter()
    result = HungarianAuction().solve(robots, tasks, bids)
    latency_ms = (time.perf_counter() - start) * 1000

    assert latency_ms < 2000.0, f"Hungarian latency {latency_ms:.1f} ms ≥ 2000 ms"
    # 任务数 ≤ 机器人数，所有任务都应被分配
    assert len(result) == 10
