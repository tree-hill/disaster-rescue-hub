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

### 2026-05-02 — P1.2

- 任务：P1.2 17 张表的 ORM 模型
- 工具：Claude Code
- 分支：main
- Commit message：feat: P1.2 implement 17 ORM models from DATA_CONTRACTS DDL
- Commit hash：（待补充）
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