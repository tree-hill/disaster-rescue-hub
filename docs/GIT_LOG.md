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

### 2026-05-10 - P8.5 论文素材：5 张算法对比图

- 任务：P8.5 生成论文算法对比图（matplotlib PNG）
- 工具：Claude Code
- 分支：main
- Commit message：feat: P8.5 paper assets — 5 algorithm comparison charts (matplotlib)
- Commit hash：（待填）
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - `backend/scripts/gen_paper_charts.py`：新文件，从 experiment_runs 表读取数据生成 5 张对比图
  - `docs/paper_assets/fig1_completion_rate.png`：任务完成率对比
  - `docs/paper_assets/fig2_response_time.png`：平均响应时间对比
  - `docs/paper_assets/fig3_path_length.png`：总路径长度对比
  - `docs/paper_assets/fig4_load_balance.png`：负载均衡标准差对比
  - `docs/paper_assets/fig5_decision_latency.png`：决策延迟对比
- 论文关键结论：Hungarian avg_path=19.654km（比 Greedy 低 2.8%），RANDOM load_std=0.610（比 Hungarian/Greedy 高 22%）

### 2026-05-10 - P8.4 前端实验面板接真实 API

- 任务：P8.4 ExperimentPanel 实接 POST /experiments + GET /experiments/{id} + GET /scenarios
- 工具：Claude Code
- 分支：main
- Commit message：feat: P8.4 frontend experiment panel — real API integration + GET /scenarios endpoint
- Commit hash：8b7f026
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - `frontend/src/api/experiment.ts`：新文件，ExperimentBatchRequest/Status/Charts 类型 + 4 个 API 函数
  - `frontend/src/pages/Replay.tsx`：ExperimentPanel 改为真实 API 集成（useEffect 加载已知批次、3s 轮询、handleStart 触发新批次）；离线 fallback REAL_EXPERIMENT_STATS（60-run 真实数据）
  - `backend/app/api/v1/scenarios.py`：新文件，GET /scenarios 端点（供实验配置面板拉取可用场景）
  - `backend/app/api/router.py`：注册 scenarios router

### 2026-05-10 - P8.3 跑实验（60 runs）

- 任务：P8.3 2 批次 × 3 算法 × 10 次 = 60 条 ExperimentRun
- 工具：Claude Code
- 分支：main
- Commit message：feat: P8.3 run experiments — 60 ExperimentRuns across 2 batches × 3 algos × 10 reps
- Commit hash：（待填）
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - `backend/scripts/run_experiments.py`：批量实验脚本（60 runs）
  - `backend/scripts/show_exp_stats.py`：实验结果汇总脚本
  - 论文关键数据：Hungarian avg_path=19.654km（比 Greedy 低 2.8%），RANDOM load_std=0.610（比 Hungarian/Greedy 高 22%）
  - batch_id_1=7207fd42-be39-4fcd-9031-b72604e3586d
  - batch_id_2=575bc666-acda-4fbc-8b4a-4038023dc8d9

### 2026-05-10 - P8.2 实验运行器后端

- 任务：P8.2 ExperimentRunner + REST API
- 工具：Claude Code
- 分支：main
- Commit message：feat: P8.2 ExperimentRunner backend — batch experiment runner + 4 REST endpoints
- Commit hash：（待填）
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - `backend/app/experiments/runner.py`：ExperimentRunner，每轮 10 个测试任务 + 拍卖 + 指标计算 + 清除
  - `backend/app/repositories/experiment.py`：ExperimentRunRepository
  - `backend/app/schemas/experiment.py`：ExperimentBatchRequest/Status/Charts/compute_stats/build_charts
  - `backend/app/api/v1/experiments.py`：4 REST 接口（POST 202/GET 状态/GET charts/GET export）
  - `backend/app/api/router.py`：注册 experiments router
  - `scripts/seed.py`：commander/admin 加 experiment:run 权限
  - `docs/DEV_MEMORY.md`、`docs/TASK_BOARD.md`：更新进度

### 2026-05-10 18:11 - P5 调度链路 Bug 修复

- 任务：修复拍卖、智能调度、任务分配到机器人执行链路的关键问题
- 工具：Codex + Claude Code
- 分支：main
- Commit message：feat: P5 dispatch chain — auction winner syncs RobotAgent to EXECUTING
- Commit hash：f0007ed
- 是否 push：✓
- 远程分支：origin/main
- 主要修改：
  - `backend/app/services/dispatch_service.py`：任务行锁防并发重复拍卖；AgentManager 运行时使用实时机器人状态；拍卖提交后同步获胜 Agent；发布 `task.status_changed`。
  - `backend/app/agents/robot_agent.py`：新增 `accept_assignment`，让 IDLE/RETURNING 机器人接单后进入 EXECUTING。
  - `backend/app/ws/event_bridge.py`：补齐 `task.status_changed` relay。
  - `backend/tests/unit/test_robot_agent_assignment.py`、`backend/tests/unit/test_dispatch_agent_sync.py`、`backend/tests/e2e/test_dispatch_e2e.py`：补充接单执行、agent 同步、任务状态事件测试。
- 自检：
  - `cd backend; .venv\Scripts\python.exe -m pytest tests\unit tests\algorithms tests\e2e -q` 通过，15 passed。
  - `cd backend; .venv\Scripts\python.exe -m ruff check app tests` 未通过，原因是环境未安装 ruff。
- 回滚命令：
  ```bash
  git checkout -- backend/app/services/dispatch_service.py backend/app/agents/robot_agent.py backend/app/ws/event_bridge.py backend/tests/e2e/test_dispatch_e2e.py docs/DEV_MEMORY.md docs/TASK_BOARD.md docs/GIT_LOG.md
  git clean -f backend/tests/unit/test_robot_agent_assignment.py backend/tests/unit/test_dispatch_agent_sync.py
  ```

### 2026-05-10 - 拍卖链路 Bug 修复

- 任务：auction_failed 根因修复 + 其他链路断点修复
- 工具：Claude Code
- Commit hash：81dbe81
- 是否 push：✓
- 主要修改：
  - `frontend/src/pages/TaskManagement.tsx` 拆分传感器/负载选择，fix 取消原因 ≥ 5 字符
  - `frontend/src/api/robots.ts` only_active → include_inactive 参数名修正
  - `scripts/seed.py` 新增 seed_robot_states() 幂等函数

### 2026-05-10 15:40 - P8.1 复盘后端 + P8 前端

- 任务：P8.1 SnapshotRecorder + 复盘 REST + P8 前端复盘中心与管理后台
- 工具：Codex + Claude Code
- 分支：main
- Commit message：feat: P8.1 replay — SnapshotRecorder + REST API + frontend replay page
- Commit hash：e1d5c0b
- 是否 push：✓
- 远程分支：origin/main
- 主要修改：
  - `frontend/src/api/replay.ts`：新增复盘 REST 客户端与类型。
  - `frontend/src/pages/Replay.tsx`：新增复盘中心页面，包含历史回放与算法对比实验双 Tab。
  - `frontend/src/pages/Admin.tsx`：重写管理后台，移除非机器人菜单占位，补齐用户、角色、审计、场景、配置面板。
  - `frontend/src/router/index.tsx`：注册 `/replay`。
  - `frontend/src/components/common/AppShell.tsx`：复盘中心导航不再 fallback 到 `/cockpit`。
  - `docs/DEV_MEMORY.md` / `docs/TASK_BOARD.md` / `docs/GIT_LOG.md`：记录本轮开发。
- 自检：
  - `cd frontend && npm.cmd run build` 通过。
  - Browser 验证 `/replay`、`/admin` 页面可访问，管理后台子菜单可切换。
- 回滚命令：
  ```bash
  git checkout -- frontend/src/components/common/AppShell.tsx frontend/src/pages/Admin.tsx frontend/src/router/index.tsx docs/DEV_MEMORY.md docs/TASK_BOARD.md docs/GIT_LOG.md
  git clean -f frontend/src/api/replay.ts frontend/src/pages/Replay.tsx
  ```

### 2026-05-10 — P7.4 改派弹窗

- 任务：P7.4 改派弹窗（HITL）
- 工具：Claude Code
- 分支：main
- Commit message：feat: P7.4 ReassignDialog (HITL) wired to /dispatch/reassign
- Commit hash：1a88f42
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - frontend/src/api/dispatch.ts（新增）：reassignTask + ReassignRequest/ReassignResponse 类型
  - frontend/src/api/tasks.ts（修改）：加 listTaskAssignments + TaskAssignmentRead
  - frontend/src/components/common/ReassignDialog.tsx（新增）：完整对照 prototype_02——蒙层 backdrop-blur + 880px elevated 弹窗 + Header 橙渐变 + 任务信息 4 列卡 + 1fr auto 1fr 对比区（左当前分配 / 中央 ArrowRight 含 pulse 动画 / 右候选列表启发式 score = battery×0.6 + (1-distKm/10)×0.4 排序，单选 radio）+ 干预原因 textarea ≥5 字符校验 + 审计提示 footer + 确认按钮 → POST /dispatch/reassign
  - frontend/src/pages/TaskManagement.tsx（修改）：TaskCard 加 onReassign prop 替换 alert 占位；挂载 ReassignDialog 跟踪 reassignTarget
  - frontend/src/pages/Cockpit.tsx（修改）：TaskCardReal 加 onReassign prop + 改派按钮（仅 EXECUTING/ASSIGNED）；挂载 ReassignDialog
  - docs/DEV_MEMORY.md / docs/TASK_BOARD.md：P7.4 完成，下一任务 P8
- 自检：`npx tsc --noEmit` exit=0；Vite HMR 已热更，可在 /tasks 任意 EXECUTING/ASSIGNED 任务卡测试
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-10 — P7.3 阶段 B + 环境修正

- 任务：P7.3 阶段 B —— 实装 RobotManagement / TaskManagement / Blackboard / Admin + Cockpit 联通真实数据 + Vite 端口绕过 Windows Hyper-V 保留段
- 工具：Claude Code
- 分支：main
- Commit message：feat: P7.3 stage B — 4 inner pages + cockpit real data + vite port 5500
- Commit hash：9e1fd72
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - frontend/src/api/robots.ts（新增）：listRobots/getRobot/listRobotStates/recallRobot + RobotRead/RobotDetailRead/RobotStateRead/FsmState/Position/RobotCapability 类型
  - frontend/src/api/tasks.ts（新增）：listTasks/getTask/createTask/cancelTask + TaskRead/TaskCreatePayload/TargetArea/TaskRequiredCapabilities/TaskStatus/TaskType 类型
  - frontend/src/api/blackboard.ts（新增）：listBlackboardEntries/getBlackboardStats + BlackboardEntry/BlackboardStats 类型
  - frontend/src/pages/RobotManagement.tsx（重写）：5 统计卡 + 工具栏 + 8 列表格点选 → 380px 详情面板（基础信息/位置任务/能力清单 + 编辑/紧急召回 grid-2）+ 分页 + 召回 prompt→POST /robots/{id}/recall→刷新
  - frontend/src/pages/TaskManagement.tsx（重写）：5 Tab + 任务卡 priority side border + 进度条 + 改派/取消/详情按钮；右侧 460px 创建表单（name/type radio/priority radio/圆心+半径目标区域 area_km2 自动算/能力 chips 多选）→POST /tasks 触发 P5.7 自动拍卖；取消 prompt→POST /tasks/{id}/cancel；WS task.created/cancelled/reassigned/auction.completed 自动 refresh
  - frontend/src/pages/Blackboard.tsx（重写）：5 统计卡 polling 5s + WS blackboard.updated / perception.detection 时间线（≤20 条 + fused/dropped/fire 三态颜色）+ 2 mock 视频卡（bbox 静态展示）+ YOLOv8 模型信息卡；右侧 filter chips + key 前缀搜索 + 黑板条目卡（fused 绿渐变 / fire 红渐变 + sources/value/TTL）
  - frontend/src/pages/Admin.tsx（重写）：左 240px 菜单 6 项 + 系统信息卡；机器人注册主面板 4 统计卡 + 工具栏 + 10 列表格（含 checkbox + 3 icon 操作）+ 底栏批量按钮 + 分页（其他 5 菜单显示 P8 占位）
  - frontend/src/pages/Cockpit.tsx（修改）：左栏接 GET /robots(25 台) + Tab 计数实时；右栏接 GET /tasks（fallback mock 当无任务）+ 新增 TaskCardReal 组件；创建任务按钮 navigate /tasks；编队/召回中心 navigate /robots；WS task.created/cancelled 自动 refresh
  - frontend/vite.config.ts（修改）：host='127.0.0.1' port=5500 strictPort=true（注释 Windows Hyper-V 5109-5208 保留段含 5173）
  - backend/app/main.py（修改）：CORS allow_origins 加 http://localhost:5500 + http://127.0.0.1:5500
  - docs/DEV_MEMORY.md / docs/TASK_BOARD.md：P7.3 完结，下一任务 P7.4
- 自检：`npx tsc --noEmit` exit=0；vite dev server HMR 持续工作，登录后可访问 7 页面（/cockpit /robots /tasks /blackboard /alerts /admin /login）
- 占位（待用户决定）：(a) Cockpit 地图静态 SVG → react-konva 实时渲染（P7.4 后），(b) 改派按钮 alert() × 3 处 → P7.4 ReassignDialog，(c) AlertCenter「派遣灭火/通知应急/实时画面」→ P8，(d) 创建任务地图绘制 → 当前经纬度文本输入替代，(e) Admin 编辑/启停/删除/批量 → P8（PUT/DELETE 后端已存在），(f) Blackboard 视频流 → 需 WebRTC/MJPEG 后端能力
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-10 — P7.3 阶段 A

- 任务：P7.3 阶段 A — Login + Cockpit + AlertCenter（按 01-06 设计标准统一）
- 工具：Claude Code
- 分支：main
- Commit message：feat: P7.3 stage A — Login/Cockpit/AlertCenter (prototype 01-06 design baseline)
- Commit hash：35abaa1
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - frontend/src/styles/global.css（重写）：注入 prototype_01 完整设计令牌（21 CSS variable + panel/badge-*/btn-*/progress-bar/scroll-thin/pulse-dot/kpi-num/nav-item/input-field/app-table 工具类）
  - frontend/index.html（修改）：preconnect Google Fonts 加载 Inter+JetBrains Mono
  - frontend/src/components/common/AppShell.tsx（新增）：顶导 7 项 NavLink + sessionInfo + Bell（→/alerts）+ 用户头像下拉登出 + fullHeight prop
  - frontend/src/api/auth.ts（新增）：login(POST /auth/login) + fetchMe(GET /auth/me)
  - frontend/src/api/situation.ts（新增）：fetchKpi + KPISnapshot 类型
  - frontend/src/api/alerts.ts（新增）：listAlerts/getAlert/acknowledgeAlert/ignoreAlert + AlertRead/Page<T>/AlertListParams
  - frontend/src/pages/Login.tsx（重写）：1:1 复刻 prototype_03 左右双栏；登录流程 POST /auth/login → fetchMe → setSession → wsConnect → navigate /cockpit
  - frontend/src/pages/Cockpit.tsx（重写）：1:1 复刻 prototype_01 三栏 + KPI 顶条接 GET /situation/kpi + WS kpi.snapshot 实时刷新；中央地图 SVG 800×600 复刻；左右栏 mock 数据；改派按钮占位 alert P7.4
  - frontend/src/pages/AlertCenter.tsx（重写）：按 01-06 风格统一（不沿用 prototype_10 青色）；GET /alerts list 7 列（severity/time/type/source/desc/status/actions）+ POST ack/ignore + WS alert.* 自动 refresh + 详情 DetailPanel 含 yolo_detection/sla_alert/影响范围（占位）+ 操作按钮（派遣灭火/通知应急/实时画面占位）
- 自检：`npx tsc --noEmit` exit=0；`npm run build` 通过 15.63s 1573 modules dist/index.js 365.39 kB gzip 115.71 kB；后端 pytest 12/12 无回归（未变更）
- 占位（待用户决定）：(a) Cockpit 机器人/任务列表 mock，(b) Cockpit 地图静态 SVG，(c) 改派按钮 + 派遣灭火/通知应急/实时画面 → alert，(d) AlertCenter 详情面板「火点面积/扩散方向/距最近水源」alerts.payload 无强约束 → "—"，(e) Login 角色选择仅 UI 提示
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-10 — P7.2

- 任务：P7.2 前端基础设施
- 工具：Claude Code
- 分支：main
- Commit message：feat: P7.2 frontend infra (auth/ws zustand stores + protected route + 6 page routes)
- Commit hash：fdba4bf
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - frontend/src/store/auth.ts（新增）：Zustand+persist(key='drh-auth')，AuthUser/accessToken/refreshToken+setSession/clear/hasPermission/hasAnyRole；selectIsAuthenticated 派生 selector
  - frontend/src/store/ws.ts（新增）：Socket.IO 单例 store。connect 用 io({path,'/socket.io', transports:['websocket'], auth: cb=>cb({token: useAuthStore.accessToken}), reconnection: true, reconnectionAttempts=MAX_RECONNECT(5), delay 1s 起封顶 5s})；'connect' 事件后 emit 'subscribe' {rooms} 重订；'auth_error' 自动 clear+disconnect+跳/login；subscribe(...rooms)/unsubscribe(...rooms) 维护本地 rooms 状态；addListener<P>(name, handler) 返回 unsubscribe；WSEventName 联合类型 22 个事件
  - frontend/src/components/common/ProtectedRoute.tsx（新增）：未登录→<Navigate to="/login" state={{from}}/>；无权限→<Navigate to="/cockpit"/>；permission 可选 prop
  - frontend/src/router/index.tsx（修改）：7 路由 /→/cockpit、/login、受保护组(/cockpit /robots /tasks /blackboard /alerts)、admin 组(/admin permission=system:admin)、*→/cockpit
  - frontend/src/pages/{Cockpit,RobotManagement,TaskManagement,Blackboard,AlertCenter,Admin}.tsx（新增）：6 个 P7.3 占位页
  - frontend/src/api/client.ts（修改）：baseURL='/api/v1'(VITE_API_BASE_URL 可覆盖)；token 改从 useAuthStore.getState().accessToken 实时读；401→useAuthStore.clear()+跳/login(避循环)
  - frontend/src/vite-env.d.ts（新增）：vite/client + ImportMetaEnv.VITE_API_BASE_URL（修复 tsc TS2339）
  - frontend/package-lock.json（新增）：npm install 生成
  - docs/DEV_MEMORY.md / docs/TASK_BOARD.md：P7.2 完成；下一任务 P7.3 6 大页面
- 自检：`npx tsc --noEmit` exit=0；`npm run build` 通过 1.80s 57 modules dist/index.js 214.67 kB gzip 69.96 kB；后端 pytest 12/12 无回归（未变更）
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-09 — P7.1

- 任务：P7.1 态势感知后端
- 工具：Claude Code
- 分支：main
- Commit message：feat: P7.1 situation backend (KPI 1Hz aggregator + alert engine 12 rules + REST/WS)
- Commit hash：4e671ab
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/situation/kpi_aggregator.py（新增）：KPIAggregator 1Hz 协程：聚合 → 缓存 → push_event 'kpi.snapshot' room=commander；fresh session per tick；get_or_refresh REST 入口（缓存为空同步聚合一次）；online_robots 用 row_number=1 取每 robot 最新 state；battery_distribution case 三桶 high≥60/30≤mid<60/low<30
  - backend/app/situation/alert_engine.py（新增）：12 条规则元数据（rule_key→type/severity）；register_alert_engine 订阅 8 类 EventBus 事件；_create_alert_and_publish 用 pg_advisory_xact_lock(0x7A5C_0002, year) 串行化 ALERT-YYYY-NNN 分配；FK violation 自动 null 化重试一次；OverdueTaskScanner 60s 扫描 sla_deadline<now AND status NOT IN terminal 任务，600s dedup（进程内 dict）；handler 覆盖 fire_detected / survivor_high_confidence / low_battery / comm_lost / sensor_error / auction_failed / high_decision_latency(>5000ms) / algorithm_switched / task_reassigned / task_cancelled / hitl_intervention
  - backend/app/situation/__init__.py（新增）：空模块标记
  - backend/app/repositories/alert.py（新增）：find_paginated 支持 severity/type/source/status(unack/ack/ignored)/start_time/end_time/search/page/page_size，排序 critical→warn→info+raised_at DESC；count_active 命中 idx_alerts_unack 部分索引；max_year_seq 用 cast(substr(code, prefix_len+1) AS Integer) max；find_by_ids 用于 batch
  - backend/app/services/alert_service.py（新增）：get/acknowledge/ignore/batch_acknowledge；commit 后 bus.publish；error code 404_ALERT_NOT_FOUND_001 / 409_ALERT_ALREADY_ACKED_001 / 409_ALERT_ALREADY_IGNORED_001
  - backend/app/api/v1/situation.py（新增）：GET /situation/kpi require_permission alert:read
  - backend/app/api/v1/alerts.py（新增）：GET /alerts list / GET /alerts/{id} / POST /alerts/{id}/acknowledge / POST /alerts/{id}/ignore / POST /alerts/batch-acknowledge；GET 用 alert:read，POST 用 alert:handle；batch 路由置于 /{id}/* 之前避免被 path 吞
  - backend/app/schemas/alert.py（新增）：AlertRead / AlertNoteRequest / AlertIgnoreRequest / AlertBatchAcknowledgeRequest+Response
  - backend/app/schemas/situation.py（新增）：BatteryDistribution / KPISnapshot
  - backend/app/api/router.py（修改）：include v1_situation + v1_alerts
  - backend/app/main.py（修改）：lifespan startup 加 register_alert_engine(bus) + KPIAggregator.start + OverdueTaskScanner.start；shutdown 反序停（kpi → overdue → blackboard_cleanup → pending_auction → bus）
  - backend/app/ws/event_bridge.py（修改）：加 _relay_alert_raised(commander+admin) / _relay_alert_acknowledged / _relay_alert_ignored；register_ws_relays 订阅
  - backend/app/perception/service.py（修改）：_push_high_confidence_alert push_event 后双发 bus.publish('perception.high_confidence_alert', payload) → AlertEngine 订阅
  - backend/app/agents/robot_agent.py（修改）：_enter_fault 在 _emit_event 后双发 bus.publish('robot.fault_occurred', fault_payload)
  - backend/app/core/config.py（修改）：加 kpi_aggregator_enabled=True / kpi_aggregator_interval_sec=1.0 / alert_overdue_scan_interval_sec=60.0 / alert_overdue_dedup_window_sec=600.0
  - scripts/seed.py（修改）：commander/admin 加 alert:read+alert:handle，observer 加 alert:read；已 re-seed
  - docs/DEV_MEMORY.md / docs/TASK_BOARD.md：P7.1 完成；下一任务 P7.2 前端基础设施
- 自检：29/29 全绿（A 2 规则元数据 + B 5 EventBus 触发 11 条规则全落库 + alert.raised 推送 11 次 + latency<=阈值不触发 + severity 校验 + code 形式 + C 2 OverdueScanner 触发+dedup + D 4 KPIAggregator 聚合+字段+缓存 + E 13 REST 401/200/404/409/批量+admin 权限 + F 3 WS 转推房间路由）；脚本验收后删除；`python -m pytest tests -q` 12/12 无回归 3.08s
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-09 — P6.9

- 任务：P6.9 Mock 视觉数据流
- 工具：Claude Code
- 分支：main
- Commit message：feat: P6.9 mock perception tick on RobotAgent (has_yolo + configurable rate)
- Commit hash：007bb32
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/agents/robot_agent.py（修改）：_tick() 末尾追加 await self._perception_tick()；新增 _perception_tick：跳过条件（mock_perception_enabled=False / has_yolo=False / fsm 不在 IDLE/EXECUTING/RETURNING / tick % interval ≠ 0）；满足时 fresh session 内调 PerceptionService.process_image，frame_id="{code}-mock-{tick:06d}"；try/except 仅日志不让 tick 死亡；新增 _mock_generate_detections：按 detection_rate 概率抽 0/1 条 + 4 类加权(survivor 0.40 / fire 0.25 / smoke 0.20 / collapsed_building 0.15) + conf 0.6+random*0.35 round(3) + 当前 position±50m 偏移（50/METERS_PER_DEGREE）+ bbox 占位 [100,100,300,300]；类常量 _MOCK_CLASSES
  - backend/app/core/config.py（修改）：加 mock_perception_enabled=False / mock_perception_tick_interval=1 / mock_perception_detection_rate=0.0；默认全关，避免 pytest 触发；演示时开 enabled=True + rate=0.05~0.2
  - docs/DEV_MEMORY.md / docs/TASK_BOARD.md：P6.9 完成；下一任务跳到 P7（P6 闭环；P6.4/P6.5 标记 Deferred 用户独立完成）
- 自检：16/16 全绿（A 跳过条件 4：enabled=False / has_yolo=False / FAULT 状态 / tick%interval≠0；B 触发 2：黑板有写入 + class 4 类内；C _mock_generate_detections 8：rate=0 空 / rate=1 单条 / class_name 4 类内 / confidence∈[0.6,0.95] / world_position 非空 + 偏移≤50m / bbox 4 元素 / 100 次抽样跨多类；D 端到端 2：5 tick × rate=1 → 5 次黑板写入 + items≥1）；脚本验收后删除；`python -m pytest tests -q` 12/12 无回归 2.81s
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-09 — P6.6 + P6.7 + P6.8（合并）

- 任务：P6.6 PerceptionService + P6.7 自动派任务 + P6.8 vision_boost 联通；P6.4/P6.5（数据集 + GPU 训练）由用户在 Colab 独立完成
- 工具：Claude Code
- 分支：main
- Commit message：feat: P6.6+P6.7+P6.8 perception service + auto-rescue + vision_boost from blackboard
- Commit hash：c25052b
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/perception/__init__.py（新增空 init）
  - backend/app/perception/service.py（新增）：PerceptionService.process_image(robot_id, robot_code, position, detections, frame_id, inference_time_ms) — filter conf≥0.5（INV-5）→ 每条 detection 走 blackboard.fuse(key=f"{class_name}:{int(lat*100)}_{int(lng*100)}", ttl_sec=300, value 含 type/position/bbox) → push WS perception.detection（一帧一推送，整 detections 数组到 commander 房间）→ survivor conf≥0.8 调 _handle_high_confidence_survivor（TaskRepository.find_active_near 500m 邻域查 search_rescue 活跃任务，已存在 priority bump 回 1，否则 system 用户 TaskService.create 自动救援任务 type=search_rescue priority=1 circle radius_m=200 area_km2=0.126 sensors=[camera_4k] min_battery_pct=30；TaskService.create 内部 commit + publish task.created → P5.7 dispatch_trigger 自动 start_auction 形成「视觉发现→自动派任务→自动拍卖」端到端链）→ fire conf≥0.7 推 perception.high_confidence_alert(class_name=fire) WS（写 alerts 表留 P7）；常量 SURVIVOR_HIGH_CONF=0.8 / FIRE_HIGH_CONF=0.7 / SURVIVOR_DEDUP_RADIUS_KM=0.5 / AUTO_RESCUE_RADIUS_M=200 / AUTO_RESCUE_AREA_KM2=0.126 / AUTO_RESCUE_MIN_BATTERY_PCT=30
  - backend/app/repositories/task.py（修改）：加 find_active_near(center_lat, center_lng, *, radius_km, types=None) — 拉 active 任务（PENDING/ASSIGNED/EXECUTING）+ 可选 type 过滤，Python haversine_km(target_area.center_point) ≤ radius_km 过滤，避免 PostGIS 依赖
  - backend/app/schemas/perception.py（新增）：InferRequest(robot_id/image_base64/position) + InferResponse(detections=[Detection]/inference_time_ms=0)
  - backend/app/api/v1/perception.py（新增）：POST /perception/infer require_permission("system:test")，_mock_infer(image_base64) → ([], 0) 占位（best.pt 落地时换 ultralytics model(image, conf=0.5, iou=0.45)），调 PerceptionService.process_image 验证主链路；frame_id={code}-{utc_yyyymmdd-hhmmss}-mock；robot 不存在 404_ROBOT_NOT_FOUND_001
  - backend/app/api/router.py（修改）：include v1_perception.router
  - backend/app/services/dispatch_service.py（修改）：P6.8 联通——filter 之后 solve 之前 nearby_survivor_count = len(get_blackboard().query_by_proximity(center=task_view.target_area.center_point, radius_m=VISION_PROXIMITY_RADIUS_M=200, type_filter="survivor", min_confidence=VISION_CONFIDENCE_THRESHOLD=0.8))，注入 compute_full_bid；per-task 一次查询，与 §5.4「不能用缓存的旧数据」对齐
  - scripts/seed.py（修改）：commander 角色加 system:test 权限，已 re-seed
  - docs/DEV_MEMORY.md / docs/TASK_BOARD.md：标记 P6.4/P6.5 为「Deferred 用户独立完成」；P6.6+P6.7+P6.8 合并完成；下一任务 P6.9 Mock 视觉数据流
- 自检：20/20 全绿（A POST /perception/infer 4：401 / commander 200 mock 空 detections / robot 404；B 主链路 8：INV-5 conf<0.5 过滤 valid=2 / 黑板写入 smoke + survivor 各 1 / fuse 路径 is_fused=True / task.created 触发 / type=search_rescue priority=1；C 邻域去重 2：500m 内已存在任务 → 不新建 + priority bump 回 1；D fire 2：不建任务 + 黑板写 fire；E P6.8 dispatch 4：vision_boost_applied=True + factor=1.5 / 黑板空 → False；UAV-001 robot_state 注入 position=(30.225,120.525) IDLE 95% 通过 R7）；脚本验收后删除；`python -m pytest tests -q` 12/12 无回归 2.70s
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-09 — P6.3

- 任务：P6.3 黑板 REST + WS
- 工具：Claude Code
- 分支：main
- Commit message：feat: P6.3 blackboard REST (entries / stats) + WS blackboard.updated relay
- Commit hash：49338b6
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/api/v1/blackboard.py（新增）：三 GET 路由 + _snapshot_to_read 适配器 —— /entries 内存 query(type/key_prefix/min_confidence/include_expired) + 切片分页 + Page[BlackboardEntryRead]；/entries/{key:path} 含 include_expired query，404_BLACKBOARD_KEY_NOT_FOUND_001；/stats 调 Blackboard.stats() → BlackboardStats；全 require_permission("blackboard:read")
  - backend/app/schemas/blackboard.py（修改）：加 BlackboardStats（total_entries/by_type/active_subscribers/avg_fusion_latency_ms/throughput_per_min）；BlackboardEntryRead.id 改 Optional[UUID]（兼容内存条目落库前 db_id=None）
  - backend/app/communication/blackboard.py（修改）：加 _write_times deque(maxlen=2000) + _fuse_latencies_ms deque(maxlen=200)；set() 入锁内 push _write_times；fuse() 调 fuse_inputs 前后 perf_counter 计入延迟；新增 stats() 方法（total_entries/by_type 排除过期 + active_subscribers + 平均延迟 + 60s 滑窗 throughput）；reset_for_tests 清空两 deque
  - backend/app/api/router.py（修改）：include v1_blackboard.router
  - backend/app/ws/event_bridge.py（修改）：加 _relay_blackboard_updated(snap)（payload 6 字段：key/value/confidence/source_robot_id/is_fused/fusion_source_count，commander 房间）+ register_blackboard_relays(blackboard) 订阅；幂等
  - backend/app/main.py（修改）：lifespan startup register_blackboard_relays(get_blackboard()) 紧跟 register_ws_relays
  - scripts/seed.py（修改）：commander/admin/observer 三角色加 blackboard:read；已 re-seed
  - docs/DEV_MEMORY.md / docs/TASK_BOARD.md：P6.3 完成移位；下一任务 P6.4
- 自检：35/35 全绿（A entries 8：401 / commander 200 / prefix 过滤 total=3 / type=fire 2 / min_confidence=0.8 2 / page_size=1 分页 / 集合相等；B entries/{key} 7：happy 200 / confidence/value 字段 / 不存在 404 + 错误码 / 已过期 404 / include_expired=true 200；C stats 8：200 / total/by_type/throughput/avg_lat/active_subs 字段 / admin 也能读；D WS 11：set 触发 1 次 + payload 6 字段 / fuse 后 is_fused=True + count>=2 / register 幂等；E seed 1：commander 角色含 blackboard:read）；脚本验收后删除；pytest 12/12 无回归 3.17s
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-09 — P6.2

- 任务：P6.2 信息融合
- 工具：Claude Code
- 分支：main
- Commit message：feat: P6.2 fusion (weighted_average + resolve_conflict + fused_from audit)
- Commit hash：7514cf7
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/communication/fusion.py（新增）：FusionInput dataclass + weighted_average(values, weights)（校验长度+sum>0 否则 ValueError，math.fsum 防累积误差）+ resolve_conflict(inputs)（max((timestamp, confidence)) → 返回 winning value['type']）+ fuse_inputs(inputs) 主入口 → (fused_value, fused_confidence, fused_from)：winner=同 type sources 走 confidence 加权 position.lat/lng + area_m2 + detected_count(int round) + altitude_m/heading_deg max conf 保留；intensity 按 max conf 投票；自由扩展字段（type/position/area_m2/intensity/detected_count 之外）保留最高 conf winner 的；fused_confidence=max(winners.confidence)；fused_from=winners weight=conf/sum 归一化(和=1) + losers weight=0 审计
  - backend/app/communication/blackboard.py（修改）：Blackboard.fuse 重写调 fusion.fuse_inputs —— existing 作为单 FusionInput（confidence/timestamp=updated_at/value=snapshot.value）+ 新写入合并；首次 fuse / existing 已过期 → 等价 set + fused_from=[新 source weight=1.0]；source_robot_id 取最近写入者；INV-5 仍守；is_fused=True
  - docs/DEV_MEMORY.md / docs/TASK_BOARD.md：P6.2 完成移位；下一任务 P6.3 黑板 REST + WS
- 自检：33/33 全绿（A wavg 4：等权/不等权/sum=0 报错/长度不一致报错；B resolve 2：时间 DESC + conf 平手；C 同 type 加权 8：position/area_m2/detected_count int 取整/intensity max conf/fused_confidence=max/fused_from 和=1/winner type 选择；D 类型冲突 5：winner=最新/position 仅 winner/loser weight=0/winner 和=1/fused_confidence=winner max；E 自由扩展 2：tag max conf + extra 保留；F 增量融合 8：首次 weight=1/二次加权/confidence=max/fused_from 含 2/和=1；G 类型冲突场景 3；H INV-5 1）；脚本验收后删除；`python -m pytest tests -q` 12/12 无回归 3.13s
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-09 — P6.1

- 任务：P6.1 黑板基础设施
- 工具：Claude Code
- 分支：main
- Commit message：feat: P6.1 blackboard infrastructure (in-mem + async DB + TTL cleanup)
- Commit hash：4b5d3e8
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/schemas/blackboard.py（新增）：BlackboardValue（extra="allow" 兼容 §4.9 自由扩展）+ FusionSource（confidence/weight 都 [0,1]）+ BlackboardEntryRead（DATA_CONTRACTS §5 字面）
  - backend/app/repositories/blackboard.py（新增）：save / find_by_id / find_latest_by_key（updated_at DESC + include_expired 切换） / find_active（type_filter 用 JSONB ->>'type' / key_prefix LIKE / min_confidence ≥ 0.5 / include_expired 默认 False） / delete_by_ids / delete_expired（DELETE WHERE expires_at IS NOT NULL AND < now，返回 rowcount）
  - backend/app/communication/__init__.py（新增空 init）
  - backend/app/communication/blackboard.py（新增）：Blackboard 进程级单例 + BlackboardEntrySnapshot dataclass（is_expired 方法）+ MIN_BLACKBOARD_CONFIDENCE=0.5（INV-5）+ DEFAULT_TTL_SEC_BY_TYPE（survivor/fire/smoke/collapsed_building=300、weather=30、custom 不给默认 → 永久）+ set/fuse 静默拒写 < 0.5 + asyncio.create_task fire-and-forget 落库（失败仅 logger.exception，不影响内存）+ 内存 dict 同 key 后写覆盖前写 + _resolve_expires_at 三级优先级（expires_at > ttl_sec > 默认表 > None）+ get/query（按 type_filter/key_prefix/min_confidence/include_expired 过滤，updated_at DESC）+ query_by_proximity（haversine_km 复用 rule_engine + 距离升序）+ subscribe/unsubscribe（去重 + await 串行 + 异常仅日志）+ cleanup_expired（lock 内删内存 + fresh session DB delete_expired，返回 (mem_count, db_count)）+ reset_blackboard_for_tests + get_blackboard()
  - backend/app/services/blackboard_cleanup.py（新增）：BlackboardCleanupScanner 仿 PendingAuctionScanner（asyncio.Event + wait_for(timeout=interval) 优雅停 + interval<=0 no-op + 重复 start/stop 幂等 + _run_loop 单轮异常仅日志保循环不退出）+ 全局单例 get_blackboard_cleanup_scanner + reset_scanner_for_tests
  - backend/app/core/config.py（扩展）：blackboard_cleanup_interval_sec: float = 60.0
  - backend/app/main.py（修改）：lifespan startup 加 BlackboardCleanupScanner.start（settings>0 才起）；shutdown 反序停（broadcaster → AgentManager → BlackboardCleanupScanner → PendingAuctionScanner → bus）
  - docs/DEV_MEMORY.md / docs/TASK_BOARD.md：移位 + 追加 P6.1 完成记录；下一任务 P6.2 信息融合
- 自检：32/32 全绿（A set/get + INV-5 4 + B TTL 4 + C query/proximity 3 + D fuse 4 + E subscribe 3 + F cleanup 6 + G DB 持久化 2 + H scanner 生命周期 6；脚本验收后删除）；`python -m pytest tests -v` 12/12 无回归 4.87s
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-09 — P5.8

- 任务：P5.8 跑通所有测试用例（ALGORITHM_TESTCASES TC-1~TC-10 + TC-E2E-1/2）
- 工具：Claude Code
- 分支：main
- Commit message：test: P5.8 algorithm test cases + dispatch e2e (TC-1..10 + TC-E2E-1/2)
- Commit hash：2fce42e
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/tests/algorithms/__init__.py（新增空 init）
  - backend/tests/algorithms/conftest.py（新增）：ALGORITHM_TESTCASES §0.2 fixtures + `_r` / `_t` / `by_code` 助手 + generate_robot(i) / generate_task(i) 网格生成器
  - backend/tests/algorithms/test_dispatch_algorithms.py（新增）：10 个测试函数对应 TC-1~TC-10；TC-7 用 `_fake_bid(value)` 注入字面出价矩阵，证明 Hungarian 28 vs Greedy 22；TC-9 用 `pstdev` 验 h_std ≤ g_std；TC-10 用 perf_counter 测 25×10 决策延迟
  - backend/tests/e2e/__init__.py（新增空 init）
  - backend/tests/e2e/conftest.py（新增）：function-scoped autouse fixture（每用例 engine.dispose + EventBus.reset_for_tests + register_auto_trigger + bus.start + DB cleanup by E2E_TASK_PREFIX="T-8888"/ROBOT="UAV-E2E"；teardown 反序）+ httpx ASGITransport client + commander_headers（复用 commander001）+ small_circle_target_area / seed_e2e_robot / wait_until 助手；engine.dispose 是关键：pytest-asyncio 0.23 每用例新 loop，asyncpg 连接池绑 loop 必须重建
  - backend/tests/e2e/test_dispatch_e2e.py（新增）：TC-E2E-1 任务全生命周期（POST /tasks → auto-trigger → ASSIGNED + auction/bids/active assignment + 手动 transit EXECUTING/COMPLETED + started_at/completed_at 副作用）+ TC-E2E-2 HITL 改派完整链路（monkeypatch bus.publish 包 real_publish 抓 task.reassigned + intervention.recorded 双事件 + DB intervention before/after_state 字段断言）
  - venv：装 pytest 8.0.2 + pytest-asyncio 0.23.8（pyproject dev 字面）
  - docs/DEV_MEMORY.md / docs/TASK_BOARD.md：移位 + 追加 P5.8 完成记录；P5 阶段完结，下一任务 P6.1 黑板系统
- 自检：`python -m pytest tests -v` 12/12 全绿 2.46s（10 算法 + 2 E2E）；幂等可重跑（teardown 清场）
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-09 — P5.7

- 任务：P5.7 任务自动触发拍卖（task.created auto-trigger + PENDING 30s scanner）
- 工具：Claude Code
- 分支：main
- Commit message：feat: P5.7 auto-trigger auctions on task.created + PENDING scanner
- Commit hash：04b5338
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/services/dispatch_trigger.py（新增）：`_try_start_auction(task_id)`（独立 session + BusinessError 404/409 静默 + 真实异常 logger.exception）+ `_on_task_created(payload)`（task.created handler，child_count>0 走 `TaskRepository.find_by_parent` 逐子触发，==0 直接触发当前 task）+ `register_auto_trigger(bus)` 订阅 EVT_TASK_CREATED + `PendingAuctionScanner(interval_sec)`（asyncio.Event 优雅停 + wait_for(timeout) + interval<=0 启动是 no-op + 重复 start/stop 幂等 + _scan_once 调 find_pending_leaves）+ `get_pending_auction_scanner` 单例 + `reset_scanner_for_tests`
  - backend/app/repositories/task.py（扩展）：`find_by_parent(parent_id)`（按 code ASC，便于稳定枚举）+ `find_pending_leaves`（distinct(parent_id WHERE NOT NULL).notin_ 子查询 + priority ASC + created_at ASC，跳过被 P4.3 网格分解的父任务）
  - backend/app/core/config.py（扩展）：`dispatch_auto_trigger_enabled: bool = True` + `dispatch_pending_scan_interval_sec: float = 30.0`（.env 可覆盖；测试场景设 0 仅停 scanner，flag 设 False 禁全部）
  - backend/app/main.py（修改）：lifespan startup `register_ws_relays → register_auto_trigger（按 settings） → bus.start → scanner.start（interval>0 才启）→ AgentManager`；shutdown 反序 `broadcaster → AgentManager → scanner → bus`，让 service 层最后一波 task.* 事件能被 dispatcher 消费完才停 bus
  - docs/DEV_MEMORY.md / docs/TASK_BOARD.md：移位 + 追加 P5.7 完成记录；当前阶段更新到「P5.1~P5.7 已完成，下一任务 P5.8」
- 自检：17/17 全绿（A 单任务 task.created → ASSIGNED 4 项；B 父+子 child_count>0 父跳过子拍卖 2 项；C scanner interval=0.5s pick PENDING → ASSIGNED 2 项；D 已 ASSIGNED 再触发静默 1 项；E find_pending_leaves NOT IN 父集合 3 项；F scanner.start/stop 幂等 + interval=0 no-op 5 项）；临时脚本 `_p57_selfcheck.py` + cleanup SQL 验收后均已删除
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-09 — P5.6

- 任务：P5.6 HITL 改派（POST /dispatch/reassign）
- 工具：Claude Code
- 分支：main
- Commit message：feat: P5.6 HITL reassign with full audit trail and dual-room WS broadcast
- Commit hash：18b8bd2
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/api/v1/dispatch.py（修改）：追加 POST /dispatch/reassign 路由（require_permission("robot:reassign")，调 DispatchService.reassign_task；返回 ReassignResponse(task: TaskRead, intervention_id)）；docstring 列错误码 + 副作用
  - backend/app/schemas/dispatch.py（扩展）：ReassignRequest（task_id / new_robot_id / reason max_length=500，min_length 业务层抛特化错误码）+ ReassignResponse(task: "TaskRead", intervention_id)；模块底部 `from app.schemas.task import TaskRead` + `ReassignResponse.model_rebuild()` 解决前向引用
  - backend/app/services/dispatch_service.py（扩展）：`reassign_task` 严格 BUSINESS_RULES §4.3.3 7 步：select(Task).with_for_update() 行锁 → 任务状态校验仅 ASSIGNED/EXECUTING（其他抛 409_TASK_STATUS_CONFLICT_001 details 含 expected_status='ASSIGNED|EXECUTING'）→ 新机器人 find_by_id（404_ROBOT_NOT_FOUND_001）+ _robot_to_eval_input(robot, latest_state, active_count) + RuleEngine.check（不合格 409_ROBOT_INELIGIBLE_001，details.code='rule_engine_reject' details.message=fail_reason）→ before_state.algorithm_used 循环 active assignment 取首个非空 auction_id 关联 auction.algorithm（默认 MANUAL_OVERRIDE）+ assigned_robot_ids=[old_robot_id]+task_code → release_active_for_task(released_at=NOW) + 新 TaskAssignment(auction_id=NULL, is_active=True) → after_state.algorithm_used='MANUAL_OVERRIDE' assigned_robot_ids=[new_robot_id] → 同事务写 human_interventions(intervention_type='reassign', target_task_id, target_robot_id=new) → commit + refresh → publish EVT_TASK_REASSIGNED commander 9 字段（含 from/to robot_id/code，多机协同 from 取 old_assignments[0]）+ EVT_INTERVENTION_RECORDED admin 6 字段；任务状态字面保持不变（不调 transit_task）；新增事件常量 EVT_TASK_REASSIGNED / EVT_INTERVENTION_RECORDED；imports 加 `from sqlalchemy import select`
  - backend/app/ws/event_bridge.py（修改）：`_relay_task_reassigned`（commander，业务面板）+ `_relay_intervention_recorded`（admin，审计页）+ register_ws_relays 订阅
  - docs/DEV_MEMORY.md / docs/TASK_BOARD.md：移位 + 追加 P5.6 完成记录；当前阶段更新到「P5.1~P5.6 已完成，下一任务 P5.7」
- 自检：38/38 全绿（A happy 19：HTTP 200 + task/intervention_id + WS 2 事件序列 + task.reassigned 9 字段 + from/to robot_id/code + intervention.recorded 6 字段 + DB 原 assignment is_active=False/released_at + 新 assignment is_active=True/auction_id IS NULL + intervention 1 条 + before/after_state.algorithm_used 取值 + assigned_robot_ids 切换 + target_robot_id + reason 落库；B 权限 3：observer 403 + 无 token 401；C reason 2：422_INTERVENTION_REASON_INVALID_001；D 任务 404 2：404_TASK_NOT_FOUND_001；E 机器人 404 2：404_ROBOT_NOT_FOUND_001；F 状态 3：PENDING/CANCELLED 409_TASK_STATUS_CONFLICT_001；G 不合格 5：is_active=FALSE 409_ROBOT_INELIGIBLE_001 + details.fail_reason='inactive' + 低电量 'low_battery'；H EXECUTING 2：HTTP 200 + task.status='EXECUTING'）；临时脚本 `_p56_selfcheck.py` + DB cleanup SQL 验证后均已删除
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-09 — P5.5

- 任务：P5.5 拍卖 REST 接口（5 路由 + HITL 算法切换）
- 工具：Claude Code
- 分支：main
- Commit message：feat: P5.5 dispatch REST routes + HITL algorithm switch
- Commit hash：5d0218a
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/api/v1/dispatch.py（新增）：POST /auction（task:create，返回含 bids 的 AuctionRead 201）+ GET /algorithm（task:read，{current, available}）+ POST /algorithm（algorithm:switch HITL，返回 {previous, current, intervention_id}）+ GET /auctions（分页 + task_id/algorithm/start_time/end_time 过滤）+ GET /auctions/{id}（含 bids 按 bid_value DESC）
  - backend/app/api/router.py（修改）：include dispatch router
  - backend/app/schemas/dispatch.py（扩展）：AuctionTriggerRequest / AlgorithmSwitchRequest / AlgorithmSwitchResponse / AlgorithmInfoResponse / BidRead / AuctionRead + AlgorithmName Literal；BidRead bid_value/vision_boost field_validator 把 Decimal 转 float
  - backend/app/repositories/auction.py（扩展）：find_paginated（task_id/algorithm/时间窗/分页，按 started_at DESC，与 idx_auctions_task 同向）
  - backend/app/repositories/bid.py（扩展）：find_by_auction（按 bid_value DESC）
  - backend/app/services/dispatch_service.py（扩展）：list_auctions / get_auction_with_bids / switch_algorithm（HITL 写 intervention 同事务，commit 失败 except 块回滚内存全局算法 set_algorithm(previous)）+ _validate_reason + _auction_not_found 错误工厂
  - backend/app/ws/event_bridge.py（修改）：追加 dispatch.algorithm_changed handler，commander + admin 两房间各 push_event 一次
  - docs/DEV_MEMORY.md / docs/TASK_BOARD.md：移位 + 追加 P5.5 完成记录
- 自检：77/77 全绿（B GET algorithm 4 + A POST auction 18 + D GET list 8 + E GET detail 4 + C POST switch 24，覆盖 401/403/404/409/422/200/201 全错误码 + AuctionRead/BidRead 字段契约 + WS 链路 5 事件 + dispatch.algorithm_changed 双房间 + intervention DB 持久化），临时脚本 `_check_p55.py` 验证后删除
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-04 — P5.4

- 任务：P5.4 拍卖编排服务（dispatch_service.start_auction 全流程）
- 工具：Claude Code
- 分支：main
- Commit message：feat: P5.4 dispatch service (start_auction) closing the auction loop end-to-end
- Commit hash：8fcdeb1
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/services/dispatch_service.py（新增）：DispatchService.start_auction(task_id, *, algorithm=None) 同事务原子写 auctions + bids + task_assignments + 状态机转移；filter→bid→solve 量 decision_latency_ms；commit 后 publish auction.started → bid_submitted×N → completed（或 failed）；DispatchSettings 全局算法单例（默认 HUNGARIAN，set_algorithm 切换 + algorithm 参数仅本次覆盖）
  - backend/app/repositories/auction.py（新增）：AuctionRepository.save / find_by_id
  - backend/app/repositories/bid.py（新增）：BidRepository.save_many 批量写入
  - backend/app/repositories/task_assignment.py（修改）：追加 count_active_by_robot_bulk 单次 GROUP BY 批量统计 active 任务数（避免 dispatch_service N+1 查询）
  - backend/app/ws/event_bridge.py（修改）：追加 4 个 auction.* → commander 房间转推 handler（auction.started / auction.bid_submitted / auction.completed / auction.failed）
  - docs/DEV_MEMORY.md / docs/TASK_BOARD.md：移位 + 追加 P5.4 完成记录
- 自检：99/99 全绿（I event_bridge 7 + H repo bulk 3 + A 404 3 + B 409 3 + C 无 eligible 11 + D Hungarian happy 16 + E WS 序列与 payload 35 + F DispatchSettings 5 + G algorithm 覆盖 3 + ...），临时脚本 `_check_p54.py` 验证后删除
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-04 — P5.3

- 任务：P5.3 三种算法（Hungarian / Greedy / Random）+ 工厂
- 工具：Claude Code
- 分支：main
- Commit message：feat: P5.3 auction algorithms (Hungarian/Greedy/Random) with factory
- Commit hash：f3d1889
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/dispatch/algorithms/__init__.py（新增）：公开接口 + get_algorithm(name, *, seed) 工厂
  - backend/app/dispatch/algorithms/base.py（新增）：AuctionAlgorithm 抽象基类 + 算法名常量 ALGORITHM_HUNGARIAN/GREEDY/RANDOM + KNOWN_ALGORITHMS frozenset
  - backend/app/dispatch/algorithms/hungarian.py（新增）：scipy.linear_sum_assignment + INF_COST=1e6 占位 + INF_COST_GUARD=1e5 过滤
  - backend/app/dispatch/algorithms/greedy.py（新增）：priority 升序 + max final_bid + 机器人不重用
  - backend/app/dispatch/algorithms/random.py（新增）：独立 Random(seed) 实例避免污染全局 RNG，文件名与 stdlib 同名故 `import random as _random`
  - backend/app/dispatch/rule_engine.py（修改）：TaskEvalInput 末尾追加 `priority: int = 2`（默认普通优先级，仅 GreedyAuction 用，RuleEngine.check / filter 不读，向后兼容）
  - docs/DEV_MEMORY.md / docs/TASK_BOARD.md：移位 + 追加 P5.3 完成记录 + 环境补装 numpy/scipy 备注
- 环境补装：venv 补装 numpy 1.26.4 + scipy 1.12.0（pyproject 已声明字面，仅是先前未 pip install）
- 自检：68/68 全绿（factory+base 14 + Hungarian 11 含 2×2 全局最优反例 1.7 vs 贪心 1.4 + Greedy 9 + Random 7 含同 seed 可复现 + 通用契约 9 + 端到端集成 14 + priority 向后兼容 3 + import sanity 2），临时脚本 `_check_p53.py` 验证后删除
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-04 — P5.2

- 任务：P5.2 出价计算（5 分量 + compute_full_bid → BidBreakdown）
- 工具：Claude Code
- 分支：main
- Commit message：feat: P5.2 bidding formulas with vision boost decoupled from blackboard
- Commit hash：9b0a0d7
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/dispatch/bidding.py（新增）：BUSINESS_RULES §1 全部 5 个分量函数（compute_distance_score haversine + 10 km 归一化 / compute_battery_score sqrt / compute_capability_match 软匹配 / compute_load_score MAX_LOAD=3 截顶 / compute_vision_boost has_yolo + 整数计数）+ compute_full_bid 主入口（base_score 加权 + vision_boost 乘法 → final_bid，复用 P5.1 RobotEvalInput / TaskEvalInput，nearby_survivor_count 整数注入避免与 P6.1 Blackboard 耦合）
  - backend/app/schemas/dispatch.py（新增）：仅 BidBreakdownComponent / BidBreakdown 两个 Pydantic 模型，对照 DATA_CONTRACTS §4.7；AuctionRead / BidRead 等留 P5.4 / P5.5 实现时增量补充
  - docs/DEV_MEMORY.md / docs/TASK_BOARD.md：移位 + 追加 P5.2 完成记录
- 自检：62/62 全绿（5 leaf 函数 27 项 + compute_full_bid 综合 27 项 + import sanity 8 项，含 Σ weighted=base_score 不变量、vision_boost 乘法不进 base、base_score ∈ [-0.10, 0.90] 两端、dist>10km 距离分=0、no-yolo 永远不享受加成），临时脚本 `_check_p52.py` 验证后删除
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-04 — P5.1

- 任务：P5.1 规则引擎（拍卖前硬约束过滤）
- 工具：Claude Code
- 分支：main
- Commit message：feat: P5.1 rule engine for hard-constraint filtering before auction
- Commit hash：47014fc
- 是否 push：是
- 远程分支：origin/main
- 主要修改：
  - backend/app/dispatch/__init__.py（新增）：dispatch 包标识
  - backend/app/dispatch/rule_engine.py（新增）：BUSINESS_RULES §3 全部 8 条硬约束 R1~R8 顺序短路 + RuleEngine.check / RuleEngine.filter 聚合统计 + 内置 haversine_km（R=6371 km）+ RobotEvalInput / TaskEvalInput 冻结 dataclass 显式入参（R8 active_assignments_count 由调用方注入，模块零 IO 无 DB 依赖）
  - docs/DEV_MEMORY.md / docs/TASK_BOARD.md（修正）：之前误把「拍卖触发器」标为 P5.1，更正为「P5.1 = 规则引擎」「P5.7 = 拍卖触发器」并补完成记录
- 自检：43/43 全绿（R1~R8 各自命中 + happy path + 短路顺序 2 项 + filter 聚合 8 项 + haversine 3 项 + import sanity 4 项），临时脚本 `_check_p51.py` 验证后删除
- 回滚命令：
  ```bash
  git revert <commit-hash>
  ```

### 2026-05-04 — P4.5

- 任务：P4.5 事件总线基础
- 工具：Claude Code
- 分支：main
- Commit message：feat: P4.5 in-process event bus + WS bridge for task.created/cancelled
- Commit hash：d8d49e9
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
