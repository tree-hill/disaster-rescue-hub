---
name: task-complete-git-push
description: 每完成一个 BUILD_ORDER 任务后使用。用于检查任务验收标准、更新共享记忆、执行 git commit，并推送到远程仓库，确保项目可以随时回滚。
---

# Task Complete Git Push Skill

## 使用场景

当完成以下任意情况时，必须使用本 skill：

1. 完成 `docs/BUILD_ORDER.md` 中的一个任务，例如 P0.1、P0.2、P1.1。
2. 完成一个明确功能模块。
3. 修复一个明确 bug。
4. 完成一次可回滚的代码变更。
5. 用户明确要求提交到远程仓库。

## 必读文件

执行前必须阅读：

- `docs/BUILD_ORDER.md`
- `docs/DEV_MEMORY.md`
- `docs/TASK_BOARD.md`
- `docs/GIT_LOG.md`
- `docs/CONVENTIONS.md`

如果任务涉及数据、API、WebSocket、业务规则，还必须阅读对应契约文档。

## 执行流程

### 1. 检查 Git 状态

运行：

```bash
git status
```
