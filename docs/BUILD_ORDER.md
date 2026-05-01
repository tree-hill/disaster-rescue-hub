# BUILD_ORDER.md — 开发执行顺序

> **文档定位**:本文档把整个项目拆解成 **9 个阶段、约 70 个任务**,每个任务有明确的验收标准。
> **使用方式**:按顺序逐个推进,每完成一个任务勾选 `[x]`,所有验收通过才能进入下一阶段。
> **依赖**:Schema 引用 `DATA_CONTRACTS.md`,接口引用 `API_SPEC.md` / `WS_EVENTS.md`,业务规则引用 `BUSINESS_RULES.md`。
> **版本**:v1.0

---

## 0. 总览

### 0.1 阶段路线图(7 周建议节奏)

```
P0 项目基建        ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  Week 1
P1 数据层          ░░░░████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  Week 1
P2 认证 + 基础 API ░░░░░░░░████░░░░░░░░░░░░░░░░░░░░░░░░░░░░  Week 2
P3 机器人模块      ░░░░░░░░░░░░██████░░░░░░░░░░░░░░░░░░░░░░  Week 2-3
P4 任务模块        ░░░░░░░░░░░░░░░░██████░░░░░░░░░░░░░░░░░░  Week 3
P5 调度算法 ⭐核心 ░░░░░░░░░░░░░░░░░░░░░░██████████░░░░░░░░  Week 3-4
P6 协同通信+CV ⭐  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░██████░░░░░░  Week 4-5
P7 态势+前端原型   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░██████░░  Week 5-6
P8 复盘+实验+论文  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░████  Week 6-7
```

### 0.2 阶段交付物

| 阶段 | 关键产出 | 是否阻塞下一阶段 |
|---|---|---|
| P0 | 仓库 + Docker + 空 FastAPI 跑通 | ✓ |
| P1 | 数据库 + 17 表 + Alembic 迁移 | ✓ |
| P2 | 登录 + JWT + 权限 | ✓ |
| P3 | 机器人 CRUD + Mock Agent + 心跳上报 | ✓ |
| P4 | 任务 CRUD + 状态机 | ✓ |
| P5 | 三种调度算法 + 拍卖闭环 | **核心,必须 100% 通过** |
| P6 | YOLOv8 训练 + 集成 + 黑板 | **CV 核心** |
| P7 | 前端完整可用 | 论文截图来源 |
| P8 | 实验数据 + 论文素材 | 答辩前完成 |

### 0.3 任务标识规范

每个任务编号 `Px.y`:
- `Px` = 阶段
- `y` = 阶段内序号

例:`P5.3` = 第 5 阶段第 3 个任务。

---

# 阶段 P0:项目基建(预计 3 天)

> **目标**:有一个能 `git clone && docker-compose up` 跑起来的空壳。

## P0.1 — 创建仓库 + 目录结构
- [ ] 在 GitHub 创建仓库 `disaster-rescue-hub`
- [ ] 初始化 `.gitignore`(Python + Node + IDE)
- [ ] 创建顶层目录结构(详见 `CONVENTIONS.md §2`):
  ```
  disaster-rescue-hub/
  ├── backend/
  ├── frontend/
  ├── docs/                  ← 把 8 份文档放这里
  ├── docker/
  ├── scripts/
  ├── tests/
  ├── README.md
  └── docker-compose.yml
  ```
- [ ] 把 `DATA_CONTRACTS.md / API_SPEC.md / WS_EVENTS.md / BUSINESS_RULES.md / ALGORITHM_TESTCASES.md / CONVENTIONS.md / PROJECT_CONTEXT.md` 全部放入 `docs/`
- [ ] 提交首次 commit:`chore: initial project skeleton`

**验收**:`tree -L 2` 输出符合上述结构,`docs/` 内 8 份文档齐全。

## P0.2 — Docker Compose 编排
- [ ] 创建 `docker-compose.yml`,含 3 个服务:
  - `postgres:15.5`(端口 5432,卷持久化)
  - `backend`(挂载本地代码,热重载)
  - `frontend`(可选,首期可不容器化)
- [ ] PostgreSQL 初始化脚本挂在 `docker/postgres/init/`
- [ ] 创建 `.env.example`,定义 DB_HOST / DB_PORT / DB_USER / DB_PASS / JWT_SECRET 等

**验收**:`docker-compose up postgres` 起来,`psql -h localhost -U disaster -d disaster_rescue` 能连。

## P0.3 — Backend 空架子(FastAPI)
- [ ] `backend/pyproject.toml`(用 uv 或 poetry)
- [ ] 装依赖(版本对照 `CONVENTIONS.md §3`):
  ```
  fastapi==0.110.* uvicorn[standard]==0.27.* sqlalchemy==2.0.*
  asyncpg==0.29.* alembic==1.13.* pydantic==2.6.* pydantic-settings==2.2.*
  python-socketio==5.11.* python-jose[cryptography]==3.3.*
  passlib[bcrypt]==1.7.* structlog==24.1.* pytest==8.0.* pytest-asyncio==0.23.*
  ultralytics==8.1.* numpy==1.26.* scipy==1.12.*
  ```
- [ ] `backend/app/main.py` 启动 FastAPI,挂 `/health` 接口
- [ ] 启动:`uvicorn app.main:app --reload`
- [ ] 浏览器访问 `http://localhost:8000/docs` 看到 Swagger UI

**验收**:`curl localhost:8000/health` 返回 `{"status":"ok"}`。

## P0.4 — Frontend 空架子(Vite + React + TS)
- [ ] `npm create vite@latest frontend -- --template react-ts`
- [ ] 装依赖:
  ```
  zustand react-router-dom socket.io-client axios
  @tanstack/react-query lucide-react recharts
  tailwindcss postcss autoprefixer
  ```
- [ ] 配置 Tailwind(`tailwind.config.js` + `index.css` 引入)
- [ ] 创建 `src/api/client.ts`(axios 单例,baseURL 从 env 取)
- [ ] 创建 `src/router/index.tsx`(空路由,默认 `/login`)
- [ ] 启动:`npm run dev`,浏览器访问 `localhost:5173` 看到空白首页

**验收**:`npm run dev` 无报错,`npm run build` 能打包。

## P0.5 — 提交完整基建
- [ ] commit:`feat: project skeleton with docker, fastapi, vite-react`

---

# 阶段 P1:数据层(预计 2 天)

> **目标**:数据库 17 张表全部建立并能用 ORM 访问。

## P1.1 — Alembic 初始化
- [ ] `cd backend && alembic init -t async migrations`
- [ ] 修改 `alembic/env.py`:从 `app.core.config` 读 DATABASE_URL,改为 async
- [ ] 创建 `app/db/base.py`(SQLAlchemy DeclarativeBase)

**验收**:`alembic current` 不报错。

## P1.2 — 17 张表的 ORM 模型
> 严格按 `DATA_CONTRACTS.md §1` 的 DDL 实现,**字段名、类型、约束完全一致**。
- [ ] `app/models/user.py`:User, Role, UserRole
- [ ] `app/models/robot.py`:Robot, RobotGroup, RobotState, RobotFault
- [ ] `app/models/task.py`:Task, TaskAssignment
- [ ] `app/models/dispatch.py`:Auction, Bid
- [ ] `app/models/intervention.py`:HumanIntervention
- [ ] `app/models/blackboard.py`:BlackboardEntry
- [ ] `app/models/alert.py`:Alert
- [ ] `app/models/replay.py`:ReplaySession, ExperimentRun, Scenario

**验收**:`grep -r "class.*Base" app/models | wc -l` 输出 17(每个模型对应一个 Base 子类)。

## P1.3 — 第一次迁移
- [ ] `alembic revision --autogenerate -m "init schema"`
- [ ] 检查生成的迁移脚本,**手动核对**索引、CHECK 约束、JSONB 默认值
- [ ] `alembic upgrade head`
- [ ] 用 `psql` 检查表结构:`\dt` 看 17 张表,`\d robots` 看字段

**验收**:`SELECT count(*) FROM information_schema.tables WHERE table_schema='public'` 返回 17(若有 alembic_version 表则 18)。

## P1.4 — 触发器与索引
- [ ] 写第二个迁移:`alembic revision -m "add triggers and gin indexes"`
- [ ] 加入 `DATA_CONTRACTS.md §1` 末尾的 `trigger_set_timestamp` 函数和触发器
- [ ] 加入 GIN 索引(JSONB 上的)

**验收**:`SELECT * FROM pg_trigger WHERE tgname LIKE 'set_timestamp%'` 返回 ≥4 条。

## P1.5 — Seed 数据脚本
- [ ] `scripts/seed.py`:
  - 创建 3 个角色(commander / admin / observer)
  - 创建 2 个用户(commander001 / admin001),密码 `password123`
  - 创建 25 台机器人(10 UAV + 10 UGV + 5 USV,按 `DATA_CONTRACTS §4.2` 填能力)
  - 创建 3 个编队
  - 创建 1 个场景(`6 级地震演练`)
- [ ] `python scripts/seed.py` 跑通

**验收**:`SELECT count(*) FROM robots WHERE is_active` 返回 25。

---

# 阶段 P2:认证 + 基础 API(预计 2 天)

> **目标**:登录/获取 Token/受保护接口能用。

## P2.1 — 配置与依赖注入
- [ ] `app/core/config.py`(Pydantic Settings,从环境变量读取)
- [ ] `app/db/session.py`(async session factory,FastAPI Depends)
- [ ] `app/core/security.py`(JWT 编解码、密码哈希)

## P2.2 — 认证 Schemas + Repository
- [ ] `app/schemas/auth.py`:`LoginRequest / TokenResponse / CurrentUser`(对照 `DATA_CONTRACTS §5`)
- [ ] `app/repositories/user.py`:`get_by_username, save, find_by_id`

## P2.3 — 登录接口
> 严格对照 `API_SPEC.md §1`
- [ ] `POST /api/v1/auth/login` → `TokenResponse`
- [ ] 失败处理:`401_AUTH_INVALID_CREDENTIAL_001`
- [ ] 账号锁定逻辑(连续 5 次失败 → 423,锁定 15 分钟,Redis 或内存计数器都行)

## P2.4 — 中间件:JWT 解析 + 当前用户
- [ ] `app/api/deps.py`:`get_current_user(token: str = Depends(oauth2_scheme))`
- [ ] `app/api/deps.py`:`require_permission(perm: str)`(权限装饰器)

## P2.5 — 其他认证接口
- [ ] `POST /auth/refresh`
- [ ] `GET /auth/me`
- [ ] `POST /auth/logout`(简化版可不做黑名单,只前端清 token)

## P2.6 — 统一错误处理
- [ ] `app/core/exceptions.py`:定义 `BusinessError(code, message, http_status)`
- [ ] FastAPI exception_handler 注册:把 `BusinessError` / `RequestValidationError` 转成 `ErrorResponse`
- [ ] 所有响应必须含 `X-Request-Id` Header(中间件实现)

**验收**(整个 P2):
```bash
# 登录拿 token
curl -X POST localhost:8000/api/v1/auth/login \
  -d '{"username":"commander001","password":"password123"}'
# 应返回 access_token

# 用 token 取 /me
curl localhost:8000/api/v1/auth/me -H "Authorization: Bearer <token>"
# 应返回用户信息

# 错误的密码 5 次 → 423
```

---

# 阶段 P3:机器人模块(预计 4 天)

> **目标**:机器人 CRUD + 25 个 Mock Agent 跑起来 + 1Hz 心跳上报。

## P3.1 — Schemas + Repository
- [ ] `app/schemas/robot.py`:`RobotCreate / RobotRead / RobotUpdate / RobotStateRead`
- [ ] `app/repositories/robot.py`:`save / find_by_id / find_all / find_by_group`
- [ ] `app/repositories/robot_state.py`:时序写入与查询

## P3.2 — REST 接口实现(对照 API_SPEC §2)
- [ ] `GET /robots`(分页 + 过滤)
- [ ] `GET /robots/{id}`
- [ ] `POST /robots`(权限 `robot:manage`)
- [ ] `PUT /robots/{id}`
- [ ] `DELETE /robots/{id}`
- [ ] `GET /robots/{id}/states`(查时序)

## P3.3 — RobotAgent 协程基础
- [ ] `app/agents/robot_agent.py`:RobotAgent 类
  - `__init__(robot_id)`:从数据库加载配置
  - `async run()`:主循环 1Hz,执行心跳/状态机/故障检测
  - 状态机使用 `BUSINESS_RULES.md §2.2` 的 `ROBOT_FSM_TRANSITIONS` 字典
- [ ] `app/agents/manager.py`:AgentManager,管理 25 个 Agent 的生命周期
  - `start_all()`:在系统启动时调用,为所有 active 机器人创建协程
  - `stop_all()`:优雅关闭

## P3.4 — Mock 行为实现
- [ ] IDLE 状态下:位置不变,电量不变
- [ ] EXECUTING 状态下:每秒位置朝目标移动 1m,电量降 0.5%
- [ ] 故障检测:battery <= 5 → FAULT
- [ ] 状态变化时:写 `robot_states` 表 + 推送 WS

## P3.5 — WebSocket 推送
- [ ] `app/ws/server.py`:python-socketio 实例
- [ ] 实现 `connect / subscribe / disconnect` 事件(对照 `WS_EVENTS.md §2`)
- [ ] 实现 `robot.position_updated` 批量推送(每秒一次,合并 25 台)

## P3.6 — 故障与召回
- [ ] `POST /robots/{id}/recall`(对照 BUSINESS_RULES §4)
  - 校验状态(EXECUTING/BIDDING/RETURNING)
  - 写 intervention
  - 推送 `robot.recall_initiated`
- [ ] Agent 收到召回信号 → 状态转 RETURNING

**验收**(整个 P3):
1. `python scripts/start_agents.py` 启动 25 个 Agent
2. `psql` 查 `robot_states`:每秒新增约 25 条
3. 用 WebSocket 客户端连 `/ws`,订阅 `commander`,能收到 `robot.position_updated` 1Hz
4. 调用 recall API,该机器人 FSM 转为 RETURNING,WS 收到事件
5. **故意把某机器人电量调到 4%** → 自动转 FAULT,WS 收到 `robot.fault_occurred`

---

# 阶段 P4:任务模块(预计 3 天)

> **目标**:任务 CRUD + 状态机 + 网格分解。

## P4.1 — Schemas + Repository
- [ ] `app/schemas/task.py`:`TaskCreate / TaskRead / TaskUpdate / TaskRequiredCapabilities`
- [ ] `app/repositories/task.py`:`save / find_by_id / find_by_status / find_pending`

## P4.2 — 任务状态机服务
- [ ] `app/services/task_status_machine.py`(严格按 `BUSINESS_RULES.md §2.1`)
  - `TASK_TRANSITIONS` 字典
  - `can_transit(from, to) -> bool`
  - `transit(task, target_status, reason=None)`(同事务记录历史日志)
- [ ] 不允许的转移抛 `409_TASK_STATUS_CONFLICT_001`

## P4.3 — 任务创建接口
- [ ] `POST /tasks`(对照 API_SPEC §3)
  - 校验 area_km2 > 0 → 否则 422
  - 自动生成 code(`T-YYYY-NNN`)
  - 若 area_km2 > 1,触发网格分解(500m × 500m 切分)
  - 写 tasks 表
  - 发布 `TaskCreatedEvent` 到事件总线

## P4.4 — 其他接口
- [ ] `GET /tasks`(分页 + 状态过滤)
- [ ] `GET /tasks/{id}`(含 assignments)
- [ ] `PUT /tasks/{id}`(只允许改 name/priority/sla_deadline,且非终态)
- [ ] `POST /tasks/{id}/cancel`(对照 BUSINESS_RULES §4.1)
- [ ] `GET /tasks/{id}/assignments`

## P4.5 — 事件总线基础
- [ ] `app/core/event_bus.py`:基于 `asyncio.Queue` 的发布订阅
  - `publish(event)`
  - `subscribe(event_type, handler)`
- [ ] 与 WS 集成:某些事件(`task.created` 等)自动转推 WS

**验收**(整个 P4):
1. POST 创建一个任务 → 数据库 tasks 表新增,状态 PENDING,WS 收 `task.created`
2. 创建一个 area_km2 > 1 的任务 → 多条 tasks 记录(主任务 + 子任务,parent_id 关联)
3. 取消一个 PENDING 任务 → 状态变 CANCELLED,human_interventions 写入,WS 收 `task.cancelled`
4. 试图取消已 CANCELLED 的任务 → 409 报错

---

# 阶段 P5:调度算法 ⭐ 核心(预计 6 天)

> **目标**:三种算法实现 + 拍卖闭环 + HITL 改派 + 全部测试用例通过。
> **本阶段最重要,质量优先于速度**。

## P5.1 — 规则引擎
- [ ] `app/dispatch/rule_engine.py`(对照 `BUSINESS_RULES.md §3`)
  - `RuleEngine.check(robot, task) -> (bool, reason)`
  - `RuleEngine.filter(robots, task) -> (eligible, stats)`
- [ ] 单元测试:8 条规则各覆盖

## P5.2 — 出价计算
- [ ] `app/dispatch/bidding.py`(对照 `BUSINESS_RULES.md §1`)
  - `compute_distance_score`(Haversine 球面距离)
  - `compute_battery_score`(平方根)
  - `compute_capability_match`
  - `compute_load_score`
  - `compute_vision_boost`(查黑板)
  - `compute_full_bid`(主入口,返回 `BidBreakdown`)
- [ ] 单元测试:每个函数覆盖

## P5.3 — 三种算法
- [ ] `app/dispatch/algorithms/base.py`:`AuctionAlgorithm` 抽象基类
- [ ] `app/dispatch/algorithms/hungarian.py`:`HungarianAuction`(用 `scipy.optimize.linear_sum_assignment`)
- [ ] `app/dispatch/algorithms/greedy.py`:`GreedyAuction`
- [ ] `app/dispatch/algorithms/random.py`:`RandomAuction`
- [ ] `app/dispatch/algorithms/__init__.py`:工厂方法 `get_algorithm(name)`

## P5.4 — 拍卖编排服务
- [ ] `app/services/dispatch_service.py`:
  - `start_auction(task_id) -> Auction`
  - 流程:加载候选 → 规则引擎过滤 → 收集 bids → 算法求解 → 写 task_assignments → 发事件
  - 必须用同事务保证 auction + bids + assignments 原子写入
  - 测量 `decision_latency_ms` 写入

## P5.5 — 拍卖 REST 接口
- [ ] `POST /dispatch/auction`(对照 API_SPEC §4)
- [ ] `GET /dispatch/algorithm`
- [ ] `POST /dispatch/algorithm`(切换算法,HITL)
- [ ] `GET /dispatch/auctions`
- [ ] `GET /dispatch/auctions/{id}`(含 bids 详情)

## P5.6 — HITL 改派
- [ ] `POST /dispatch/reassign`(对照 BUSINESS_RULES §4.3.3 的完整伪代码)
  - 严格按 7 步执行:加锁 → 校验 → before_state → 执行 → after_state → 写 intervention → 推 WS

## P5.7 — 任务自动触发拍卖
- [ ] 监听 `TaskCreatedEvent` → 自动调用 `start_auction`
- [ ] PENDING 任务定时扫描(每 30 秒)→ 重新尝试拍卖

## P5.8 — 跑通所有测试用例
- [ ] 实现 `ALGORITHM_TESTCASES.md` 中的 TC-1 ~ TC-10
- [ ] 实现 TC-E2E-1, TC-E2E-2(TC-E2E-3 在 P6 后做)
- [ ] **所有用例必须全绿**

**验收**(整个 P5,极其重要):
1. `pytest backend/tests/algorithms/` 全绿
2. WebSocket 客户端能完整接收一次拍卖的所有事件:`auction.started → auction.bid_submitted × N → auction.completed`
3. 调用改派 API → human_interventions 表新增 1 条,before/after 字段完整
4. **决策延迟 25×10 场景实测 < 2 秒**(这是论文 NFR 指标)

---

# 阶段 P6:协同通信 + CV 模块 ⭐(预计 5 天)

> **目标**:YOLOv8 训练完成 + 集成系统 + 黑板 + 信息融合 + 视觉加成生效。

## P6.1 — 黑板基础设施
- [ ] `app/communication/blackboard.py`:Blackboard 单例
  - 内存维护 `dict[str, BlackboardEntry]`(主)
  - 异步写库(后台 task)
  - `get / set / fuse / query / subscribe` 方法
- [ ] `app/repositories/blackboard.py`:数据库读写
- [ ] TTL 清理:定时任务每分钟清理过期条目

## P6.2 — 信息融合
- [ ] `app/communication/fusion.py`:
  - `weighted_average`:同 key 多源融合,按 confidence 加权
  - `resolve_conflict`:类型冲突时按时间最新或置信度最高
  - 写 `fused_from` 审计字段(对照 DATA_CONTRACTS §4.10)

## P6.3 — 黑板 REST + WS
- [ ] `GET /blackboard/entries`(对照 API_SPEC §5)
- [ ] `GET /blackboard/entries/{key}`
- [ ] `GET /blackboard/stats`
- [ ] WS 事件 `blackboard.updated` 推送

## P6.4 — YOLOv8 数据集准备
- [ ] 下载 AIDER 数据集(EPFL 官网或 Kaggle 搜 "AIDER dataset")
- [ ] 编写 `scripts/prepare_aider.py`:
  - 从 AIDER 原始分类标注 → 转 YOLO 格式(`.txt`,每行 `class x_center y_center w h`)
  - 部分类别可能需要补充 BBox 标注(可用 Label Studio 或 CVAT)
  - 划分 train/val/test = 70/20/10
- [ ] 生成 `data.yaml`(类别 4 个:survivor / collapsed_building / smoke / fire)

## P6.5 — YOLOv8 训练
- [ ] 使用 Google Colab T4 GPU(免费)或本地 GPU
- [ ] 编写 `scripts/train_yolo.py`(参考 `BUSINESS_RULES.md §5.2` 与论文写作输入文档 §4.3.2 的超参)
  ```python
  from ultralytics import YOLO
  model = YOLO('yolov8s.pt')
  model.train(data='aider_data.yaml', epochs=100, imgsz=640, batch=16,
              optimizer='SGD', lr0=0.01, patience=20, device=0)
  ```
- [ ] 等待训练完成(6-8 小时)
- [ ] 检查 `runs/train/aider_v1/results.png`:mAP@0.5 应 > 0.75

## P6.6 — PerceptionService 集成
- [ ] `app/perception/service.py`(对照 BUSINESS_RULES §5.2)
  - `__init__(model_path)`:加载 best.pt
  - `process_image(robot_id, image, position)`:
    - 推理 → 过滤(conf ≥ 0.5)→ 写黑板 → WS 推送 → 触发自动救援/告警
- [ ] `POST /perception/infer`(开发用 Mock 接口)

## P6.7 — 自动派任务规则
- [ ] 高置信度幸存者(conf ≥ 0.8)且 500m 内无救援任务 → 自动创建任务(`BUSINESS_RULES.md §5.3`)
- [ ] 系统用户 `system` 在 P1.5 seed 时预创建,作为自动任务的 created_by

## P6.8 — 视觉加成在拍卖中生效
- [ ] 出价计算时,`compute_vision_boost` 查黑板
- [ ] 写 bids 时,`vision_boost = 1.5`,`breakdown.vision_boosted = True`
- [ ] **跑 ALGORITHM_TESTCASES TC-5、TC-6、TC-E2E-3 通过**

## P6.9 — Mock 视觉数据流
- [ ] UAV Agent 每 1Hz 调用 `PerceptionService.process_image`
- [ ] 输入:从 AIDER 测试集随机抽一张图(模拟摄像头帧)
- [ ] 这样在不接真实摄像头的情况下,系统能跑出真实 YOLO 推理 + 黑板更新 + 加成

**验收**(整个 P6):
1. YOLOv8 模型在 AIDER 测试集 mAP@0.5 ≥ 0.75
2. 启动系统 → UAV Agent 每秒推送 perception.detection 事件
3. 注入一张含幸存者的图 → 黑板新增 entry,WS 收 `blackboard.updated`
4. 创建该区域的搜救任务 → UAV bid 加成 1.5x(查 bids.breakdown.vision_boosted = True)
5. **TC-E2E-3 完整链路跑通**

---

# 阶段 P7:态势感知 + 前端原型(预计 7 天)

> **目标**:6 个核心页面前端实现,论文截图来源就绪。

## P7.1 — 态势感知后端
- [ ] `app/situation/kpi_aggregator.py`:KPI 聚合服务,1Hz 写缓存,WS 推送
- [ ] `app/situation/alert_engine.py`:告警规则引擎
  - 12 条预置规则(电量低 / 任务超时 / YOLO 高置信度 / 故障 / ...)
- [ ] `GET /situation/kpi`
- [ ] `GET /alerts` + `POST /alerts/{id}/acknowledge` + `POST /alerts/{id}/ignore`
- [ ] WS 事件:`kpi.snapshot / alert.raised / alert.acknowledged / alert.ignored`

## P7.2 — 前端基础设施
- [ ] `src/api/client.ts`:axios 拦截器(自动加 Token,401 跳登录)
- [ ] `src/store/auth.ts`(Zustand):用户、token、登录登出
- [ ] `src/store/ws.ts`:Socket.IO 客户端单例,自动重连,房间订阅
- [ ] `src/router/index.tsx`:6 大页面路由 + 受保护路由组件

## P7.3 — 6 大页面实现
> 每个页面对照已有 HTML 原型(`prototype_*.html`)

- [ ] `src/pages/Login.tsx`(对照 prototype_03)
- [ ] `src/pages/Cockpit.tsx`(对照 prototype_01,核心,含地图/列表/告警/KPI)
  - 地图组件用 React-Konva
  - WS 订阅 `commander`,实时渲染
- [ ] `src/pages/RobotManagement.tsx`(对照 prototype_07)
- [ ] `src/pages/TaskManagement.tsx`(对照 prototype_08)
- [ ] `src/pages/Blackboard.tsx`(对照 prototype_09)
- [ ] `src/pages/AlertCenter.tsx`(对照 prototype_10)
- [ ] `src/pages/Replay.tsx`(对照 prototype_04,P8 完成)
- [ ] `src/pages/Experiment.tsx`(对照 prototype_05,P8 完成)
- [ ] `src/pages/Admin.tsx`(对照 prototype_06)

## P7.4 — 改派弹窗
- [ ] `src/components/ReassignDialog.tsx`(对照 prototype_02)
- [ ] 集成到 Cockpit + TaskManagement

## P7.5 — 通用组件库
- [ ] Button / Input / Select / Tabs / Toast / Dialog / Table(基于 Tailwind 或 shadcn/ui)
- [ ] 状态徽标:`<StatusBadge status="EXECUTING" />` 自动配色

**验收**(整个 P7):
1. 浏览器访问 `localhost:5173` → 登录 → 进入指挥工作台
2. 工作台地图实时显示 25 个机器人移动
3. 创建任务 → UI 实时更新,告警弹出
4. 改派功能可用,intervention 写入数据库
5. 6 个核心页面全部可访问且无报错

---

# 阶段 P8:复盘 + 实验 + 论文素材(预计 7 天)

> **目标**:实验数据齐全,论文所需截图与图表全部产出。

## P8.1 — 复盘后端
- [ ] `app/replay/snapshot_recorder.py`:
  - 在 EXECUTING 期间每秒录制系统全量状态(robots / tasks / blackboard)
  - 写 `replay_sessions` + 关联快照
- [ ] `app/replay/timeline_player.py`:回放控制
- [ ] `GET /replay/sessions / GET /replay/sessions/{id}/snapshots / .../key-events`

## P8.2 — 实验运行器
- [ ] `app/experiments/runner.py`:`ExperimentRunner`
  - `run_batch(scenario_id, algorithms, repetitions)`:循环 N 次,每次重置场景 + 跑完 + 记录指标
  - 写 `experiment_runs` 表
- [ ] `POST /experiments`(异步任务,返回 batch_id)
- [ ] `GET /experiments/{batch_id}`(查进度)
- [ ] `GET /experiments/{batch_id}/charts`(出图数据)

## P8.3 — 跑实验 ⭐
- [ ] **2 场景 × 3 算法 × 10 次 = 60 次运行**
- [ ] 等待大约 1-2 小时
- [ ] 验证 `experiment_runs` 表新增 60 条
- [ ] 用 ECharts 生成 5 张对比图(完成率 / 响应时间 / 路径长度 / 负载均衡 / 决策耗时)

## P8.4 — 复盘前端
- [ ] `src/pages/Replay.tsx`:时间轴拖动 + 倍速 + 跳转干预
- [ ] `src/pages/Experiment.tsx`:配置 + 结果对比图

## P8.5 — 论文素材产出 ⭐
- [ ] 用浏览器全屏(F11)+ 截图工具,截 6 个核心页面 + 改派弹窗 + 复盘 + 实验
  - 推荐分辨率 1920×1080
- [ ] YOLOv8 训练曲线:`runs/train/aider_v1/results.png` 直接用
- [ ] 模型推理可视化:用 5 张代表性 AIDER 测试图,跑推理 + matplotlib 出图
- [ ] 算法对比 5 张图导出 PNG
- [ ] 整理到 `docs/paper_assets/` 目录

## P8.6 — 答辩 PPT 准备(可选)
- [ ] 用现有 12 张 UML 图 + 6 张原型图 + 5 张实验图 = 23 张核心素材
- [ ] PPT 不超过 25 页

**验收**(整个 P8):
1. `experiment_runs` 表 60 条数据
2. mAP@0.5 ≥ 0.75 写进论文
3. 5 张实验对比图齐全,Hungarian vs Greedy 明显区分
4. `docs/paper_assets/` 内含 ≥ 25 张论文图片素材

---

# 跨阶段质量门(每个阶段必过)

| 门禁 | 检查点 | 触发阶段 |
|---|---|---|
| **G1 数据库完整性** | 17 张表全部建立 + 索引 + 触发器 | P1 末 |
| **G2 认证可用** | 登录 → 受保护接口正常返回 | P2 末 |
| **G3 心跳实时性** | WS 收到 1Hz 位置推送,延迟 < 500ms | P3 末 |
| **G4 状态机正确** | 任务全状态转移测试通过 | P4 末 |
| **G5 算法测试全绿** | TC-1 ~ TC-10 全部通过 | P5 末 |
| **G6 视觉加成生效** | TC-5、TC-6、TC-E2E-3 全部通过 | P6 末 |
| **G7 前端可用** | 6 大页面完整可操作,无控制台报错 | P7 末 |
| **G8 实验数据完整** | experiment_runs 表 60 条,5 张对比图 | P8 末 |

---

# 关键里程碑(MVP / Beta / RC)

| 里程碑 | 完成阶段 | 用途 |
|---|---|---|
| **M1 — Internal Demo** | P5 末 | 给导师演示算法核心 |
| **M2 — CV Integrated** | P6 末 | 论文实验前置条件就绪 |
| **M3 — Beta** | P7 末 | 全功能可演示,可截图 |
| **M4 — Final** | P8 末 | 论文全部素材齐全,可定稿 |

---

# 风险与应急预案

### 风险 1:YOLOv8 训练 mAP 达不到 0.75
- **缓解**:微调 epochs / 数据增强 / 调 lr → 见 `论文写作输入文档 §4.3.2`
- **兜底**:论文里如实写实际值,只要 ≥ 0.65 就能交差;同时分析未达预期的原因

### 风险 2:25 个 Agent 性能瓶颈
- **缓解**:Agent 上报频率从 1Hz 降到 0.5Hz
- **兜底**:实验场景缩到 15 个机器人

### 风险 3:实验跑出来 Hungarian 不显著优于 Greedy
- **缓解**:增加重复次数(10 → 30),提高统计显著性
- **兜底**:论文里改写"两者各有优势,Hungarian 在负载均衡上显著更优"

### 风险 4:开发进度滞后
- **优先放弃顺序**:P8.4 复盘前端 → P7.5 通用组件优化 → P3.6 召回完整逻辑(简化版)
- **必须保**:P5(算法核心)、P6.4-P6.5(YOLO 训练)、P8.3(实验跑通)

---

# 下一步行动(开始的第一步)

```bash
# 1. 创建仓库
mkdir disaster-rescue-hub && cd disaster-rescue-hub
git init

# 2. 把 8 份文档放进 docs/
mkdir -p docs
cp /path/to/*.md docs/

# 3. 在 Claude Code 中开新会话
#    第一条粘贴 PROJECT_CONTEXT.md 的内容
#    第二条说:"按 BUILD_ORDER.md P0.1,创建项目骨架"
```

---

**END OF BUILD_ORDER.md**
