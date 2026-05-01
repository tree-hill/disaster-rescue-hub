# DEV_MEMORY.md — 共享开发记忆

> 本文档用于 Claude Code 和 Codex 共享开发上下文。
> 每完成一个任务、修复一个 bug、调整一个模块后，必须更新本文档。
> 不允许只把开发过程留在对话里。

---

## 当前项目状态

项目名称：disaster-rescue-hub  
当前阶段：P0 项目基建  
当前任务：P0.1 创建仓库 + 目录结构  
最近完成：暂无  
下一任务：P0.2 Docker Compose 编排  

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

暂无。

---

## 重要决策记录

### 决策 1：每个 BUILD_ORDER 任务完成后必须提交远程仓库

原因：保证项目可回滚，避免 AI 多轮修改后项目不可控。

---

## 已知问题与注意事项

暂无。