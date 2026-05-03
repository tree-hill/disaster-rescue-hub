"""任务状态机服务。

对照：
- BUSINESS_RULES §2.1（TaskStatus 转移表 + 实现指南）
- BUSINESS_RULES §6.3（409_TASK_STATUS_CONFLICT_001）
- DATA_CONTRACTS §1.8（tasks 表的 started_at / completed_at / updated_at）

设计边界（保持状态机内聚，避免与上层服务耦合）：
- 本模块只做：1) 转移合法性校验  2) 修改 `task.status`  3) 按转移类型置
  `task.started_at` / `task.completed_at`  4) 结构化日志（task_status_transit）。
- 以下副作用由调用方负责：
  - 释放 task_assignments（is_active=False, released_at=NOW）— 由 cancel /
    completion service 在同事务里完成
  - 推送 WS 事件（task.status_changed / task.cancelled）— 由调用方决定房间
  - 写 human_interventions（仅 HITL 路径需要）— 由 cancel / reassign service 完成
- 这样状态机能被自动路径（拍卖 → ASSIGNED、Agent 到达 → EXECUTING、progress=100
  → COMPLETED）和 HITL 路径（cancel → CANCELLED）共用。

事务边界：transit 只修改 ORM 对象上的属性，不 commit / flush；调用方持有 session
并负责事务提交，确保「状态变更」与其副作用（assignment 释放、intervention 写入）
落在同一事务里（INV-G）。

历史日志：BUILD_ORDER §P4.2 要求「同事务记录历史日志」。当前 schema 中没有
task_status_history 表（DATA_CONTRACTS 仅定义 human_interventions 用于 HITL
审计），因此沿用 RobotAgent.transit 的做法：结构化 logger.info 输出
{from, to, reason, task_id, code}，由日志聚合层归档。后续若要补持久化历史表，
只需在此处追加 repo.append() 即可，不影响接口。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.core.exceptions import BusinessError
from app.models.task import Task

logger = logging.getLogger(__name__)


# 任务状态转移表，严格对照 BUSINESS_RULES §2.1.3。
TASK_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"ASSIGNED", "CANCELLED"},
    "ASSIGNED": {"EXECUTING", "CANCELLED", "PENDING"},
    "EXECUTING": {"COMPLETED", "FAILED", "CANCELLED", "EXECUTING"},
    "COMPLETED": set(),  # 终态
    "FAILED": set(),
    "CANCELLED": set(),
}

VALID_TASK_STATUSES: frozenset[str] = frozenset(TASK_TRANSITIONS.keys())

# 终态集合（FAILED / COMPLETED / CANCELLED 任一进入即不可再转出）。
TERMINAL_TASK_STATUSES: frozenset[str] = frozenset(
    s for s, allowed in TASK_TRANSITIONS.items() if not allowed
)


def can_transit(from_status: str, to_status: str) -> bool:
    """纯函数：判断 from→to 是否在 TASK_TRANSITIONS 中。

    未知状态一律返回 False，调用方需先校验输入是否为已知状态。
    """
    return to_status in TASK_TRANSITIONS.get(from_status, set())


def _conflict(from_status: str, to_status: str, reason: str | None) -> BusinessError:
    return BusinessError(
        code="409_TASK_STATUS_CONFLICT_001",
        message=f"任务状态不允许从 {from_status} 转移到 {to_status}",
        http_status=409,
        details=[
            {"field": "task.status", "code": "current_status", "message": from_status},
            {"field": "task.status", "code": "target_status", "message": to_status},
            *(
                [{"field": "reason", "code": "transit_reason", "message": reason}]
                if reason
                else []
            ),
        ],
    )


def transit(task: Task, target_status: str, *, reason: str = "") -> None:
    """执行一次任务状态转移。

    参数:
        task: 已绑定到 session 的 Task ORM 对象（由 service 通过 repo.find_by_id 取出）。
        target_status: 目标状态字符串（必须 ∈ VALID_TASK_STATUSES）。
        reason: 可选转移原因，写入结构化日志，便于事后审计追踪（HITL 路径建议必填）。

    副作用（仅修改 ORM 字段，不 commit / flush）:
        - task.status 更新为 target_status
        - ASSIGNED → EXECUTING：设置 task.started_at = NOW()（仅当为 None 时，避免
          EXECUTING→EXECUTING 改派覆盖原始开始时间）
        - EXECUTING → {COMPLETED, FAILED, CANCELLED}：设置 task.completed_at = NOW()
        - 其他转移不动时间戳（updated_at 由数据库触发器 set_timestamp_tasks 处理）

    抛出:
        BusinessError(409_TASK_STATUS_CONFLICT_001):
            - target_status 不在 VALID_TASK_STATUSES 中
            - 当前 status 不在 VALID_TASK_STATUSES 中
            - 转移不在 TASK_TRANSITIONS[from] 集合内（含终态）
    """
    from_status = task.status

    if from_status not in VALID_TASK_STATUSES:
        raise _conflict(from_status, target_status, reason)
    if target_status not in VALID_TASK_STATUSES:
        raise _conflict(from_status, target_status, reason)
    if not can_transit(from_status, target_status):
        raise _conflict(from_status, target_status, reason)

    now = datetime.now(timezone.utc)

    # 时间戳副作用（BUSINESS_RULES §2.1.1）。
    if from_status == "ASSIGNED" and target_status == "EXECUTING":
        if task.started_at is None:
            task.started_at = now
    elif from_status == "EXECUTING" and target_status in {
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    }:
        task.completed_at = now

    task.status = target_status

    logger.info(
        "task_status_transit",
        extra={
            "task_id": str(task.id) if task.id is not None else None,
            "code": task.code,
            "from": from_status,
            "to": target_status,
            "reason": reason,
        },
    )
