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

### 2026-05-02 — P2.5

- 任务：P2.5 其他认证接口（refresh + me + logout）
- 工具：Claude Code
- 分支：main
- Commit message：feat: P2.5 auth refresh me logout endpoints
- Commit hash：（提交后回填）
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