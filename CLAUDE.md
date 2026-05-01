@AGENTS.md

## Claude Code Role

Claude Code should be used for complex and high-value tasks:

- Architecture design
- Database model implementation
- WebSocket architecture
- Dispatch algorithm
- Business rules
- State machines
- HITL decision loop
- YOLO and blackboard integration
- Complex cross-module bugs
- Thesis-oriented implementation explanations

## Required Behavior

Before modifying code:

1. Read the relevant docs.
2. Identify the BUILD_ORDER task number.
3. Explain the plan.
4. List affected files.
5. Confirm acceptance criteria.

After completing a BUILD_ORDER task:

1. Update docs/DEV_MEMORY.md.
2. Update docs/TASK_BOARD.md.
3. Update docs/GIT_LOG.md.
4. Run necessary checks.
5. Commit and push to remote repository.

## Token Discipline

- Do not scan the whole repository unless necessary.
- Always read the smallest relevant document set.
- Do not read dependency folders, build output, generated files, lock files, or virtual environments.
- Before large changes, output a plan first.