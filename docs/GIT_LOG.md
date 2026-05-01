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

### 2026-05-02 — P0.2

- 任务：P0.2 Docker Compose 编排
- 工具：Claude Code
- 分支：main
- Commit message：chore: P0.2 docker-compose with postgres and env example
- Commit hash：（提交后回填）
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