# DEV_MEMORY.md — 共享开发记忆

> 本文档用于 Claude Code 和 Codex 共享开发上下文。
> 每完成一个任务、修复一个 bug、调整一个模块后，必须更新本文档。
> 不允许只把开发过程留在对话里。

---

## 当前项目状态

项目名称：disaster-rescue-hub  
当前阶段：P0 项目基建  
当前任务：P0.4 Frontend 空架子（Vite + React + TS）  
最近完成：P0.3 Backend 空架子（2026-05-02）  
下一任务：P0.5 提交完整基建  

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

---

## 重要决策记录

### 决策 1：每个 BUILD_ORDER 任务完成后必须提交远程仓库

原因：保证项目可回滚，避免 AI 多轮修改后项目不可控。

---

## 已知问题与注意事项

暂无。