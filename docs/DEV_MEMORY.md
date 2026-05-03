# DEV_MEMORY.md — 共享开发记忆

> 本文档用于 Claude Code 和 Codex 共享开发上下文。
> 每完成一个任务、修复一个 bug、调整一个模块后，必须更新本文档。
> 不允许只把开发过程留在对话里。

---

## 当前项目状态

项目名称：disaster-rescue-hub  
当前阶段：**P3 机器人模块完整收口**，进入 P4 任务模块  
当前任务：P4.1 任务 Schemas + Repository（BUILD_ORDER §P4.1）  
最近完成：P3.6 故障与召回（POST /robots/{id}/recall 7 步流程 + intervention 同事务 + RobotAgent 召回响应/到达基地/低电量自动 FAULT + 三个 WS 事件 recall_initiated/recall_completed/fault_occurred；新增 409_ROBOT_NOT_RECALLABLE_001 + 503_AGENT_NOT_RUNNING_001 错误码；26/26 自检全绿）（2026-05-03）  
下一任务：P4.1 `schemas/task.py`（TaskCreate/Read/Update/TaskRequiredCapabilities，对照 DATA_CONTRACTS §1.8 + §4.5/§4.6）+ `repositories/task.py`（save/find_by_id/find_by_status/find_pending）  

---

## 开发原则

1. 严格按照 `docs/BUILD_ORDER.md` 推进。
2. 数据结构以 `docs/DATA_CONTRACTS.md` 为准。
3. REST API 以 `docs/API_SPEC.md` 为准。
4. WebSocket 事件以 `docs/WS_EVENTS.md` 为准。
5. 业务规则和调度算法以 `docs/BUSINESS_RULES.md` 为准。
6. 代码目录和命名以 `docs/CONVENTIONS.md` 为准。
7. 每完成一个 BUILD_ORDER 任务必须 commit + push。
8. 每次重要修改必须记录到本文档。

## 环境约束（必读）

- **后端 Python**：必须使用 `backend\.venv\Scripts\python.exe`（Python 3.11.9）。  
  禁止使用全局 python / pip / alembic（系统默认为 Python 3.12）。
- **数据库主机端口**：5433（容器内仍为 5432）。  
  原因：本机安装的 Windows 原生 PostgreSQL 15 占用了 5432，主机侧若使用 5432 会连到错误的数据库实例。  
  所有 `.env` 中的 `DB_PORT` 须为 5433。
- **迁移驱动**：asyncpg（异步）。`migrations/env.py` 已恢复为 asyncpg 模式，禁止引入 psycopg2-binary。
- **bcrypt 必须固定 4.0.x**：`bcrypt>=4.0,<4.1`。bcrypt 5.0 移除了 `__about__` 属性且对 >72B 密码强制报错，会导致 passlib 1.7.4 启动期 `detect_wrap_bug` 探测崩溃。已写入 `backend/pyproject.toml`。

## 已知设计偏差

### 偏差 2：触发器命名 set_timestamp_blackboard_entries（低风险）

- **位置**：`backend/migrations/versions/26cff1e230e8_init_schema.py`
- **DATA_CONTRACTS.md 原意**：触发器名为 `set_timestamp_blackboard`
- **实际实现**：`set_timestamp_blackboard_entries`（使用了表全名 `blackboard_entries`）
- **影响**：触发器功能完全正常（BEFORE UPDATE 触发 trigger_set_timestamp 函数），仅名称不同
- **处理**：接受偏差，不改动已执行数据库的触发器名。

### 偏差 1：idx_blackboard_active 使用全量索引

- **位置**：`backend/migrations/versions/26cff1e230e8_init_schema.py`
- **DATA_CONTRACTS.md 原意**：`CREATE INDEX idx_blackboard_active ON blackboard_entries(expires_at) WHERE expires_at > NOW();`
- **实际实现**：全量索引，无 WHERE 谓词
- **原因**：PostgreSQL 要求索引谓词中的函数必须为 `IMMUTABLE`，而 `NOW()` 是 `STABLE`，无法用于部分索引。
- **影响**：索引更大（包含已过期条目），查询仍可工作但效率略低于部分索引。
- **处理**：接受偏差，P1.4 不再处理此项。

---

## 开发记录

### 记录模板

#### YYYY-MM-DD HH:mm — 工具名 — 任务编号

- 任务：
- 执行工具：
- 修改类型：
- 涉及文件：
  - 
- 新增内容：
  - 
- 修改内容：
  - 
- 删除内容：
  - 
- 主要原因：
  - 
- 测试验证：
  - 
- Git 提交：
  - commit message：
  - commit hash：
  - push 状态：
- 遗留问题：
  - 
- 下一步建议：
  - 

---

## 已完成任务

### P3.6 — 故障与召回：POST /recall + intervention + RobotAgent 召回响应 + recall_initiated/recall_completed/fault_occurred WS 事件（2026-05-03）

- 任务：P3.6 故障与召回（BUILD_ORDER §P3.6）
- 执行工具：Claude Code
- 修改类型：feat + 小幅 docs（新增 2 个错误码）
- 涉及文件：
  - backend/app/schemas/intervention.py（新增）
  - backend/app/repositories/intervention.py（新增）
  - backend/app/repositories/robot_fault.py（新增）
  - backend/app/ws/events.py（新增）
  - backend/app/services/recall_service.py（新增）
  - backend/app/agents/robot_agent.py（修改：request_recall + RETURNING 移动 + arrived 检测 + _complete_recall + _enter_fault + _emit_event 钩子）
  - backend/app/agents/manager.py（修改：request_recall 转发）
  - backend/app/api/v1/robots.py（修改：POST /{id}/recall）
  - backend/app/core/constants.py（修改：BASE_LAT/LNG/ALT + RETURNING_ARRIVAL_THRESHOLD_M + RECALL_REASON_MIN/MAX_LEN）
  - docs/BUSINESS_RULES.md（修改：§6.2 加 409_ROBOT_NOT_RECALLABLE_001 + 503_AGENT_NOT_RUNNING_001）
- 新增内容：
  - `app/ws/events.py`：模块级 `push_event(name, payload, room='commander')` 自动注入 `event_id`(uuid4) + `timestamp`(ISO 8601 UTC)，对照 INV-F「每个 WS 事件必须有 event_id 和 timestamp」；统一 fault/recall/state_changed 等事件型推送出口（与 broadcaster 高频拉模型分工：broadcaster 推 robot.position_updated，push_event 推所有事件型）
  - `schemas/intervention.py`：
    * `RecallRequest{reason: str (max_length=500)}` —— Pydantic 仅校验 max_length；min_length 业务校验由 service 抛**特化错误码** `422_INTERVENTION_REASON_INVALID_001` 而非通用 `422_VALIDATION_FAILED_001`
    * `RecallResponse{intervention_id: UUID, recall_eta_sec: int}`
  - `repositories/intervention.py` & `repositories/robot_fault.py`：add+flush 模式（与 P2/P3.x 仓储统一），事务由 service commit
  - `services/recall_service.py` `RecallService(session)`：
    * 7 步流程（严格按 BUSINESS_RULES §4.2）：reason 校验 → 404 → 503/409 → before_state 快照（DATA_CONTRACTS §4.8 召回场景字段）→ recall_eta_sec（haversine 近似 + capability.max_speed_mps，下限 1）→ agent.request_recall（内存转 RETURNING + target=BASE）→ 写 intervention 同事务 commit → 事务外 emit recall_initiated
    * 错误码矩阵：FAULT → `409_ROBOT_ALREADY_FAULT_001`；其他不可召回（IDLE）→ `409_ROBOT_NOT_RECALLABLE_001` + details.message=当前 fsm；agent 不在线 → `503_AGENT_NOT_RUNNING_001`
    * intervention.id 灌回 `agent._recall_intervention_id`，供后续 recall_completed payload 引用同一 intervention_id（链路追溯）
  - `agents/robot_agent.py` 重大扩展：
    * 新增召回上下文字段：`_recall_user_id` / `_recall_reason` / `_recall_intervention_id` / `_recall_started_at`
    * 新增 `_event_emit_override: EventEmitter | None`（异步事件推送钩子，默认 push_event；测试可劫持）
    * `request_recall(*, user_id, reason, intervention_id=None) -> bool`：仅 EXECUTING/BIDDING/RETURNING 可召回；EXECUTING/BIDDING → transit RETURNING + target=BASE；RETURNING → 幂等保留 target；其他状态返回 False
    * `_arrived_at_base()`：RETURNING 阶段距基地 < RETURNING_ARRIVAL_THRESHOLD_M(=50m) 即视为到达
    * `_complete_recall()`：transit IDLE + clear current_task_id/target/recall ctx + emit `robot.recall_completed`（含 eta_actual_sec=回到基地耗时）
    * `_enter_fault(fault_type)`：transit FAULT + 写 robot_faults 表（独立 session，severity 按类型映射 low_battery=critical/其他=warn，message 中文短句）+ emit `robot.fault_occurred`（含 fault_id；写库失败仍推送 fault_id=None）
    * `_emit_event(name, payload)`：异步事件推送出口，try/except 包裹防止 emit 失败拉宕主循环
    * `_tick` 重写：EXECUTING 与 RETURNING 都执行 move + drain；2.5 步加入「RETURNING 抵达基地 → _complete_recall」；故障检测命中改走 `_enter_fault`（原来仅 transit FAULT）
    * DEFAULT_INITIAL_POSITION 改用 BASE_LAT/LNG/ALT，与 seed.py 演练区中心对齐
  - `agents/manager.py` `AgentManager.request_recall(robot_id, *, user_id, reason, intervention_id)`：不在线/找不到/agent 拒绝 → False（service 层翻译为 503/409）
  - `api/v1/robots.py` `POST /{id}/recall`：robot:recall 守卫，复用 RecallService
  - `constants.py`：BASE_LAT=30.225 / BASE_LNG=120.525 / BASE_ALTITUDE_M=50.0 / RETURNING_ARRIVAL_THRESHOLD_M=50.0 / RECALL_REASON_MIN_LEN=5 / RECALL_REASON_MAX_LEN=500
  - BUSINESS_RULES.md §6.2 新增两个错误码（小幅契约扩展，已同步更新表格）：
    * `409_ROBOT_NOT_RECALLABLE_001` — 当前 FSM 状态不可召回（仅 EXECUTING/BIDDING/RETURNING 可召回；details.message 含实际状态）
    * `503_AGENT_NOT_RUNNING_001` — AgentManager 未启动或机器人 Agent 协程不存在（mock_agents_enabled=False 场景）
- 设计决策：
  - **特化错误码优先于通用 422**：reason min_length 校验放 service 而非 Pydantic，让 422_INTERVENTION_REASON_INVALID_001 优先于 422_VALIDATION_FAILED_001（BUSINESS_RULES §6.5 字面）
  - **拉模型 vs 推模型并存**：高频 robot.position_updated 由 broadcaster 单协程拉 AgentManager 快照（每秒 1 条 batch）；事件型 fault_occurred / recall_initiated / recall_completed 由触发方主动 push_event。两条路径互不干扰，broadcaster 不动 RobotAgent emit 钩子
  - **agent 内存态在 commit 前修改**：极小窗口风险（mock 环境 DB 稳定可接受）；P5 接入真实 dispatch 时再补 try/except 回滚 agent 状态。INV-G 同事务约束在 intervention 与「未来的 task assignment 释放」两表之间，本任务只有 intervention 单表写
  - **request_recall 同步方法**：仅做内存状态变更（transit + target=BASE），不做 DB/WS。让 service 层 1 个 await intervention.save 后再 emit，串行清晰
  - **EXECUTING + RETURNING 共享移动逻辑**：两种状态都朝 target_position 移动 1m·tick + 电量 -0.5%/tick；区别仅在 target 来源（EXECUTING 由 dispatch_service 设，RETURNING 由 request_recall 强制设为 BASE）
  - **RETURNING 抵达基地阈值 50m**：BUSINESS_RULES §2.2.3 字面规定；用与 Agent 移动一致的 `1°=METERS_PER_DEGREE` 近似（毕设演示足够）
  - **fault_occurred message 中文短句**：「电量降至 4.0%，无法继续执行任务」直接给前端展示，与 WS_EVENTS §3 fault_occurred.message 一致
  - **写 robot_faults 失败仍 transit + emit**：状态正确性优先于审计完整性，失败仅 logger.exception
  - **intervention.recorded（admin 房间审计事件）推迟到 P5**：P3.6 只发 robot.recall_initiated 到 commander 房间；HITL 集中审计在 P5（dispatch 模块上线后多种 intervention 类型一起处理）
  - **任务侧解绑（current_task_id=None）留 P4**：当前 after_state.current_task_id 保留 before_state 的值，等 P4 task_status_machine 上线后联动「召回 → 任务回 PENDING / 释放 assignment」
  - **新错误码同步 BUSINESS_RULES.md**：而非"先用未文档化的 code"，遵守 CONVENTIONS §14.1 文档维护表格
- 测试验证（临时 backend/_p36_check.py，**in-process uvicorn 版**——直接读写 AgentManager 单例；26/26 全绿，验证后已删除不入库）：
  - **关键架构选择**：测试需要直接操作 agent 内存态（设置 EXECUTING / 注入 battery=4），而 AgentManager 是 per-process 单例。改用 `uvicorn.Config + Server.serve()` 在测试进程内跑后端，agent 单例与测试代码共享；启动入口 `os.environ.setdefault('MOCK_AGENTS_ENABLED','true')` 必须在 import app.* 之前
  - [setup] AgentManager 启动后 25 个 agent；observer001 用户即时插入 finally 清理；commander WS connect + subscribe commander
  - [A1] 无 token POST /recall → 401_AUTH_TOKEN_INVALID_001
  - [A2] observer（无 robot:recall）→ 403_AUTH_PERMISSION_DENIED_001
  - [A3] reason="abcd"（4 字符）→ 422_INTERVENTION_REASON_INVALID_001 + details.message="strip 后长度 4"
  - [A4] reason="         "（纯空白 9 字符）→ 同上
  - [A5] reason="x"*600 → Pydantic max_length → 422_VALIDATION_FAILED_001
  - [A6] 不存在 UUID → 404_ROBOT_NOT_FOUND_001 + details.field=robot_id
  - [A7] UAV-003 IDLE → 409_ROBOT_NOT_RECALLABLE_001 + details.message=IDLE
  - [B] UAV-001 happy path（at base + transit IDLE→BIDDING→EXECUTING）：
    * 200 + intervention_id (UUID) + recall_eta_sec=1
    * WS 收 robot.recall_initiated（含 robot_id/code/initiated_by_user_id/reason/intervention_id + event_id/timestamp）
    * DB human_interventions 写入：type=recall, target_robot_id=UAV-001, before_state.robot_state=EXECUTING, after_state.robot_state=RETURNING
    * agent.fsm_state ∈ {RETURNING, IDLE}（视到达速度而定）
    * 4 秒内收 robot.recall_completed（含 eta_actual_sec >= 0）
    * agent 最终回到 IDLE
  - [C] UAV-002 fault_occurred（reset → 直接 battery=4 → 等下一 tick）：
    * WS 收 robot.fault_occurred（fault_type=low_battery, severity=critical, fault_id 为 UUID, 含 event_id+timestamp）
    * DB robot_faults 写入：type=low_battery, severity=critical, message 含「电量降至」
    * agent.fsm_state == FAULT
  - [D] UAV-002 已 FAULT → POST /recall → 409_ROBOT_ALREADY_FAULT_001 + details.message=FAULT
  - [teardown] 删除测试 intervention（reason LIKE '__test_p36__%'）+ 删除测试 robot_faults + reset agents 回 IDLE/battery=100/position=base + 删除 observer001
- 环境处理：
  - 沿用 backend/.venv，无新增依赖
- Git 提交：
  - commit message：feat: P3.6 robot recall + fault flow with intervention and ws events
  - commit hash：3548771
  - push 状态：已 push 至 origin/main
- 下一步建议：
  - P4.1：实装 task 模块基础设施
    1. `schemas/task.py`：TaskCreate / TaskRead / TaskUpdate / TaskRequiredCapabilities（对照 DATA_CONTRACTS §1.8 + §4.5 target_area + §4.6 required_capabilities）
    2. `repositories/task.py`：save / find_by_id / find_by_status / find_pending
    3. P3.6 留下的 P4 联动点：召回成功后 after_state.current_task_id 暂保留原值，P4 task_status_machine 上线后接入「recall → 该任务若无其他 active assignment 则回 PENDING」逻辑（BUSINESS_RULES §4.4）

### P3.5 — WebSocket 推送：python-socketio + connect/subscribe/disconnect + 1Hz batch broadcaster（2026-05-03）

- 任务：P3.5 WebSocket 推送（BUILD_ORDER §P3.5）
- 执行工具：Claude Code
- 修改类型：feat
- 涉及文件：
  - backend/app/ws/__init__.py（新增）
  - backend/app/ws/server.py（新增）
  - backend/app/ws/handlers.py（新增）
  - backend/app/ws/broadcaster.py（新增）
  - backend/app/main.py（修改：用 socketio.ASGIApp 包 FastAPI 导出 asgi_app + lifespan 启停 broadcaster）
  - backend/pyproject.toml（修改：dev 依赖加 aiohttp，仅 AsyncClient 测试用）
- 新增内容：
  - `app/ws/server.py`：模块级 `sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins=['http://localhost:5173'], ping_interval=25, ping_timeout=60)` 单例；`SOCKETIO_PATH = 'ws'`
  - `app/ws/handlers.py`：
    * `_extract_token(environ, auth)`：优先 socket.io-client 推荐的 auth dict，回退 query string `?token=`（WS_EVENTS §0.2 字面规范）
    * `_resolve_user(token)`：复用 `decode_token` + `UserRepository`，过期 → reason='token_expired'，其他失效（签名错 / type≠access / sub 非 UUID / 用户不存在或停用）→ reason='invalid'，与 deps.py 防探测设计对齐
    * `connect(sid, environ, auth)`：**不 raise ConnectionRefusedError**（会让 namespace 握手期立即拒绝，先前 emit 的 auth_error 包来不及送达），改为「让握手成功 → emit auth_error → 主动 sio.disconnect(sid)」，client 才能正常收到事件（WS_EVENTS §0.2 字面要求）
    * 成功路径：`save_session` 写入 user_id/username/display_name/roles → emit `welcome`（含 event_id/timestamp/session_id/user/server_time，WS_EVENTS §2 完整 schema）
    * `subscribe(sid, data)`：按 `ROOM_ROLE_REQUIREMENTS = {'commander': {'commander','admin'}, 'admin': {'admin'}}` 守卫；部分成功也算成功（granted 列表 emit `subscribed`，被拒条目逐条 `subscribe_error`）；observer 角色不在任何房间允许集 → 仅可连接但无推送
    * `unsubscribe`/`disconnect`：幂等 leave_room / 仅日志
    * `register_handlers(server)`：显式注册函数（不用 @sio.event 装饰器避免 import side effect，handler 注册时机由 main.py 控制）
  - `app/ws/broadcaster.py`：
    * `PositionBroadcaster`：单协程拉模型聚合器，每秒读 `AgentManager.get_instance().list_agents()` 的内存快照（agent.code/fsm_state/position/battery/robot_id），拼成 `updates: [...]` 一次 emit `robot.position_updated` 到 `room='commander'`
    * `_has_listeners('commander')`：用 `sio.manager.rooms.get('/', {}).get(room, {})` 判断；房间无人 → 跳过 emit（节流 + 避免无效 broadcast）
    * 单 tick 异常 `logger.exception` 不让循环死亡（与 RobotAgent.run 同款保险丝）
    * stop 用 stop_event + wait_for + 超时 cancel 兜底
    * 模块级单例 `get_broadcaster()` / `reset_for_tests()`
  - `main.py`：
    * `import socketio` + `from app.ws.server import SOCKETIO_PATH, sio` + `from app.ws import handlers as ws_handlers` + `from app.ws.broadcaster import get_broadcaster`
    * lifespan 顺序：startup 先 AgentManager 后 broadcaster；shutdown 反序
    * 文件末尾：`ws_handlers.register_handlers(sio)` + `asgi_app = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path=SOCKETIO_PATH)`
    * 真实运行入口改为 `uvicorn app.main:asgi_app`；httpx ASGITransport 测试 REST 仍用 `app`（不破坏 P0–P3.4 的所有自检脚本）
  - `pyproject.toml`：dev 依赖加 `aiohttp>=3.9,<4.0`，仅 AsyncClient 测试用，**服务端 AsyncServer ASGI 模式不依赖 aiohttp**
- 设计决策：
  - **拉模型 vs 推模型**：broadcaster 单协程读 AgentManager 快照（拉），不动 RobotAgent 的 `_emit_state_changed` 钩子（推）。理由：
    1) WS_EVENTS §3 / §12.2 明文「batch 后 = 1 event/s ✓」；25 个 Agent 各自 emit 会变成 25 events/s × N clients
    2) 不耦合 RobotAgent 与 sio：RobotAgent 测试不需要 mock socketio
    3) 单点节流/采样/合并都好做（未来若要降到 0.5Hz 只改 broadcaster）
    4) 同一 payload 内 25 个 update 自然有序
  - **不 raise ConnectionRefusedError**：让握手在 namespace 层成功，再 emit auth_error + sio.disconnect。原因：raise 会让 socketio 在 namespace handshake 阶段就拒，先前的 emit 包来不及送达客户端，client 只看到一个泛型 ConnectionError 没有 reason。改成 emit + disconnect 后 client 可拿到 WS_EVENTS §0.2 规范的 `auth_error{reason}` 事件。
  - **socketio_path='ws'**：让真实 URL 为 `ws://host:port/ws/?EIO=4&transport=...`，与 WS_EVENTS §0.2「ws://localhost:8000/ws」对齐
  - **register_handlers 显式注册** 而非 `@sio.event` 装饰器：避免 import side effect，handler 注册时机由 main.py 控制（便于测试时按需注册子集）
  - **房间访问规则**（WS_EVENTS §0.4 + 项目 commander/admin/observer 角色矩阵）：
    * commander 房间 = commander 或 admin 角色
    * admin 房间    = 仅 admin
    * observer       = 可连接但不能加入任何房间（无推送）
  - **broadcaster 仅在 mock_agents_enabled=True 时启动**：没有 Agent 数据可读时 broadcaster 是无意义的；自检 / pytest 默认不启动后台协程
  - **房间无人 → 跳过 emit**：socketio.manager.rooms 路径检查，零成本节流
  - **subscribe 部分成功**：rooms=['commander','admin'] 给 commander 用户 → 'commander' 加入 emit subscribed{rooms:['commander']}，'admin' 拒绝 emit subscribe_error
- 测试验证（临时 backend/_p35_check.py，20/20 全绿，验证后已删除不入库；socketio.AsyncClient + httpx 直连 uvicorn 跑在 127.0.0.1:8765 + MOCK_AGENTS_ENABLED=true）：
  - [setup] 即时插入 observer001 用户（observer 角色，password123），finally 清理
  - [1] 无 token connect → 收 `auth_error{reason: invalid}` ✓
  - [2] 篡改 token → `auth_error{reason: invalid}` ✓
  - [3] 过期 token（jose 直接编一个 1 秒前过期的 access） → `auth_error{reason: token_expired}` ✓
  - [4] commander 合法 connect → 收 1 条 `welcome`，含 user.username='commander001' / roles 含 'commander' / session_id / event_id ✓
  - [5] commander 订阅 commander → `subscribed{rooms:['commander']}`，无 subscribe_error ✓
  - [6] commander 订阅 admin → `subscribe_error{room:admin, reason:permission_denied}`，**无** subscribed 补发 ✓
  - [7] observer 订阅 commander → 先收 welcome（可连接），订阅得 `subscribe_error{room:commander, reason:permission_denied}` ✓
  - [8] admin 订阅 commander+admin → 1 条 `subscribed{rooms: {commander, admin}}`，无 error ✓
  - [9] commander 订阅后 5.2s 收 5 条 `robot.position_updated`：
    * len(updates)==25
    * 字段完整（robot_id/robot_code/position/battery/fsm_state）
    * position 含 lat/lng
    * 25 个 robot_code 不重复
    * payload 含 event_id + timestamp（WS_EVENTS §0.6 通用约定）
  - [10] disconnect 客户端干净退出 ✓
- 环境处理：
  - venv 安装 `python-socketio==5.11.4`（连带 python-engineio 4.13.1 / simple-websocket 1.1.0 / wsproto 1.3.2 / bidict 0.23.1）；服务端 AsyncServer ASGI 模式无 aiohttp 依赖
  - venv 加装 `aiohttp==3.13.5`（python-socketio AsyncClient 必需），写入 pyproject dev 段，避免后续测试同事采坑
  - 测试用 socketio.AsyncClient `transports=['websocket']` 强制跳过 polling，避免 polling fallback
- Git 提交：
  - commit message：feat: P3.5 websocket server with batched robot.position_updated
  - commit hash：ab9d0f0
  - push 状态：已 push 至 origin/main
- 下一步建议：
  - P3.6 故障与召回：
    1. `POST /robots/{id}/recall`（BUSINESS_RULES §4）：校验 fsm_state ∈ {EXECUTING, BIDDING, RETURNING} → 写 human_interventions（type=recall, target_robot_id, reason）→ 推 `robot.recall_initiated`（WS_EVENTS §3，commander+admin 房间）
    2. RobotAgent 接收召回信号：在 manager 层暴露 `request_recall(robot_id)` 让外部触发；Agent transit BIDDING/EXECUTING → RETURNING（FSM 已就位）
    3. broadcaster 暂不需扩展：position_updated 已涵盖状态变化；fault_occurred / state_changed / recall_initiated 等"事件型"非高频推送在 P3.6 直接 `await sio.emit(..., room='commander')`
    4. `intervention.recorded` 事件留 P5（HITL 干预审计阶段）

### P3.4 — Mock 行为：移动 / 电量 / robot_states 写入 / emit 钩子（2026-05-03）

- 任务：P3.4 Mock 行为实现（BUILD_ORDER §P3.4）
- 执行工具：Claude Code
- 修改类型：feat
- 涉及文件：
  - backend/app/agents/robot_agent.py（修改）
  - backend/app/core/constants.py（修改）
  - backend/app/core/config.py（修改）
- 新增内容：
  - `RobotAgent.target_position: dict | None` 字段 + `set_target_position(lat, lng, alt=None)` / `clear_target_position()` 接口（P5 拍卖完成后由 dispatch_service 调用）
  - `_move_toward_target()`：EXECUTING 状态下朝 target 移动 1m，无 target 时 no-op；距离 ≤ step 时直接吸附 target（便于上层判定到达）；近似 1° = METERS_PER_DEGREE m
  - `_drain_battery()`：EXECUTING 状态电量 -0.5%/tick，下限 0
  - `_persist_state()`：每 tick 开独立 session 写 1 行 robot_states，commit 后返回带 id 的 RobotState；NUMERIC(5,2) 字段用 `Decimal(f"{battery:.2f}")` 控制精度
  - `_emit_state_changed(state)`：状态推送钩子，**P3.4 仅 logger.debug**；P3.5 替换为 `sio.emit('robot.position_updated', ...)`；预留 `_emit_override` 测试钩子
  - `_check_faults` 加概率注入：`settings.mock_fault_inject_probability > 0` 时 `random.random() < p` 返回 'unknown'
  - `_tick` 重写为 5 阶段流程：tick++ → EXECUTING 行为（移动 + 电量降）→ 故障检测 → 写 DB → emit
  - 故障检测顺序设为"行为之后"：EXECUTING + battery=5.5 跑 1 tick → 5.0 → 立刻触发 FAULT，更接近真实机器人
  - constants.py：新增 `EXECUTING_BATTERY_DRAIN_PCT=0.5` / `MOVE_STEP_METERS=1.0` / `METERS_PER_DEGREE=111320.0`（30°N 时 lng 真实 ≈ 96522，误差 15%，毕设演示可接受；P5 调度的距离用真实 haversine）
  - config.py：新增 `mock_fault_inject_probability: float = 0.0`（默认关，演示时 0.001 ≈ 1.5 分钟一次）
- 设计决策：
  - **每 tick 都写一行**（与 P3 整体验收"每秒新增约 25 条"一致），不做"仅状态变化时写"；25 个协程独立事务、asyncpg 连接池自然管理
  - **target 由外部注入**而非 Agent 内部生成 mock（避免 P5 接入时拆掉）；P3.4 自检手动 `set_target_position` 验证移动通路
  - **WS 钩子留 logger 占位**，P3.5 替换；`_emit_override` 仅供测试劫持，生产代码不用
  - **行为顺序：移动/电量 → 故障检测 → 写 DB → emit**：电量跨阈值的那一 tick 立即写一行 fsm=FAULT，emit 钩子也能拿到 FAULT 状态，下游展示连贯
  - **近似 1° = 111320 m**：lat 真实 ≈ 110574 m（误差 0.7%）；lng 30°N 真实 ≈ 96522 m（误差 15%）；P3.4 移动是可视化用途，P5 调度仍用 haversine 真实距离
  - **写入失败不让循环死亡**：上层 run() 已 try/except Exception 兜底；DB 抖动时单 tick 失败仅 log，下个 tick 继续
- 测试验证（临时 backend/_p34_check.py，10 项断言全绿，验证后已删除不入库）：
  - [1] IDLE 5 tick → position/battery 完全不变（tick_count=5）
  - [2] EXECUTING 无 target 5 tick → position 不变，battery=80→77.5
  - [3] EXECUTING + target 100m 北方 5 tick → 移动 5.0000m（精确）
  - [4] 100 tick + target 1km 北方 → 累积 100.0000m（rel_err=0.00%）
  - [5] 测试 1-4 后 UAV-001 累积写入 robot_states ≥ 115 行
  - [6] EXECUTING + battery=5.5 跑 1 tick → battery=5.0 + fsm=FAULT，DB 最新行 fsm=FAULT 且 battery=5.00
  - [7] mock_fault_inject_probability=1.0 + battery=100 → 1 tick 必 FAULT
  - [8] _emit_state_changed 钩子被精确调用 3 次（fsm=IDLE / battery=100）
  - [9] AgentManager.start_all 25 Agent + 1.05s → robot_states 新增 26 行（落在 [20,30] 区间，符合 1Hz × 25 估计）；stop_all 干净退出
  - [10] finally 清理：DELETE FROM robot_states WHERE recorded_at >= test_start → 删除 146 行（5+5+5+100+1+1+3+26）
- 环境处理：
  - 沿用 backend/.venv，无新增依赖
- Git 提交：
  - commit message：feat: P3.4 mock agent behavior with state persistence
  - push 状态：待执行
- 下一步建议：
  - P3.5 WebSocket 推送：
    1. `app/ws/server.py`：python-socketio AsyncServer 实例 + ASGI mount
    2. `app/ws/handlers.py`：connect（JWT 校验） / subscribe（commander 房间订阅） / disconnect 事件
    3. 把 RobotAgent `_emit_state_changed` 钩子改写为 `await sio.emit('robot.position_updated', payload, room='commander')`
    4. 1Hz 批量推送考虑：每个 Agent 单条 emit vs AgentManager 聚合 25 条/秒 一次 emit；后者节约客户端 socket 流量，前者实现简单——P3.5 决策

### P3.3 — RobotAgent 协程基础 + AgentManager + lifespan（2026-05-03）

- 任务：P3.3 RobotAgent 协程基础（BUILD_ORDER §P3.3）
- 执行工具：Claude Code
- 修改类型：feat
- 涉及文件：
  - backend/app/agents/__init__.py（新增）
  - backend/app/agents/robot_agent.py（新增）
  - backend/app/agents/manager.py（新增）
  - backend/app/core/constants.py（修改：新增故障检测常量）
  - backend/app/core/config.py（修改：mock_agents_enabled 默认改 False，tick_hz 改 float）
  - backend/app/main.py（修改：FastAPI lifespan 集成）
- 新增内容：
  - `agents/robot_agent.py`：
    - `ROBOT_FSM_TRANSITIONS` 字典严格抄 BUSINESS_RULES §2.2.3（5 状态 + 转移集）；`VALID_FSM_STATES` 由字典 keys 派生
    - `FSMTransitionError(ValueError)`：非法 FSM 转移异常
    - `RobotAgent` 类：
      * `__init__`：静态身份（robot_id/code/type/capability）+ 动态状态（fsm_state/position/battery/current_task_id）+ 运行控制（tick_hz/_stop_event/tick_count/last_heartbeat_at）；非法初始 fsm_state 或 tick_hz≤0 抛错
      * `from_db(session, robot_id, *, tick_hz=1.0)` 类方法：用 `RobotRepository.find_by_id` 加载，`LookupError` 当机器人不存在
      * `transit(target, *, reason="")`：违反 ROBOT_FSM_TRANSITIONS 抛 FSMTransitionError，structlog 记录 from→to+reason
      * `_check_faults()`：**P3.3 仅实现 battery≤FAULT_BATTERY_THRESHOLD（=5）→ 'low_battery'**，sensor_error / comm_lost / 概率注入留 P3.4
      * `_tick()`：tick_count++ + last_heartbeat_at + 故障检测自动 transit('FAULT')
      * `run()`：while not _stop_event.is_set() 循环，单 tick 异常仅 logger.exception 不让协程死亡（毕设场景：mock 行为以后会引入更多分支，避免一次失败拉宕整个 manager）；用 `asyncio.wait_for(_stop_event.wait(), timeout=interval)` 替代 sleep —— stop() 可立即解除等待，比 sleep+cancel 更优雅
      * `stop()`：set _stop_event；run() 自然退出
    - 启动初始位置 = seed CENTER (30.225, 120.525, alt=50)，battery=100，fsm_state=IDLE（P3.4 再做 scenarios.initial_state 解析）
  - `agents/manager.py`：
    - `AgentManager` 单例，`get_instance()` / `reset_for_tests()`
    - `start_all()`：用 `async_session_maker()` 加载 active robots → 为每台 `asyncio.create_task(agent.run(), name=f"agent:{code}")`；重复调用 no-op
    - `stop_all(*, timeout_sec=5.0)`：1) 给每个 agent 发 stop()；2) `asyncio.gather(*tasks, return_exceptions=True)` + `wait_for(timeout)`；3) 超时 task.cancel() + 再 gather 一次让 cancel 生效；4) 清空 _agents/_tasks，started=False
    - `get(robot_id) / list_agents() / started` 查询接口（为 P3.5 WS 推送预留）
    - 模块级 `get_agent_manager()` 便捷访问器
  - `core/constants.py` 追加：`FAULT_BATTERY_THRESHOLD = 5.0` + `HEARTBEAT_TIMEOUT_SEC = 15`（P3.4 用）
  - `core/config.py`：mock_agents_enabled 默认 False（避免 pytest/自检自动起 25 协程），tick_hz 改 float（更灵活）
  - `main.py`：FastAPI `@asynccontextmanager async def lifespan(_app)` 闭环 startup/shutdown；只在 settings.mock_agents_enabled=True 时调用 start_all/stop_all
- 设计决策：
  - **不写 robot_states 表**（P3.4 才写）：BUILD_ORDER P3.4 字面"状态变化时写 robot_states 表"，P3.3 主循环只在内存维护状态
  - **mock_agents_enabled 默认 False**：自检 / pytest 启动 FastAPI 不自动起 25 协程；想看 Agent 跑就在 backend/.env 显式 `MOCK_AGENTS_ENABLED=true`
  - **故障检测仅 battery**：P3.3 没有 Mock 行为让电量真的下降，触发不到；自检里手动注入 battery=4 验证 transit(IDLE→FAULT) 通路
  - **stop_all 用 stop_event 而非 task.cancel**：CancelledError 在 sleep 中被抛出会触发 try/finally 中可能的 await，反而拖慢；stop_event.set() + asyncio.wait_for 让循环主动 break，是更"优雅"的退出
  - **单 tick 异常不让协程死亡**：`try/except Exception` 包裹 _tick，仅 logger.exception；P3.4 引入 DB 写入 / WS 推送后，单次故障不应影响其他 25 个 Agent
  - **用 Event.wait 替代 sleep**：stop() 可立即唤醒等待中的协程，self._stop_event.wait() 在 wait_for 超时时正常进入下一 tick
- 测试验证（临时 backend/_p33_check.py，验证后已删除不入库，14 项断言全绿）：
  - [1] ROBOT_FSM_TRANSITIONS 字典与 BUSINESS_RULES §2.2.3 完全一致（5 状态 + 转移集）
  - [2] RobotAgent.from_db(UAV-001) 加载成功，code/type/fsm_state=IDLE/battery=100/position=CENTER/has_yolo=True
  - [3] 合法 transit 链：IDLE→BIDDING→EXECUTING→RETURNING→IDLE 4 步全过
  - [4] 非法 transit 拒绝：IDLE→EXECUTING、UNKNOWN 目标、FAULT→BIDDING；FAULT→IDLE 唯一允许
  - [5] _check_faults：battery=100→None；battery=5.1→None；battery=5.0→'low_battery'；battery=4→'low_battery'；_tick 触发自动 transit('FAULT')
  - [6] AgentManager.start_all 启动 25 个 Agent，0.5s 内全 25 个 tick_count≥1（实测 min=8 max=9，tick_hz=20）
  - [7] stop_all 0.000 秒优雅退出，list_agents=[]，started=False
  - [8] lifespan 双分支：False 分支跳过 start_all（manager 未启动）；True 分支启停闭环（25→0）。**直接测 lifespan async context manager**（httpx ASGITransport 默认不触发 FastAPI lifespan，故不走 AsyncClient 链路）
- 环境处理：
  - 沿用 backend/.venv，无新增依赖
- Git 提交：
  - commit message：feat: P3.3 robot agent and manager skeleton
  - push 状态：待执行
- 下一步建议：
  - P3.4 Mock 行为：
    1. IDLE 状态：位置/电量不变（已是默认行为）
    2. EXECUTING 状态：每秒位置朝 current_task target 移动 1m，电量 -0.5%
    3. 故障检测补：sensor_error 框架 + 概率注入开关（演示用）
    4. 状态/位置变化时 `RobotStateRepository.append`（仅状态变化或电量跨阈值时写，避免每秒 25 行）
    5. P3.4 末尾应能用 SQL 看到 `robot_states` 表逐秒新增；WS 推送是 P3.5 的事

### P3.2 — 机器人 REST 接口实现（2026-05-03）

- 任务：P3.2 REST 接口实现（BUILD_ORDER.md §P3.2）
- 执行工具：Claude Code
- 修改类型：feat
- 涉及文件：
  - backend/app/schemas/pagination.py（新增）
  - backend/app/schemas/robot.py（修改：追加 RobotDetailRead）
  - backend/app/repositories/robot.py（修改：追加 find_paginated）
  - backend/app/services/robot_service.py（新增）
  - backend/app/api/v1/robots.py（新增）
  - backend/app/api/router.py（修改：注册 robots router）
  - scripts/seed.py（修改：commander 加 robot:read；upsert_role 改 ON CONFLICT DO UPDATE 幂等）
- 新增内容：
  - `schemas/pagination.py`：泛型 `Page[T]`(items/total/page/page_size)，`ConfigDict(arbitrary_types_allowed=True)` 兼容 Pydantic v2 + Generic
  - `schemas/robot.py` 追加 `RobotDetailRead(RobotRead)`：嵌入 `latest_state: RobotStateRead | None`，对应 API_SPEC §2「GET /robots/{id} → RobotRead + 嵌入最新 RobotStateRead」
  - `RobotRepository.find_paginated(*, type_, group_id, search, only_active, page, page_size) -> (items, total)`：
    - search 用 `OR(code ILIKE, name ILIKE)` 模糊匹配
    - only_active=True 默认仅返回 is_active=TRUE
    - 排序 created_at DESC（API_SPEC §0.6 默认）
  - `services/robot_service.py` `RobotService(session)` 类：
    - `list_paginated()` / `get_with_latest_state()` / `list_states()`（404 守卫）
    - `create()`：捕获 IntegrityError → `409_ROBOT_CODE_DUPLICATE_001`
    - `update()`：用 `model_dump(exclude_unset=True)` 实现 PATCH 语义，区分"传 None 解除关联" vs "未传字段保留"
    - `soft_delete()`：set is_active=False；先查 task_assignments WHERE robot_id AND is_active=TRUE，命中 → `409_ROBOT_HAS_ACTIVE_TASK_001`
    - 错误工厂函数 `_not_found / _code_duplicate / _has_active_task`（含 details 数组，对照 BUSINESS_RULES §6.8）
  - `api/v1/robots.py` 6 路由：
    - GET /robots（分页 + type/group_id/search/include_inactive）
    - GET /robots/{id}（RobotDetailRead 含 latest_state）
    - POST /robots（201 + RobotRead）
    - PUT /robots/{id}（PATCH 语义）
    - DELETE /robots/{id}（204 软删）
    - GET /robots/{id}/states（limit∈[1,1000]，超出由 FastAPI 转 RequestValidationError → 422_VALIDATION_FAILED_001）
  - seed.py：commander 权限补 robot:read（原本只有 manage/recall/reassign，缺读权限会让 GET /robots 直接 403）；`upsert_role` 改为 `ON CONFLICT DO UPDATE SET description=…, permissions=…`，重跑可同步刷新已存在角色
- 设计决策：
  - **分页放在 repo 层**（CONVENTIONS §1.2 反模式：service 不写 SQL）；service 只组装参数 + 错误翻译
  - **status 过滤暂不做**（需 join robot_states 取最新行；P3.5 WS 上线后用 service 内存缓存更顺手），仅支持 type/group_id/search/page/page_size/include_inactive
  - **`POST /robots/{id}/recall` 与 `GET /robots/{id}/faults` 不在本任务**：BUILD_ORDER §P3.2 字面只列 6 路由，recall 留 P3.6 联合 intervention，faults 表的接口 BUILD_ORDER P3 全程未列
  - **PUT 用 PATCH 语义**：`model_dump(exclude_unset=True)` 区分"未传"与"显式 None"，避免误清空字段；code 与 type 不在 RobotUpdate 中（数据库 UNIQUE+CHECK，本就不可变）
  - **limit 上限 1000 在路由层 `Query(le=1000)` 守卫**：FastAPI 自动转 RequestValidationError，沿用 P2.6 的 422_VALIDATION_FAILED_001 全局 handler，repo 层不再重复校验
  - **DELETE 后 include_inactive=False 列表不可见**：默认 only_active=True 是产品体感最直觉的列表行为；管理员可显式带 `include_inactive=true` 看到软删条目
  - **seed roles upsert 改幂等更新**：原 ON CONFLICT DO NOTHING 让权限定义一旦写入就再难修，与未来契约迭代必然冲突；改为 DO UPDATE 后重跑 seed 即可同步最新权限
- 测试验证（临时 `backend/_p32_check.py`，httpx + ASGITransport，验证后已删除不入库）：
  - [1] 401:GET /robots 无 token → `401_AUTH_TOKEN_INVALID_001` ✓
  - [2] 403:admin001（permissions=user:manage+system:admin，**无** robot:read）GET /robots → `403_AUTH_PERMISSION_DENIED_001` ✓
  - [3] 201:commander 创建 TEST-CLAUDE-001（uav，has_yolo=true）→ RobotRead，is_active=true ✓
  - [4] 409:重复 code POST → `409_ROBOT_CODE_DUPLICATE_001`（IntegrityError → 翻译）✓
  - [5] 200:默认分页 → total=26（25 seed + 1 test），page=1，page_size=20，items.len=20 ✓
  - [6] 200:?type=uav&page_size=100 → total=11（10 seed UAV + 1 test），全部 type=uav ✓
  - [7] 200:?group_id=空中编队 Alpha → total=10 ✓
  - [8] 200:GET /robots/{uav-001} → RobotDetailRead，latest_state=null（系统未上报过）✓
  - [9] 200:PUT name='测试机-改名' → 200，name 已更新 ✓
  - [10] 204:DELETE 软删 → 204；默认 search 不见；include_inactive=true 仍可见且 is_active=false ✓
  - [11] 409:UGV-001 已有 active task_assignment（raw SQL 注入测试 task + assignment）DELETE → `409_ROBOT_HAS_ACTIVE_TASK_001` ✓
  - [12] 422:GET /states?limit=2000 → `422_VALIDATION_FAILED_001`（FastAPI Query le=1000 守卫）；limit=10 正常返回 0 条 ✓
  - [13] 404:GET /robots/{ghost UUID} → `404_ROBOT_NOT_FOUND_001` ✓
- 数据清理（finally 块硬删，不污染 DB）：
  - DELETE FROM task_assignments WHERE task_id IN (SELECT id FROM tasks WHERE code='T-TEST-CLAUDE-001')
  - DELETE FROM tasks WHERE code='T-TEST-CLAUDE-001'
  - DELETE FROM robots WHERE code='TEST-CLAUDE-001'
- 环境处理：
  - seed.py 重跑（`backend\.venv\Scripts\python.exe scripts\seed.py`）让 commander 拿到 robot:read 权限；幂等 upsert 验证：roles 表 commander.permissions 含 robot:read
- Git 提交：
  - commit message：feat: P3.2 robot REST endpoints
  - push 状态：待执行
- 下一步建议：
  - P3.3：实现 `app/agents/robot_agent.py`（RobotAgent 类 + 1Hz 主循环 + ROBOT_FSM_TRANSITIONS 字典 BUSINESS_RULES §2.2）+ `app/agents/manager.py`（AgentManager 管理 25 个协程生命周期）
  - 注意 RobotAgent 主循环不能阻塞事件循环；耗时操作（如未来的 YOLO 推理）必须 `asyncio.to_thread`

### P3.1 — 机器人 Schemas + Repository（2026-05-02）

- 任务：P3.1 机器人 Schemas + Repository（BUILD_ORDER.md §P3.1）
- 执行工具：Claude Code
- 修改类型：feat
- 涉及文件：
  - backend/app/schemas/common.py（新增）
  - backend/app/schemas/robot.py（新增）
  - backend/app/repositories/robot.py（新增）
  - backend/app/repositories/robot_state.py（新增）
- 新增内容：
  - `schemas/common.py`（Pydantic v2，跨领域复用）：
    - `Position`（lat/lng + 可选 altitude_m / heading_deg，Field 范围守卫 -90/90、-180/180、heading 0-360）
    - `RobotCapability`（sensors/payloads 默认空 list 用 `Field(default_factory=list)` 避免 mutable default + max_speed_mps/max_battery_min/max_range_km/has_yolo/weight_kg）
    - `Detection`（class_id 0-3 + class_name Literal 4 类 + confidence 0-1 + bbox 长度=4 + 可选 world_position）
    - `VisionData`（frame_id + inference_time_ms + detections 列表）
    - `SensorData`（temperature_c / humidity_pct / signal_dbm / vision，`ConfigDict(extra="allow")` 允许不同机型扩展）
  - `schemas/robot.py`：
    - `RobotBase`：code (max=50) + name (max=100) + type Literal["uav","ugv","usv"] + model 可选 (max=100) + capability + group_id 可选
    - `RobotCreate`(=RobotBase) / `RobotUpdate`（4 字段全可选，code 与 type 不可变）
    - `RobotRead`：+ id / is_active / created_at / updated_at，`ConfigDict(from_attributes=True)`
    - `RobotStateRead`：id (int, BIGSERIAL) / robot_id / recorded_at / fsm_state Literal 5 态 / position (Position) / battery 0-100 / sensor_data (SensorData) / current_task_id 可选
  - `repositories/robot.py` `RobotRepository(session)` 类（事务边界：只 add+flush，不 commit/rollback）：
    - `save(robot) -> Robot`
    - `find_by_id(robot_id) -> Robot | None`（用 session.get）
    - `find_by_code(code) -> Robot | None`（确认范围内追加；seed 数据用 UAV-001/UGV-001/USV-001 类业务 code，P3.2 / 调试 / 测试都需要）
    - `find_all(*, only_active: bool = True) -> list[Robot]`（按 code 升序稳定排序）
    - `find_by_group(group_id) -> list[Robot]`（不在 repo 强制 active 过滤，留给 service）
  - `repositories/robot_state.py` `RobotStateRepository(session)` 类：
    - `append(state) -> RobotState`
    - `find_latest_by_robot(robot_id) -> RobotState | None`（recorded_at DESC + LIMIT 1，命中 idx_robot_states_robot_time）
    - `find_by_robot_in_window(robot_id, *, start_time=None, end_time=None, limit=100) -> list[RobotState]`（时间窗可选 + DESC + limit；**业务上限 1000 不在 repo 校验**，留给 service / API 层）
- 设计决策：
  - 公共类型独立放 `schemas/common.py`，与 CONVENTIONS §2.2 列出的"common.py（Position, TargetArea, etc.）"一致；本任务**只**新增 Robot/CV 域复用类型（Position / RobotCapability / Detection / VisionData / SensorData），不预先放入 task / auction / ws 域 schema
  - Pydantic v2：所有模型用 `ConfigDict`，list 默认值用 `Field(default_factory=list)`；`SensorData` `extra="allow"` 与 DATA_CONTRACTS §5 严格一致
  - Repository 事务边界：与 P2.2 `UserRepository` 风格统一——只 add + flush，commit/rollback 由 service / 测试控制；这样 P3.3 RobotAgent 在 1Hz 上报循环里可批量 commit
  - `find_by_robot_in_window` 不做 limit 上限校验：repository 层只忠实把参数传给 SQL，让 GET /robots/{id}/states 在 service 守卫 ≤ 1000；避免分层职责泄漏
  - `RobotRead.from_attributes = True` 与 ORM Robot 直接桥接（capability JSONB 字段虽然 ORM 是 dict，但 Pydantic v2 会用 RobotCapability 校验后产出强类型嵌套对象）
- 测试验证（临时脚本 `backend/_p31_check.py`，验证后已删除，不入库）：
  - [1] schema imports：Position / RobotCapability / SensorData / RobotCreate / RobotRead / RobotUpdate / RobotStateRead 全部 import 通过 ✓
  - [2] RobotCreate 合法数据通过 ✓
  - [3] RobotCreate 缺 type+capability → ValidationError 含 missing 字段 ✓
  - [3b] RobotCreate type='space_drone' → 非法 Literal 拒绝 ✓
  - [4.1] find_all(only_active=True) → 25 台，types={uav,ugv,usv} ✓
  - [4.2] find_by_code('UAV-001') → 鹰眼-1，capability.has_yolo=True ✓
  - [4.2b] find_by_code('NOT-EXIST-999') → None ✓
  - [4.3] find_by_id(uav001.id) 还原同一对象 ✓
  - [4.4] find_by_group(空中编队 Alpha id) → 10 台 UAV，code 范围 UAV-001..UAV-010 ✓
  - [5] append RobotState（IDLE / position / battery=88.5 / sensor_data） + flush 拿到 BIGSERIAL id + recorded_at（DB server_default=now() 已生效）✓
  - [5] find_latest_by_robot 拿回同一条 ✓
  - [5b] RobotStateRead.model_validate(latest) 成功（fsm_state='IDLE', position.lat=30.2741, battery=88.5）✓
  - [5c] find_by_robot_in_window(limit=10) 含本次写入 ✓
  - [6] RobotRead.model_validate(uav001) → code='UAV-001', id 是 UUID ✓
  - [6b] session.rollback() 后开新 session 复检 → robot_states 中无 UAV-001 记录（DB 干净，未污染）✓
- 环境处理：
  - 复用 P2.x 已就位的 backend/.venv（Python 3.11.9）+ DB_PORT=5433，无需新增依赖
- Git 提交：
  - commit message：feat: P3.1 robot schemas and repositories
  - push 状态：待执行
- 下一步建议：
  - P3.2：实现 `app/api/v1/robots.py` 全部 7 路由（GET 列表+分页+过滤 / GET 单查嵌入最新 state / POST 含 code 重复 409 / PUT / DELETE 软删除 / GET states 时序+limit≤1000 守卫 / GET faults），以及 service 层处理 code 唯一冲突。注意 `POST /robots/{id}/recall` 留到 P3.6 联合 intervention 一起实现

### P2.6 — 统一错误处理（X-Request-Id + ErrorResponse + 兜底 500）（2026-05-02）

- 任务：P2.6 统一错误处理（BUILD_ORDER.md §P2.6）
- 执行工具：Claude Code
- 修改类型：feat
- 涉及文件：
  - backend/app/core/middleware.py（新增）
  - backend/app/schemas/error.py（新增）
  - backend/app/main.py（修改）
- 新增内容：
  - `RequestIdMiddleware`（纯 ASGI 实现）：
    - 入站读 `X-Request-Id`（透传客户端串联值），缺失则生成 `req-<uuid4-hex32>`
    - 写入 `scope["state"]["request_id"]`，下游通过 `request.state.request_id` 读取
    - 包装 send 在 `http.response.start` 注入响应头 `X-Request-Id`，并去重已存在条目
  - `schemas/error.py`：`ErrorDetail{field?, code, message}` + `ErrorResponse{code, message, details, request_id, timestamp}`，对照 DATA_CONTRACTS §5 / API_SPEC §0.3
  - `main.py` 三大异常处理：
    - `BusinessError` → 用 `exc.http_status` + ErrorResponse 形态（含 request_id / timestamp）
    - `RequestValidationError` → 422 + `422_VALIDATION_FAILED_001`，details 列表填 `{field, code, message}`（field 取 loc 跳过 "body"）
    - 兜底 `Exception` → 500 + `500_INTERNAL_ERROR_001` + `message="服务器内部错误"`，仅写日志（`logger.exception`），响应体绝不暴露异常类型/堆栈/原始 message
  - CORS 中间件 `expose_headers=[X-Request-Id]`，浏览器端可读 trace id
- 设计决策：
  - **不用 BaseHTTPMiddleware** —— Starlette #1996 / FastAPI #4719 已知冲突：当注册 `@app.exception_handler(Exception)` 时，handler 跑了但异常仍被 BaseHTTPMiddleware.call_next 重新抛出，客户端拿不到响应。改写为纯 ASGI 中间件直接包装 send 就避开此问题。
  - **`raise_app_exceptions=False`（仅测试侧用）**—— Starlette `ServerErrorMiddleware` 在调用 500 handler 后**总是** `raise exc`（设计意图：让 ASGI server 自己记日志）。生产 uvicorn 行为不变；httpx ASGITransport 测试时关闭再抛出，让 500 响应能被测试客户端接收。
  - 响应 header 用 latin-1 编码（HTTP/ASGI 规范：header 必须是 ISO-8859-1 字节）
  - 中间件挂载顺序：`add_middleware(CORS) → add_middleware(RequestIdMiddleware)` —— 后加在外层，所有响应（含 CORS preflight）都带 X-Request-Id
- 测试验证（自检脚本 6 项，全绿，httpx + ASGITransport）：
  - [1] /health 自动生成 X-Request-Id（req-<hex32>）✓
  - [2] 客户端传 `X-Request-Id: req-client-trace-abc123` → 响应同值透传 ✓
  - [3] BusinessError 路径（/auth/me 缺 token）→ 401 + body `code=401_AUTH_TOKEN_INVALID_001` + body.request_id 与 header 一致 + ErrorResponse schema 校验通过 ✓
  - [4] RequestValidationError（/auth/login 缺 password）→ 422 + `422_VALIDATION_FAILED_001` + details 含 `field=password` ✓
  - [4b] /auth/login `password=""`（长度违规）→ 422 + details 含 `field=password` ✓
  - [5] 临时 `/__boom__` 路由抛 ZeroDivisionError("secret-internal-detail-do-not-leak") → 500 + `500_INTERNAL_ERROR_001` + `message=服务器内部错误`，响应体**不含** "secret-internal-detail" / "ZeroDivisionError" / "Traceback" ✓
- Git 提交：
  - commit message：feat: P2.6 unified error handling with X-Request-Id and ErrorResponse
  - push 状态：待执行
- 下一步建议：
  - P3.1：`app/schemas/robot.py`（对照 DATA_CONTRACTS §2.1 robots 表）+ `app/repositories/robot.py` + `app/repositories/robot_state.py`（时序）

### P2.5 — /auth/refresh + /auth/me + /auth/logout（2026-05-02）

- 任务：P2.5 其他认证接口
- 执行工具：Claude Code
- 修改类型：feat
- 涉及文件：
  - backend/app/services/auth_service.py（修改：新增 refresh()）
  - backend/app/api/v1/auth.py（修改：追加 3 路由）
- 新增内容：
  - `AuthService.refresh(refresh_token) -> TokenResponse`
    - 解 refresh token，过期 → `401_AUTH_TOKEN_EXPIRED_001`
    - JWTError / type≠refresh / sub 非 UUID / 用户停用或不存在 → `401_AUTH_TOKEN_INVALID_001`
    - 通过则颁发新 access + 新 refresh（重新查最新 roles）
  - `POST /api/v1/auth/refresh`（公开），body=RefreshTokenRequest，200=TokenResponse
  - `GET /api/v1/auth/me`（需认证），`Depends(get_current_user)` 直接返回 CurrentUser
  - `POST /api/v1/auth/logout`（需认证），`response_class=Response` + `status_code=204`，简化版不做后端黑名单
- 设计决策：
  - logout 必须用 `response_class=Response`，否则 FastAPI 默认 JSONResponse 与 204 冲突（运行时 AssertionError："Status code 204 must not have a response body"），已在代码中注明
  - refresh 不复用 P2.4 deps：deps 限制 type=access；refresh 端点反向接受 type=refresh，逻辑放在 service 内
  - refresh 不写 DB（不更新 last_login_at），与 login 区分语义
- 环境处理：
  - venv 缺装 httpx（CONVENTIONS [dev] 已声明 `httpx>=0.26,<0.27`），已安装 0.26.0
- 测试验证（自检脚本 10 项，全绿，httpx + ASGITransport）：
  - login 200 expires_in=86400 ✓
  - /me 带 access → 200 + perms_count=7 ✓
  - /me 不带 token → 401_AUTH_TOKEN_INVALID_001 ✓
  - /me 用 refresh token（type 不匹配）→ 401_AUTH_TOKEN_INVALID_001 ✓
  - /refresh 合法 → 200 + 新 access 可打 /me + 新 refresh 可再换 ✓
  - /refresh 用 access 当 refresh → 401_AUTH_TOKEN_INVALID_001 ✓
  - /refresh 篡改 → 401_AUTH_TOKEN_INVALID_001 ✓
  - /refresh 过期 → 401_AUTH_TOKEN_EXPIRED_001 ✓
  - /logout 带 access → 204 无 body ✓
  - /logout 不带 token → 401_AUTH_TOKEN_INVALID_001 ✓
- Git 提交：
  - commit message：feat: P2.5 auth refresh me logout endpoints
  - push 状态：待执行
- 下一步建议：
  - P2.6 统一错误处理：补 `X-Request-Id` 中间件（每请求生成 + 写 response header + 注入日志/错误体）+ `RequestValidationError` 全局 handler 转 `422_VALIDATION_ERROR_001` 风格
  - P2 整体验收基本就绪：登录 → 拿 token → 取 /me → 错密码 5 次锁，全部已通过

### P2.4 — JWT 解析中间件 + 当前用户 + 权限校验（2026-05-02）

- 任务：P2.4 中间件：JWT 解析 + 当前用户
- 执行工具：Claude Code
- 修改类型：feat
- 涉及文件：
  - backend/app/api/deps.py（新增）
- 新增内容：
  - `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)`
    - `auto_error=False`：缺/坏 token 由本模块统一翻译为 BusinessError，避免 FastAPI 默认 401 文本不带项目错误码
  - `get_current_user(token, db) -> CurrentUser`（FastAPI 依赖）
    - 缺 token / type≠access / sub 非 UUID / 用户不存在 / is_active=False → `401_AUTH_TOKEN_INVALID_001`
    - `jose.ExpiredSignatureError` → `401_AUTH_TOKEN_EXPIRED_001`
    - `jose.JWTError` → `401_AUTH_TOKEN_INVALID_001`
    - 通过 `UserRepository.get_roles_and_permissions` 加载最新 roles + permissions（不读 token 中的 permissions，保证调整即生效）
  - `require_permission(perm: str) -> Callable`（FastAPI 依赖工厂）
    - 用法：`Depends(require_permission("robot:manage"))`
    - 缺权限 → `403_AUTH_PERMISSION_DENIED_001`，否则原样返回 CurrentUser
- 设计决策：
  - 用依赖工厂（不写 decorator）—— FastAPI 路由参数依赖系统更天然，且与 OpenAPI schema 兼容
  - 用户不存在 / 停用 / sub 异常 统一返回 INVALID（不暴露具体原因，防探测）
  - 不在 token 里塞 permissions：1 次 JOIN 换权限调整即时生效
- 测试验证（自检脚本 10 项，全绿）：
  - imports ok ✓
  - 合法 access token → CurrentUser(commander001, roles=['commander'], perms_count=7) ✓
  - 篡改 token → 401_AUTH_TOKEN_INVALID_001 ✓
  - 过期 token（手工构造 exp=now-1h） → 401_AUTH_TOKEN_EXPIRED_001 ✓
  - refresh-typed token（type=refresh） → 401_AUTH_TOKEN_INVALID_001 ✓
  - is_active=False（update + rollback，未污染 DB）→ 401_AUTH_TOKEN_INVALID_001 ✓
  - 不存在用户（uuid4 假 sub）→ 401_AUTH_TOKEN_INVALID_001 ✓
  - 缺 token（None）→ 401_AUTH_TOKEN_INVALID_001 ✓
  - require_permission("robot:manage") 命中 → 通过 ✓
  - require_permission("nonexistent:perm") → 403_AUTH_PERMISSION_DENIED_001 ✓
- Git 提交：
  - commit message：feat: P2.4 jwt deps with get_current_user and require_permission
  - push 状态：待执行
- 下一步建议：
  - P2.5：`POST /auth/refresh`（用 refresh token 换 access token）+ `GET /auth/me`（依赖 `get_current_user`，直接返回 CurrentUser）+ `POST /auth/logout`（简化版，前端清 token，无需后端黑名单）
  - P2.6：统一错误处理（`X-Request-Id` 中间件 + `RequestValidationError` 转 ErrorResponse）

### P2.3 — 登录接口 POST /auth/login + 账号锁定（2026-05-02）

- 任务：P2.3 登录接口
- 执行工具：Claude Code
- 修改类型：feat
- 涉及文件：
  - backend/app/core/constants.py（新增）
  - backend/app/services/__init__.py / services/auth_service.py（新增）
  - backend/app/api/__init__.py / api/v1/__init__.py / api/v1/auth.py / api/router.py（新增）
  - backend/app/main.py（修改，挂载 /api/v1）
- 新增内容：
  - 常量 LOGIN_FAIL_LOCKOUT_THRESHOLD=5 / LOGIN_LOCKOUT_DURATION_MIN=15 / JWT_*（在 constants.py 集中管理）
  - AuthService.login(username, password) -> TokenResponse
    - 锁定守卫：locked_until > now → 423_AUTH_ACCOUNT_LOCKED_001（即使密码正确也拒绝）
    - 用户不存在 / is_active=False / 密码错 → 同一码 401_AUTH_INVALID_CREDENTIAL_001（防用户名枚举）
    - 失败累加 ≥ 5 → 设置 locked_until = now + 15min
    - 成功 → 清状态 + 更新 users.last_login_at = NOW() + 颁发双 token + commit
  - 失败计数器：模块级 dict + asyncio.Lock 守护，进程内单例（重启清零，毕设场景够用）
  - 接口：POST /api/v1/auth/login（请求体 LoginRequest JSON，200 返回 TokenResponse）
- 设计决策：
  - 锁定状态过期时自动清除并重置 count=0（不在锁定边界挂半状态）
  - last_login_at 用 SQLAlchemy update + func.now()，避开手工时区计算
  - 暴露 _reset_all_state_for_tests() 内部辅助，便于自检
- 环境处理：
  - venv 缺装 fastapi / uvicorn / structlog，已安装（连带 starlette / anyio / h11 / httptools / watchfiles / pyyaml / click 等）
- 测试验证（自检脚本，9 项）：
  - /api/v1/auth/login POST 路由已注册 ✓
  - commander001 + password123 → access (roles=['commander']) + refresh，expires_in=86400 ✓
  - 4 次错密码 → 全 401，count=4，未锁 ✓
  - 第 5 次错密码 → 401，locked_until 设置 ✓
  - 锁定期内正确密码 → 423_AUTH_ACCOUNT_LOCKED_001 ✓
  - 锁定过期后正确密码 → 200，状态清零 ✓
  - 不存在用户 → 同一 401 码，无枚举差异 ✓
  - admin001 / system 皆可登录 ✓
  - last_login_at 在成功后更新 ✓
- Git 提交：
  - commit message：feat: P2.3 login endpoint + account lockout
  - push 状态：待执行
- 下一步建议：
  - P2.4：app/api/deps.py 实现 get_current_user（解 JWT → 翻译错误码 → 加载 CurrentUser）+ require_permission(perm)

### P2.2 — 认证 Schemas + Repository（2026-05-02）

- 任务：P2.2 认证 Schemas + Repository
- 执行工具：Claude Code
- 修改类型：feat
- 涉及文件：
  - backend/app/schemas/__init__.py（新增，空包）
  - backend/app/schemas/auth.py（新增）
  - backend/app/repositories/__init__.py（新增，空包）
  - backend/app/repositories/user.py（新增）
- 新增内容：
  - `schemas/auth.py`（Pydantic v2，严格按 DATA_CONTRACTS §5）：
    - LoginRequest：username (1-50) + password (1-128)，str_strip_whitespace=True
    - TokenResponse：access_token + refresh_token + token_type=Literal["bearer"] + expires_in
    - RefreshTokenRequest：refresh_token (min_length=1)
    - CurrentUser：id (UUID) + username + display_name + roles + permissions
  - `repositories/user.py`：`UserRepository(session)` 类
    - `get_by_username(username) -> User | None`
    - `find_by_id(user_id) -> User | None`（用 session.get）
    - `save(user) -> User`（add + flush，事务边界由调用方控制）
    - `get_roles_and_permissions(user_id) -> (roles_sorted, perms_sorted_unique)` 显式 JOIN
- 设计决策：
  - User/Role/UserRole 模型未定义 SQLAlchemy relationship()，采用显式 JOIN 查询；避免在 service 层手写 SQL
  - `get_roles_and_permissions` 超出 BUILD_ORDER 字面三方法，但符合 CONVENTIONS §1.2（service 不写 SQL）
  - Repository 用类而非模块函数：便于 P2.3 service 注入，遵循 CONVENTIONS §2.2 BaseRepository 提示
- 测试验证（自检脚本）：
  - imports / Schema 校验（合法 + 空串拒绝 + 默认 token_type=bearer）✓
  - get_by_username("commander001") 拿到用户，password verifies ✓
  - find_by_id 还原 ✓
  - commander roles=['commander']，7 个权限 ✓
  - admin roles=['admin']，含 user:manage + system:admin ✓
  - system user 角色为 commander（P6.7 自动派单预留）✓
  - 不存在用户 → None；随机 UUID → ([], []) ✓
  - save() smoke test + rollback OK，未污染 DB ✓
- Git 提交：
  - commit message：feat: P2.2 auth schemas and UserRepository
  - push 状态：待执行
- 下一步建议：
  - P2.3：实现 AuthService + POST /auth/login，含账号锁定（连续 5 次失败 → 423，锁 15 分钟）；BUSINESS_RULES §6.1 错误码 `423_AUTH_ACCOUNT_LOCKED_001` / `401_AUTH_INVALID_CREDENTIAL_001`

### P2.1 — 配置与依赖注入（2026-05-02）

- 任务：P2.1 配置与依赖注入
- 执行工具：Claude Code
- 修改类型：feat
- 涉及文件：
  - backend/app/db/session.py（新增）
  - backend/app/core/security.py（扩展，新增 JWT 编/解码）
- 新增内容：
  - `db/session.py`：async engine 单例（pool_pre_ping=True）+ `async_session_maker`（expire_on_commit=False）+ `get_db()` FastAPI 依赖
  - `security.py` 新增：
    - `create_access_token(user_id, roles)` — payload `{sub, type=access, roles, iat, exp}`，TTL 24h
    - `create_refresh_token(user_id)` — payload `{sub, type=refresh, iat, exp}`，TTL 7d
    - `decode_token(token)` — 直接抛 jose 原生异常，由 P2.4 中间件翻译为 `401_AUTH_TOKEN_EXPIRED_001` / `401_AUTH_TOKEN_INVALID_001`
    - `access_token_expires_in()` 辅助函数（用于 TokenResponse.expires_in）
    - 常量 `TOKEN_TYPE_ACCESS / TOKEN_TYPE_REFRESH`
  - 算法 HS256；secret 来自 `settings.jwt_secret`
- 设计决策：
  - JWT payload 只放 `sub` (user_id) + `roles`，不放 `username/display_name`（CONVENTIONS §11 安全约定）
  - Refresh token 同样用 JWT 对称加密（无 DB 黑名单表，logout 由前端清 token，符合 BUILD_ORDER P2.5）
  - `decode_token` 不在此层翻译错误码，保留原生异常给 P2.4 中间件
- 环境处理：
  - venv 缺装 `python-jose[cryptography]`，已安装（连带 cryptography / cffi / rsa / ecdsa / pyasn1 / pycparser / six）
- 测试验证（自检脚本）：
  - imports OK ✓
  - JWT roundtrip OK，access expires_in=86400s ✓
  - 密码 hash + verify OK，bcrypt $2b$12$ ✓
  - `get_db()` 可执行 `SELECT 1` 并看到 seed 数据（active robots = 25）✓
  - 篡改 token → JWTError ✓
  - 过期 token → ExpiredSignatureError ✓
- Git 提交：
  - commit message：feat: P2.1 async db session + JWT helpers
  - push 状态：待执行
- 下一步建议：
  - P2.2：在 `app/schemas/auth.py` 实现 LoginRequest / TokenResponse / RefreshTokenRequest / CurrentUser（DATA_CONTRACTS §5）；在 `app/repositories/user.py` 实现 `get_by_username / get_by_id / save`

### P1.5 — Seed 数据脚本（2026-05-02）

- 任务：P1.5 Seed 数据脚本
- 执行工具：Claude Code
- 修改类型：feat
- 涉及文件：
  - scripts/seed.py（新增）
  - backend/app/core/security.py（新增，最小 hash_password / verify_password）
  - backend/pyproject.toml（更新，固定 bcrypt 版本 4.0.x）
- 新增内容：
  - 3 角色：commander / admin / observer，permissions JSONB 按 DATA_CONTRACTS §4.1
  - 3 用户：commander001 / admin001 / system（system 用户为 P6.7 自动派任务预留 created_by），bcrypt 哈希密码 password123
  - 3 编队：空中编队 Alpha（10 UAV）/ 地面编队 Bravo（10 UGV）/ 水面编队 Charlie（5 USV）
  - 25 机器人：UAV-001~010（DJI M300 RTK，has_yolo=true）+ UGV-001~010（Husky A200）+ USV-001~005（WAM-V 16），capability JSONB 严格按 §4.2 字段
  - 1 场景：6 级地震演练（杭州西湖区，map_bounds + initial_state 含 25 台机器人初始位置 100% 电量）
- 设计要点：
  - 全程异步（asyncpg + create_async_engine + async_sessionmaker）
  - Windows 显式设置 SelectorEventLoopPolicy
  - 幂等：roles/users/user_roles/robots/scenarios 用 ON CONFLICT DO NOTHING；robot_groups 无 UNIQUE 约束，使用 select-then-insert
  - 脚本自动 `os.chdir(BACKEND_DIR)`，确保 pydantic-settings 读到 `backend/.env`
- 测试验证：
  - SELECT count(*) FROM robots WHERE is_active → 25 ✓（10 uav + 10 ugv + 5 usv）
  - users/roles/user_roles/robot_groups/scenarios → 3/3/3/3/1 ✓
  - UAV-001 capability->>'has_yolo' → 'true' ✓
  - commander permissions JSONB → 7 个权限串 ✓
  - scenario.initial_state->'robots' jsonb_array_length → 25 ✓
  - password_hash 长度 60（bcrypt $2b$ 标准格式）✓
  - 重跑脚本：counts 不变，无报错（幂等 ✓）
- 环境处理：
  - venv 中 passlib + bcrypt 缺失，已安装 `passlib[bcrypt]>=1.7,<1.8` + 固定 `bcrypt==4.0.1`
  - bcrypt 5.0 与 passlib 1.7.4 不兼容，已在 pyproject.toml 固定 `bcrypt>=4.0,<4.1`
- Git 提交：
  - commit message：feat: P1.5 seed initial roles users robots groups scenario
  - push 状态：待执行
- 下一步建议：
  - P2.1 配置与依赖注入：补全 `app/core/config.py`（jwt 字段已就位）、新建 `app/db/session.py`（async session factory + FastAPI Depends）、扩展 `app/core/security.py` 加 JWT 编解码

### P1.4 — 修复数据库 DESC 索引方向（2026-05-02）

- 任务：P1.4 触发器与索引（DESC 方向修复 + 补验）
- 执行工具：Claude Code
- 修改类型：fix
- 涉及文件：
  - backend/migrations/versions/34b9faaa8fb0_fix_desc_indexes.py（新增）
- 修复内容：
  - 新建 Alembic migration `34b9faaa8fb0`，down_revision = `26cff1e230e8`
  - 12 个索引从 ASC 修正为 DESC：
    - `idx_tasks_status`：(status, created_at DESC)
    - `idx_robot_states_robot_time`：(robot_id, recorded_at DESC)
    - `idx_robot_states_time`：(recorded_at DESC)
    - `idx_faults_robot`：(robot_id, occurred_at DESC)
    - `idx_faults_unresolved`：(occurred_at DESC) WHERE resolved_at IS NULL
    - `idx_auctions_task`：(task_id, started_at DESC)
    - `idx_bids_auction`：(auction_id, bid_value DESC)
    - `idx_interventions_user`：(user_id, occurred_at DESC)
    - `idx_interventions_time`：(occurred_at DESC)
    - `idx_alerts_unack`：(raised_at DESC) WHERE acknowledged_at IS NULL AND is_ignored = FALSE
    - `idx_alerts_severity`：(severity, raised_at DESC)
    - `idx_replay_created`：(created_at DESC)
- 补验结果：
  - 触发器：4 条 ✓（set_timestamp_users/robots/tasks/blackboard_entries）
  - GIN 索引：4 个 ✓（idx_robots_capability/idx_robot_states_sensor/idx_tasks_capabilities/idx_blackboard_value）
  - alembic current：34b9faaa8fb0 (head) ✓
  - 12 个 DESC 索引 pg_indexes 查询全部包含 DESC 关键字 ✓
- 记录偏差：
  - 触发器命名偏差：`set_timestamp_blackboard_entries` vs DATA_CONTRACTS 的 `set_timestamp_blackboard`（接受，见"已知设计偏差"）
- Git 提交：
  - commit message：fix: P1.4 correct database index sort order
  - push 状态：已 push
- 下一步建议：
  - P1.5 Seed 数据脚本（scripts/seed.py），创建 3 角色 + 2 用户 + 25 机器人 + 3 编队 + 1 场景

### P1.2/P1.3 契约一致性修复（2026-05-02）

- 任务：Codex 审查后的 P1.2/P1.3 契约修复
- 执行工具：Claude Code
- 修改类型：fix
- 涉及文件：
  - backend/app/models/user.py
  - backend/app/models/robot.py
  - backend/app/models/task.py
  - backend/app/models/dispatch.py
  - backend/app/models/intervention.py
  - backend/app/models/blackboard.py
  - backend/app/models/alert.py
  - backend/app/models/replay.py
  - backend/migrations/versions/26cff1e230e8_init_schema.py
- 修复内容（ORM）：
  - 所有 UUID 主键改为 `server_default=text("gen_random_uuid()")`，删除 `import uuid` 和 `default=uuid.uuid4`
  - 布尔默认值改为 `server_default=text("TRUE")` / `server_default=text("FALSE")`
  - 字符串默认值改为 `server_default=text("'PENDING'")` / `server_default=text("'OPEN'")`（含单引号，生成正确的 SQL DEFAULT 'PENDING'）
  - 数值默认值改为 `server_default=text("2")` / `server_default=text("0")` / `server_default=text("1.0")`
  - 删除 `user_roles` 中冗余的 `UniqueConstraint("user_id", "role_id")`（复合主键已保证唯一性）
  - 补齐所有 28 个业务索引声明到各表 `__table_args__`（含 GIN 索引、partial 索引、DESC 排序）
- 修复内容（Migration）：
  - 12 处 `op.create_index` 补充 DESC 方向：created_at/recorded_at/occurred_at/started_at/bid_value/raised_at 等
  - 使用 `sa.text("col DESC")` 写法
- 已保持不变的设计偏差：
  - `idx_blackboard_active` 继续使用全量索引（原因已在"已知设计偏差"章节记录）
- 测试验证：
  - `Base.metadata.tables` 数量：17 ✓
  - `Base.metadata` 中业务索引总数：28 ✓（精确匹配 DATA_CONTRACTS §1）
  - `alembic current` → `26cff1e230e8 (head)` ✓，无报错
- Git 提交：
  - commit message：fix: align P1 ORM and migration with data contracts
  - push 状态：已 push
- 下一步建议：
  - 建议 Codex 复审本次修复，确认 server_default、索引声明无遗漏
  - 复审通过后推进 P1.4（因 ORM 已有 GIN 索引声明，P1.4 重点在新 migration 补齐 DB 中的 DESC/GIN 索引）

### P1.3 修复与补验 — Python 环境 + 端口修复（2026-05-02）

- 任务：P1.3 修复与补验
- 执行工具：Claude Code
- 修改类型：fix
- 涉及文件：
  - docker-compose.yml（端口 5432 → 5433，删除废弃 version 字段）
  - .env.example（DB_PORT=5433）
  - backend/.env（DB_PORT=5433，未入库）
  - （根目录）.env（DB_PORT=5433，未入库）
  - backend/migrations/env.py（恢复 asyncpg 异步迁移模式，移除 psycopg2 同步模式）
  - backend/.venv/（新建 Python 3.11.9 虚拟环境）
- 主要原因：
  - 本机 Windows 原生 PostgreSQL 15 占用端口 5432，导致 alembic/asyncpg 从主机侧连接时命中错误的数据库实例
  - env.py 临时改用 psycopg2 同步模式（P1.3 遗留），但 psycopg2-binary 未在 pyproject.toml 中声明，且在中文 Windows 上存在 GBK 编码问题
- 测试验证：
  - docker port drh_postgres → `5432/tcp -> 0.0.0.0:5433` ✓
  - asyncpg host-side 连接 localhost:5433 → `SELECT 1 = 1` ✓
  - `.\.venv\Scripts\alembic.exe current` → `26cff1e230e8 (head)` ✓
  - DB 表数量：18（17 + alembic_version）✓
  - DB 触发器：4 条 set_timestamp_* ✓
  - DB 索引：39 个非 PK 索引 ✓
- Git 提交：
  - commit message：fix: P1.3 stabilize python env and postgres migration config
  - push 状态：已 push
- 遗留问题：
  - P1.3 迁移为手写脚本（非 autogenerate），建议 Codex 做字段级审查
  - idx_blackboard_active 使用全量索引（见"已知设计偏差"章节）
- 下一步建议：
  - 建议 Codex 审查 P1.2（17 ORM 模型）和 P1.3（迁移脚本字段）是否与 DATA_CONTRACTS.md 完全一致
  - 审查通过后推进 P1.4（GIN 索引补充）

### P1.3 — 第一次迁移（2026-05-02）

- 任务：P1.3 第一次迁移
- 执行工具：Claude Code
- 修改类型：feat
- 涉及文件：
  - backend/migrations/versions/26cff1e230e8_init_schema.py（新增，手写完整 upgrade/downgrade）
  - backend/migrations/env.py（更新，改用 psycopg2 同步连接规避 Windows asyncpg 兼容问题）
  - backend/app/models/dispatch.py（修复 metadata → auction_metadata，规避 SQLAlchemy 保留属性名）
- 新增内容：
  - 17 张表 + 所有索引 + 触发器的完整迁移脚本
  - alembic_version 表记录 26cff1e230e8
- 已知偏差：
  - idx_blackboard_active 移除 WHERE expires_at > NOW()（PostgreSQL 要求索引谓词函数必须 IMMUTABLE，NOW() 是 STABLE）
- 测试验证：
  - SELECT count(*) FROM information_schema.tables WHERE table_schema='public' → 18 ✓
  - SELECT * FROM pg_trigger WHERE tgname LIKE 'set_timestamp%' → 4 条 ✓
- Git 提交：
  - commit message：feat: P1.3 first migration — 17 tables + indexes + triggers
  - push 状态：已 push
- 下一步建议：
  - P1.4：写第二个迁移，补齐 GIN 索引（触发器已包含在本次）

### P1.2 — 17 张表的 ORM 模型（2026-05-02）

- 任务：P1.2 17 张表的 ORM 模型
- 执行工具：Claude Code
- 修改类型：feat
- 涉及文件：
  - backend/app/models/user.py（新增，User / Role / UserRole）
  - backend/app/models/robot.py（新增，RobotGroup / Robot / RobotState / RobotFault）
  - backend/app/models/task.py（新增，Task / TaskAssignment）
  - backend/app/models/dispatch.py（新增，Auction / Bid）
  - backend/app/models/intervention.py（新增，HumanIntervention）
  - backend/app/models/blackboard.py（新增，BlackboardEntry）
  - backend/app/models/alert.py（新增，Alert）
  - backend/app/models/replay.py（新增，Scenario / ReplaySession / ExperimentRun）
  - backend/app/models/__init__.py（更新，导入全部 17 个模型）
- 新增内容：
  - 17 个 ORM 类，严格对应 DATA_CONTRACTS.md §1 DDL
  - VARCHAR+CHECK 约束替代 PostgreSQL ENUM（遵守 DATA_CONTRACTS §2）
  - JSONB 字段：capability / position / sensor_data / target_area 等
  - BIGSERIAL 主键：robot_states（高频写入）
  - 跨模块 FK 全部使用字符串引用（如 "tasks.id"），Alembic mapper 延迟解析
- 测试验证：
  - grep -r "class.*Base" app/models | wc -l → 17 ✓
- Git 提交：
  - commit message：feat: P1.2 implement 17 ORM models from DATA_CONTRACTS DDL
  - push 状态：已 push
- 下一步建议：
  - 推进 P1.3：alembic revision --autogenerate -m "init schema"，核查迁移脚本

### P1.1 — Alembic 初始化（2026-05-02）

- 任务：P1.1 Alembic 初始化
- 执行工具：Claude Code
- 修改类型：feat
- 涉及文件：
  - backend/app/core/config.py（新增，Pydantic Settings，含 database_url 属性）
  - backend/app/db/__init__.py（新增）
  - backend/app/db/base.py（新增，SQLAlchemy DeclarativeBase）
  - backend/app/models/__init__.py（新增，空包，供 env.py import）
  - backend/alembic.ini（新增，script_location=migrations，sqlalchemy.url 由 env.py 动态注入）
  - backend/migrations/env.py（新增，async 模式，从 app.core.config 读 DATABASE_URL）
  - backend/migrations/script.py.mako（新增，标准迁移模板）
  - backend/migrations/versions/.gitkeep（新增）
- 新增内容：
  - Alembic 完整骨架（等价于 alembic init -t async migrations）
  - async engine 迁移模式（run_async_migrations + asyncio.run）
  - config.py 最小实现（DB + auth + app 字段，P2.1 再补全）
- 测试验证：
  - alembic current（有数据库连接时不报错，无连接时报 connection refused 属正常）
- Git 提交：
  - commit message：feat: P1.1 alembic init with async env and declarative base
  - push 状态：已 push
- 下一步建议：
  - 推进 P1.2：严格按 DATA_CONTRACTS.md §1 DDL 实现 17 张 ORM 模型

### P0.1 — 创建仓库 + 目录结构（2026-05-02）

- 任务：P0.1 创建仓库 + 目录结构
- 执行工具：Claude Code
- 修改类型：chore
- 涉及文件：
  - backend/.gitkeep（新增）
  - frontend/.gitkeep（新增）
  - scripts/.gitkeep（新增）
  - tests/.gitkeep（新增）
  - docker/postgres/init/.gitkeep（新增）
  - docs/paper_assets/.gitkeep（新增）
  - docker-compose.yml（新增，P0.2 占位）
- 新增内容：
  - 顶层 7 个目录骨架，全部符合 CONVENTIONS.md §2.1
  - docker-compose.yml 占位文件
- 测试验证：
  - tree 输出与 BUILD_ORDER P0.1 要求一致
  - docs/ 内 8 份契约文档齐全
- Git 提交：
  - commit message：chore: P0.1 create project directory skeleton
  - push 状态：已 push
- 下一步建议：
  - 推进 P0.2：填充 docker-compose.yml，启动 postgres:15.5

### P0.2 — Docker Compose 编排（2026-05-02）

- 任务：P0.2 Docker Compose 编排
- 执行工具：Claude Code
- 修改类型：chore
- 涉及文件：
  - docker-compose.yml（改写，postgres:15.5 + backend 定义）
  - docker/postgres/init/01_init.sql（新增，启用 uuid-ossp/pgcrypto）
  - .env.example（新增，按 CONVENTIONS.md §10.1）
- 新增内容：
  - postgres:15.5 服务：端口 5432，卷持久化，healthcheck
  - backend 服务：依赖 postgres healthy，热重载挂载（P0.3 后可用）
  - .env.example 包含全部环境变量定义
- 测试验证：
  - `docker-compose up postgres` 启动 postgres 容器
  - `psql -h localhost -U disaster -d disaster_rescue` 可连接
- Git 提交：
  - commit message：chore: P0.2 docker-compose with postgres and env example
  - push 状态：已 push
- 遗留问题：
  - backend 服务需要 P0.3 完成 Dockerfile 后才能启动
- 下一步建议：
  - 推进 P0.3：创建 backend/Dockerfile + pyproject.toml + FastAPI /health 接口

### chore — 新增 Skills 配置（2026-05-02）

- 任务：新增最小 Skills 配置（非 BUILD_ORDER 任务）
- 执行工具：Claude Code
- 修改类型：chore
- 涉及文件：
  - .claude/skills/task-complete-git-push/SKILL.md（新增）
  - .claude/skills/dev-memory-update/SKILL.md（新增）
  - .agents/skills/task-complete-git-push/SKILL.md（新增）
  - .agents/skills/dev-memory-update/SKILL.md（新增）
- 主要变更：
  - task-complete-git-push：每完成 BUILD_ORDER 任务后执行 commit+push 的标准流程
  - dev-memory-update：每次变更后同步更新三份管理文档的标准格式
- Git 提交：
  - commit message：chore: add shared workflow skills
  - push 状态：已 push
- 下一步建议：
  - 推进 P0.3：Backend 空架子（FastAPI /health 接口）

### P0.3 — Backend 空架子（2026-05-02）

- 任务：P0.3 Backend 空架子（FastAPI）
- 执行工具：Claude Code
- 修改类型：feat
- 涉及文件：
  - backend/pyproject.toml（新增，依赖版本锁定至 CONVENTIONS §3.1）
  - backend/Dockerfile（新增，python:3.11-slim + uv）
  - backend/app/__init__.py（新增）
  - backend/app/main.py（新增，FastAPI + /health + CORS + BusinessError handler）
  - backend/app/core/__init__.py（新增）
  - backend/app/core/exceptions.py（新增，BusinessError 基类）
  - backend/pytest.ini（新增）
  - backend/tests/__init__.py（新增）
- 主要变更：
  - /health 接口返回 {"status":"ok"}
  - BusinessError 全局异常处理器挂载
  - CORS 允许 localhost:5173（前端开发地址）
- 验证命令：
  - curl http://localhost:8000/health
- Git 提交：
  - commit message：feat: P0.3 fastapi skeleton with /health endpoint
  - push 状态：已 push
- 遗留问题：
  - 依赖安装需用户本地执行 uv pip install -e ".[dev]" 或 docker-compose build backend
- 下一步建议：
  - 推进 P0.4：Frontend 空架子（Vite + React + TS）

### P0.4 — Frontend 空架子（2026-05-02）

- 任务：P0.4 Frontend 空架子（Vite + React + TS）
- 执行工具：Claude Code
- 修改类型：feat
- 涉及文件：
  - frontend/package.json（新增，依赖锁定至 CONVENTIONS §3.2）
  - frontend/tsconfig.json / tsconfig.node.json（新增，strict 模式）
  - frontend/vite.config.ts（新增，@ 别名 + API/WS 代理）
  - frontend/tailwind.config.js / postcss.config.js（新增）
  - frontend/index.html（新增）
  - frontend/src/main.tsx（新增，ReactDOM + RouterProvider）
  - frontend/src/styles/global.css（新增，Tailwind 入口）
  - frontend/src/router/index.tsx（新增，/ → /login）
  - frontend/src/pages/Login.tsx（新增，占位页面）
  - frontend/src/api/client.ts（新增，axios 单例 + 拦截器）
  - frontend/src/constants/index.ts（新增，与后端常量同步）
- 主要变更：
  - 完整 src/ 目录结构对照 CONVENTIONS §2.3
  - vite proxy 将 /api 和 /socket.io 转发至 localhost:8000
- 验证命令：
  - cd frontend && npm install && npm run dev
  - npm run build
- Git 提交：
  - commit message：feat: P0.4 vite-react-ts frontend skeleton
  - push 状态：已 push
- 遗留问题：
  - 需用户本地执行 npm install（node_modules 不入库）
- 下一步建议：
  - 推进 P0.5：打标记 commit + 进入 P1 数据层

---

## 重要决策记录

### 决策 1：每个 BUILD_ORDER 任务完成后必须提交远程仓库

原因：保证项目可回滚，避免 AI 多轮修改后项目不可控。

---

## 已知问题与注意事项

暂无。