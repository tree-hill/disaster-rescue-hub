# TASK_BOARD.md — 当前任务看板

> 本文档用于记录当前开发进度。
> Claude Code 和 Codex 在开始任务前必须先阅读本文档。

---

## 当前阶段

当前阶段：P2 认证 + 基础 API  
当前任务：P2.5 其他认证接口（/auth/refresh + /auth/me + /auth/logout）  
任务来源：docs/BUILD_ORDER.md  
备注：P2.4 完成（app/api/deps.py：oauth2_scheme + get_current_user + require_permission 依赖工厂，10/10 自检），下一步用 deps 挂三个端点  

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

- [ ] P2.5 其他认证接口：POST /auth/refresh + GET /auth/me + POST /auth/logout

### In Progress

暂无。

### Done

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

---

## 当前锁定模块

当前无锁定模块。

规则：

1. 一个模块同一时间只允许一个工具修改。
2. Claude Code 修改复杂模块后，Codex 只能先审查，不要直接二次重构。
3. Codex 修复小 bug 后，必须记录到 DEV_MEMORY.md。
4. 完成一个 BUILD_ORDER 任务后，必须 Git commit + push。