# DEV_MEMORY.md — 共享开发记忆

> 本文档用于 Claude Code 和 Codex 共享开发上下文。
> 每完成一个任务、修复一个 bug、调整一个模块后，必须更新本文档。
> 不允许只把开发过程留在对话里。

---

## 当前项目状态

项目名称：disaster-rescue-hub  
当前阶段：P1 数据层  
当前任务：P1.4 触发器与索引（建议 Codex 复审 P1.2/P1.3 修复后再推进）  
最近完成：P1.2/P1.3 契约一致性修复（2026-05-02）  
下一任务：P1.4 GIN 索引（触发器已在 P1.3 完成；ORM 中已补 GIN 索引声明）  

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

## 已知设计偏差

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