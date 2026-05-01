# DATA_CONTRACTS.md — 数据契约文档

> **文档定位**:本文档是系统所有数据结构的**唯一真理来源**。所有后端代码、前端类型、API 契约必须以此为准。
> **使用方式**:开发任何涉及数据持久化、API 字段、状态结构的代码前,**先查本文档**。
> **变更约束**:本文档变更必须 review,严禁开发中"顺手改字段"。
> **版本**:v1.0(2026-04-25 定稿)

---

## 0. 总览

### 0.1 数据库选型与版本
- **数据库**:PostgreSQL 15.5+(为 JSONB / GIN 索引 / pgcrypto 而选)
- **ORM**:SQLAlchemy 2.0(async API)
- **迁移工具**:Alembic
- **字符集**:UTF-8

### 0.2 命名规范(强制)
- 表名:`snake_case` 复数(`robots`, `tasks`, `human_interventions`)
- 字段名:`snake_case`(`created_at`, `target_area`)
- 主键:`id`,默认 UUIDv4(高频写入表用 BIGSERIAL,见单表说明)
- 时间戳:统一 `TIMESTAMPTZ`,UTC 存储,前端转本地时区显示
- 软删除:不使用,**采用 `is_active: BOOLEAN` 标志**(避免外键悬空)
- JSONB 字段:命名后缀加 `_json` 不必,但内容结构必须在本文档第 4 节定义

### 0.3 17 张表全清单

| # | 表名 | 主键类型 | 用途 | 高频写入? |
|---|---|---|---|---|
| 1 | `users` | UUID | 用户账号 | ✗ |
| 2 | `roles` | UUID | 角色定义 | ✗ |
| 3 | `user_roles` | (UUID, UUID) | 用户-角色关联 | ✗ |
| 4 | `robots` | UUID | 机器人配置 | ✗ |
| 5 | `robot_groups` | UUID | 编队 | ✗ |
| 6 | `robot_states` | BIGSERIAL | 机器人实时状态时序 | **✓** |
| 7 | `robot_faults` | UUID | 机器人故障记录 | ✗ |
| 8 | `tasks` | UUID | 任务 | ✗ |
| 9 | `task_assignments` | UUID | 任务-机器人分配 | ✗ |
| 10 | `auctions` | UUID | 拍卖会话 | ✗ |
| 11 | `bids` | UUID | 出价记录 | ✗ |
| 12 | `human_interventions` | UUID | HITL 审计 | ✗ |
| 13 | `blackboard_entries` | UUID | 共享黑板条目 | **✓** |
| 14 | `alerts` | UUID | 告警 | ✗ |
| 15 | `replay_sessions` | UUID | 回放会话 | ✗ |
| 16 | `experiment_runs` | UUID | 实验运行记录 | ✗ |
| 17 | `scenarios` | UUID | 场景剧本 | ✗ |

---

## 1. SQL DDL(完整建表语句)

> 直接将本节内容保存为 `schema.sql`,执行后即可建库。
> 索引策略已嵌入(见每表末尾)。

```sql
-- =============================================================================
-- 救灾中枢系统数据库 Schema v1.0
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- 模糊搜索

-- ============ 1. users ============
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,            -- bcrypt
    display_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_users_username ON users(username) WHERE is_active = TRUE;

-- ============ 2. roles ============
CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(50) UNIQUE NOT NULL,                -- 'commander', 'admin', 'observer'
    description TEXT,
    permissions JSONB NOT NULL DEFAULT '[]',         -- 见 §4.1
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============ 3. user_roles ============
CREATE TABLE user_roles (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, role_id)
);

-- ============ 4. robots ============
CREATE TABLE robots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(50) UNIQUE NOT NULL,                -- 'UAV-001'
    name VARCHAR(100) NOT NULL,                      -- '鹰眼-1'
    type VARCHAR(20) NOT NULL,                       -- 'uav' | 'ugv' | 'usv'
    model VARCHAR(100),                              -- 'DJI M300'
    capability JSONB NOT NULL DEFAULT '{}',          -- 见 §4.2
    group_id UUID REFERENCES robot_groups(id) ON DELETE SET NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT robots_type_check CHECK (type IN ('uav', 'ugv', 'usv'))
);
CREATE INDEX idx_robots_type ON robots(type) WHERE is_active = TRUE;
CREATE INDEX idx_robots_group ON robots(group_id);
CREATE INDEX idx_robots_capability ON robots USING GIN (capability);

-- ============ 5. robot_groups ============
CREATE TABLE robot_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    leader_robot_id UUID,                            -- 不加 FK,允许 NULL/失效
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============ 6. robot_states (高频写入) ============
CREATE TABLE robot_states (
    id BIGSERIAL PRIMARY KEY,
    robot_id UUID NOT NULL REFERENCES robots(id) ON DELETE CASCADE,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fsm_state VARCHAR(20) NOT NULL,                  -- IDLE/BIDDING/EXECUTING/RETURNING/FAULT
    position JSONB NOT NULL,                         -- 见 §4.3
    battery NUMERIC(5,2) NOT NULL,                   -- 0.00 ~ 100.00
    sensor_data JSONB NOT NULL DEFAULT '{}',         -- 见 §4.4 (含 YOLO 推理结果)
    current_task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    CONSTRAINT robot_states_fsm_check CHECK (fsm_state IN ('IDLE','BIDDING','EXECUTING','RETURNING','FAULT'))
);
CREATE INDEX idx_robot_states_robot_time ON robot_states(robot_id, recorded_at DESC);
CREATE INDEX idx_robot_states_time ON robot_states(recorded_at DESC);
CREATE INDEX idx_robot_states_sensor ON robot_states USING GIN (sensor_data);

-- ============ 7. robot_faults ============
CREATE TABLE robot_faults (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    robot_id UUID NOT NULL REFERENCES robots(id) ON DELETE CASCADE,
    fault_type VARCHAR(50) NOT NULL,                 -- 'low_battery'/'comm_lost'/'sensor_error'/...
    severity VARCHAR(20) NOT NULL,                   -- 'info'/'warn'/'critical'
    message TEXT NOT NULL,
    detail JSONB DEFAULT '{}',
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolved_by UUID REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT faults_severity_check CHECK (severity IN ('info','warn','critical'))
);
CREATE INDEX idx_faults_robot ON robot_faults(robot_id, occurred_at DESC);
CREATE INDEX idx_faults_unresolved ON robot_faults(occurred_at DESC) WHERE resolved_at IS NULL;

-- ============ 8. tasks ============
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(50) UNIQUE NOT NULL,                -- 'T-2024-001'
    name VARCHAR(200) NOT NULL,
    type VARCHAR(30) NOT NULL,                       -- 'search_rescue'/'recon'/'transport'/'patrol'
    priority SMALLINT NOT NULL DEFAULT 2,            -- 1=高 2=中 3=低
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',   -- 状态机见 BUSINESS_RULES
    target_area JSONB NOT NULL,                      -- 见 §4.5
    required_capabilities JSONB NOT NULL DEFAULT '[]', -- 见 §4.6
    parent_id UUID REFERENCES tasks(id) ON DELETE CASCADE, -- 子任务关联
    progress NUMERIC(5,2) NOT NULL DEFAULT 0,        -- 0.00 ~ 100.00
    sla_deadline TIMESTAMPTZ,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT tasks_status_check CHECK (status IN ('PENDING','ASSIGNED','EXECUTING','COMPLETED','FAILED','CANCELLED')),
    CONSTRAINT tasks_priority_check CHECK (priority IN (1,2,3))
);
CREATE INDEX idx_tasks_status ON tasks(status, created_at DESC);
CREATE INDEX idx_tasks_priority ON tasks(priority, created_at) WHERE status = 'PENDING';
CREATE INDEX idx_tasks_parent ON tasks(parent_id);
CREATE INDEX idx_tasks_capabilities ON tasks USING GIN (required_capabilities);

-- ============ 9. task_assignments ============
CREATE TABLE task_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    robot_id UUID NOT NULL REFERENCES robots(id),
    auction_id UUID REFERENCES auctions(id) ON DELETE SET NULL, -- 可能为 NULL(人工指派)
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    released_at TIMESTAMPTZ,                         -- 释放(任务完成或改派)
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (task_id, robot_id, assigned_at)
);
CREATE INDEX idx_assignments_task ON task_assignments(task_id) WHERE is_active = TRUE;
CREATE INDEX idx_assignments_robot ON task_assignments(robot_id) WHERE is_active = TRUE;

-- ============ 10. auctions ============
CREATE TABLE auctions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    algorithm VARCHAR(30) NOT NULL,                  -- 'AUCTION_HUNGARIAN'/'GREEDY'/'RANDOM'
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN',      -- 'OPEN'/'CLOSED'/'FAILED'
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    winner_robot_id UUID REFERENCES robots(id),
    decision_latency_ms INTEGER,                     -- 算法耗时
    metadata JSONB DEFAULT '{}',                     -- 算法参数等
    CONSTRAINT auctions_algo_check CHECK (algorithm IN ('AUCTION_HUNGARIAN','GREEDY','RANDOM')),
    CONSTRAINT auctions_status_check CHECK (status IN ('OPEN','CLOSED','FAILED'))
);
CREATE INDEX idx_auctions_task ON auctions(task_id, started_at DESC);

-- ============ 11. bids ============
CREATE TABLE bids (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auction_id UUID NOT NULL REFERENCES auctions(id) ON DELETE CASCADE,
    robot_id UUID NOT NULL REFERENCES robots(id),
    bid_value NUMERIC(10,4) NOT NULL,                -- 出价数值
    breakdown JSONB NOT NULL,                        -- 见 §4.7
    vision_boost NUMERIC(4,2) DEFAULT 1.0,           -- 视觉加成倍数(默认 1.0,触发为 1.5)
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (auction_id, robot_id)
);
CREATE INDEX idx_bids_auction ON bids(auction_id, bid_value DESC);

-- ============ 12. human_interventions(HITL 审计) ============
CREATE TABLE human_interventions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    intervention_type VARCHAR(30) NOT NULL,          -- 'reassign'/'recall'/'cancel_task'/'algorithm_switch'
    target_task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    target_robot_id UUID REFERENCES robots(id) ON DELETE SET NULL,
    before_state JSONB NOT NULL,                     -- 见 §4.8
    after_state JSONB NOT NULL,
    reason TEXT NOT NULL,                            -- 干预原因(必填)
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT interventions_type_check CHECK (intervention_type IN ('reassign','recall','cancel_task','algorithm_switch'))
);
CREATE INDEX idx_interventions_user ON human_interventions(user_id, occurred_at DESC);
CREATE INDEX idx_interventions_task ON human_interventions(target_task_id);
CREATE INDEX idx_interventions_time ON human_interventions(occurred_at DESC);

-- ============ 13. blackboard_entries(高频写入) ============
CREATE TABLE blackboard_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(200) NOT NULL,                       -- 'survivor:120.51_30.21'
    value JSONB NOT NULL,                            -- 见 §4.9
    confidence NUMERIC(4,3) NOT NULL,                -- 0.000~1.000
    source_robot_id UUID REFERENCES robots(id) ON DELETE SET NULL,
    fused_from JSONB DEFAULT '[]',                   -- 见 §4.10
    expires_at TIMESTAMPTZ,                          -- TTL 控制
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_blackboard_key ON blackboard_entries(key);
CREATE INDEX idx_blackboard_active ON blackboard_entries(expires_at) WHERE expires_at > NOW();
CREATE INDEX idx_blackboard_value ON blackboard_entries USING GIN (value);

-- ============ 14. alerts ============
CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(50) UNIQUE NOT NULL,                -- 'ALERT-2024-018'
    type VARCHAR(50) NOT NULL,                       -- 'fire_detected'/'low_battery'/'task_overdue'/...
    severity VARCHAR(20) NOT NULL,                   -- 'info'/'warn'/'critical'
    source VARCHAR(100) NOT NULL,                    -- 来源标识(机器人编码/任务编码)
    message TEXT NOT NULL,
    payload JSONB DEFAULT '{}',                      -- 见 §4.11
    related_task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    related_robot_id UUID REFERENCES robots(id) ON DELETE SET NULL,
    raised_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by UUID REFERENCES users(id) ON DELETE SET NULL,
    is_ignored BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT alerts_severity_check CHECK (severity IN ('info','warn','critical'))
);
CREATE INDEX idx_alerts_unack ON alerts(raised_at DESC) WHERE acknowledged_at IS NULL AND is_ignored = FALSE;
CREATE INDEX idx_alerts_severity ON alerts(severity, raised_at DESC);

-- ============ 15. replay_sessions ============
CREATE TABLE replay_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    scenario_id UUID REFERENCES scenarios(id) ON DELETE SET NULL,
    algorithm VARCHAR(30) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    duration_sec INTEGER,
    completion_rate NUMERIC(5,2),
    summary JSONB DEFAULT '{}',                      -- 见 §4.12
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_replay_created ON replay_sessions(created_at DESC);

-- ============ 16. experiment_runs ============
CREATE TABLE experiment_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL,                          -- 同批次实验共享
    scenario_id UUID NOT NULL REFERENCES scenarios(id),
    algorithm VARCHAR(30) NOT NULL,
    run_index INTEGER NOT NULL,                      -- 1..10
    completion_rate NUMERIC(5,2),
    avg_response_sec NUMERIC(8,2),
    total_path_km NUMERIC(8,3),
    load_std_dev NUMERIC(6,3),
    decision_latency_ms INTEGER,
    raw_metrics JSONB DEFAULT '{}',                  -- 见 §4.13
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    UNIQUE (batch_id, algorithm, run_index)
);
CREATE INDEX idx_exp_batch ON experiment_runs(batch_id);
CREATE INDEX idx_exp_algo ON experiment_runs(algorithm, scenario_id);

-- ============ 17. scenarios ============
CREATE TABLE scenarios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,               -- '6 级地震演练'
    disaster_type VARCHAR(30) NOT NULL,              -- 'earthquake'/'forest_fire'/'flood'
    map_bounds JSONB NOT NULL,                       -- 见 §4.14
    initial_state JSONB NOT NULL,                    -- 见 §4.15
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============ 触发器:自动更新 updated_at ============
CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_timestamp_users BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();
CREATE TRIGGER set_timestamp_robots BEFORE UPDATE ON robots
  FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();
CREATE TRIGGER set_timestamp_tasks BEFORE UPDATE ON tasks
  FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();
CREATE TRIGGER set_timestamp_blackboard BEFORE UPDATE ON blackboard_entries
  FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();
```

---

## 2. 枚举类型清单(代码层定义)

> **说明**:为简化迁移,枚举值用 VARCHAR + CHECK 约束,而非 PostgreSQL ENUM。
> 后端代码中用 Python Enum 镜像如下:

```python
from enum import Enum

class RobotType(str, Enum):
    UAV = "uav"
    UGV = "ugv"
    USV = "usv"

class FSMState(str, Enum):
    IDLE = "IDLE"
    BIDDING = "BIDDING"
    EXECUTING = "EXECUTING"
    RETURNING = "RETURNING"
    FAULT = "FAULT"

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class TaskType(str, Enum):
    SEARCH_RESCUE = "search_rescue"
    RECON = "recon"
    TRANSPORT = "transport"
    PATROL = "patrol"

class TaskPriority(int, Enum):
    HIGH = 1
    MEDIUM = 2
    LOW = 3

class AuctionAlgorithm(str, Enum):
    HUNGARIAN = "AUCTION_HUNGARIAN"
    GREEDY = "GREEDY"
    RANDOM = "RANDOM"

class AuctionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    FAILED = "FAILED"

class InterventionType(str, Enum):
    REASSIGN = "reassign"
    RECALL = "recall"
    CANCEL_TASK = "cancel_task"
    ALGORITHM_SWITCH = "algorithm_switch"

class AlertSeverity(str, Enum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"

class FaultType(str, Enum):
    LOW_BATTERY = "low_battery"
    COMM_LOST = "comm_lost"
    SENSOR_ERROR = "sensor_error"
    COLLISION = "collision"
    UNKNOWN = "unknown"

class DisasterType(str, Enum):
    EARTHQUAKE = "earthquake"
    FOREST_FIRE = "forest_fire"
    FLOOD = "flood"

class YOLOClass(str, Enum):
    SURVIVOR = "survivor"
    COLLAPSED_BUILDING = "collapsed_building"
    SMOKE = "smoke"
    FIRE = "fire"
```

---

## 3. 状态机定义(强制转移规则)

> **完整规则参见 BUSINESS_RULES.md §2,本节仅给出状态枚举对照**

### 3.1 任务状态转移图

```
PENDING ──assign──► ASSIGNED ──start──► EXECUTING ──finish──► COMPLETED
   │                    │                    │
   │                    │                    ├──fail──► FAILED
   │                    │                    │
   ├──cancel──► CANCELLED ◄─────cancel───────┤
   │                                         │
   └──cancel──────────────────────────────────┘
```

### 3.2 机器人 FSM 状态转移图

```
IDLE ──recv_task──► BIDDING ──win──► EXECUTING ──finish──► RETURNING ──arrive──► IDLE
  │                    │                  │
  │                    └──lose──► IDLE    ├──fault──► FAULT
  │                                       │
  └──fault──► FAULT ◄─────────────────────┘
                │
                └──repair──► IDLE
```

---

## 4. JSONB 字段结构定义

> **核心约束**:JSONB 字段虽然 schemaless,但**应用层必须遵循以下结构**。
> 任何不符合此结构的写入都视为 bug。

### 4.1 `roles.permissions` — 权限列表

```typescript
// JSON Schema(伪代码)
type Permissions = string[];

// 示例
[
  "task:create",
  "task:cancel",
  "robot:reassign",
  "robot:recall",
  "algorithm:switch",
  "user:manage",
  "system:admin"
]

// 权限命名规范:{资源}:{动作},全小写
```

### 4.2 `robots.capability` — 机器人能力声明

```typescript
{
  sensors: string[],          // ["camera_4k", "thermal", "lidar"]
  payloads: string[],         // ["winch", "rescue_kit"]
  max_speed_mps: number,      // 23.0
  max_battery_min: number,    // 55
  max_range_km: number,       // 8.0
  has_yolo: boolean,          // 是否搭载 YOLO 推理(无人机为 true)
  weight_kg: number           // 自重
}

// 完整示例
{
  "sensors": ["camera_4k", "thermal"],
  "payloads": [],
  "max_speed_mps": 23.0,
  "max_battery_min": 55,
  "max_range_km": 8.0,
  "has_yolo": true,
  "weight_kg": 6.3
}
```

### 4.3 `robot_states.position` — 位置信息(WGS84)

```typescript
{
  lat: number,         // -90.0 ~ 90.0,精度 6 位
  lng: number,         // -180.0 ~ 180.0,精度 6 位
  altitude_m?: number, // 海拔(无人机使用,可选)
  heading_deg?: number // 朝向 0-359(可选)
}

// 示例
{ "lat": 30.123456, "lng": 120.654321, "altitude_m": 50.5, "heading_deg": 45 }
```

### 4.4 `robot_states.sensor_data` — 传感器数据(含 YOLO 结果)

```typescript
{
  // 通用字段(可选,根据机器人类型出现)
  temperature_c?: number,
  humidity_pct?: number,
  signal_dbm?: number,

  // 视觉感知(YOLO 推理结果),仅 has_yolo=true 的机器人上报
  vision?: {
    frame_id: string,            // 帧标识
    inference_time_ms: number,   // 推理耗时
    detections: Detection[]      // 检测结果
  },

  // 其他自定义字段(扩展点)
  [key: string]: any
}

// Detection 结构
type Detection = {
  class_id: number,              // 0~3
  class_name: "survivor" | "collapsed_building" | "smoke" | "fire",
  confidence: number,            // 0.0~1.0
  bbox: [number, number, number, number],   // [x1,y1,x2,y2] 像素坐标
  world_position?: { lat: number, lng: number }  // 世界坐标(若可解算)
}

// 完整示例
{
  "temperature_c": 28.5,
  "signal_dbm": -58,
  "vision": {
    "frame_id": "UAV-001-20260425-143218-001",
    "inference_time_ms": 25,
    "detections": [
      {
        "class_id": 0,
        "class_name": "survivor",
        "confidence": 0.92,
        "bbox": [342, 156, 460, 380],
        "world_position": { "lat": 30.21, "lng": 120.51 }
      }
    ]
  }
}
```

### 4.5 `tasks.target_area` — 目标区域

```typescript
{
  type: "rectangle" | "polygon" | "circle",

  // type=rectangle 时
  bounds?: {
    sw: { lat: number, lng: number },   // 西南角
    ne: { lat: number, lng: number }    // 东北角
  },

  // type=polygon 时
  vertices?: { lat: number, lng: number }[],

  // type=circle 时
  center?: { lat: number, lng: number },
  radius_m?: number,

  // 通用
  area_km2: number,           // 面积(预计算,方便排序)
  center_point: { lat: number, lng: number }  // 中心点(预计算)
}

// 完整示例
{
  "type": "rectangle",
  "bounds": {
    "sw": { "lat": 30.20, "lng": 120.50 },
    "ne": { "lat": 30.25, "lng": 120.55 }
  },
  "area_km2": 5.0,
  "center_point": { "lat": 30.225, "lng": 120.525 }
}
```

### 4.6 `tasks.required_capabilities` — 任务所需能力

```typescript
{
  sensors: string[],          // 必须具备的传感器
  payloads: string[],         // 必须具备的载荷
  min_battery_pct?: number,   // 最低电量要求(默认 20)
  robot_type?: ("uav"|"ugv"|"usv")[]  // 限定类型
}

// 示例
{
  "sensors": ["camera_4k", "thermal"],
  "payloads": [],
  "min_battery_pct": 30,
  "robot_type": ["uav"]
}
```

### 4.7 `bids.breakdown` — 出价分解

```typescript
{
  base_score: number,          // 基础得分(归一化前)
  components: {
    distance: { value: number, weighted: number },  // 距离项
    battery: { value: number, weighted: number },   // 电量项
    capability: { value: number, weighted: number },// 能力匹配项
    load: { value: number, weighted: number }       // 负载惩罚项
  },
  vision_boosted: boolean,     // 是否触发视觉加成
  final_bid: number            // 最终出价值
}

// 示例
{
  "base_score": 0.72,
  "components": {
    "distance": { "value": 0.85, "weighted": 0.34 },
    "battery": { "value": 0.78, "weighted": 0.156 },
    "capability": { "value": 1.0, "weighted": 0.30 },
    "load": { "value": 0.2, "weighted": 0.02 }
  },
  "vision_boosted": true,
  "final_bid": 1.08
}
```

### 4.8 `human_interventions.before_state` / `after_state` — HITL 状态快照

```typescript
{
  // 改派场景
  task_id?: string,
  task_code?: string,
  assigned_robot_ids: string[],
  algorithm_used?: string,

  // 召回场景
  robot_id?: string,
  robot_code?: string,
  robot_state?: string,        // FSM 状态
  current_task_id?: string,

  // 算法切换场景
  algorithm_name?: string,

  // 时间戳
  timestamp: string            // ISO 8601
}

// 示例(改派 before)
{
  "task_id": "uuid-aaa",
  "task_code": "T-2024-001",
  "assigned_robot_ids": ["uuid-r1"],
  "algorithm_used": "AUCTION_HUNGARIAN",
  "timestamp": "2026-04-25T14:32:18Z"
}

// 示例(改派 after)
{
  "task_id": "uuid-aaa",
  "task_code": "T-2024-001",
  "assigned_robot_ids": ["uuid-r2"],
  "algorithm_used": "MANUAL_OVERRIDE",
  "timestamp": "2026-04-25T14:32:25Z"
}
```

### 4.9 `blackboard_entries.value` — 黑板条目值

```typescript
{
  type: "survivor" | "fire" | "smoke" | "collapsed_building" | "weather" | "custom",
  position?: { lat: number, lng: number },

  // type=fire 专属
  area_m2?: number,
  intensity?: "low" | "medium" | "high",

  // type=survivor 专属
  detected_count?: number,

  // 通用扩展
  [key: string]: any
}

// 示例
{
  "type": "fire",
  "position": { "lat": 30.18, "lng": 120.62 },
  "area_m2": 120,
  "intensity": "high"
}
```

### 4.10 `blackboard_entries.fused_from` — 融合来源审计

```typescript
[
  {
    robot_id: string,
    confidence: number,
    timestamp: string,        // ISO 8601
    weight: number            // 融合权重(0~1,所有 weight 之和=1)
  }
]

// 示例
[
  { "robot_id": "uuid-uav-001", "confidence": 0.92, "timestamp": "2026-04-25T14:32:15Z", "weight": 0.55 },
  { "robot_id": "uuid-ugv-002", "confidence": 0.88, "timestamp": "2026-04-25T14:32:30Z", "weight": 0.45 }
]
```

### 4.11 `alerts.payload` — 告警载荷

```typescript
{
  // YOLO 触发的告警
  yolo_detection?: {
    class_name: string,
    confidence: number,
    source_robot: string,
    position: { lat: number, lng: number }
  },

  // 电量告警
  battery_alert?: {
    current_pct: number,
    threshold_pct: number
  },

  // SLA 超时告警
  sla_alert?: {
    task_code: string,
    deadline: string,
    overdue_min: number
  },

  // 自由扩展
  [key: string]: any
}
```

### 4.12 `replay_sessions.summary` — 复盘汇总

```typescript
{
  total_tasks: number,
  completed_tasks: number,
  failed_tasks: number,
  total_robots_used: number,
  total_interventions: number,
  total_alerts: number,
  yolo_detections_summary: {
    survivor: number,
    fire: number,
    smoke: number,
    collapsed_building: number
  }
}
```

### 4.13 `experiment_runs.raw_metrics` — 原始实验指标

```typescript
{
  per_robot_load: { robot_id: string, task_count: number }[],
  per_task_response_sec: { task_id: string, response_sec: number }[],
  total_decisions: number,
  hitl_interventions: number,
  vision_assisted_count: number   // 触发视觉加成的次数
}
```

### 4.14 `scenarios.map_bounds` — 场景地图范围

```typescript
{
  sw: { lat: number, lng: number },
  ne: { lat: number, lng: number },
  center: { lat: number, lng: number },
  zoom_default: number          // 默认缩放级别 1-18
}
```

### 4.15 `scenarios.initial_state` — 场景初始化状态

```typescript
{
  robots: {
    code: string,                       // 机器人编码
    initial_position: { lat: number, lng: number },
    initial_battery: number             // 0-100
  }[],
  preset_tasks?: {                      // 可选,预设任务
    code: string,
    name: string,
    type: TaskType,
    priority: number,
    target_area: TargetArea,
    spawn_at_sec: number                // 场景启动后多少秒生成
  }[],
  weather?: {
    visibility_km: number,
    wind_mps: number,
    precipitation: "none" | "rain" | "snow"
  }
}
```

---

## 5. Pydantic Schema 草案

> **位置**:这些 Schema 应放在 `backend/app/schemas/` 目录下,按模块拆分文件。
> **原则**:与 ORM 模型分离,Schema 用于 API 入参/出参,不直接映射数据库。

```python
# backend/app/schemas/common.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Literal, Any
from datetime import datetime
from uuid import UUID
from decimal import Decimal


class Position(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    altitude_m: Optional[float] = None
    heading_deg: Optional[float] = Field(None, ge=0, lt=360)


class TargetArea(BaseModel):
    type: Literal["rectangle", "polygon", "circle"]
    bounds: Optional[dict] = None
    vertices: Optional[List[Position]] = None
    center: Optional[Position] = None
    radius_m: Optional[float] = None
    area_km2: float
    center_point: Position


class RobotCapability(BaseModel):
    sensors: List[str] = []
    payloads: List[str] = []
    max_speed_mps: float
    max_battery_min: int
    max_range_km: float
    has_yolo: bool = False
    weight_kg: float


class Detection(BaseModel):
    class_id: int = Field(..., ge=0, le=3)
    class_name: Literal["survivor", "collapsed_building", "smoke", "fire"]
    confidence: float = Field(..., ge=0, le=1)
    bbox: List[float] = Field(..., min_items=4, max_items=4)
    world_position: Optional[Position] = None


class VisionData(BaseModel):
    frame_id: str
    inference_time_ms: int
    detections: List[Detection]


class SensorData(BaseModel):
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    signal_dbm: Optional[float] = None
    vision: Optional[VisionData] = None
    model_config = ConfigDict(extra="allow")  # 允许扩展字段


# ==================== Robot Schemas ====================
# backend/app/schemas/robot.py

class RobotBase(BaseModel):
    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=100)
    type: Literal["uav", "ugv", "usv"]
    model: Optional[str] = None
    capability: RobotCapability
    group_id: Optional[UUID] = None


class RobotCreate(RobotBase):
    pass


class RobotUpdate(BaseModel):
    name: Optional[str] = None
    capability: Optional[RobotCapability] = None
    group_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class RobotRead(RobotBase):
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class RobotStateRead(BaseModel):
    id: int
    robot_id: UUID
    recorded_at: datetime
    fsm_state: Literal["IDLE", "BIDDING", "EXECUTING", "RETURNING", "FAULT"]
    position: Position
    battery: float = Field(..., ge=0, le=100)
    sensor_data: SensorData
    current_task_id: Optional[UUID] = None
    model_config = ConfigDict(from_attributes=True)


# ==================== Task Schemas ====================
# backend/app/schemas/task.py

class TaskRequiredCapabilities(BaseModel):
    sensors: List[str] = []
    payloads: List[str] = []
    min_battery_pct: float = 20.0
    robot_type: Optional[List[Literal["uav", "ugv", "usv"]]] = None


class TaskCreate(BaseModel):
    name: str = Field(..., max_length=200)
    type: Literal["search_rescue", "recon", "transport", "patrol"]
    priority: Literal[1, 2, 3] = 2
    target_area: TargetArea
    required_capabilities: TaskRequiredCapabilities
    sla_deadline: Optional[datetime] = None


class TaskRead(BaseModel):
    id: UUID
    code: str
    name: str
    type: str
    priority: int
    status: str
    target_area: TargetArea
    required_capabilities: TaskRequiredCapabilities
    parent_id: Optional[UUID] = None
    progress: float
    sla_deadline: Optional[datetime] = None
    created_by: UUID
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    priority: Optional[Literal[1, 2, 3]] = None
    sla_deadline: Optional[datetime] = None


# ==================== Auction / Bid Schemas ====================
# backend/app/schemas/dispatch.py

class BidBreakdownComponent(BaseModel):
    value: float
    weighted: float


class BidBreakdown(BaseModel):
    base_score: float
    components: dict[str, BidBreakdownComponent]
    vision_boosted: bool
    final_bid: float


class BidRead(BaseModel):
    id: UUID
    auction_id: UUID
    robot_id: UUID
    bid_value: float
    breakdown: BidBreakdown
    vision_boost: float
    submitted_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AuctionRead(BaseModel):
    id: UUID
    task_id: UUID
    algorithm: Literal["AUCTION_HUNGARIAN", "GREEDY", "RANDOM"]
    status: Literal["OPEN", "CLOSED", "FAILED"]
    started_at: datetime
    closed_at: Optional[datetime] = None
    winner_robot_id: Optional[UUID] = None
    decision_latency_ms: Optional[int] = None
    bids: List[BidRead] = []
    model_config = ConfigDict(from_attributes=True)


class ReassignRequest(BaseModel):
    task_id: UUID
    new_robot_id: UUID
    reason: str = Field(..., min_length=5, max_length=500)


class RecallRequest(BaseModel):
    robot_id: UUID
    reason: str = Field(..., min_length=5, max_length=500)


class AlgorithmSwitchRequest(BaseModel):
    algorithm: Literal["AUCTION_HUNGARIAN", "GREEDY", "RANDOM"]
    reason: str = Field(..., min_length=5, max_length=500)


# ==================== Intervention Schemas ====================
# backend/app/schemas/intervention.py

class InterventionRead(BaseModel):
    id: UUID
    user_id: UUID
    intervention_type: Literal["reassign", "recall", "cancel_task", "algorithm_switch"]
    target_task_id: Optional[UUID] = None
    target_robot_id: Optional[UUID] = None
    before_state: dict
    after_state: dict
    reason: str
    occurred_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ==================== Alert Schemas ====================
# backend/app/schemas/alert.py

class AlertRead(BaseModel):
    id: UUID
    code: str
    type: str
    severity: Literal["info", "warn", "critical"]
    source: str
    message: str
    payload: dict
    related_task_id: Optional[UUID] = None
    related_robot_id: Optional[UUID] = None
    raised_at: datetime
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[UUID] = None
    is_ignored: bool
    model_config = ConfigDict(from_attributes=True)


class AlertAcknowledgeRequest(BaseModel):
    alert_id: UUID
    note: Optional[str] = None


# ==================== Blackboard Schemas ====================
# backend/app/schemas/blackboard.py

class BlackboardValue(BaseModel):
    type: Literal["survivor", "fire", "smoke", "collapsed_building", "weather", "custom"]
    position: Optional[Position] = None
    area_m2: Optional[float] = None
    intensity: Optional[Literal["low", "medium", "high"]] = None
    detected_count: Optional[int] = None
    model_config = ConfigDict(extra="allow")


class FusionSource(BaseModel):
    robot_id: UUID
    confidence: float
    timestamp: datetime
    weight: float


class BlackboardEntryRead(BaseModel):
    id: UUID
    key: str
    value: BlackboardValue
    confidence: float
    source_robot_id: Optional[UUID] = None
    fused_from: List[FusionSource] = []
    expires_at: Optional[datetime] = None
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ==================== Auth Schemas ====================
# backend/app/schemas/auth.py

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # 秒


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class CurrentUser(BaseModel):
    id: UUID
    username: str
    display_name: str
    roles: List[str]
    permissions: List[str]


# ==================== Error Schemas ====================
# backend/app/schemas/error.py

class ErrorDetail(BaseModel):
    field: Optional[str] = None
    code: str
    message: str


class ErrorResponse(BaseModel):
    code: str               # 业务错误码,如 "400_TASK_INVALID_AREA_001"
    message: str            # 给用户看的友好消息
    details: List[ErrorDetail] = []
    request_id: str         # 全链路追踪 ID
    timestamp: datetime
```

---

## 6. 数据约束与不变量(Invariants)

> 这些约束**应用层必须保证**,数据库 CHECK 不一定能覆盖。

| # | 约束 | 检查时机 | 违反处理 |
|---|---|---|---|
| INV-1 | 一个机器人在同一时刻最多有一个 active task_assignment(`is_active=TRUE`)| 任务分配时 | 抛 ConflictError(409)|
| INV-2 | 一个任务在 ASSIGNED/EXECUTING 状态下,必须至少有一个 active task_assignment | 状态转移时 | 抛 IntegrityError |
| INV-3 | `robot_states.battery` 不能从 50% 跳变到 0%(单步降幅 ≤ 5%) | 状态写入时 | 标记为可疑数据,记日志 |
| INV-4 | `human_interventions.reason` 必填且 ≥ 5 字符 | API 入参校验 | 422 Validation Error |
| INV-5 | `blackboard_entries.confidence` 必须在 [0.5, 1.0](< 0.5 不应入库) | 写入时 | 拒绝写入,记录被丢弃事件 |
| INV-6 | `tasks.target_area.area_km2` 必须 > 0 | 创建时 | 422 |
| INV-7 | `auctions.decision_latency_ms` 不应 > 5000(超过视为算法异常) | 拍卖关闭时 | 触发 critical 告警 |
| INV-8 | 同一个 `experiment_runs.batch_id` 内,同算法的 `run_index` 必须连续 1..N | 实验完成时 | 标记 batch 不完整 |

---

## 7. 索引策略说明

| 索引名 | 用途 | 选择性 |
|---|---|---|
| `idx_users_username` | 登录查询 | 高 |
| `idx_robots_capability` (GIN) | 按能力筛选机器人(JSONB GIN)| 中 |
| `idx_robot_states_robot_time` | 时序查询(最近 N 条)| 高 |
| `idx_robot_states_sensor` (GIN) | 按 YOLO 检测结果筛选 | 中 |
| `idx_tasks_status` | 任务列表分组展示 | 中 |
| `idx_tasks_priority` (partial) | 待分配任务按优先级排序 | 高 |
| `idx_blackboard_active` (partial) | 仅查询未过期黑板条目 | 高 |
| `idx_alerts_unack` (partial) | 待处理告警查询(高频)| 高 |

---

## 8. 数据生命周期管理

| 表 | 保留策略 |
|---|---|
| `robot_states` | 保留 30 天,之后归档(可写定时任务)|
| `blackboard_entries` | 按 `expires_at` 自动失效,每天清理过期 7 天以上的 |
| `alerts` | 永久保留(审计要求)|
| `human_interventions` | **永久保留**(审计强制)|
| `experiment_runs` | 永久保留(论文用)|
| `replay_sessions` | 永久保留 |

---

**END OF DATA_CONTRACTS.md**
