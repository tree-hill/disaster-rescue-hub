# GIT_LOG.md — Git 提交记录

> 每完成一个 BUILD_ORDER 任务后，必须 commit + push。
> 本文档用于记录每次提交对应的任务、修改内容和回滚点。

---

## 提交记录模板

### YYYY-MM-DD HH:mm — 任务编号

- 任务：
- 工具：
- 分支：
- Commit message：
- Commit hash：
- 是否 push：
- 远程分支：
- 主要修改：
  - 
- 回滚命令：
  ```bash
  git revert <commit-hash>

## 提交记录

### 2026-05-04 — P4.5

- 任务：P4.5 事件总线基础
- 工具：Claude Code
- 分支：main
- Commit message：feat: P4.5 in-process event bus + WS bridge for task.created/cancelled
- Commit hash：(待 push 后回填)
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/core/event_bus.py（新增）：EventBus 单例 + asyncio.Queue + 后台 dispatcher + publish / subscribe 幂等 + unsubscribe + handler 异常隔离 + start/stop 优雅退出 + reset_for_tests
  - backend/app/ws/event_bridge.py（新增）：register_ws_relays 注册 task.created → push_event(commander) / task.cancelled → push_event(commander) 转推 handler
  - backend/app/services/task_service.py（修改）：_emit_created / cancel 内的 push_event 改为 bus.publish；service 层不再直接依赖 WS 协议层
  - backend/app/main.py（修改）：lifespan startup = bus → agents → broadcaster；shutdown 反向；register_ws_relays(bus) 在 bus.start() 之前
- 自检：22/22 全绿（unit 13 + e2e 9，含 publish-before-start 丢弃 / 重复 start/stop no-op / 异常隔离 / 多 handler 并发 / 端到端 bus→bridge→sio.emit + payload 7 键），临时脚本验证后删除
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-04 — P4.4

- 任务：P4.4 其他任务接口（GET 列表 / 详情 / assignments + PUT + cancel）
- 工具：Claude Code
- 分支：main
- Commit message：feat: P4.4 task list/detail/update/cancel/assignments + cancel_task intervention
- Commit hash：7b3fcef
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/api/v1/tasks.py（扩展）：GET /tasks 多过滤 + Page[TaskRead] / GET /tasks/{id} TaskDetailRead 含 assignments+auctions[] / GET /tasks/{id}/assignments / PUT /tasks/{id} 仅非终态 / POST /tasks/{id}/cancel
  - backend/app/services/task_service.py（扩展）：list_paginated / get_with_assignments / list_assignments / update（PATCH 语义 + 终态拒绝）/ cancel（reason 校验 → status_machine.transit → release_active_for_task → 写 intervention → push task.cancelled）+ _validate_reason / _not_found 工厂
  - backend/app/repositories/task.py（扩展）：find_paginated（status_in / priority / type / created_by / search ILIKE）
  - backend/app/repositories/task_assignment.py（新增）：save / find_by_task / release_active_for_task（批量 UPDATE，synchronize_session=False）
  - backend/app/schemas/task.py（扩展）：TaskAssignmentRead / TaskDetailRead（含 auctions: list[dict] = [] 占位）/ TaskCancelRequest（reason max_length=500）
  - scripts/seed.py（修改）：commander/admin/observer 加 task:read；admin/observer 加 robot:read（observer 不再空权限）
- 自检：38/38 全绿（列表 9 + 详情 4 + PUT 3 + cancel 业务 12 + cancel WS 3 + cancel 错误路径 5 + PUT 终态拒绝 1 + setup 1），临时脚本验证后删除，DB 清理 0 残留
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-04 — P4.3

- 任务：P4.3 任务创建接口
- 工具：Claude Code
- 分支：main
- Commit message：feat: P4.3 POST /tasks with area validation, year-scoped code allocation, 500m grid decompose
- Commit hash：203c74a
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/services/task_service.py（新增）：TaskService.create + _validate_area + _decompose_to_tiles + _allocate_root_code（pg_advisory_xact_lock 按年串行）+ _child_code（T-YYYY-NNN-CC）+ _emit_created（commit 后 WS push）+ IntegrityError 重试 3 次
  - backend/app/api/v1/tasks.py（新增）：POST /tasks 201 + TaskRead，权限 task:create
  - backend/app/api/router.py（修改）：include v1_tasks.router
  - backend/app/core/constants.py（修改）：新增 TASK_GRID_DECOMPOSE_THRESHOLD_KM2 / TASK_GRID_TILE_METERS / TASK_CODE_SEQ_WIDTH / TASK_CHILD_CODE_SEQ_WIDTH
  - backend/app/schemas/task.py（修改）：移除 area_km2 / radius_m 的 gt=0（迁到 service 抛特化 422_TASK_INVALID_AREA_001）
- 自检：27/27 全绿（纯函数 11 + advisory lock 串行 1 + HTTP 15），临时脚本验证后删除，DB 清理 0 残留
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-04 — P4.2

- 任务：P4.2 任务状态机服务
- 工具：Claude Code
- 分支：main
- Commit message：feat: P4.2 task status machine with timestamp side effects
- Commit hash：9271dc1
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/services/task_status_machine.py（新增）：TASK_TRANSITIONS / VALID_TASK_STATUSES / TERMINAL_TASK_STATUSES / can_transit() / transit(task, target, *, reason=)；时间戳副作用按 BUSINESS_RULES §2.1.1 实施；非法转移统一抛 BusinessError(409_TASK_STATUS_CONFLICT_001)；结构化日志 task_status_transit
- 自检：27/27 全绿（矩阵 6 + happy 9 + reject 11 + error details 1），临时脚本验证后删除
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-03 — P4.1

- 任务：P4.1 任务 Schemas + Repository
- 工具：Claude Code
- 分支：main
- Commit message：feat: P4.1 task schemas + repository
- Commit hash：442caf9
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/schemas/task.py（新增）：TargetArea / TaskRequiredCapabilities / TaskBase / TaskCreate / TaskUpdate / TaskRead，对照 DATA_CONTRACTS §1.8/§4.5/§4.6/§5
  - backend/app/repositories/task.py（新增）：save / find_by_id / find_by_status（接受 str | Sequence[str]，空序列短路）/ find_pending（priority ASC + created_at ASC 对齐 idx_tasks_priority），事务边界 add+flush
- 自检：17/17 全绿（schema 7 + repo 9 + rollback 1），临时脚本验证后删除
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-03 — P3.6

- 任务：P3.6 故障与召回（recall API + intervention + RobotAgent recall 响应 + recall_initiated/recall_completed/fault_occurred WS 事件）
- 工具：Claude Code
- 分支：main
- Commit message：feat: P3.6 robot recall + fault flow with intervention and ws events
- Commit hash：3548771
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/schemas/intervention.py（新增）：RecallRequest（max_length=500，min_length 让 service 抛特化错误码）+ RecallResponse{intervention_id, recall_eta_sec}
  - backend/app/repositories/intervention.py & robot_fault.py（新增）：add+flush 模式
  - backend/app/ws/events.py（新增）：`push_event(name, payload, room='commander')` 自动注入 event_id+timestamp（INV-F）
  - backend/app/services/recall_service.py（新增）：7 步流程（reason 校验 → 404 → 503/409 → before_state → eta_sec → request_recall → intervention 同事务 → emit recall_initiated）
  - backend/app/agents/robot_agent.py（修改）：request_recall + RETURNING 移动 + _arrived_at_base + _complete_recall（emit recall_completed 含 eta_actual_sec）+ _enter_fault（transit FAULT + 写 robot_faults + emit fault_occurred）+ _emit_event 钩子；DEFAULT_INITIAL_POSITION 改用 BASE_LAT/LNG/ALT
  - backend/app/agents/manager.py（修改）：request_recall 转发
  - backend/app/api/v1/robots.py（修改）：POST /{id}/recall（robot:recall 守卫）
  - backend/app/core/constants.py（修改）：BASE_LAT/LNG/ALT + RETURNING_ARRIVAL_THRESHOLD_M=50 + RECALL_REASON_MIN/MAX_LEN
  - docs/BUSINESS_RULES.md（修改）：§6.2 加 `409_ROBOT_NOT_RECALLABLE_001` + `503_AGENT_NOT_RUNNING_001`（小幅契约扩展）
  - docs/DEV_MEMORY.md / TASK_BOARD.md / GIT_LOG.md：更新记录
- 设计决策：
  - 特化错误码优先于通用 422：reason min_length 校验放 service 抛 422_INTERVENTION_REASON_INVALID_001（BUSINESS_RULES §6.5 字面），而非 Pydantic 422_VALIDATION_FAILED_001
  - 拉模型 vs 推模型并存：高频 robot.position_updated 走 broadcaster 拉模型；事件型 fault/recall 走 push_event 主动推。两者互不干扰
  - request_recall 同步方法：仅做内存状态变更（transit RETURNING + target=BASE）；DB/WS 由 service 层串行
  - EXECUTING 与 RETURNING 共享移动逻辑（move + drain）；区别仅在 target 来源
  - RETURNING 抵达基地阈值 50m（BUSINESS_RULES §2.2.3 字面）；用与 Agent 移动一致的 1°=METERS_PER_DEGREE 近似
  - intervention.recorded（admin 房间审计事件）推迟到 P5；P3.6 只发 commander 房间
  - 任务侧解绑（current_task_id=None）留 P4：当前 after_state.current_task_id 保留 before_state 值
  - 写 robot_faults 失败仍 transit + emit：状态正确性优先于审计完整性
- 自检（26/26 全绿，临时 backend/_p36_check.py 验证后已删除；**in-process uvicorn**：因为测试需要直接读写 AgentManager 单例，把 uvicorn.Config + Server.serve() 跑在测试进程内）：
  - [setup] AgentManager 25 agents + observer001 用户即时插入 + commander WS subscribe
  - [A1-A7] 权限/输入边界：401 / 403（observer 无 robot:recall）/ 422_INTERVENTION_REASON_INVALID_001（4 字符 + 纯空白）/ 422_VALIDATION_FAILED_001（>500）/ 404 / 409_ROBOT_NOT_RECALLABLE_001(IDLE)
  - [B] UAV-001 happy path：200 + intervention_id + eta_sec=1 + WS recall_initiated（含全字段+event_id+timestamp）+ DB human_interventions 写入正确（before/after_state schema 对照 §4.8）+ agent transit RETURNING + 到达基地后收 recall_completed（含 eta_actual_sec）+ 最终 IDLE
  - [C] UAV-002 fault_occurred（直接 battery=4 → 下一 tick）：WS fault_occurred（low_battery/critical/fault_id UUID）+ DB robot_faults 写入 + agent FAULT
  - [D] FAULT 状态再召回 → 409_ROBOT_ALREADY_FAULT_001 + details.message=FAULT
  - [teardown] 清测试 intervention（reason LIKE '__test_p36__%%'）+ robot_faults + observer001 + reset 25 agents
- P3 阶段完整收口：BUILD_ORDER §P3 验收 5 条全过（CRUD + Mock Agent + 1Hz 心跳 + WS 推送 + recall + fault）
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-03 — P3.5

- 任务：P3.5 WebSocket 推送（python-socketio + connect/subscribe/disconnect + 1Hz batch broadcaster）
- 工具：Claude Code
- 分支：main
- Commit message：feat: P3.5 websocket server with batched robot.position_updated
- Commit hash：ab9d0f0
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/ws/__init__.py（新增）
  - backend/app/ws/server.py（新增）：`socketio.AsyncServer(async_mode='asgi', cors_allowed_origins=['http://localhost:5173'], ping_interval=25, ping_timeout=60)` 单例 + `SOCKETIO_PATH='ws'`
  - backend/app/ws/handlers.py（新增）：connect 取 query/auth dict 取 token + emit auth_error 后主动 disconnect（**不 raise**，否则 namespace 握手期就拒先前 emit 的 auth_error 包来不及送达）/ subscribe 按 commander/admin/observer 角色矩阵守卫房间 / unsubscribe / disconnect / `register_handlers(sio)` 显式注册
  - backend/app/ws/broadcaster.py（新增）：`PositionBroadcaster` 拉模型单协程 1Hz 读 `AgentManager.list_agents()` 内存快照 + 拼成 batch payload `updates: [...]` emit `robot.position_updated` 到 `room='commander'` + 房间无人 → 跳过 emit 节流 + 单 tick 异常仅 log 不让循环死亡 + stop 用 stop_event + 超时 cancel 兜底
  - backend/app/main.py（修改）：`import socketio` + 顶部 import ws 子包；lifespan 顺序 startup AgentManager → broadcaster，shutdown 反序；末尾 `ws_handlers.register_handlers(sio)` + `asgi_app = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path=SOCKETIO_PATH)`；真实运行入口改为 `uvicorn app.main:asgi_app`，httpx ASGITransport 测试 REST 仍用 `app`（不破坏 P0–P3.4 自检）
  - backend/pyproject.toml（修改）：dev 依赖加 `aiohttp>=3.9,<4.0`（仅 AsyncClient 测试用，**服务端 AsyncServer ASGI 模式不依赖 aiohttp**）
  - docs/DEV_MEMORY.md / TASK_BOARD.md / GIT_LOG.md：更新记录
- 设计决策：
  - 拉模型 vs 推模型：broadcaster 拉 AgentManager 快照，**不动 RobotAgent.\_emit\_state\_changed 钩子**。理由：WS_EVENTS §3 / §12.2 明文「batch 后 = 1 event/s ✓」+ 解耦 + 单点节流好做
  - 不 raise ConnectionRefusedError：让握手在 namespace 层成功，emit auth_error + sio.disconnect，client 才能拿到 WS_EVENTS §0.2 规范的 `auth_error{reason}` 事件
  - socketio_path='ws'：真实 URL `ws://host:port/ws/?EIO=4&...` 与 WS_EVENTS §0.2「ws://localhost:8000/ws」对齐
  - 房间角色矩阵：commander 房 = commander/admin；admin 房 = 仅 admin；observer 仅可连接无推送
  - broadcaster 仅在 mock_agents_enabled=True 时启动（无 Agent 数据 broadcaster 无意义）
- 自检（20/20 全绿，临时 backend/_p35_check.py 验证后已删除；socketio.AsyncClient + httpx 直连 uvicorn 跑在 127.0.0.1:8765 + MOCK_AGENTS_ENABLED=true；observer001 用户即时插入 finally 清理）：
  - [1] 无 token → auth_error{reason:invalid}
  - [2] 篡改 token → auth_error{reason:invalid}
  - [3] 过期 token（jose 编一个 1 秒前过期的 access）→ auth_error{reason:token_expired}
  - [4] commander 合法 → welcome 含 user.username='commander001' / roles 含 'commander' / session_id / event_id
  - [5] commander 订阅 commander → subscribed{rooms:['commander']}，无 subscribe_error
  - [6] commander 订阅 admin → subscribe_error{room:admin, reason:permission_denied}，**无** subscribed 补发
  - [7] observer 订阅 commander → 先收 welcome（可连接），订阅得 subscribe_error{room:commander, reason:permission_denied}
  - [8] admin 订阅 commander+admin → 1 条 subscribed{rooms:{commander,admin}}，无 error
  - [9] commander 订阅后 5.2s 收 5 条 robot.position_updated：updates 长度 25 / 字段完整 / position 含 lat/lng / 25 个 robot_code 不重复 / 含 event_id + timestamp
  - [10] disconnect 客户端干净退出
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-03 — P3.4

- 任务：P3.4 Mock 行为实现（移动 / 电量下降 / 每 tick 写 robot_states / emit 钩子）
- 工具：Claude Code
- 分支：main
- Commit message：feat: P3.4 mock agent behavior with state persistence
- Commit hash：93134a6
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/agents/robot_agent.py：
    * 新增 `target_position` + `set_target_position` / `clear_target_position`（P5 拍卖完成由 dispatch_service 注入）
    * 新增 `_move_toward_target`（近似 1° = METERS_PER_DEGREE，距离 ≤ step 时吸附 target）
    * 新增 `_drain_battery`（EXECUTING -0.5%/tick，下限 0）
    * 新增 `_persist_state`（每 tick 独立 session 写一行 robot_states，NUMERIC(5,2) 用 Decimal）
    * 新增 `_emit_state_changed` WS 推送钩子（P3.4 logger.debug 占位 + `_emit_override` 测试钩子）
    * `_check_faults` 加概率注入分支（settings.mock_fault_inject_probability > 0 时 random < p → 'unknown'）
    * `_tick` 重写为 5 阶段：tick++ → EXECUTING 行为 → 故障检测 → 写 DB → emit
  - backend/app/core/constants.py：新增 EXECUTING_BATTERY_DRAIN_PCT=0.5 / MOVE_STEP_METERS=1.0 / METERS_PER_DEGREE=111320.0
  - backend/app/core/config.py：新增 mock_fault_inject_probability: float = 0.0（默认关）
  - docs/DEV_MEMORY.md / TASK_BOARD.md / GIT_LOG.md：更新记录
- 设计决策：
  - 每 tick 都写 robot_states（与 P3 整体验收"每秒新增约 25 条"一致），非"仅状态变化时写"
  - target 由外部注入而非 Agent 内生成 mock（避免 P5 接入时拆代码）
  - 行为顺序：移动/电量 → 故障检测 → 写 DB → emit；电量跨阈值的那一 tick 立即写一行 fsm=FAULT
  - 近似 1° = 111320 m：lat 误差 0.7%，lng 30°N 误差 15%；P5 调度仍用真实 haversine
  - WS 钩子留 logger 占位 + `_emit_override` 测试劫持；P3.5 替换为 `sio.emit('robot.position_updated', ..., room='commander')`
- 自检（10 项断言全绿，临时 backend/_p34_check.py 验证后已删除）：
  - IDLE 5 tick → position/battery 不变
  - EXECUTING 无 target 5 tick → position 不变 + battery 80→77.5
  - EXECUTING + target 100m 北方 5 tick → 移动 5.0000m（精确）
  - 100 tick + target 1km → 累积 100.0000m（rel_err=0.00%）
  - UAV-001 累积写入 robot_states ≥ 115 行
  - EXECUTING + battery=5.5 → 1 tick → battery=5.0 + fsm=FAULT 写入
  - mock_fault_inject_probability=1.0 + battery=100 → 1 tick 必 FAULT
  - _emit_state_changed 钩子 3 次精确调用
  - **AgentManager 25 Agent + 1.05s → robot_states +26 行（1Hz × 25 验收通过）**
  - finally 清理：DELETE FROM robot_states WHERE recorded_at >= test_start → 146 行
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-03 — P3.3

- 任务：P3.3 RobotAgent 协程基础
- 工具：Claude Code
- 分支：main
- Commit message：feat: P3.3 robot agent and manager skeleton
- Commit hash：0a5d77c
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/agents/__init__.py（新增）
  - backend/app/agents/robot_agent.py（新增）：`ROBOT_FSM_TRANSITIONS` 字典严格抄 BUSINESS_RULES §2.2.3 + `RobotAgent` 类（__init__ + from_db + transit 守卫 + _check_faults battery≤5 + _tick + run 1Hz 主循环用 stop_event 替代 sleep + stop()）
  - backend/app/agents/manager.py（新增）：`AgentManager` 单例 + start_all 加载 active robots → asyncio.create_task + stop_all 用 stop_event + asyncio.gather + 超时 cancel 兜底 + reset_for_tests
  - backend/app/core/constants.py（修改）：新增 FAULT_BATTERY_THRESHOLD=5.0 + HEARTBEAT_TIMEOUT_SEC=15
  - backend/app/core/config.py（修改）：mock_agents_enabled 默认 True → False（避免 pytest/自检自动起 25 协程）；tick_hz int → float
  - backend/app/main.py（修改）：FastAPI `@asynccontextmanager async def lifespan(_app)` 闭环 startup/shutdown，仅在 settings.mock_agents_enabled=True 时调用 start_all/stop_all
  - docs/DEV_MEMORY.md / TASK_BOARD.md / GIT_LOG.md：更新记录
- 设计决策：
  - P3.3 不写 robot_states 表（P3.4 才写）：BUILD_ORDER 字面 P3.4 才说"状态变化时写表"
  - mock_agents_enabled 默认 False：自检 / pytest 启动 FastAPI 不自动起后台协程；本地开发想看 Agent 跑就在 backend/.env 显式开启
  - 故障检测仅 battery（P3.4 补 sensor_error / comm_lost / 概率注入）
  - stop_all 用 stop_event 而非 task.cancel：CancelledError 在 sleep 中被抛会触发 try/finally 中的 await，反而拖慢；stop_event.set() 让循环主动 break 更优雅
  - 单 tick 异常仅 logger.exception：P3.4 引入 DB/WS 后单次故障不应让协程整体死亡
  - 用 Event.wait 替代 sleep：stop() 可立即唤醒等待中的协程
- 自检（14 项断言全绿，临时 backend/_p33_check.py 验证后已删除）：
  - FSM 字典与 BUSINESS_RULES §2.2.3 完全一致
  - from_db(UAV-001) → code/type/fsm_state=IDLE/battery=100/position=CENTER/has_yolo=True
  - 合法 transit 链 IDLE→BIDDING→EXECUTING→RETURNING→IDLE 4 步全过
  - 非法 transit 拒绝：IDLE→EXECUTING / UNKNOWN 目标 / FAULT→BIDDING；FAULT→IDLE 唯一允许
  - _check_faults：battery=100/5.1→None；5.0/4.0→'low_battery'；_tick 自动 transit('FAULT')
  - AgentManager.start_all 启动 25，0.5s 内 tick_count min=8 max=9（tick_hz=20）
  - stop_all 0.000s 优雅退出，list_agents=[]
  - lifespan 双分支：False 跳过 start_all；True 启停闭环（25→0），直接测 async context manager（httpx ASGITransport 默认不触发 lifespan）
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-03 — P3.2

- 任务：P3.2 机器人 REST 接口实现
- 工具：Claude Code
- 分支：main
- Commit message：feat: P3.2 robot REST endpoints
- Commit hash：c79c1c7
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/schemas/pagination.py（新增）：泛型 `Page[T]`，所有 List 接口复用
  - backend/app/schemas/robot.py（修改）：追加 `RobotDetailRead(RobotRead)`，含 `latest_state: RobotStateRead | None`
  - backend/app/repositories/robot.py（修改）：追加 `find_paginated(*, type_, group_id, search, only_active, page, page_size)`，OR(code ILIKE, name ILIKE) 模糊匹配 + created_at DESC 排序 + offset/limit
  - backend/app/services/robot_service.py（新增）：`RobotService` 类，封装 list_paginated / get_with_latest_state / list_states / create / update / soft_delete；IntegrityError → `409_ROBOT_CODE_DUPLICATE_001`；task_assignments 检查 → `409_ROBOT_HAS_ACTIVE_TASK_001`；`404_ROBOT_NOT_FOUND_001` 错误工厂
  - backend/app/api/v1/robots.py（新增）：6 路由（GET 列表 + GET 详情 + POST + PUT + DELETE + GET /states），权限 robot:read / robot:manage 分层；limit Query(le=1000) 自动 422
  - backend/app/api/router.py（修改）：注册 v1_robots.router
  - scripts/seed.py（修改）：commander 权限补 `robot:read`；`upsert_role` 改 `ON CONFLICT DO UPDATE SET description=…, permissions=…`（重跑可同步刷新已存在角色，避免契约迭代后种子数据漂移）
  - docs/DEV_MEMORY.md / TASK_BOARD.md / GIT_LOG.md：更新记录
- 设计决策：
  - 分页放在 repo 层（CONVENTIONS §1.2 反模式：service 不写 SQL）
  - status（=fsm_state）过滤暂不实现，留 P3.5 WS 上线后用 service 内存缓存做
  - PUT 用 PATCH 语义（`model_dump(exclude_unset=True)`），区分"未传"与"显式 None"
  - limit 上限校验在路由层 `Query(le=1000)`，复用 P2.6 全局 422 handler
  - DELETE 默认 only_active 列表不可见；`include_inactive=true` 显式可见软删条目
  - `POST /robots/{id}/recall` 留 P3.6；`GET /robots/{id}/faults` BUILD_ORDER P3 全程未列，跳过
- 自检（13 项 18 断言全绿，临时 backend/_p32_check.py 验证后已删除）：
  - 401（无 token）/ 403（admin 无 robot:read）/ 201（POST）/ 409（重复 code）/ 200（默认分页 total=26）/ 200（type=uav total=11）/ 200（group_id=Alpha total=10）/ 200（GET detail with latest_state=null）/ 200（PUT 改名）/ 204（DELETE 软删）/ 默认列表不见 / include_inactive=true 仍可见 is_active=false / 409（DELETE 有 active task → 409_ROBOT_HAS_ACTIVE_TASK_001）/ 422（limit=2000 → 422_VALIDATION_FAILED_001）/ 200（limit=10）/ 404（不存在 UUID）
  - 测试数据 finally 块硬删（task_assignments / tasks / robots），不污染 DB
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P3.1

- 任务：P3.1 机器人 Schemas + Repository
- 工具：Claude Code
- 分支：main
- Commit message：feat: P3.1 robot schemas and repositories
- Commit hash：562835e
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/schemas/common.py（新增）：Position / RobotCapability / Detection / VisionData / SensorData，Pydantic v2，跨领域复用（P3 / P4 / P5 / P6）
  - backend/app/schemas/robot.py（新增）：RobotBase / RobotCreate / RobotUpdate / RobotRead / RobotStateRead，对照 DATA_CONTRACTS §5 + §1.4 + §1.6
  - backend/app/repositories/robot.py（新增）：`RobotRepository` 类，`save / find_by_id / find_by_code / find_all(only_active=True) / find_by_group`，事务边界=add+flush（不在 repo commit）
  - backend/app/repositories/robot_state.py（新增）：`RobotStateRepository` 类，`append / find_latest_by_robot / find_by_robot_in_window(start_time, end_time, limit=100)`，**limit 上限 1000 不在 repo 校验**，留给 service / API 层
  - docs/DEV_MEMORY.md / TASK_BOARD.md / GIT_LOG.md：更新记录
- 自检（18/18 全绿，临时脚本 backend/_p31_check.py 验证后删除，不入库）：
  - schema imports / RobotCreate 合法 / 缺字段拒绝 / type Literal 守卫
  - find_all(only_active=True)=25（types={uav,ugv,usv}）
  - find_by_code('UAV-001') 命中 + has_yolo=True / find_by_code('NOT-EXIST-999')=None / find_by_id 还原
  - find_by_group(空中编队 Alpha)=10 UAV（UAV-001..UAV-010）
  - RobotState.append 拿到 BIGSERIAL id + recorded_at
  - find_latest_by_robot 返回同一条
  - RobotStateRead.model_validate（fsm_state=IDLE / position.lat=30.2741 / battery=88.5）
  - find_by_robot_in_window(limit=10) 含本次写入
  - RobotRead.model_validate(uav001) → code=UAV-001
  - **rollback 后开新 session 复检 robot_states 干净（DB 未污染）**
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P2.6

- 任务：P2.6 统一错误处理（X-Request-Id + ErrorResponse + 兜底 500）
- 工具：Claude Code
- 分支：main
- Commit message：feat: P2.6 unified error handling with X-Request-Id and ErrorResponse
- Commit hash：d272147
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/core/middleware.py（新增）：纯 ASGI `RequestIdMiddleware`，每请求生成或透传 `X-Request-Id`（`req-<uuid4-hex32>`），写入 `scope["state"]["request_id"]`，包装 send 在 `http.response.start` 注入响应头（去重）。**有意不用 BaseHTTPMiddleware**（Starlette #1996 / FastAPI #4719：与 `@app.exception_handler(Exception)` 兜底冲突）
  - backend/app/schemas/error.py（新增）：`ErrorDetail{field?, code, message}` + `ErrorResponse{code, message, details, request_id, timestamp}`，对照 DATA_CONTRACTS §5 / API_SPEC §0.3
  - backend/app/main.py（修改）：挂 `RequestIdMiddleware`（最外层）+ CORS expose `X-Request-Id`；BusinessError handler 切换到 ErrorResponse 形态；新增 RequestValidationError handler → `422_VALIDATION_FAILED_001`；新增兜底 Exception handler → `500_INTERNAL_ERROR_001`（响应体仅 `服务器内部错误`，不暴露异常类型/堆栈/原始 message，仅 `logger.exception` 写日志）
  - docs/DEV_MEMORY.md / TASK_BOARD.md / GIT_LOG.md：更新记录
- 自检（6/6 全绿，httpx + ASGITransport，`raise_app_exceptions=False` 仅测试侧用以收回 ServerErrorMiddleware re-raise 的 500）：
  - [1] /health 自动生成 X-Request-Id（req-<hex32>）
  - [2] 客户端传 X-Request-Id 透传到响应同值
  - [3] BusinessError 路径（/auth/me 缺 token）→ 401 + body.code=401_AUTH_TOKEN_INVALID_001 + body.request_id 与 header 一致 + ErrorResponse schema 校验通过
  - [4] RequestValidationError（/auth/login 缺 password）→ 422 + 422_VALIDATION_FAILED_001 + details 含 field=password
  - [4b] /auth/login password="" → 422 + details 含 field=password
  - [5] 兜底 500：临时 `/__boom__` 抛 `ZeroDivisionError("secret-internal-detail-do-not-leak")` → 500 + 500_INTERNAL_ERROR_001 + message=服务器内部错误，响应体**不含** "secret-internal-detail" / "ZeroDivisionError" / "Traceback"
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P2.5

- 任务：P2.5 其他认证接口（refresh + me + logout）
- 工具：Claude Code
- 分支：main
- Commit message：feat: P2.5 auth refresh me logout endpoints
- Commit hash：fcede53
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/services/auth_service.py：新增 `refresh()` 方法（解 refresh token → 校验 type=refresh / 用户存活 → 颁新 access+refresh，过期/失效翻译为 401_AUTH_TOKEN_EXPIRED_001 / 401_AUTH_TOKEN_INVALID_001）
  - backend/app/api/v1/auth.py：追加 POST /refresh、GET /me（依赖 get_current_user）、POST /logout（204，response_class=Response，简化版无黑名单）
  - docs/DEV_MEMORY.md / TASK_BOARD.md / GIT_LOG.md：更新记录
- 自检（10/10 全绿，httpx + ASGITransport）：login / /me 带 access / /me 缺 token / /me 用 refresh / /refresh 合法（新 access 可打 /me） / /refresh 用 access / /refresh 篡改 / /refresh 过期 / /logout 204 / /logout 缺 token
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P2.4

- 任务：P2.4 中间件：JWT 解析 + 当前用户
- 工具：Claude Code
- 分支：main
- Commit message：feat: P2.4 jwt deps with get_current_user and require_permission
- Commit hash：984b66d
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/api/deps.py（新增）：oauth2_scheme（auto_error=False）+ get_current_user（翻译 401_AUTH_TOKEN_EXPIRED_001 / 401_AUTH_TOKEN_INVALID_001，校验 type=access，加载 roles+permissions）+ require_permission(perm) 依赖工厂（缺权限抛 403_AUTH_PERMISSION_DENIED_001）
  - docs/DEV_MEMORY.md / TASK_BOARD.md / GIT_LOG.md：更新记录
- 自检（10/10 全绿）：imports / 合法 access / 篡改 / 过期 / refresh-typed / inactive / ghost / 缺 token / require_permission 命中 / require_permission 缺失
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P2.3

- 任务：P2.3 登录接口 + 账号锁定
- 工具：Claude Code
- 分支：main
- Commit message：feat: P2.3 login endpoint + account lockout
- Commit hash：53b0bcf
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/core/constants.py（新增）：JWT TTL + 锁定阈值集中管理
  - backend/app/services/auth_service.py（新增）：AuthService.login + 模块级失败计数器（asyncio.Lock 守护）
  - backend/app/api/v1/auth.py + api/router.py（新增）：POST /api/v1/auth/login
  - backend/app/main.py（修改）：挂载 api_router
  - docs/DEV_MEMORY.md / TASK_BOARD.md / GIT_LOG.md：更新记录
- 自检：路由注册 / 成功登录 / 4 次失败不锁 / 第 5 次锁 / 锁内拒绝正确密码 / 锁过期重置 / 不存在用户同 401 / 三个 seed 用户全可登 / last_login_at 更新，9/9 全绿
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P2.2

- 任务：P2.2 认证 Schemas + Repository
- 工具：Claude Code
- 分支：main
- Commit message：feat: P2.2 auth schemas and UserRepository
- Commit hash：e6a87c2
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/schemas/__init__.py / schemas/auth.py（新增）：LoginRequest / TokenResponse / RefreshTokenRequest / CurrentUser（Pydantic v2，对照 DATA_CONTRACTS §5）
  - backend/app/repositories/__init__.py / repositories/user.py（新增）：UserRepository 类，含 get_by_username / find_by_id / save / get_roles_and_permissions（显式 JOIN，无 relationship() 依赖）
  - docs/DEV_MEMORY.md / TASK_BOARD.md / GIT_LOG.md：更新记录
- 自检：imports / Schema 校验 / 用 commander001 + admin001 + system 三个 seed 用户跑通 repo 4 方法 / save+rollback 不污染 DB，全绿
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P2.1

- 任务：P2.1 配置与依赖注入
- 工具：Claude Code
- 分支：main
- Commit message：feat: P2.1 async db session + JWT helpers
- Commit hash：6bef530
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/db/session.py（新增）：async engine + async_session_maker + get_db() Depends
  - backend/app/core/security.py（扩展）：create_access_token / create_refresh_token / decode_token / access_token_expires_in
  - docs/DEV_MEMORY.md / TASK_BOARD.md / GIT_LOG.md：更新记录
- 自检：imports / JWT roundtrip / get_db SELECT 1 / 篡改 token 拒绝 / 过期 token 拒绝 全绿
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P1.5

- 任务：P1.5 Seed 数据脚本
- 工具：Claude Code
- 分支：main
- Commit message：feat: P1.5 seed initial roles users robots groups scenario
- Commit hash：15cec31
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - scripts/seed.py（新增）：3 角色 + 3 用户（含 system）+ 3 编队 + 25 机器人 + 1 场景，幂等执行
  - backend/app/core/security.py（新增）：最小 hash_password / verify_password（bcrypt 12）
  - backend/pyproject.toml：固定 bcrypt 版本 4.0.x（避免 5.0 与 passlib 1.7.4 不兼容）
  - docs/PROJECT_CONTEXT.md §6：标记 P1 阶段完成
  - docs/DEV_MEMORY.md / TASK_BOARD.md / GIT_LOG.md：更新记录
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P1.4

- 任务：P1.4 修复数据库 DESC 索引方向
- 工具：Claude Code
- 分支：main
- Commit message：fix: P1.4 correct database index sort order
- Commit hash：27f5887
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/migrations/versions/34b9faaa8fb0_fix_desc_indexes.py（新增）：12 个索引 drop/recreate ASC→DESC
  - docs/DEV_MEMORY.md、TASK_BOARD.md、GIT_LOG.md：更新记录
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P1.2/P1.3 契约一致性修复

- 任务：P1.2/P1.3 契约一致性修复（Codex 审查后）
- 工具：Claude Code
- 分支：main
- Commit message：fix: align P1 ORM and migration with data contracts
- Commit hash：371f337
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/models/*.py（8个文件）：UUID server_default、布尔/字符串/数值 server_default、删冗余 UniqueConstraint、补齐28个业务 Index 声明
  - backend/migrations/versions/26cff1e230e8_init_schema.py：12处 DESC 索引方向修复
  - docs/DEV_MEMORY.md、TASK_BOARD.md、GIT_LOG.md：更新记录
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P1.3 修复与补验

- 任务：P1.3 修复与补验（Python 环境 + 端口冲突修复）
- 工具：Claude Code
- 分支：main
- Commit message：fix: P1.3 stabilize python env and postgres migration config
- Commit hash：37a5139
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - docker-compose.yml（删除 version 字段，PostgreSQL 主机端口 5432 → 5433）
  - .env.example（DB_PORT=5433）
  - backend/migrations/env.py（恢复 asyncpg 异步迁移模式，移除 psycopg2 同步模式）
  - docs/DEV_MEMORY.md（新增环境约束、已知设计偏差、P1.3 修复记录）
  - docs/TASK_BOARD.md（更新当前任务、新增 Codex 审查项）
  - docs/GIT_LOG.md（本次记录）
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P1.3

- 任务：P1.3 第一次迁移
- 工具：Claude Code
- 分支：main
- Commit message：feat: P1.3 first migration — 17 tables + indexes + triggers
- Commit hash：678bff2
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/migrations/versions/26cff1e230e8_init_schema.py（新增）
  - backend/migrations/env.py（psycopg2 sync 模式）
  - backend/app/models/dispatch.py（metadata → auction_metadata 修复）
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P1.2

- 任务：P1.2 17 张表的 ORM 模型
- 工具：Claude Code
- 分支：main
- Commit message：feat: P1.2 implement 17 ORM models from DATA_CONTRACTS DDL
- Commit hash：a77cd01
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/models/ 下 8 个模型文件（user/robot/task/dispatch/intervention/blackboard/alert/replay）
  - backend/app/models/__init__.py 导入全部 17 个模型类
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P1.1

- 任务：P1.1 Alembic 初始化
- 工具：Claude Code
- 分支：main
- Commit message：feat: P1.1 alembic init with async env and declarative base
- Commit hash：f5db3f5
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/core/config.py（新增，Pydantic Settings）
  - backend/app/db/__init__.py + base.py（新增，DeclarativeBase）
  - backend/app/models/__init__.py（新增，空包）
  - backend/alembic.ini（新增）
  - backend/migrations/env.py（新增，async 迁移）
  - backend/migrations/script.py.mako（新增）
  - backend/migrations/versions/.gitkeep（新增）
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P0.5

- 任务：P0.5 提交完整基建
- 工具：Claude Code
- 分支：main
- Commit message：feat: P0.5 complete project skeleton — docker fastapi vite-react
- Commit hash：86d8d84
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - docs/PROJECT_CONTEXT.md §6 标记 P0 完成
  - docs/DEV_MEMORY.md / TASK_BOARD.md / GIT_LOG.md 更新
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P0.4

- 任务：P0.4 Frontend 空架子
- 工具：Claude Code
- 分支：main
- Commit message：feat: P0.4 vite-react-ts frontend skeleton
- Commit hash：a4e5310
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - frontend/ 完整目录结构（package.json / tsconfig / vite / tailwind / router / client）
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P0.3

- 任务：P0.3 Backend 空架子（FastAPI）
- 工具：Claude Code
- 分支：main
- Commit message：feat: P0.3 fastapi skeleton with /health endpoint
- Commit hash：f047ee0
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/pyproject.toml / Dockerfile / pytest.ini
  - backend/app/main.py（/health + CORS + BusinessError handler）
  - backend/app/core/exceptions.py
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — chore: add shared workflow skills

- 任务：新增 .claude/skills 和 .agents/skills 最小配置
- 工具：Claude Code
- 分支：main
- Commit message：chore: add shared workflow skills
- Commit hash：c0c300d
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - .claude/skills/task-complete-git-push/SKILL.md
  - .claude/skills/dev-memory-update/SKILL.md
  - .agents/skills/task-complete-git-push/SKILL.md
  - .agents/skills/dev-memory-update/SKILL.md
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P0.2

- 任务：P0.2 Docker Compose 编排
- 工具：Claude Code
- 分支：main
- Commit message：chore: P0.2 docker-compose with postgres and env example
- Commit hash：c321c02
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - docker-compose.yml 改写（postgres:15.5 + backend 占位）
  - docker/postgres/init/01_init.sql 新增
  - .env.example 新增
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-02 — P0.1

- 任务：P0.1 创建仓库 + 目录结构
- 工具：Claude Code
- 分支：main
- Commit message：chore: P0.1 create project directory skeleton
- Commit hash：2e869f1
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - 新增 backend/ frontend/ scripts/ tests/ docker/postgres/init/ docs/paper_assets/ 目录
  - 新增 docker-compose.yml 占位文件
  - 更新 DEV_MEMORY.md / TASK_BOARD.md / GIT_LOG.md
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```