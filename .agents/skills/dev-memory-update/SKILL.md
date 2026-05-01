---
name: dev-memory-update
description: 每次完成开发、修复 bug、调整文档、提交代码前后使用。用于更新 docs/DEV_MEMORY.md、docs/TASK_BOARD.md 和 docs/GIT_LOG.md，实现 Claude Code 与 Codex 的开发记忆共享。
---

# Dev Memory Update Skill

## 使用场景

以下情况必须使用本 skill：

1. 完成一个 BUILD_ORDER 任务。
2. 修复一个 bug。
3. 修改 API、数据结构、WebSocket 事件。
4. 修改调度算法、状态机、HITL 规则。
5. 完成一次 Git commit。
6. 切换 Claude Code 和 Codex 处理同一项目之前。

## 必读文件

执行前必须阅读：

- `docs/DEV_MEMORY.md`
- `docs/TASK_BOARD.md`
- `docs/GIT_LOG.md`
- `docs/BUILD_ORDER.md`

必要时阅读：

- `docs/PROJECT_CONTEXT.md`
- `docs/CONVENTIONS.md`

## 更新 DEV_MEMORY.md

必须追加一条开发记录，不要覆盖旧记录。

格式：

```md
#### YYYY-MM-DD HH:mm — 工具名 — 任务编号

- 任务：
- 执行工具：
- 修改类型：
- 涉及文件：
  - 
- 主要变更：
  - 
- 验证命令：
  - 
- 验证结果：
  - 
- Git 提交：
  - commit message：
  - commit hash：
  - push 状态：
- 遗留问题：
  - 
- 下一步建议：
  - 
```
