# ALGORITHM_TESTCASES.md — 调度算法测试用例

> **文档定位**:本文档定义调度算法的"输入 → 期望输出"测试用例,用于:
> 1. 让 Claude Code 在写完算法后**立即用这些用例验证**
> 2. 编写 pytest 单元测试时直接使用
> 3. 论文实验前的 sanity check
>
> **依赖**:`BUSINESS_RULES.md`(算法定义)、`DATA_CONTRACTS.md`(数据结构)
> **版本**:v1.0

---

## 0. 测试组织约定

### 0.1 测试文件位置
建议放在 `backend/tests/algorithms/test_dispatch.py`,每个 case 一个 `def test_xxx`。

### 0.2 测试数据夹具(fixtures)
所有 case 共享一组基础夹具,定义在文件顶部:

```python
@pytest.fixture
def base_robots():
    """4 台机器人,覆盖三种类型"""
    return [
        Robot(
            id="r1", code="UAV-001", type="uav",
            capability=RobotCapability(
                sensors=["camera_4k", "thermal"],
                payloads=[],
                max_speed_mps=23, max_battery_min=55,
                max_range_km=8.0, has_yolo=True,
                weight_kg=6.3
            ),
            position=Position(lat=30.20, lng=120.50),
            battery=80.0, fsm_state="IDLE", is_active=True
        ),
        Robot(
            id="r2", code="UAV-002", type="uav",
            capability=RobotCapability(
                sensors=["camera_4k"],
                payloads=[], max_speed_mps=20, max_battery_min=45,
                max_range_km=6.0, has_yolo=True, weight_kg=5.8
            ),
            position=Position(lat=30.22, lng=120.52),
            battery=60.0, fsm_state="IDLE", is_active=True
        ),
        Robot(
            id="r3", code="UGV-001", type="ugv",
            capability=RobotCapability(
                sensors=["camera_4k", "lidar"],
                payloads=["rescue_kit"],
                max_speed_mps=5, max_battery_min=120,
                max_range_km=4.0, has_yolo=False, weight_kg=180
            ),
            position=Position(lat=30.21, lng=120.51),
            battery=92.0, fsm_state="IDLE", is_active=True
        ),
        Robot(
            id="r4", code="USV-001", type="usv",
            capability=RobotCapability(
                sensors=["sonar"],
                payloads=["winch"], max_speed_mps=8, max_battery_min=180,
                max_range_km=10.0, has_yolo=False, weight_kg=350
            ),
            position=Position(lat=30.30, lng=120.60),
            battery=15.0, fsm_state="IDLE", is_active=True   # 电量不足
        ),
    ]


@pytest.fixture
def empty_blackboard():
    """空黑板,不触发视觉加成"""
    return Blackboard()


@pytest.fixture
def blackboard_with_survivor():
    """黑板有高置信度幸存者条目"""
    bb = Blackboard()
    bb.set(
        key="survivor:120.51_30.21",
        value={"type": "survivor", "position": {"lat": 30.21, "lng": 120.51}},
        confidence=0.92,
        source_robot_id="r1"
    )
    return bb
```

---

## 1. 测试用例清单(共 10 组)

| # | 用例名 | 目标 | 难度 |
|---|---|---|---|
| TC-1 | 基础匈牙利:1 任务 1 候选 | 验证最简单情况下能正确分配 | ⭐ |
| TC-2 | 规则引擎电量过滤 | 电量不足的机器人被过滤 | ⭐⭐ |
| TC-3 | 规则引擎能力过滤 | 缺少必需传感器/载荷的被过滤 | ⭐⭐ |
| TC-4 | 距离权重生效 | 距离近的机器人胜出 | ⭐⭐ |
| TC-5 | 视觉加成 1.5x 触发 | 高置信度幸存者区域,UAV 出价被加成 | ⭐⭐⭐ |
| TC-6 | 视觉加成不对无 YOLO 机器人生效 | UGV/USV 即使在区域附近也不享受加成 | ⭐⭐⭐ |
| TC-7 | 多任务多机器人:Hungarian 全局最优 | 验证算法找到全局最优,而非贪心局部最优 | ⭐⭐⭐⭐ |
| TC-8 | 拍卖失败:无合格机器人 | 所有机器人都不通过规则引擎 | ⭐⭐ |
| TC-9 | Hungarian vs Greedy:负载均衡对比 | 同一输入下,Hungarian 负载更均衡 | ⭐⭐⭐⭐ |
| TC-10 | 决策延迟测试:25 机器人 × 10 任务 | 决策延迟必须 < 2000ms | ⭐⭐ |

---

## 2. 详细用例

### TC-1:基础匈牙利,1 任务 1 候选

**目标**:验证最简单情况下,合格的唯一候选机器人被分配。

**输入**
```python
robots = [base_robots[0]]  # UAV-001 满电(80%)
task = Task(
    id="t1", code="T-001",
    type="search_rescue", priority=2,
    target_area=TargetArea(
        type="rectangle",
        bounds={"sw": {"lat": 30.20, "lng": 120.50}, "ne": {"lat": 30.21, "lng": 120.51}},
        area_km2=1.0,
        center_point=Position(lat=30.205, lng=120.505)
    ),
    required_capabilities=TaskRequiredCapabilities(
        sensors=["camera_4k"], payloads=[], min_battery_pct=20
    ),
    status="PENDING"
)
algorithm = "AUCTION_HUNGARIAN"
blackboard = empty_blackboard
```

**期望输出**
```python
{
    "assignments": {"t1": "r1"},
    "auction": {
        "status": "CLOSED",
        "winner_robot_id": "r1",
        "decision_latency_ms": "< 100",   # 单任务很快
    },
    "bids": [
        {
            "robot_id": "r1",
            "vision_boost": 1.0,    # 黑板空,无加成
            "breakdown.vision_boosted": False,
            "breakdown.final_bid": "约 0.6 ~ 0.8"   # 不要写死,验范围
        }
    ]
}
```

**断言要点**
- `assignments["t1"] == "r1"`
- `bids` 长度 = 1
- `bid_value > 0`
- `vision_boosted == False`

---

### TC-2:规则引擎电量过滤

**目标**:USV-001(15% 电量)被过滤,不出现在 bids 中。

**输入**
```python
robots = base_robots  # 包含 USV-001 电量 15%
task = Task(
    id="t2", code="T-002", type="search_rescue", priority=1,
    target_area=TargetArea(
        type="rectangle",
        bounds={"sw": {"lat": 30.29, "lng": 120.59}, "ne": {"lat": 30.31, "lng": 120.61}},
        area_km2=2.0,
        center_point=Position(lat=30.30, lng=120.60)
    ),
    required_capabilities=TaskRequiredCapabilities(
        sensors=["sonar"],   # 只有 USV 有
        payloads=["winch"],
        min_battery_pct=20
    ),
)
```

**期望输出**
```python
{
    "auction.status": "FAILED",   # USV 电量不足,无其他候选
    "auction.reason": "no_eligible_robot",
    "filter_stats": {
        "low_battery": 1,        # USV-001
        "missing_sensor": 3,     # 其他三台无 sonar
    }
}
```

**断言要点**
- 拍卖状态 FAILED
- WS 事件 `auction.failed` 被推送
- 无 bids 写入

---

### TC-3:规则引擎能力过滤

**目标**:任务要求 `payloads=["rescue_kit"]`,只有 UGV-001 满足,验证其他机器人被过滤。

**输入**
```python
robots = base_robots
task = Task(
    id="t3", code="T-003", type="search_rescue", priority=2,
    target_area=TargetArea(
        type="circle",
        center=Position(lat=30.21, lng=120.51), radius_m=300,
        area_km2=0.28,
        center_point=Position(lat=30.21, lng=120.51)
    ),
    required_capabilities=TaskRequiredCapabilities(
        sensors=["camera_4k"],
        payloads=["rescue_kit"],   # 只有 UGV-001 有
        min_battery_pct=30
    ),
)
```

**期望输出**
```python
{
    "assignments": {"t3": "r3"},  # 只有 UGV-001 合格
    "bids": [{"robot_id": "r3", ...}],   # 只 1 条 bid
    "filter_stats": {
        "missing_payload": 2,   # UAV-001, UAV-002
        "low_battery": 1        # USV-001
    }
}
```

---

### TC-4:距离权重生效

**目标**:两个能力相同的 UAV,距离任务近的胜出。

**输入**
```python
robots = [base_robots[0], base_robots[1]]   # UAV-001 在 (30.20, 120.50), UAV-002 在 (30.22, 120.52)
task = Task(
    id="t4", code="T-004", type="search_rescue",
    target_area=TargetArea(
        type="circle",
        center=Position(lat=30.205, lng=120.505),  # 离 UAV-001 更近
        radius_m=200, area_km2=0.13,
        center_point=Position(lat=30.205, lng=120.505)
    ),
    required_capabilities=TaskRequiredCapabilities(sensors=["camera_4k"], payloads=[])
)
blackboard = empty_blackboard   # 不触发视觉加成
```

**期望输出**
```python
{
    "assignments": {"t4": "r1"},   # UAV-001 胜出
    "bids": [
        {"robot_id": "r1", "bid_value": "X1"},
        {"robot_id": "r2", "bid_value": "X2"}
    ],
    "assertion": "X1 > X2"   # UAV-001 出价 > UAV-002
}
```

**断言要点**
- `winner == "r1"`
- `bid(r1) > bid(r2)` 严格大于
- 两者差距应主要来自距离分量(检查 `breakdown.components.distance.weighted`)

---

### TC-5:视觉加成 1.5x 触发(★ 论文核心)

**目标**:任务区域附近黑板有高置信度幸存者(0.92),UAV-001(has_yolo=True)的出价被乘以 1.5。

**输入**
```python
robots = [base_robots[0]]   # 只 UAV-001
task = Task(
    id="t5", code="T-005", type="search_rescue", priority=1,
    target_area=TargetArea(
        type="circle",
        center=Position(lat=30.21, lng=120.51),  # 与黑板幸存者同位置
        radius_m=200, area_km2=0.13,
        center_point=Position(lat=30.21, lng=120.51)
    ),
    required_capabilities=TaskRequiredCapabilities(sensors=["camera_4k"])
)
blackboard = blackboard_with_survivor   # key=survivor:120.51_30.21, conf=0.92
```

**期望输出**
```python
{
    "assignments": {"t5": "r1"},
    "bids": [{
        "robot_id": "r1",
        "vision_boost": 1.5,                       # ★ 关键
        "breakdown.vision_boosted": True,           # ★ 关键
        "breakdown.final_bid": "X * 1.5",          # ★ 关键
        # 即:final_bid == base_score * 1.5
    }]
}
```

**断言要点**
- `bids[0].vision_boost == 1.5`
- `bids[0].breakdown.vision_boosted is True`
- `final_bid == base_score * 1.5`(浮点精度容差 1e-6)
- 数据库 `bids.breakdown` JSONB 字段实际写入

**论文价值**:这个用例直接对应论文创新点 1。**必须通过**。

---

### TC-6:视觉加成不对无 YOLO 机器人生效

**目标**:同样位置同样幸存者,UGV-001(has_yolo=False)出价**不**被加成。

**输入**
```python
robots = [base_robots[0], base_robots[2]]   # UAV-001(has_yolo) + UGV-001(无)
task = Task(
    id="t6", code="T-006",
    target_area=TargetArea(
        type="circle",
        center=Position(lat=30.21, lng=120.51),
        radius_m=200, area_km2=0.13,
        center_point=Position(lat=30.21, lng=120.51)
    ),
    required_capabilities=TaskRequiredCapabilities(sensors=["camera_4k"])
)
blackboard = blackboard_with_survivor
```

**期望输出**
```python
{
    "bids": [
        {"robot_id": "r1", "vision_boost": 1.5, "breakdown.vision_boosted": True},   # UAV
        {"robot_id": "r3", "vision_boost": 1.0, "breakdown.vision_boosted": False}   # UGV
    ]
}
```

**断言要点**
- UAV-001 加成
- UGV-001 不加成
- 大概率 UAV 胜出(因为 1.5x)

---

### TC-7:多任务多机器人,Hungarian 全局最优

**目标**:在 3 个任务 + 3 个机器人的局面下,匈牙利能找到"局部最差,全局最优"的分配,与贪心算法形成对比。

**输入**
```python
# 构造一个 cost matrix(取负后):
# r1 r2 r3
# t1: -5  -3  -1
# t2: -4  -8  -2
# t3: -1  -2  -7
# 即:
# t1 给 r1 出价 5,给 r2 出价 3,给 r3 出价 1
# t2 给 r1 出价 4,给 r2 出价 8,给 r3 出价 2
# t3 给 r1 出价 1,给 r2 出价 2,给 r3 出价 7

# 贪心策略(按优先级 t1→t2→t3):
#   t1 选最高出价 r1 (=5)
#   t2 选最高出价 r2 (=8)
#   t3 选最高出价 r3 (=7)
#   总分 = 5 + 8 + 7 = 20

# 匈牙利同样得到此最优解,因为这是显然的对角线最优
# (此例中 Hungarian 与 Greedy 一致)

# === 真正区分两者的例子 ===
# 出价矩阵:
# r1 r2 r3
# t1: 10  9  1
# t2: 9   2  1
# t3: 1   1 10
#
# 贪心(按 t1→t2→t3):
#   t1 → r1 (10), 锁定 r1
#   t2 → r2 (2),  剩 r2,r3
#   t3 → r3 (10)
#   总 = 22, 但 t2 拿到的 bid 只有 2,负载差(t2 用得不好)
#
# 匈牙利:
#   t1 → r2 (9)
#   t2 → r1 (9)
#   t3 → r3 (10)
#   总 = 28, 全局更优
```

**实际构造**:用 `mock_compute_bid` monkey-patch 强制返回上述出价矩阵。

**期望输出**
```python
# 用 AUCTION_HUNGARIAN
hungarian_result = {"t1": "r2", "t2": "r1", "t3": "r3"}
hungarian_total = 9 + 9 + 10  # 28

# 用 GREEDY
greedy_result = {"t1": "r1", "t2": "r2", "t3": "r3"}
greedy_total = 10 + 2 + 10   # 22
```

**断言要点**
- `sum(hungarian_bids) > sum(greedy_bids)`
- `hungarian_result != greedy_result`(关键:能体现差异)

---

### TC-8:拍卖失败,无合格机器人

**目标**:所有机器人都不通过规则引擎,拍卖标记为 FAILED。

**输入**
```python
robots = [
    Robot(id="r1", battery=10.0, ...),  # 电量不足
    Robot(id="r2", battery=15.0, ...),  # 电量不足
    Robot(id="r3", battery=18.0, ...),  # 电量不足
]
task = Task(...)  # 标准任务
```

**期望输出**
```python
{
    "auction.status": "FAILED",
    "auction.reason": "no_eligible_robot",
    "WS event": "auction.failed",
    "task.status": "PENDING"   # 任务保持待分配
}
```

---

### TC-9:Hungarian vs Greedy 负载均衡对比

**目标**:在大规模场景下(8 任务 + 8 机器人),Hungarian 的负载标准差应小于 Greedy。

**输入**
```python
robots = [generate_robot(i) for i in range(8)]   # 8 台机器人,能力均匀
tasks = [generate_task(i) for i in range(8)]     # 8 个任务,均匀分布
```

**测试逻辑**
```python
def test_load_balance():
    # 用 Hungarian
    h_result = hungarian_solve(...)
    h_load = compute_load_per_robot(h_result)   # [1, 1, 1, 1, 1, 1, 1, 1] 理想
    h_std = np.std(h_load)

    # 用 Greedy
    g_result = greedy_solve(...)
    g_load = compute_load_per_robot(g_result)   # 可能 [3, 2, 2, 1, 0, 0, 0, 0]
    g_std = np.std(g_load)

    assert h_std < g_std, f"Hungarian 负载({h_std}) 应优于 Greedy({g_std})"
```

**期望输出**
- `Hungarian std < Greedy std`(具体值受随机性影响,只验大小关系)
- 论文声称的 1.21 vs 3.84 是平均结果,单次可能波动

---

### TC-10:决策延迟测试,25 机器人 × 10 任务

**目标**:验证大规模场景下,Hungarian 求解延迟仍在 2 秒内。

**输入**
```python
robots = [generate_robot(i) for i in range(25)]
tasks = [generate_task(i) for i in range(10)]
```

**测试**
```python
import time

def test_decision_latency():
    start = time.perf_counter()
    result = hungarian_solve(robots, tasks, blackboard)
    latency_ms = (time.perf_counter() - start) * 1000

    assert latency_ms < 2000, f"Hungarian 延迟 {latency_ms} 超过 2000ms"
    assert len(result) == 10   # 所有任务都分配
```

**期望输出**
- 延迟 ≈ 50~500 ms(不应超 2000)
- 决策准确性:每个任务都有分配

---

## 3. 集成测试(End-to-End)

### TC-E2E-1:完整任务生命周期

**步骤**
1. 创建任务(POST /tasks)→ 状态 PENDING
2. 自动触发拍卖 → WS 事件 `auction.started`
3. 拍卖完成 → WS 事件 `auction.completed` → 任务状态 ASSIGNED
4. 模拟机器人开始执行 → 状态 EXECUTING
5. 模拟进度上报 → progress 累积
6. progress = 100 → 状态 COMPLETED
7. 检查数据库:
   - `tasks` 终态正确
   - `auctions` 1 条
   - `bids` N 条
   - `task_assignments` 释放(`is_active=FALSE`,`released_at` 非空)

### TC-E2E-2:HITL 改派完整链路

1. 任务 ASSIGNED 状态
2. 调用 POST /dispatch/reassign + reason
3. 验证:
   - 旧 assignment `is_active=False`
   - 新 assignment 创建
   - `human_interventions` 写入,before/after 字段完整
   - WS 推送 `task.reassigned` + `intervention.recorded`(双事件)

### TC-E2E-3:YOLO 触发自动救援链路

1. Mock UAV-001 调用 `process_image`,返回 survivor 检测,conf=0.92
2. 验证:
   - 黑板写入 `survivor:xxx_yyy` 条目
   - WS 推送 `perception.detection` + `perception.high_confidence_alert`
   - 自动创建救援任务,priority=1
   - 触发拍卖,UAV-001 出价被加成 1.5x
   - UAV-001 中标

---

## 4. 测试数据生成器

### 4.1 generate_robot(i)

```python
def generate_robot(i: int) -> Robot:
    """生成第 i 个测试机器人(均匀分布,能力一致)"""
    return Robot(
        id=f"r{i+1}",
        code=f"UAV-{i+1:03d}",
        type="uav",
        capability=RobotCapability(
            sensors=["camera_4k", "thermal"],
            payloads=[],
            max_speed_mps=20, max_battery_min=50,
            max_range_km=8.0, has_yolo=True, weight_kg=6.0
        ),
        position=Position(
            lat=30.20 + (i % 5) * 0.01,
            lng=120.50 + (i // 5) * 0.01
        ),
        battery=80.0,
        fsm_state="IDLE",
        is_active=True
    )
```

### 4.2 generate_task(i)

```python
def generate_task(i: int) -> Task:
    return Task(
        id=f"t{i+1}",
        code=f"T-{i+1:03d}",
        type="search_rescue",
        priority=2,
        target_area=TargetArea(
            type="circle",
            center=Position(
                lat=30.20 + (i % 5) * 0.015,
                lng=120.50 + (i // 5) * 0.015
            ),
            radius_m=200,
            area_km2=0.13,
            center_point=Position(
                lat=30.20 + (i % 5) * 0.015,
                lng=120.50 + (i // 5) * 0.015
            )
        ),
        required_capabilities=TaskRequiredCapabilities(
            sensors=["camera_4k"], payloads=[], min_battery_pct=20
        ),
        status="PENDING"
    )
```

---

## 5. 测试运行约定

### 5.1 命令

```bash
# 全部跑
pytest backend/tests/algorithms/

# 只跑核心 5 个用例(快速验证)
pytest backend/tests/algorithms/ -k "TC-1 or TC-2 or TC-5 or TC-7 or TC-9"

# 含覆盖率
pytest --cov=app.dispatch backend/tests/algorithms/
```

### 5.2 必通过的最小集
开发到"调度模块基本可用"的里程碑时,**至少 TC-1, TC-2, TC-3, TC-4, TC-5, TC-8 必须通过**。
TC-7, TC-9, TC-10 可在论文实验前通过。

### 5.3 失败处理
任何用例失败,**不要修改用例数值**(用例是规约),应修复算法实现。
若你确信用例本身有问题,**停下来问我**。

---

## 6. 论文实验对接

论文 §5.2.3 报告的实验数据来自这些用例的"放大版":
- TC-9 → 实验图 5-4 负载均衡度对比
- TC-10 → 实验图 5-5 决策耗时对比
- TC-7 + TC-9 的多次运行 → 实验图 5-1 完成率对比

实验运行时:
- 每算法跑 10 次,取均值±标准差
- 共 60 次(2 场景 × 3 算法 × 10),写 `experiment_runs` 表
- 用 `/experiments/{batch_id}/charts` 接口取数据,前端 ECharts 出图

---

**END OF ALGORITHM_TESTCASES.md**
