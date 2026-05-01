# AGENTS.md

## Project

This is `disaster-rescue-hub`, a graduation project for a disaster rescue robot central control system.

## Required Reading

Before any non-trivial task, read:

- docs/PROJECT_CONTEXT.md
- docs/BUILD_ORDER.md
- docs/CONVENTIONS.md
- docs/DEV_MEMORY.md
- docs/TASK_BOARD.md

For data/API work, read:

- docs/DATA_CONTRACTS.md
- docs/API_SPEC.md

For WebSocket work, read:

- docs/WS_EVENTS.md

For business logic, dispatch, HITL, state machines, or algorithms, read:

- docs/BUSINESS_RULES.md
- docs/ALGORITHM_TESTCASES.md

## Mandatory Rules

1. Follow docs/BUILD_ORDER.md task order.
2. Follow docs/CONVENTIONS.md for directory structure and code style.
3. Follow docs/DATA_CONTRACTS.md as the single source of truth for data structures.
4. Follow docs/API_SPEC.md for REST API contracts.
5. Follow docs/WS_EVENTS.md for WebSocket events.
6. Follow docs/BUSINESS_RULES.md for business logic and algorithms.
7. Do not invent new fields, APIs, states, events, or business rules.
8. Write tests for backend modules.
9. Keep code explainable for graduation thesis writing.

## Git Rule

Every completed BUILD_ORDER task must be committed and pushed to the remote repository.

Before committing:

1. Run git status.
2. Confirm the task acceptance criteria.
3. Run necessary tests.
4. Update docs/DEV_MEMORY.md.
5. Update docs/TASK_BOARD.md.
6. Update docs/GIT_LOG.md.

Then:

```bash
git add .
git commit -m "<type>: <task-id> <summary>"
git push
```
