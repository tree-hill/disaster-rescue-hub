# API_SPEC.md — REST API 规范

> **文档定位**:本文档定义所有 HTTP REST 接口的契约。
> **依赖**:本文档中所有 schema 引用均指向 `DATA_CONTRACTS.md` §5。
> **版本**:v1.0

---

## 0. 通用约定

### 0.1 基础信息
- **Base URL**:`http://localhost:8000/api/v1`(开发环境)
- **协议**:HTTP/1.1(开发)→ HTTPS(生产)
- **Content-Type**:`application/json`(请求和响应统一)
- **字符编码**:UTF-8

### 0.2 认证
- **方案**:JWT Bearer Token
- **Header**:`Authorization: Bearer <access_token>`
- **过期**:Access Token 24h,Refresh Token 7d
- **公开接口**(无需认证):`/auth/login`, `/auth/refresh`, `/health`
- **其他接口**:全部需要认证

### 0.3 统一响应格式

**成功响应**(HTTP 2xx):
直接返回数据本身或数据数组,不包裹。
```json
// GET /robots/{id} 成功
{
  "id": "uuid-xxx",
  "code": "UAV-001",
  ...
}

// GET /robots 列表成功(分页)
{
  "items": [...],
  "total": 25,
  "page": 1,
  "page_size": 20
}
```

**错误响应**(HTTP 4xx/5xx):
统一使用 `ErrorResponse` schema(见 DATA_CONTRACTS §5)。
```json
{
  "code": "404_TASK_NOT_FOUND_001",
  "message": "任务不存在或已被删除",
  "details": [],
  "request_id": "req-20260425-143218-abc123",
  "timestamp": "2026-04-25T14:32:18Z"
}
```

### 0.4 状态码使用规范

| HTTP 码 | 使用场景 |
|---|---|
| 200 | GET / PUT 成功 |
| 201 | POST 成功创建资源 |
| 204 | DELETE 成功(无响应体)|
| 400 | 业务逻辑错误(如状态不允许转移)|
| 401 | 未认证或 Token 失效 |
| 403 | 已认证但权限不足 |
| 404 | 资源不存在 |
| 409 | 资源冲突(如重复创建)|
| 422 | 入参校验失败(Pydantic 自动)|
| 500 | 服务器内部错误 |
| 503 | 服务暂时不可用(如数据库挂掉)|

### 0.5 业务错误码命名规范

格式:`{HTTP状态}_{领域}_{子类型}_{序号}`

| 错误码示例 | 含义 |
|---|---|
| `400_TASK_INVALID_AREA_001` | 任务区域参数非法 |
| `404_ROBOT_NOT_FOUND_001` | 机器人不存在 |
| `409_TASK_STATUS_CONFLICT_001` | 任务状态不允许此操作 |
| `403_PERMISSION_DENIED_001` | 权限不足 |
| `422_VALIDATION_FAILED_001` | 入参校验失败 |

完整错误码清单见 `BUSINESS_RULES.md §6`。

### 0.6 分页规范

所有 List 接口支持以下 query 参数:
- `page` int 默认 1,从 1 起
- `page_size` int 默认 20,最大 100
- `sort` string 默认按 `created_at desc`,格式如 `created_at:desc,priority:asc`

### 0.7 过滤规范

GET 列表接口可接受过滤参数(见各接口具体定义)。多值用逗号分隔:`status=PENDING,EXECUTING`。

### 0.8 请求追踪

每个请求必须返回 `X-Request-Id` Header(后端自动生成 UUID)。前端在错误提示中展示该 ID,便于排查。

---

## 1. 认证模块(/auth)

### POST /auth/login
**功能**:用户登录,获取 Token。

| 项 | 内容 |
|---|---|
| 公开 | 是 |
| 请求体 | `LoginRequest`(username, password)|
| 200 响应 | `TokenResponse` |
| 401 响应 | `401_AUTH_INVALID_CREDENTIAL_001`:用户名或密码错误 |
| 423 响应 | `423_AUTH_ACCOUNT_LOCKED_001`:账号锁定(连续 5 次失败) |

### POST /auth/refresh
**功能**:用 Refresh Token 换新的 Access Token。

| 项 | 内容 |
|---|---|
| 公开 | 是 |
| 请求体 | `RefreshTokenRequest` |
| 200 响应 | `TokenResponse` |
| 401 响应 | Refresh Token 失效 |

### GET /auth/me
**功能**:获取当前登录用户信息。

| 项 | 内容 |
|---|---|
| 公开 | 否 |
| 200 响应 | `CurrentUser` |

### POST /auth/logout
**功能**:登出(将 Token 加入黑名单)。

| 项 | 内容 |
|---|---|
| 公开 | 否 |
| 204 响应 | 无 |

---

## 2. 机器人模块(/robots)

### GET /robots
**功能**:获取机器人列表(分页)。

| 项 | 内容 |
|---|---|
| Query | `type`, `status`(=fsm_state), `group_id`, `search`(模糊搜索 code/name), `page`, `page_size`, `sort` |
| 200 响应 | `{items: RobotRead[], total, page, page_size}` |
| 权限 | `robot:read` |

### GET /robots/{id}
**功能**:获取单个机器人详情。

| 项 | 内容 |
|---|---|
| 200 响应 | `RobotRead` + 嵌入最新 `RobotStateRead` |
| 404 | 机器人不存在 |
| 权限 | `robot:read` |

### POST /robots
**功能**:注册新机器人。

| 项 | 内容 |
|---|---|
| 请求体 | `RobotCreate` |
| 201 响应 | `RobotRead` |
| 409 | code 重复 |
| 权限 | `robot:manage` |

### PUT /robots/{id}
**功能**:更新机器人配置。

| 项 | 内容 |
|---|---|
| 请求体 | `RobotUpdate` |
| 200 响应 | `RobotRead` |
| 权限 | `robot:manage` |

### DELETE /robots/{id}
**功能**:注销机器人(软删除,设置 `is_active=FALSE`)。

| 项 | 内容 |
|---|---|
| 204 响应 | 无 |
| 409 | 机器人有正在执行的任务 |
| 权限 | `robot:manage` |

### POST /robots/{id}/recall
**功能**:紧急召回机器人(HITL 操作)。

| 项 | 内容 |
|---|---|
| 请求体 | `{reason: string}` |
| 200 响应 | `{intervention_id: UUID, recall_eta_sec: number}` |
| 副作用 | 写 `human_interventions` 表;广播 WS 事件 `robot.recall_initiated` |
| 权限 | `robot:recall` |

### GET /robots/{id}/states
**功能**:获取机器人历史状态时序。

| 项 | 内容 |
|---|---|
| Query | `start_time`, `end_time`, `limit`(默认 100,最大 1000)|
| 200 响应 | `RobotStateRead[]` |
| 权限 | `robot:read` |

### GET /robots/{id}/faults
**功能**:获取机器人故障历史。

| 项 | 内容 |
|---|---|
| Query | `unresolved_only`(bool,默认 false)|
| 200 响应 | `FaultRead[]` |
| 权限 | `robot:read` |

---

## 3. 任务模块(/tasks)

### GET /tasks
**功能**:获取任务列表。

| 项 | 内容 |
|---|---|
| Query | `status`(可多选), `priority`, `type`, `created_by`, `search`, `page`, `page_size`, `sort` |
| 200 响应 | `{items: TaskRead[], total, page, page_size}` |
| 权限 | `task:read` |

### GET /tasks/{id}
**功能**:获取任务详情。

| 项 | 内容 |
|---|---|
| 200 响应 | `TaskRead` + `assignments: TaskAssignmentRead[]` + `auctions: AuctionRead[]`(摘要)|
| 权限 | `task:read` |

### POST /tasks
**功能**:创建任务,自动触发拍卖。

| 项 | 内容 |
|---|---|
| 请求体 | `TaskCreate` |
| 201 响应 | `TaskRead`(含 `code`)|
| 副作用 | 1. 写 `tasks` 表 2. 若 `area_km2 > 1`,自动分解子任务 3. 触发拍卖(异步)4. 广播 WS 事件 `task.created` |
| 422 | 区域非法 / 必填字段缺失 |
| 权限 | `task:create` |

### PUT /tasks/{id}
**功能**:更新任务(仅允许修改 name/priority/sla_deadline,且任务非 COMPLETED/CANCELLED 状态)。

| 项 | 内容 |
|---|---|
| 请求体 | `TaskUpdate` |
| 200 响应 | `TaskRead` |
| 409 | 任务状态不允许修改 |
| 权限 | `task:update` |

### POST /tasks/{id}/cancel
**功能**:取消任务(HITL 操作)。

| 项 | 内容 |
|---|---|
| 请求体 | `{reason: string}` |
| 200 响应 | `TaskRead` |
| 副作用 | 1. 状态转 CANCELLED 2. 释放所有 assignment 3. 写 intervention 4. 广播 `task.cancelled` |
| 409 | 已 COMPLETED/CANCELLED 不能再取消 |
| 权限 | `task:cancel` |

### GET /tasks/{id}/assignments
**功能**:获取任务的所有分配历史(含改派记录)。

| 项 | 内容 |
|---|---|
| 200 响应 | `TaskAssignmentRead[]`(按时间倒序)|
| 权限 | `task:read` |

---

## 4. 调度模块(/dispatch)

### POST /dispatch/auction
**功能**:手动触发拍卖(自动触发由系统内部完成)。

| 项 | 内容 |
|---|---|
| 请求体 | `{task_id: UUID}` |
| 201 响应 | `AuctionRead` |
| 409 | 任务非 PENDING 状态 |
| 权限 | `task:create` |

### POST /dispatch/reassign
**功能**:HITL 改派 —— 把任务从机器人 A 改派给机器人 B。

| 项 | 内容 |
|---|---|
| 请求体 | `ReassignRequest` |
| 200 响应 | `{task: TaskRead, intervention_id: UUID}` |
| 409 | 新机器人不可用 / 任务状态不允许改派 |
| 副作用 | 1. 释放原 assignment 2. 创建新 assignment 3. 写 intervention 4. 广播 `task.reassigned` |
| 权限 | `robot:reassign` |

### GET /dispatch/algorithm
**功能**:获取当前生效的调度算法。

| 项 | 内容 |
|---|---|
| 200 响应 | `{current: "AUCTION_HUNGARIAN", available: ["AUCTION_HUNGARIAN", "GREEDY", "RANDOM"]}` |

### POST /dispatch/algorithm
**功能**:切换调度算法(HITL 操作)。

| 项 | 内容 |
|---|---|
| 请求体 | `AlgorithmSwitchRequest` |
| 200 响应 | `{previous: "GREEDY", current: "AUCTION_HUNGARIAN", intervention_id: UUID}` |
| 权限 | `algorithm:switch` |

### GET /dispatch/auctions
**功能**:获取拍卖会话历史。

| 项 | 内容 |
|---|---|
| Query | `task_id`, `algorithm`, `start_time`, `end_time`, `page`, `page_size` |
| 200 响应 | `{items: AuctionRead[], total, ...}` |
| 权限 | `task:read` |

### GET /dispatch/auctions/{id}
**功能**:获取单次拍卖详情(含所有出价)。

| 项 | 内容 |
|---|---|
| 200 响应 | `AuctionRead`(含 `bids: BidRead[]`)|
| 权限 | `task:read` |

---

## 5. 协同通信模块(/blackboard)

### GET /blackboard/entries
**功能**:查询黑板条目。

| 项 | 内容 |
|---|---|
| Query | `type`(survivor/fire/...), `key_prefix`, `min_confidence`(默认 0.5), `include_expired`(bool,默认 false), `page`, `page_size` |
| 200 响应 | `{items: BlackboardEntryRead[], total, ...}` |
| 权限 | `blackboard:read` |

### GET /blackboard/entries/{key}
**功能**:按 key 精确查询单个条目。

| 项 | 内容 |
|---|---|
| 200 响应 | `BlackboardEntryRead` |
| 404 | key 不存在或已过期 |

### GET /blackboard/stats
**功能**:获取黑板统计数据(用于黑板可视化页 KPI)。

| 项 | 内容 |
|---|---|
| 200 响应 | `{total_entries, by_type: {...}, active_subscribers, avg_fusion_latency_ms, throughput_per_min}` |

### POST /perception/infer
**功能**:Mock 视觉感知推理(开发/测试用)。生产中由机器人 Agent 内部调用,不暴露 HTTP。

| 项 | 内容 |
|---|---|
| 请求体 | `{robot_id: UUID, image_base64: string, position: Position}` |
| 200 响应 | `{detections: Detection[], inference_time_ms: number}` |
| 副作用 | 写黑板 + 可能触发告警 |
| 权限 | `system:test` |

---

## 6. 态势感知模块(/situation)

### GET /situation/kpi
**功能**:获取实时 KPI(指挥工作台顶条用)。

| 项 | 内容 |
|---|---|
| 200 响应 | `{online_robots: int, total_robots: int, completion_rate: float, avg_response_sec: float, battery_distribution: {high: int, mid: int, low: int}, active_alerts: int}` |

### GET /alerts
**功能**:获取告警列表。

| 项 | 内容 |
|---|---|
| Query | `severity`, `type`, `source`, `status`(unack/ack/ignored), `start_time`, `end_time`, `search`, `page`, `page_size` |
| 200 响应 | `{items: AlertRead[], total, ...}` |
| 权限 | `alert:read` |

### GET /alerts/{id}
**功能**:获取告警详情。

| 项 | 内容 |
|---|---|
| 200 响应 | `AlertRead` |

### POST /alerts/{id}/acknowledge
**功能**:确认告警(HITL)。

| 项 | 内容 |
|---|---|
| 请求体 | `{note?: string}` |
| 200 响应 | `AlertRead`(更新 `acknowledged_at` / `acknowledged_by`)|
| 副作用 | 广播 `alert.acknowledged` |
| 权限 | `alert:handle` |

### POST /alerts/{id}/ignore
**功能**:忽略告警。

| 项 | 内容 |
|---|---|
| 请求体 | `{reason: string}` |
| 200 响应 | `AlertRead`(`is_ignored=TRUE`)|
| 权限 | `alert:handle` |

### POST /alerts/batch-acknowledge
**功能**:批量确认。

| 项 | 内容 |
|---|---|
| 请求体 | `{alert_ids: UUID[]}` |
| 200 响应 | `{acknowledged: int, failed: int}` |
| 权限 | `alert:handle` |

---

## 7. 复盘与分析模块(/replay, /experiments)

### GET /replay/sessions
**功能**:获取回放会话列表。

| 项 | 内容 |
|---|---|
| Query | `start_time`, `end_time`, `algorithm`, `scenario_id`, `page`, `page_size` |
| 200 响应 | `{items: ReplaySessionRead[], total, ...}` |
| 权限 | `replay:read` |

### GET /replay/sessions/{id}
**功能**:获取回放会话详情。

| 项 | 内容 |
|---|---|
| 200 响应 | `ReplaySessionRead`(含 `summary` 详细字段)|

### GET /replay/sessions/{id}/snapshots
**功能**:获取回放快照流(分页流式拉取)。

| 项 | 内容 |
|---|---|
| Query | `start_time`, `end_time`, `interval_sec`(默认 1)|
| 200 响应 | `Snapshot[]`(每个快照含 robots 状态 / tasks 状态 / blackboard)|
| 权限 | `replay:read` |

### GET /replay/sessions/{id}/key-events
**功能**:获取关键事件时间轴(干预/告警/任务完成等)。

| 项 | 内容 |
|---|---|
| 200 响应 | `KeyEvent[]`(含 type, timestamp, description, related_id)|

### POST /experiments
**功能**:启动一次对比实验。

| 项 | 内容 |
|---|---|
| 请求体 | `{scenario_id: UUID, algorithms: ["AUCTION_HUNGARIAN", "GREEDY", "RANDOM"], repetitions: 10}` |
| 202 响应 | `{batch_id: UUID, status: "running", estimated_duration_sec: int}` |
| 副作用 | 异步执行 N 次,结果写 `experiment_runs` |
| 权限 | `experiment:run` |

### GET /experiments/{batch_id}
**功能**:获取实验批次状态与结果。

| 项 | 内容 |
|---|---|
| 200 响应 | `{batch_id, status: "running"|"completed"|"failed", progress_pct, runs: ExperimentRunRead[], stats: {...}}` |

### GET /experiments/{batch_id}/charts
**功能**:获取实验图表数据(供前端 ECharts 渲染)。

| 项 | 内容 |
|---|---|
| 200 响应 | `{completion_rate_chart: ChartData, response_time_chart: ChartData, path_length_chart: ChartData, load_balance_chart: ChartData, decision_latency_chart: ChartData}` |

### GET /experiments/{batch_id}/export
**功能**:导出实验结果。

| 项 | 内容 |
|---|---|
| Query | `format=csv\|json` |
| 200 响应 | 文件下载 |

---

## 8. 系统管理模块(/admin)

### GET /admin/users
**功能**:用户列表。

| 项 | 内容 |
|---|---|
| 权限 | `user:manage` |
| Query | 分页/搜索 |
| 200 响应 | `UserRead[]` |

### POST /admin/users
**功能**:创建用户。

| 项 | 内容 |
|---|---|
| 请求体 | `UserCreate(username, password, display_name, email, role_ids)` |
| 201 响应 | `UserRead` |
| 权限 | `user:manage` |

### PUT /admin/users/{id}
**功能**:更新用户。
| 权限 | `user:manage` |

### DELETE /admin/users/{id}
**功能**:停用用户(`is_active=FALSE`)。
| 权限 | `user:manage` |

### GET /admin/roles
**功能**:角色列表(系统预置 commander/admin/observer)。

### GET /admin/scenarios
**功能**:场景列表。

### POST /admin/scenarios
**功能**:创建场景。

### GET /admin/interventions
**功能**:HITL 干预审计查询。

| 项 | 内容 |
|---|---|
| Query | `user_id`, `intervention_type`, `start_time`, `end_time`, `page`, `page_size` |
| 200 响应 | `{items: InterventionRead[], total, ...}` |
| 权限 | `audit:read` |

---

## 9. 系统健康与运维(/system)

### GET /health
**功能**:健康检查(K8s liveness probe 用)。
- 公开
- 200:`{status: "ok", db: "ok", version: "1.0.0"}`

### GET /system/info
**功能**:系统信息。
- 200:`{version, build_time, env: "dev"|"prod", scenario_loaded: string}`

### GET /system/metrics
**功能**:Prometheus 格式指标(可选,运维用)。
- Content-Type: `text/plain`

---

## 10. 接口分组优先级(Vibe Coding 时按此顺序实现)

| 优先级 | 模块 | 关键接口 |
|---|---|---|
| **P0** | 认证 | `/auth/login`, `/auth/me` |
| **P0** | 机器人 | `/robots` (GET/POST), `/robots/{id}/states` |
| **P0** | 任务 | `/tasks` (GET/POST), `/tasks/{id}/cancel` |
| **P0** | 调度 | `/dispatch/auction`, `/dispatch/reassign` |
| **P0** | 实时通信 | WebSocket(见 WS_EVENTS.md)|
| **P1** | 协同通信 | `/blackboard/entries`, `/perception/infer` |
| **P1** | 态势感知 | `/situation/kpi`, `/alerts` |
| **P2** | 复盘分析 | `/replay/sessions`, `/experiments` |
| **P2** | 系统管理 | `/admin/users`, `/admin/scenarios` |

---

## 11. 接口测试用例提示

### 11.1 关键路径(用 Postman / pytest 强制覆盖)

1. **登录 → 获取机器人列表** (Auth → Robots)
2. **创建任务 → 触发拍卖 → 查询任务详情** (验证状态 PENDING → ASSIGNED)
3. **创建任务 → 拍卖完成 → 改派** (验证 intervention 写入 + 状态变迁)
4. **机器人故障 → 自动告警 → 人工确认** (Alert 流程闭环)
5. **YOLO 推理 → 黑板写入 → 拍卖 bid 加成 1.5x** (CV 与调度的端到端)
6. **启动实验 60 次 → 结果聚合 → 导出 CSV** (复盘流程)

### 11.2 必测的错误场景

- 无 Token 访问受保护接口 → 401
- 普通用户访问 `/admin/*` → 403
- 创建任务区域非法(area_km2 = 0)→ 422
- 取消已完成的任务 → 409
- 改派给不存在的机器人 → 404
- 改派给电量不足的机器人 → 409

---

**END OF API_SPEC.md**
