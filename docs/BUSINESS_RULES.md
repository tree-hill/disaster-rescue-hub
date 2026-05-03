# BUSINESS_RULES.md — 业务规则与算法逻辑

> **文档定位**:本文档是系统所有"硬规则"的唯一来源。**任何 AI 生成代码涉及业务逻辑时,必须严格按本文档实现,不得自由发挥**。
> **依赖**:Schema 引用 `DATA_CONTRACTS.md`,接口引用 `API_SPEC.md` / `WS_EVENTS.md`。
> **测试**:所有规则在 `ALGORITHM_TESTCASES.md` 中有对应测试用例。
> **版本**:v1.0

---

## 0. 文档使用说明

### 给 Claude Code 的明确指令(粘贴用)
> 当你实现 dispatch 服务、状态机、规则引擎、HITL 操作时,**必须严格遵循 BUSINESS_RULES.md 中的公式、阈值、转移规则**。所有数值是经过设计推导的,不要"优化"或"简化"它们。如果你发现规则有歧义或矛盾,**停下来问我**,不要擅自决定。

### 文档结构
- §1 调度出价公式(算法核心)
- §2 状态机转移规则(任务 + 机器人)
- §3 规则引擎硬约束(谁能参与拍卖)
- §4 HITL 干预规则(人工覆盖)
- §5 视觉感知触发规则(YOLO 与调度的耦合点)
- §6 错误码完整清单
- §7 各类阈值汇总表(查询用)

---

## 1. 调度出价公式(SCHEDULER 核心)

### 1.1 公式定义

对于机器人 `r` 与任务 `t`,机器人提交的出价值 `bid(r, t)` 计算如下:

```
bid(r, t) = base_score(r, t) × vision_boost(r, t)
```

其中 `base_score` 由四个分量加权求和:

```
base_score(r, t) = w₁·D(r,t) + w₂·B(r) + w₃·C(r,t) − w₄·L(r)
```

| 符号 | 含义 | 取值范围 |
|---|---|---|
| `w₁ = 0.40` | 距离权重 | 固定常量 |
| `w₂ = 0.20` | 电量权重 | 固定常量 |
| `w₃ = 0.30` | 能力匹配权重 | 固定常量 |
| `w₄ = 0.10` | 负载惩罚权重 | 固定常量 |
| `D(r,t)` | 距离归一化得分 | [0, 1] |
| `B(r)` | 电量归一化得分 | [0, 1] |
| `C(r,t)` | 能力匹配度 | [0, 1] |
| `L(r)` | 当前负载(已分配任务数) | [0, 1] |

**权重之和**:`w₁ + w₂ + w₃ − w₄ = 0.80`(故 `base_score ∈ [-0.10, 0.90]`,实际几乎不会负)

### 1.2 各分量计算公式

#### 1.2.1 距离分量 D(r, t)

```python
def compute_distance_score(robot_pos: Position, task_center: Position) -> float:
    """
    机器人当前位置到任务区域中心的归一化距离得分。
    距离越近,得分越高(越想接任务)。
    """
    dist_km = haversine(robot_pos.lat, robot_pos.lng,
                        task_center.lat, task_center.lng)
    # 归一化:超过 10 km 得分为 0,0 km 得分为 1,线性
    if dist_km >= 10.0:
        return 0.0
    return 1.0 - (dist_km / 10.0)
```

**注意**:
- 距离用 Haversine 公式(球面距离),不要用欧氏距离
- 单位 km
- 上限 10 km(超出即视为无效候选,但不在此处过滤,过滤交给规则引擎)

#### 1.2.2 电量分量 B(r)

```python
def compute_battery_score(battery_pct: float) -> float:
    """
    电量得分。电量越高,得分越高。
    使用平方根函数以惩罚低电量。
    """
    if battery_pct <= 20:
        return 0.0  # 不应到达这里(规则引擎已过滤)
    # sqrt 化:battery=100 → 1.0, battery=50 → 0.71, battery=25 → 0.5
    return math.sqrt(battery_pct / 100.0)
```

**注意**:
- 用平方根而非线性,使得 50% 电量比 25% 电量"显著更优"
- 25% 是规则引擎下限,实际进入此函数的最小值是 21

#### 1.2.3 能力匹配度 C(r, t)

```python
def compute_capability_match(
    robot_capability: RobotCapability,
    task_required: TaskRequiredCapabilities
) -> float:
    """
    能力匹配度。
    硬约束(无对应传感器/载荷)在规则引擎过滤;
    此处计算"软匹配度",即匹配数占总需求数的比例。
    """
    required_sensors = set(task_required.sensors)
    required_payloads = set(task_required.payloads)
    has_sensors = set(robot_capability.sensors)
    has_payloads = set(robot_capability.payloads)

    total_required = len(required_sensors) + len(required_payloads)
    if total_required == 0:
        return 1.0  # 任务无能力要求,默认满分

    matched = len(required_sensors & has_sensors) + len(required_payloads & has_payloads)
    return matched / total_required
```

#### 1.2.4 负载分量 L(r)

```python
def compute_load_score(current_active_assignments: int) -> float:
    """
    当前负载得分。已分配任务越多,负载越高(惩罚越大)。
    单机器人最多承担 3 个任务。
    """
    MAX_LOAD = 3
    return min(current_active_assignments / MAX_LOAD, 1.0)
```

**注意**:`current_active_assignments` 来自 `task_assignments WHERE robot_id = r AND is_active = TRUE` 的计数。

### 1.3 视觉感知加成 vision_boost(r, t)

```python
def compute_vision_boost(
    robot_position: Position,
    task_target_area: TargetArea,
    blackboard: Blackboard
) -> float:
    """
    视觉加成。
    若任务目标区域附近(< 200 m)存在黑板上 conf ≥ 0.8 的幸存者条目,
    且机器人本身搭载 YOLO 能力(has_yolo=True),
    则返回 1.5,否则返回 1.0。

    设计理由:有视觉能力的机器人,在已识别幸存者的区域有更强适配性。
    """
    BOOST_FACTOR = 1.5
    DISTANCE_THRESHOLD_M = 200
    CONFIDENCE_THRESHOLD = 0.8

    # 仅 has_yolo 的机器人享受加成
    if not robot.capability.has_yolo:
        return 1.0

    # 在黑板查询任务区域附近的高置信度幸存者
    nearby_survivors = blackboard.query_by_proximity(
        center=task_target_area.center_point,
        radius_m=DISTANCE_THRESHOLD_M,
        type_filter="survivor",
        min_confidence=CONFIDENCE_THRESHOLD
    )

    if len(nearby_survivors) > 0:
        return BOOST_FACTOR
    return 1.0
```

**重要**:
- **加成是乘法**(不是加法),反映"质的优势"
- 加成只对有视觉能力的机器人(has_yolo=True),其他不享受
- 触发后必须在 `bids.breakdown.vision_boosted = True`(写库审计)
- 这是论文核心创新点,**绝对不可省略或简化**

### 1.4 拍卖求解算法(三种)

#### 1.4.1 AUCTION_HUNGARIAN(主算法)

```python
def hungarian_solve(
    eligible_pairs: list[tuple[Robot, Task]],
    robots: list[Robot],
    tasks: list[Task],
    blackboard: Blackboard
) -> dict[UUID, UUID]:
    """
    匈牙利算法求最优匹配。
    返回 {task_id: robot_id} 的分配字典。

    核心:
    1. 构建代价矩阵 C[n][m] = -bid_value(取负转最小化)
    2. 不合格的 (r,t) 对设代价为 1e6(极大值)
    3. 调用 scipy.optimize.linear_sum_assignment 求解
    """
    n, m = len(robots), len(tasks)
    cost_matrix = np.full((n, m), 1e6)  # 默认极大

    for i, robot in enumerate(robots):
        for j, task in enumerate(tasks):
            if (robot, task) not in eligible_pairs:
                continue  # 保持极大值
            bid = compute_full_bid(robot, task, blackboard)
            cost_matrix[i, j] = -bid  # 取负

    row_ind, col_ind = linear_sum_assignment(cost_matrix)

    assignments = {}
    for i, j in zip(row_ind, col_ind):
        if cost_matrix[i, j] >= 1e5:
            continue  # 跳过被过滤的
        assignments[tasks[j].id] = robots[i].id

    return assignments
```

#### 1.4.2 GREEDY(对照)

```python
def greedy_solve(eligible_pairs, robots, tasks, blackboard) -> dict:
    """
    贪心算法:按任务优先级 → 选择 bid 最高的机器人。
    """
    assignments = {}
    used_robots = set()
    sorted_tasks = sorted(tasks, key=lambda t: t.priority)  # 1=高优先

    for task in sorted_tasks:
        candidates = [r for r in robots
                     if r.id not in used_robots
                     and (r, task) in eligible_pairs]
        if not candidates:
            continue
        best = max(candidates, key=lambda r: compute_full_bid(r, task, blackboard))
        assignments[task.id] = best.id
        used_robots.add(best.id)

    return assignments
```

#### 1.4.3 RANDOM(基线)

```python
def random_solve(eligible_pairs, robots, tasks, blackboard, seed=None) -> dict:
    """
    随机分配:从合格集合中随机匹配。仅用于实验对照。
    """
    rng = random.Random(seed)
    assignments = {}
    used_robots = set()

    for task in rng.sample(tasks, len(tasks)):
        candidates = [r for r in robots
                     if r.id not in used_robots
                     and (r, task) in eligible_pairs]
        if not candidates:
            continue
        chosen = rng.choice(candidates)
        assignments[task.id] = chosen.id
        used_robots.add(chosen.id)

    return assignments
```

### 1.5 写入审计的标准格式

每次拍卖,无论用哪种算法,必须写入:
- `auctions` 表 1 条
- `bids` 表 N 条(每个候选机器人 1 条,记录其出价分解)

`bids.breakdown` 严格按 `DATA_CONTRACTS.md §4.7` 结构,**所有分量值必须可追溯**(不能只存最终 bid)。

---

## 2. 状态机转移规则

### 2.1 任务状态机(TaskStatus)

#### 2.1.1 允许的转移

| From | To | 触发动作 | 守卫条件 | 副作用 |
|---|---|---|---|---|
| PENDING | ASSIGNED | 拍卖完成且有获胜者 | 至少 1 个 task_assignment 写入 | 推送 `task.status_changed`;创建 `task_assignments` |
| PENDING | CANCELLED | 用户取消 | 用户有 `task:cancel` 权限 | 写 intervention;推送 `task.cancelled` |
| ASSIGNED | EXECUTING | 机器人到达任务区域并开始 | `current_task_id == this.id` | 推送 `task.status_changed`;`tasks.started_at = NOW()` |
| ASSIGNED | CANCELLED | 用户取消 | 同上 | 释放 assignment;写 intervention |
| ASSIGNED | PENDING | 改派(在新拍卖前) | HITL 改派触发 | 释放原 assignment(`is_active=FALSE`)|
| EXECUTING | COMPLETED | 进度达 100% | `progress >= 100.0` | `tasks.completed_at = NOW()`;释放 assignment;推送 `task.status_changed` |
| EXECUTING | FAILED | 机器人故障且无替补 | 当前 robot FAULT 且无 HITL 介入 | 同上 |
| EXECUTING | CANCELLED | 用户强制取消 | 用户有权限 | 同上 |
| EXECUTING | EXECUTING | 改派(无缝切换) | HITL 改派触发 | 旧 assignment 失效,新 assignment 生效,task 状态保持 |

#### 2.1.2 禁止的转移(违反即抛 `409_TASK_STATUS_CONFLICT_001`)

- COMPLETED → 任何状态(终态)
- FAILED → 任何状态(终态)
- CANCELLED → 任何状态(终态)
- PENDING → COMPLETED(必须经过 ASSIGNED)
- PENDING → EXECUTING(必须经过 ASSIGNED)
- ASSIGNED → COMPLETED(必须经过 EXECUTING)

#### 2.1.3 实现指南

```python
# 推荐:用字典表达转移图,统一校验入口
TASK_TRANSITIONS = {
    "PENDING":    {"ASSIGNED", "CANCELLED"},
    "ASSIGNED":   {"EXECUTING", "CANCELLED", "PENDING"},
    "EXECUTING":  {"COMPLETED", "FAILED", "CANCELLED", "EXECUTING"},
    "COMPLETED":  set(),  # 终态
    "FAILED":     set(),
    "CANCELLED":  set(),
}

def can_transit(from_status: str, to_status: str) -> bool:
    return to_status in TASK_TRANSITIONS.get(from_status, set())
```

### 2.2 机器人 FSM 状态机(FSMState)

#### 2.2.1 允许的转移

| From | To | 触发 | 守卫 | 副作用 |
|---|---|---|---|---|
| IDLE | BIDDING | 收到拍卖邀请 | battery ≥ 20% | 计算并提交 bid |
| BIDDING | EXECUTING | 拍卖获胜 | 收到 `auction.completed` 且自己是 winner | `current_task_id` 写入;开始执行 |
| BIDDING | IDLE | 拍卖落选 | 收到 `auction.completed` 且自己非 winner | 清除临时状态 |
| EXECUTING | RETURNING | 任务完成 | 任务 `progress = 100` | 路径规划返回基地 |
| EXECUTING | FAULT | 内部故障检测 | 任意故障条件命中 | 写 `robot_faults`;广播 `robot.fault_occurred` |
| RETURNING | IDLE | 抵达基地 | 距基地 < 50m | `current_task_id = NULL` |
| RETURNING | FAULT | 故障 | 同上 | 同上 |
| FAULT | IDLE | 故障解除 | 人工修复(`robot_faults.resolved_at IS NOT NULL`)| 重置故障状态 |
| EXECUTING | RETURNING | HITL 召回 | 用户调用 recall API | 写 intervention;立即停止任务 |

#### 2.2.2 故障触发条件

机器人 Agent 主循环每 1Hz 检测一次,以下任一命中即转 FAULT:

| 条件 | 故障类型 | 严重等级 |
|---|---|---|
| `battery <= 5%` | `low_battery` | critical |
| 连续 15 秒未上报心跳(指 Agent 协程未推送状态)| `comm_lost` | critical |
| `sensor_data` 中关键字段缺失或异常 | `sensor_error` | warn |
| Mock 中按概率注入(用于演示)| `unknown` | info / warn |

#### 2.2.3 状态机字典实现

```python
ROBOT_FSM_TRANSITIONS = {
    "IDLE":      {"BIDDING", "FAULT"},
    "BIDDING":   {"EXECUTING", "IDLE", "FAULT"},
    "EXECUTING": {"RETURNING", "FAULT"},
    "RETURNING": {"IDLE", "FAULT"},
    "FAULT":     {"IDLE"},  # 仅修复后回到 IDLE
}
```

---

## 3. 规则引擎硬约束(Rule Engine)

### 3.1 引擎职责

在拍卖前过滤候选机器人。**任何不通过硬约束的 (robot, task) 对,代价矩阵中设为 ∞**(实际用 1e6),不参与匹配。

### 3.2 硬约束清单(顺序执行,任一失败即过滤)

| # | 约束名 | 检查逻辑 | 失败标记 |
|---|---|---|---|
| R1 | `is_active` | `robot.is_active == True` | `inactive` |
| R2 | `state_idle` | `robot.fsm_state in {"IDLE", "RETURNING"}` | `not_idle` |
| R3 | `min_battery` | `robot.battery >= max(20.0, task.required_capabilities.min_battery_pct)` | `low_battery` |
| R4 | `robot_type` | 若 `task.required.robot_type` 非空,`robot.type` 必须在其中 | `wrong_type` |
| R5 | `required_sensors` | `set(task.required.sensors).issubset(set(robot.capability.sensors))` | `missing_sensor` |
| R6 | `required_payloads` | `set(task.required.payloads).issubset(set(robot.capability.payloads))` | `missing_payload` |
| R7 | `range_check` | `haversine(robot.pos, task.center) <= robot.capability.max_range_km` | `out_of_range` |
| R8 | `load_limit` | `current_active_assignments < 3` | `overloaded` |

### 3.3 引擎实现伪代码

```python
class RuleEngine:
    def check(self, robot: Robot, task: Task) -> tuple[bool, str]:
        """返回 (是否通过, 失败原因)"""
        if not robot.is_active:
            return False, "inactive"
        if robot.fsm_state not in {"IDLE", "RETURNING"}:
            return False, "not_idle"
        if robot.battery < max(20.0, task.required_capabilities.min_battery_pct):
            return False, "low_battery"
        if task.required_capabilities.robot_type and robot.type not in task.required_capabilities.robot_type:
            return False, "wrong_type"
        if not set(task.required_capabilities.sensors).issubset(set(robot.capability.sensors)):
            return False, "missing_sensor"
        if not set(task.required_capabilities.payloads).issubset(set(robot.capability.payloads)):
            return False, "missing_payload"
        dist = haversine(robot.position.lat, robot.position.lng,
                        task.target_area.center_point.lat,
                        task.target_area.center_point.lng)
        if dist > robot.capability.max_range_km:
            return False, "out_of_range"
        if self._count_active_assignments(robot.id) >= 3:
            return False, "overloaded"
        return True, "ok"

    def filter(self, robots: list[Robot], task: Task) -> tuple[list[Robot], dict]:
        """返回 (合格机器人列表, 过滤统计 {reason: count})"""
        eligible = []
        stats = defaultdict(int)
        for r in robots:
            ok, reason = self.check(r, task)
            if ok:
                eligible.append(r)
            else:
                stats[reason] += 1
        return eligible, dict(stats)
```

### 3.4 拍卖失败处理

若 `len(eligible) == 0`:
- 拍卖立即关闭,`auctions.status = 'FAILED'`
- 任务保持 `PENDING` 状态(等待下次机会)
- 推送 `auction.failed` 事件,payload 含 `filtered_out_count` 与 `reason_breakdown`
- **不**自动重试;由系统每 30 秒扫描一次 PENDING 任务并重新发起拍卖

---

## 4. HITL 干预规则

### 4.1 干预类型与权限对照

| 干预类型 | 接口 | 所需权限 | 必须填 reason | 副作用 |
|---|---|---|---|---|
| `reassign` | POST /dispatch/reassign | `robot:reassign` | ✓(≥5字符) | 1. 释放原 assignment 2. 创建新 3. 写 intervention 4. WS 双事件 |
| `recall` | POST /robots/{id}/recall | `robot:recall` | ✓ | 1. 推送召回指令 2. 机器人 → RETURNING 3. 写 intervention 4. 关联任务释放 |
| `cancel_task` | POST /tasks/{id}/cancel | `task:cancel` | ✓ | 1. 任务 → CANCELLED 2. 释放所有 assignment 3. 写 intervention |
| `algorithm_switch` | POST /dispatch/algorithm | `algorithm:switch` | ✓ | 1. 全局算法切换 2. 后续拍卖用新算法 3. 写 intervention 4. WS 通知 |

### 4.2 干预通用流程

```
1. 用户调用 API,带 reason
2. 服务端权限校验(401/403)
3. 业务校验:
   - reassign:校验新机器人合格(走 RuleEngine)
   - recall:校验机器人当前状态可召回(EXECUTING/BIDDING/RETURNING)
   - cancel_task:校验任务非终态
4. 取 before_state(快照当前状态)
5. 执行操作(状态变迁、释放 assignment 等)
6. 取 after_state(快照新状态)
7. 写 human_interventions 表(同事务)
8. 广播 WS 事件(对应业务事件 + intervention.recorded)
9. 返回 200 + intervention_id
```

### 4.3 关键实现细节

#### 4.3.1 reason 字段约束

- 长度 5-500 字符
- 不允许纯空白
- 校验失败:`422_INTERVENTION_REASON_INVALID_001`

#### 4.3.2 before/after_state 必须一致格式

按 `DATA_CONTRACTS.md §4.8` 严格执行,字段缺失视为 bug。

#### 4.3.3 改派的核心逻辑

```python
async def reassign_task(task_id, new_robot_id, reason, user_id):
    # 1. 加锁(行级或 Redis 锁,避免并发改派)
    async with lock(f"task:{task_id}"):
        task = await task_repo.get(task_id)
        if task.status not in {"ASSIGNED", "EXECUTING"}:
            raise BusinessError("409_TASK_STATUS_CONFLICT_001",
                              "任务状态不允许改派")

        # 2. 校验新机器人
        new_robot = await robot_repo.get(new_robot_id)
        ok, fail_reason = rule_engine.check(new_robot, task)
        if not ok:
            raise BusinessError("409_ROBOT_INELIGIBLE_001",
                              f"目标机器人不合格:{fail_reason}")

        # 3. before_state
        old_assignments = await assignment_repo.find_active(task_id)
        before_state = {
            "task_id": str(task.id),
            "task_code": task.code,
            "assigned_robot_ids": [str(a.robot_id) for a in old_assignments],
            "algorithm_used": "AUCTION_HUNGARIAN",  # 或从最近的 auction 取
            "timestamp": datetime.utcnow().isoformat()
        }

        # 4. 执行
        for a in old_assignments:
            a.is_active = False
            a.released_at = datetime.utcnow()
        new_assignment = TaskAssignment(
            task_id=task.id, robot_id=new_robot.id,
            auction_id=None  # 人工指派
        )
        await assignment_repo.save(new_assignment)

        # 5. after_state
        after_state = {
            "task_id": str(task.id),
            "task_code": task.code,
            "assigned_robot_ids": [str(new_robot.id)],
            "algorithm_used": "MANUAL_OVERRIDE",
            "timestamp": datetime.utcnow().isoformat()
        }

        # 6. 写 intervention(同事务)
        intervention = HumanIntervention(
            user_id=user_id,
            intervention_type="reassign",
            target_task_id=task.id,
            target_robot_id=new_robot.id,
            before_state=before_state,
            after_state=after_state,
            reason=reason
        )
        await intervention_repo.save(intervention)

    # 7. 事务外推送 WS 事件
    await event_bus.publish(TaskReassignedEvent(...))
    await event_bus.publish(InterventionRecordedEvent(...))

    return intervention.id
```

### 4.4 召回的特殊规则

- 召回操作触发后,机器人立即停止当前任务(中断,而非完成)
- 关联任务状态:
  - 若任务有其他 active assignment(多机协同),保持 EXECUTING
  - 若没有,任务回到 PENDING(等待重新拍卖)
- 召回的机器人进入 RETURNING 状态,到基地后进入 IDLE

### 4.5 算法切换的全局影响

- 切换是**全局**的,影响所有未来拍卖
- 已经在进行中的拍卖(`auctions.status = OPEN`)不受影响,继续用旧算法
- 切换后立即生效,无需重启

---

## 5. 视觉感知触发规则(YOLO 与系统的集成点)

### 5.1 YOLO 推理触发

机器人 Agent 中,**仅 has_yolo=True 的机器人**周期性触发推理:
- **频率**:1Hz(可配置,Mock 时可降低)
- **输入**:Mock 图像(从 AIDER 测试集随机抽取)或真实摄像头帧
- **执行**:调用 `PerceptionService.process_image()`

### 5.2 推理结果处理流程

```python
async def process_image(robot_id, image, current_position):
    # 1. YOLOv8 推理
    detections = self.model(image, conf=0.5, iou=0.45)

    # 2. 过滤(规则统一)
    valid = [d for d in detections if d.confidence >= 0.5]

    if not valid:
        return  # 全部丢弃

    # 3. 写黑板(每个 detection 一条)
    for d in valid:
        world_pos = self._compute_world_position(d.bbox, current_position)
        key = f"{d.class_name}:{int(world_pos.lat * 100)}_{int(world_pos.lng * 100)}"

        await blackboard.fuse(
            key=key,
            value={
                "type": d.class_name,
                "position": world_pos,
                "bbox": d.bbox.tolist()
            },
            confidence=d.confidence,
            source_robot_id=robot_id,
            ttl_sec=300  # 5 分钟
        )

        # 4. 推送 WS perception.detection
        await ws_broadcast("commander", "perception.detection", {...})

        # 5. 判断是否触发高置信度告警
        if d.class_name == "survivor" and d.confidence >= 0.8:
            await self._handle_high_confidence_survivor(d, world_pos, robot_id)
        elif d.class_name == "fire" and d.confidence >= 0.7:
            await self._raise_fire_alert(d, world_pos, robot_id)
```

### 5.3 高置信度幸存者自动派任务规则

```python
async def _handle_high_confidence_survivor(detection, position, robot_id):
    """
    高置信度幸存者 → 检查是否已有相邻任务 → 否则自动创建救援任务
    """
    SEARCH_RADIUS_KM = 0.5  # 500m 内已有任务则不新建

    nearby_tasks = await task_repo.find_active_near(
        position, SEARCH_RADIUS_KM,
        types=["search_rescue"]
    )

    if nearby_tasks:
        # 已有任务,提升其优先级即可
        for t in nearby_tasks:
            if t.priority > 1:
                t.priority = 1
                await task_repo.save(t)
        return

    # 自动创建救援任务
    auto_task = Task(
        name=f"自动救援:发现幸存者(置信度 {detection.confidence:.2f})",
        type="search_rescue",
        priority=1,  # 高
        target_area=TargetArea(
            type="circle",
            center=position,
            radius_m=200,
            area_km2=0.126,  # π × 0.2²
            center_point=position
        ),
        required_capabilities=TaskRequiredCapabilities(
            sensors=["camera_4k"],
            min_battery_pct=30
        ),
        created_by=SYSTEM_USER_ID  # 系统自动创建,需在 users 表预留 system 账户
    )
    await task_service.create(auto_task)
```

### 5.4 视觉加成在拍卖中的应用

详见 §1.3。**关键**:加成判断必须查黑板**当时**的状态,不能用缓存的旧数据。

---

## 6. 错误码完整清单

> 格式:`{HTTP状态}_{领域}_{子类型}_{序号}`

### 6.1 认证类 (AUTH)
| 错误码 | HTTP | 含义 |
|---|---|---|
| `401_AUTH_INVALID_CREDENTIAL_001` | 401 | 用户名或密码错误 |
| `401_AUTH_TOKEN_EXPIRED_001` | 401 | Access Token 已过期 |
| `401_AUTH_TOKEN_INVALID_001` | 401 | Token 格式错误或被吊销 |
| `403_AUTH_PERMISSION_DENIED_001` | 403 | 权限不足 |
| `423_AUTH_ACCOUNT_LOCKED_001` | 423 | 账号锁定(连续 5 次失败)|

### 6.2 机器人类 (ROBOT)
| 错误码 | HTTP | 含义 |
|---|---|---|
| `404_ROBOT_NOT_FOUND_001` | 404 | 机器人不存在 |
| `409_ROBOT_CODE_DUPLICATE_001` | 409 | 机器人编码重复 |
| `409_ROBOT_INELIGIBLE_001` | 409 | 机器人不符合任务要求 |
| `409_ROBOT_HAS_ACTIVE_TASK_001` | 409 | 机器人有进行中任务,不能注销 |
| `409_ROBOT_ALREADY_FAULT_001` | 409 | 机器人已是 FAULT,不能召回 |
| `409_ROBOT_NOT_RECALLABLE_001` | 409 | 当前 FSM 状态不可召回（仅 EXECUTING/BIDDING/RETURNING 可召回；details 含实际状态） |
| `503_AGENT_NOT_RUNNING_001` | 503 | AgentManager 未启动或机器人 Agent 协程不存在（mock_agents_enabled=False 场景） |

### 6.3 任务类 (TASK)
| 错误码 | HTTP | 含义 |
|---|---|---|
| `404_TASK_NOT_FOUND_001` | 404 | 任务不存在 |
| `422_TASK_INVALID_AREA_001` | 422 | 任务区域参数非法(area_km2 ≤ 0)|
| `422_TASK_INVALID_PRIORITY_001` | 422 | 优先级超出 1/2/3 |
| `409_TASK_STATUS_CONFLICT_001` | 409 | 任务当前状态不允许此操作 |
| `409_TASK_ALREADY_CANCELLED_001` | 409 | 任务已被取消 |
| `409_TASK_NO_ELIGIBLE_ROBOT_001` | 409 | 无合格机器人可分配(用于直接分配 API)|

### 6.4 调度类 (DISPATCH)
| 错误码 | HTTP | 含义 |
|---|---|---|
| `409_DISPATCH_AUCTION_OPEN_001` | 409 | 该任务已有 OPEN 状态拍卖 |
| `409_DISPATCH_ALGORITHM_INVALID_001` | 409 | 切换的算法名不在白名单 |
| `500_DISPATCH_SOLVER_ERROR_001` | 500 | 算法求解器抛异常 |

### 6.5 干预类 (INTERVENTION)
| 错误码 | HTTP | 含义 |
|---|---|---|
| `422_INTERVENTION_REASON_INVALID_001` | 422 | reason 长度不足 5 字符 |
| `409_INTERVENTION_TARGET_LOCKED_001` | 409 | 目标资源被其他干预占用 |

### 6.6 黑板与感知类 (PERCEPTION)
| 错误码 | HTTP | 含义 |
|---|---|---|
| `422_PERCEPTION_LOW_CONFIDENCE_001` | 422 | 推理结果置信度过低,被拒绝写入 |
| `500_PERCEPTION_MODEL_ERROR_001` | 500 | YOLO 模型推理异常 |

### 6.7 通用类
| 错误码 | HTTP | 含义 |
|---|---|---|
| `422_VALIDATION_FAILED_001` | 422 | Pydantic 校验失败(通用)|
| `500_INTERNAL_ERROR_001` | 500 | 未捕获的服务器错误 |
| `503_DATABASE_UNAVAILABLE_001` | 503 | 数据库连接失败 |
| `503_DEPENDENCY_DOWN_001` | 503 | 关键依赖不可用 |

### 6.8 错误响应规范

所有错误响应必须使用 `ErrorResponse` schema(见 `DATA_CONTRACTS.md §5`):
```json
{
  "code": "409_TASK_STATUS_CONFLICT_001",
  "message": "任务已完成,不能再取消",
  "details": [
    { "field": "task.status", "code": "current_status", "message": "COMPLETED" }
  ],
  "request_id": "req-uuid-xxx",
  "timestamp": "2026-04-25T14:32:18Z"
}
```

---

## 7. 各类阈值汇总表(查询速查用)

| 类别 | 参数 | 值 | 出处 |
|---|---|---|---|
| **拍卖出价** | w₁ 距离权重 | 0.40 | §1.1 |
| | w₂ 电量权重 | 0.20 | §1.1 |
| | w₃ 能力权重 | 0.30 | §1.1 |
| | w₄ 负载权重 | 0.10 | §1.1 |
| | 距离上限 | 10 km | §1.2.1 |
| | 视觉加成倍数 | 1.5 | §1.3 |
| | 视觉加成距离阈值 | 200 m | §1.3 |
| | 视觉加成置信度阈值 | 0.8 | §1.3 |
| **规则引擎** | 最低电量 | 20% | §3.2 R3 |
| | 单机最大并发任务 | 3 | §3.2 R8 |
| **机器人** | 故障电量阈值 | 5% | §2.2.2 |
| | 心跳超时 | 15 秒 | §2.2.2 |
| | 心跳频率 | 1 Hz | §5.1 |
| **任务** | 网格分解阈值 | 1 km² | (任务管理模块)|
| | 网格大小 | 500m × 500m | (任务管理模块)|
| | 自动救援距离去重 | 500 m | §5.3 |
| | 自动救援区域半径 | 200 m | §5.3 |
| **黑板** | 视觉数据 TTL | 300 秒(5 min)| §5.2 |
| | 告警数据 TTL | 600 秒(10 min)| (黑板模块)|
| | 状态数据 TTL | 30 秒 | (黑板模块)|
| | 写入置信度下限 | 0.5 | §5.2 |
| | 高置信度告警下限 | 0.8 | §5.3 |
| | 火灾告警下限 | 0.7 | §5.2 |
| **YOLO** | conf 阈值 | 0.5 | §5.2 |
| | NMS IoU | 0.45 | §5.2 |
| | 输入分辨率 | 640×640 | (CV 模块)|
| **拍卖求解** | 决策延迟告警阈值 | 5000 ms | INV-7(DATA_CONTRACTS)|
| | 决策延迟目标 | < 2000 ms | (NFR)|
| **WebSocket** | 心跳间隔 | 25 秒 | §0.3(WS_EVENTS)|
| | 超时断开 | 60 秒 | §0.3(WS_EVENTS)|
| | 状态推送目标延迟 | < 500 ms | (NFR)|
| **JWT** | Access Token 过期 | 24 h | (Auth)|
| | Refresh Token 过期 | 7 d | (Auth)|
| **账号** | 失败锁定阈值 | 连续 5 次 | (Auth)|
| | 锁定持续时间 | 15 分钟 | (Auth)|
| **实验** | 重复次数 | 10 次/算法 | (论文设计)|
| | 算法对比组数 | 3(Hungarian/Greedy/Random)| (论文设计)|

---

## 8. 关键不变量(Invariants)总结

> 这些规则**任何代码路径都不能违反**,违反即视为严重 bug。

| # | 不变量 | 检查点 |
|---|---|---|
| INV-A | 一个机器人在同一时刻最多有 1 个 active assignment(多任务并行 ≤ 3,通过 R8 约束)| 创建 assignment 时 |
| INV-B | 任务状态从终态(COMPLETED/FAILED/CANCELLED)出发不可改变 | 状态转移时 |
| INV-C | HITL 操作必须有 reason 且必须写 intervention 表 | API 入口 |
| INV-D | 视觉加成 1.5x 触发时必须在 `bids.breakdown.vision_boosted = True` | 出价计算 |
| INV-E | 拍卖关闭时必须写入完整 bids(每个候选机器人 1 条)| 拍卖关闭流程 |
| INV-F | 每个 WS 事件必须有 `event_id` 和 `timestamp` | WS 发送前 |
| INV-G | 数据库写操作涉及多表时必须用同一事务(尤其 intervention + 业务表)| 服务层 |

---

**END OF BUSINESS_RULES.md**
