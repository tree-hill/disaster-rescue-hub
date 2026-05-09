# TASK_BOARD.md — 当前任务看板

> 本文档用于记录当前开发进度。
> Claude Code 和 Codex 在开始任务前必须先阅读本文档。

---

## 当前阶段

当前阶段：P5 调度算法（P5.1~P5.6 已完成，拍卖闭环 + REST + HITL 改派对外）  
当前任务：P5.7 任务自动触发拍卖（BUILD_ORDER §P5.7）  
任务来源：docs/BUILD_ORDER.md  
备注：P5.6 HITL 改派完成（POST /dispatch/reassign 严格 7 步：FOR UPDATE 锁 task → 状态校验 ASSIGNED/EXECUTING → 新机器人 RuleEngine.check（不合格 409_ROBOT_INELIGIBLE_001 + fail_reason 入 details）→ before_state.algorithm_used 取自 active auction.algorithm（默认 MANUAL_OVERRIDE）→ release_active + 新 TaskAssignment(auction_id=NULL) → after_state(MANUAL_OVERRIDE) → 写 human_interventions(reassign) → commit → publish task.reassigned 9 字段 commander + intervention.recorded 6 字段 admin；任务状态字面保持不变；schemas 追加 ReassignRequest/Response + 前向引用 model_rebuild；event_bridge 加 2 个 relay；38/38 自检全绿）。  

---

## 工具分工

### Claude Code 负责

- 架构设计
- 数据库模型
- WebSocket 架构
- 调度算法
- 业务规则
- 状态机
- HITL 人工干预
- 复杂 bug
- 论文核心创新点相关实现

### Codex 负责

- 小范围 bug 修复
- 前端 TypeScript 报错
- API 字段检查
- UI 样式调整
- 测试补充
- 代码审查
- 小范围重构

---

## 任务状态

### To Do

- [ ] P5.7 任务自动触发拍卖（BUILD_ORDER §P5.7）：监听 TaskCreatedEvent → 自动调用 start_auction + PENDING 30s 扫描重试
- [ ] P5.8 跑通所有测试用例（BUILD_ORDER §P5.8）：ALGORITHM_TESTCASES.md TC-1~TC-10 + TC-E2E-1/2

### In Progress

暂无。

### Done

- [x] P5.6 HITL 改派：`app/api/v1/dispatch.py` 追加 POST /dispatch/reassign（robot:reassign 守卫，调 DispatchService.reassign_task）；DispatchService.reassign_task 严格 BUSINESS_RULES §4.3.3 7 步：select(Task).with_for_update() 行锁 → 状态校验仅 ASSIGNED/EXECUTING（其他 409_TASK_STATUS_CONFLICT_001 含 expected_status='ASSIGNED|EXECUTING'）→ 新机器人 _robot_to_eval_input + RuleEngine.check（fail_reason 入 details，409_ROBOT_INELIGIBLE_001）→ before_state.algorithm_used 循环 active assignment 取首个非空 auction_id 关联 auction.algorithm（默认 MANUAL_OVERRIDE）+ assigned_robot_ids[old]→ release_active_for_task(released_at=NOW) + 新 TaskAssignment(auction_id=NULL is_active=True) → after_state.algorithm_used='MANUAL_OVERRIDE' assigned_robot_ids=[new] → 同事务写 human_interventions(intervention_type='reassign', target_task_id, target_robot_id=new) → commit → publish EVT_TASK_REASSIGNED commander 9 字段（task_id/code, from_robot_id/code, to_robot_id/code, reassigned_by_user_id, reason, intervention_id；多机协同 from 取 old_assignments[0]）+ EVT_INTERVENTION_RECORDED admin 6 字段（intervention_id, user_id, intervention_type, target_task_id, target_robot_id, reason）；任务状态字面保持不变（不调 transit_task）；schemas/dispatch.py 追加 ReassignRequest（task_id/new_robot_id/reason max_length=500）+ ReassignResponse(task: TaskRead, intervention_id) + from app.schemas.task import TaskRead 末尾 + model_rebuild；ws/event_bridge.py 加 _relay_task_reassigned(commander) / _relay_intervention_recorded(admin)；38/38 自检全绿（A happy 19 + B 权限 3 + C reason 2 + D 任务 404 2 + E 机器人 404 2 + F 状态 409 3 + G 不合格 5 + H EXECUTING 2，monkeypatch event_bus 捕获双事件 payload + DB 检查 active/inactive assignment + intervention.before/after_state 字段；脚本验收后删除）（2026-05-09，Claude Code）
- [x] P5.5 拍卖 REST 接口：`app/api/v1/dispatch.py` 5 路由（POST /auction 调 start_auction 返回含 bids 的 AuctionRead 201 / GET /algorithm 返回 {current, available} / POST /algorithm HITL 切换 commit 失败回滚内存全局 + 写 human_interventions + 双房间 dispatch.algorithm_changed / GET /auctions Page 分页 + 4 过滤参 / GET /auctions/{id} 含 bids 按 bid_value DESC）+ schemas/dispatch.py 追加 AuctionRead/BidRead/AuctionTriggerRequest/AlgorithmSwitchRequest/AlgorithmSwitchResponse/AlgorithmInfoResponse + AlgorithmName Literal + BidRead Numeric→float field_validator + AuctionRepository.find_paginated + BidRepository.find_by_auction + DispatchService.list_auctions / get_auction_with_bids / switch_algorithm + event_bridge 加 dispatch.algorithm_changed → commander+admin 双房间转推；77/77 自检全绿（B GET algorithm 4 + A POST auction 18 含 401/403/404/409/201 happy 全 WS 链路 + D GET list 8 含分页过滤 + E GET detail 4 含 bids DESC + C POST switch 24 含权限 / reason / algorithm Literal / DB intervention 4 字段 / WS 双房间 + payload 7 键）（2026-05-09，Claude Code）
- [x] P5.4 拍卖编排服务：`app/services/dispatch_service.py` DispatchService.start_auction(task_id, *, algorithm=None) 全流程同事务原子写 auctions + bids + task_assignments + 状态机转移（PENDING→ASSIGNED）；filter→bid→solve 之间用 perf_counter 量 decision_latency_ms（论文 NFR < 2 秒）；commit 后发 auction.started → auction.bid_submitted×N → auction.completed（无 eligible 时直接 auction.failed，不发其他事件）；DispatchSettings 全局算法单例（默认 HUNGARIAN，可被 set_algorithm 切换 + algorithm 参数仅本次覆盖）；vision_boost 暂传 0（P6.1 黑板未建）；新增 AuctionRepository（save / find_by_id）+ BidRepository（save_many 批量）+ TaskAssignmentRepository.count_active_by_robot_bulk（单次 GROUP BY，避免 N+1）；event_bridge 加 4 个 auction.* → commander 房间转推 handler；99/99 自检全绿（覆盖 404 / 409 / no_eligible / Hungarian happy path / WS 事件序列与 payload 35 项 / DispatchSettings 全局切换 / algorithm 参数覆盖 / repo bulk）（2026-05-04，Claude Code）
- [x] P5.3 三种算法 + 工厂：`app/dispatch/algorithms/{base,hungarian,greedy,random,__init__}.py`（AuctionAlgorithm 抽象基类 + HungarianAuction 用 scipy.optimize.linear_sum_assignment 全局最优 + GreedyAuction 按 priority 升序 + final_bid 最大 + 机器人不重用 + RandomAuction 独立 Random(seed) 可复现 + get_algorithm 工厂；统一接口 solve(robots, tasks, bids: dict[(rid,tid), BidBreakdown]) → {tid: rid}，bids 字典缺位即不合格）+ rule_engine.py 修改（TaskEvalInput 末尾 priority: int = 2，仅 Greedy 用，向后兼容 RuleEngine 行为不变）+ venv 补装 numpy 1.26.4 + scipy 1.12.0（pyproject 已声明字面）；68/68 自检全绿（factory+base 14 + Hungarian 11 包含 2×2 全局最优反例 1.7 vs 1.4 + Greedy 9 + Random 7 含同 seed 复现 + 通用契约 9 + 端到端集成 14 + priority 向后兼容 3 + import sanity 2）（2026-05-04，Claude Code）
- [x] P5.2 出价计算：`app/dispatch/bidding.py`（BUSINESS_RULES §1 全部 5 个分量函数 + compute_full_bid 主入口；权重常量 W_DISTANCE=0.40 / W_BATTERY=0.20 / W_CAPABILITY=0.30 / W_LOAD=0.10、距离归一化 10 km、电量 sqrt、能力软匹配、MAX_LOAD=3、VISION_BOOST_FACTOR=1.5）+ `app/schemas/dispatch.py`（仅 BidBreakdownComponent / BidBreakdown，按 DATA_CONTRACTS §4.7 字面）；compute_full_bid 复用 P5.1 RobotEvalInput / TaskEvalInput，nearby_survivor_count 整数注入避免与 P6.1 Blackboard 耦合；模块零 IO；62/62 自检全绿（5 leaf 函数 27 项 + compute_full_bid 综合 27 项 + import sanity 8 项，含 Σ weighted=base_score 不变量、vision_boost 乘法不进 base、base_score ∈ [-0.10, 0.90] 端点）（2026-05-04，Claude Code）
- [x] P5.1 规则引擎：`app/dispatch/rule_engine.py`（BUSINESS_RULES §3 全部 8 条硬约束 R1~R8 顺序短路 + RuleEngine.check / RuleEngine.filter 聚合统计 + 内置 haversine_km，R=6371 km）+ `RobotEvalInput` / `TaskEvalInput` 冻结 dataclass 显式入参（is_active / fsm_state / battery / position / type / capability / active_assignments_count；R8 计数由调用方从 task_assignments 注入）+ `app/dispatch/__init__.py` 包标识；模块零 IO 无 DB 依赖、import 不触发任何副作用；43/43 自检全绿（R1~R8 各自命中 + happy path + 短路顺序 2 项 + filter 聚合 8 项 + haversine 3 项 + import sanity 4 项）（2026-05-04，Claude Code）
- [x] P4.5 事件总线基础：`app/core/event_bus.py`（EventBus 单例 + asyncio.Queue + 后台 dispatcher + publish/subscribe 幂等 + handler 异常 logger.exception 隔离 + start/stop 优雅退出 + reset_for_tests）+ `app/ws/event_bridge.py` register_ws_relays（task.created/cancelled → push_event 转推 commander 房间）+ task_service 两处 push_event 改为 bus.publish + lifespan 启停 bus；22/22 自检全绿（unit 13 + e2e 9，含 publish-before-start 丢弃 / 重复 start/stop no-op / 异常隔离 / 多 handler 并发 / 端到端 bus→bridge→sio.emit 链路 + payload 7 键）（2026-05-04，Claude Code）
- [x] P4.4 其他任务接口：`api/v1/tasks.py` 5 个接口（GET 列表多过滤+分页 / GET /{id} TaskDetailRead 含 assignments+auctions[]占位 / GET /{id}/assignments / PUT /{id} 非终态 / POST /{id}/cancel）+ `services/task_service.py` 5 个方法（list_paginated / get_with_assignments / list_assignments / update / cancel 走状态机 transit + 释放 active assignments + 写 intervention + WS task.cancelled）+ `repositories/task.py` find_paginated（status_in / priority / type / created_by / search）+ `repositories/task_assignment.py`（save / find_by_task / release_active_for_task 批量更新）+ `schemas/task.py` 加 TaskAssignmentRead / TaskDetailRead / TaskCancelRequest + `scripts/seed.py` 给 commander/admin/observer 加 task:read，admin/observer 加 robot:read；38/38 自检全绿（含 WS payload 7 键 + intervention before/after_state + assignment 释放）（2026-05-04，Claude Code）
- [x] P4.3 任务创建接口：`api/v1/tasks.py` POST /tasks + `services/task_service.py`（area service 层校验 → 422_TASK_INVALID_AREA_001 / advisory lock 按年分配 T-YYYY-NNN root code 重试 3 次 / area_km2 > 1 触发 500m × 500m 网格分解（rectangle/polygon/circle 共用 bbox 平铺，子任务 code T-YYYY-NNN-CC，parent_id 关联） / 父+子同事务 commit / 失败回滚 / commit 后 push WS task.created 到 commander 房间 child_count）+ `core/constants.py` 新增 4 个任务常量 + 移除 `schemas/task.py` 中 area_km2/radius_m 的 schema 层 gt=0；27/27 自检全绿（纯函数 11 + advisory lock 串行 1 + HTTP 15）（2026-05-04，Claude Code）
- [x] P4.2 任务状态机服务：`services/task_status_machine.py`（TASK_TRANSITIONS 完全对齐 BUSINESS_RULES §2.1.3 + can_transit 纯函数 + transit 时间戳副作用 + 终态/跨级跳转拒绝 409_TASK_STATUS_CONFLICT_001 + 结构化日志 task_status_transit）；27/27 自检全绿（6×6 矩阵 + 9 happy path + 11 reject + error details 包含 from/to/reason）（2026-05-04，Claude Code）
- [x] P4.1 任务 Schemas + Repository：`schemas/task.py`（TargetArea + TaskRequiredCapabilities + TaskCreate/Read/Update，对照 DATA_CONTRACTS §1.8/§4.5/§4.6/§5）+ `repositories/task.py`（save/find_by_id/find_by_status[支持 str | Sequence[str]]/find_pending[priority ASC, created_at ASC]，事务边界 add+flush）；17/17 自检全绿（schema 静态校验 7 项 + repo 9 项 + rollback 清理 1 项）（2026-05-03，Claude Code）

- [x] P0.1 创建仓库 + 目录结构（2026-05-02，Claude Code）
- [x] P0.2 Docker Compose 编排（2026-05-02，Claude Code）
- [x] P0.3 Backend 空架子（2026-05-02，Claude Code）
- [x] P0.4 Frontend 空架子（2026-05-02，Claude Code）
- [x] P0.5 提交完整基建（2026-05-02，Claude Code）
- [x] P1.1 Alembic 初始化（2026-05-02，Claude Code）
- [x] P1.2 17 张表的 ORM 模型（2026-05-02，Claude Code）
- [x] P1.3 第一次迁移（2026-05-02，Claude Code）
- [x] P1.3 修复与补验：Python 3.11 venv + 端口 5433 + asyncpg env.py（2026-05-02，Claude Code）
- [x] P1.2/P1.3 契约一致性修复：server_default + 删冗余UniqueConstraint + 补28个Index + migration DESC（2026-05-02，Claude Code）
- [x] P1.4 触发器与索引：新建 migration 34b9faaa8fb0，修正 DB 中 12 个 ASC→DESC 索引；补验触发器 4 条 + GIN 索引 4 个（2026-05-02，Claude Code）
- [x] P1.5 Seed 数据脚本：3 角色 + 3 用户（含 system）+ 3 编队 + 25 机器人 + 1 场景，幂等可重跑（2026-05-02，Claude Code）
- [x] P2.1 配置与依赖注入：db/session.py async + security.py JWT（access 24h / refresh 7d，HS256）（2026-05-02，Claude Code）
- [x] P2.2 认证 Schemas + Repository：schemas/auth.py（4 schemas）+ UserRepository（4 方法含 roles/permissions JOIN）（2026-05-02，Claude Code）
- [x] P2.3 登录接口：POST /api/v1/auth/login + AuthService + 账号锁定（内存版，5 次失败锁 15 分钟，防用户名枚举）（2026-05-02，Claude Code）
- [x] P2.4 JWT 中间件：app/api/deps.py（oauth2_scheme + get_current_user + require_permission 依赖工厂），覆盖 401_AUTH_TOKEN_EXPIRED_001 / 401_AUTH_TOKEN_INVALID_001 / 403_AUTH_PERMISSION_DENIED_001，10/10 自检（2026-05-02，Claude Code）
- [x] P2.5 其他认证接口：POST /auth/refresh（AuthService.refresh）+ GET /auth/me + POST /auth/logout（204，response_class=Response，简化版无黑名单），httpx ASGITransport 10/10 自检（2026-05-02，Claude Code）
- [x] P2.6 统一错误处理：纯 ASGI `RequestIdMiddleware`（X-Request-Id 透传/生成）+ `ErrorResponse` schema + BusinessError/RequestValidationError/Exception 三大 handler，兜底 500 sanitization 不暴露内部错误细节，6/6 自检（2026-05-02，Claude Code）
- [x] P3.1 机器人 Schemas + Repository：`schemas/common.py`（Position/RobotCapability/Detection/VisionData/SensorData，跨领域复用）+ `schemas/robot.py`（RobotBase/Create/Update/Read/StateRead，Pydantic v2）+ `repositories/robot.py`（save/find_by_id/find_by_code/find_all/find_by_group，事务边界=add+flush）+ `repositories/robot_state.py`（append/find_latest_by_robot/find_by_robot_in_window，limit 上限不在 repo 校验），18/18 自检全绿、rollback 不污染 DB（2026-05-02，Claude Code）
- [x] P3.2 机器人 REST 接口实现：`schemas/pagination.py`（泛型 Page[T]）+ `schemas/robot.py` 追加 `RobotDetailRead` + `repositories/robot.py` 追加 `find_paginated`（type/group_id/search 过滤 + ILIKE）+ `services/robot_service.py`（404/409 错误工厂 + IntegrityError 翻译 + PATCH 语义 update + active task 守卫的 soft_delete）+ `api/v1/robots.py` 6 路由（GET 列表/详情/states + POST/PUT/DELETE，权限分 robot:read 和 robot:manage，limit le=1000 路由层 422）+ seed.py upsert_role 改幂等并补 commander 的 robot:read，13 项 18 断言 httpx ASGITransport 全绿（2026-05-03，Claude Code）
- [x] P3.3 RobotAgent 协程基础：`agents/robot_agent.py`（ROBOT_FSM_TRANSITIONS 字典 + transit 守卫 + 1Hz `run()` 主循环用 stop_event 替代 sleep + battery≤5 故障检测自动 transit FAULT）+ `agents/manager.py`（单例 AgentManager + start_all/stop_all 优雅退出 + 超时强制 cancel）+ `core/constants.py` 新增 FAULT_BATTERY_THRESHOLD / HEARTBEAT_TIMEOUT_SEC + `config.py` mock_agents_enabled 默认改 False + `main.py` FastAPI lifespan 集成；14 项断言全绿（含 lifespan 双分支直接测 async context manager）（2026-05-03，Claude Code）
- [x] P3.4 Mock 行为实现：`agents/robot_agent.py` 加 `target_position` + `set_target_position` + `_move_toward_target`（近似 1°=111320m，5 tick 误差 0.00%）+ `_drain_battery` + `_persist_state`（每 tick 独立 session 写一行 robot_states）+ `_emit_state_changed` WS 推送钩子（P3.4 仅 logger，P3.5 接 sio.emit）+ `_check_faults` 加概率注入分支；`constants.py` 新增 EXECUTING_BATTERY_DRAIN_PCT / MOVE_STEP_METERS / METERS_PER_DEGREE；`config.py` 新增 mock_fault_inject_probability；行为顺序：移动/电量 → 故障检测 → 写 DB → emit；10/10 自检全绿（1.05s × 25 Agent = 26 行符合 1Hz）（2026-05-03，Claude Code）
- [x] P3.5 WebSocket 推送：`app/ws/server.py`（python-socketio AsyncServer ASGI 模式 + socketio_path='ws'）+ `app/ws/handlers.py`（connect 走 query/auth dict 取 token + emit auth_error 后 disconnect 而非 raise / subscribe 按 commander/admin/observer 角色守卫房间 / unsubscribe / disconnect）+ `app/ws/broadcaster.py`（拉模型单协程 1Hz 读 AgentManager 快照 + 房间无人跳过 emit + 单 tick 异常仅 log）+ `main.py` 用 `socketio.ASGIApp(sio, other_asgi_app=app)` 导出 `asgi_app` + lifespan 同步启停 broadcaster；pyproject.toml 加 aiohttp dev 依赖（仅 AsyncClient 测试用）；20/20 自检全绿（commander 5s 收 5 条 batch × 25 updates，observer 拒 commander 房间，admin 同时获得 commander+admin）（2026-05-03，Claude Code）
- [x] P3.6 故障与召回：`schemas/intervention.py`（RecallRequest/Response，Pydantic max_length=500，min_length 业务校验由 service 抛特化错误码）+ `repositories/intervention.py` & `repositories/robot_fault.py`（add+flush）+ `ws/events.py`（push_event 自动注入 event_id+timestamp，INV-F）+ `services/recall_service.py`（7 步流程：reason 校验 → 404 → 503/409 → before_state → eta_sec → request_recall → intervention 同事务 → emit recall_initiated）+ `agents/robot_agent.py` 加 request_recall / `_arrived_at_base` / `_complete_recall`（emit recall_completed + transit IDLE）/ `_enter_fault`（transit FAULT + 写 robot_faults + emit fault_occurred）+ _tick 整合 RETURNING 移动 + 到达检测；`agents/manager.py` 加 request_recall 转发；`api/v1/robots.py` 加 POST /{id}/recall（robot:recall 守卫）；BUSINESS_RULES.md §6.2 新增 `409_ROBOT_NOT_RECALLABLE_001` + `503_AGENT_NOT_RUNNING_001`；26/26 自检全绿（in-process uvicorn）：A1-A7 权限/边界/404/IDLE 全过 + B 召回 happy path（intervention 持久化 + WS 双事件 + 到达基地 IDLE）+ C 低电量自动 FAULT（写 robot_faults + emit fault_occurred）+ D FAULT 再召回 → 409（2026-05-03，Claude Code）

---

## 当前锁定模块

当前无锁定模块。

规则：

1. 一个模块同一时间只允许一个工具修改。
2. Claude Code 修改复杂模块后，Codex 只能先审查，不要直接二次重构。
3. Codex 修复小 bug 后，必须记录到 DEV_MEMORY.md。
4. 完成一个 BUILD_ORDER 任务后，必须 Git commit + push。