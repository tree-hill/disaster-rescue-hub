"""E2E 测试 TC-E2E-1（任务全生命周期）+ TC-E2E-2（HITL 改派完整链路）。

对照 ALGORITHM_TESTCASES.md §3。

测试约定：
- 使用 conftest 的 client / commander_headers / seed_e2e_robot / wait_until。
- 任务前缀 T-8888-* + 机器人前缀 UAV-E2E-* 由 conftest session-scoped 清场，
  无需在用例内手工删除。
- TC-E2E-1 的 ASSIGNED→EXECUTING→COMPLETED 转移在生产由 Agent 驱动；E2E 用
  `transit_task` 直接驱状态机（覆盖 BUSINESS_RULES §2.1.3 转移表本身）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core.event_bus import get_event_bus
from app.models.dispatch import Auction, Bid
from app.models.intervention import HumanIntervention
from app.models.task import Task, TaskAssignment
from app.services.task_status_machine import transit as transit_task
from tests.e2e.conftest import (
    seed_e2e_robot,
    small_circle_target_area,
    wait_until,
)


pytestmark = pytest.mark.asyncio


# ============================== TC-E2E-1 ==============================


async def test_e2e_1_full_task_lifecycle(client, commander_headers):
    """TC-E2E-1：POST /tasks → auto-trigger 拍卖 → ASSIGNED → 手动 EXECUTING →
    COMPLETED；DB 终态正确。"""
    from app.db.session import async_session_maker

    # 0) 准备 1 台 IDLE 机器人，足以拿单任务
    await seed_e2e_robot(code_suffix=f"E1-R-{uuid.uuid4().hex[:5]}")

    bus = get_event_bus()
    captured: list[tuple[str, dict]] = []
    real_publish = bus.publish

    async def _capture(evt_type: str, payload: dict) -> None:
        captured.append((evt_type, dict(payload)))
        await real_publish(evt_type, payload)

    bus.publish = _capture  # type: ignore[assignment]

    # 1) POST /tasks 创建一个 < 1 km² 任务（避免网格分解干扰 auto-trigger）
    payload = {
        "name": f"E2E-1 {uuid.uuid4().hex[:6]}",
        "type": "search_rescue",
        "priority": 2,
        "target_area": small_circle_target_area(),
        "required_capabilities": {
            "sensors": [],
            "payloads": [],
            "min_battery_pct": 20.0,
            "robot_type": None,
        },
    }
    try:
        resp = await client.post("/api/v1/tasks", json=payload, headers=commander_headers)
        assert resp.status_code == 201, resp.text
        task_body = resp.json()
        task_id = uuid.UUID(task_body["id"])
        # POST /tasks 返回 code 应已是 T-YYYY-NNN；E2E 清场只匹配 T-8888-*，
        # 因此本测试不写 T-8888- 前缀，改用 task_id 自身追踪 + 在 teardown 清。
        # 为保证 teardown 也能清这条记录，转手把 task code 改为 T-8888-* 前缀。
        async with async_session_maker() as session:
            t = await session.get(Task, task_id)
            if t is not None:
                t.code = f"T-8888-{uuid.uuid4().hex[:6].upper()}"
                await session.commit()

        # 2) 等 auto-trigger handler 跑完一轮 → 任务变 ASSIGNED
        async def _is_assigned_and_event_captured() -> bool:
            async with async_session_maker() as session:
                t = await session.get(Task, task_id)
                assigned = t is not None and t.status == "ASSIGNED"
            has_event = any(
                evt_type == "task.status_changed"
                and payload.get("task_id") == str(task_id)
                and payload.get("to_status") == "ASSIGNED"
                for evt_type, payload in captured
            )
            return assigned and has_event

        assert await wait_until(_is_assigned_and_event_captured, timeout=10.0), (
            "auto-trigger 未在 10s 内完成 ASSIGNED 状态与状态事件"
        )
    finally:
        bus.publish = real_publish  # type: ignore[assignment]

    status_events = [p for (t, p) in captured if t == "task.status_changed"]
    assert len(status_events) == 1
    assert status_events[0]["task_id"] == str(task_id)
    assert status_events[0]["from_status"] == "PENDING"
    assert status_events[0]["to_status"] == "ASSIGNED"
    assert len(status_events[0]["assigned_robot_ids"]) == 1

    # 3) 验证 auction + bids + active assignment
    async with async_session_maker() as session:
        aucs = (
            await session.execute(select(Auction).where(Auction.task_id == task_id))
        ).scalars().all()
        assert len(aucs) == 1
        auc = aucs[0]
        assert auc.status == "CLOSED"
        assert auc.winner_robot_id is not None
        assert auc.decision_latency_ms is not None and auc.decision_latency_ms < 2000

        bids = (
            await session.execute(select(Bid).where(Bid.auction_id == auc.id))
        ).scalars().all()
        assert len(bids) >= 1

        actives = (
            await session.execute(
                select(TaskAssignment).where(
                    TaskAssignment.task_id == task_id,
                    TaskAssignment.is_active.is_(True),
                )
            )
        ).scalars().all()
        assert len(actives) == 1
        assert actives[0].auction_id == auc.id

    # 4) 模拟机器人开始执行：状态机 ASSIGNED → EXECUTING
    async with async_session_maker() as session:
        t = await session.get(Task, task_id)
        assert t is not None
        transit_task(t, "EXECUTING", reason="e2e simulate executing")
        await session.commit()
        await session.refresh(t)
        assert t.status == "EXECUTING"
        assert t.started_at is not None  # ASSIGNED→EXECUTING 时间戳被状态机置位

    # 5) 模拟 progress 累积 + COMPLETED：EXECUTING → COMPLETED
    async with async_session_maker() as session:
        t = await session.get(Task, task_id)
        assert t is not None
        from decimal import Decimal as D

        t.progress = D("100.00")
        transit_task(t, "COMPLETED", reason="e2e simulate progress=100")
        await session.commit()
        await session.refresh(t)
        assert t.status == "COMPLETED"
        assert t.completed_at is not None  # EXECUTING→COMPLETED 时间戳被状态机置位

    # 6) 终态后的 DB 校验：assignment 仍存在但 release_at 暂未由状态机自动写
    #    （BUSINESS_RULES §2.1.1 的 release_assignment 副作用由 service 层负责，
    #    本测试范围只验任务状态机本身）
    async with async_session_maker() as session:
        t = await session.get(Task, task_id)
        assert t is not None
        assert t.status == "COMPLETED"

        aucs = (
            await session.execute(select(Auction).where(Auction.task_id == task_id))
        ).scalars().all()
        assert len(aucs) == 1  # 仍只 1 条 auction


# ============================== TC-E2E-2 ==============================


async def test_e2e_2_hitl_reassign_full_chain(client, commander_headers):
    """TC-E2E-2：任务 ASSIGNED → POST /dispatch/reassign → DB + WS 双事件。"""
    from app.db.session import async_session_maker

    # 0) 准备 2 台机器人（一台被自动选中，一台留给改派）
    r_old_id = await seed_e2e_robot(code_suffix=f"E2-OLD-{uuid.uuid4().hex[:5]}")
    r_new_id = await seed_e2e_robot(code_suffix=f"E2-NEW-{uuid.uuid4().hex[:5]}")

    # 1) 创建任务 → auto-trigger 拍卖 → ASSIGNED
    payload = {
        "name": f"E2E-2 {uuid.uuid4().hex[:6]}",
        "type": "search_rescue",
        "priority": 2,
        "target_area": small_circle_target_area(),
        "required_capabilities": {
            "sensors": [],
            "payloads": [],
            "min_battery_pct": 20.0,
            "robot_type": None,
        },
    }
    resp = await client.post("/api/v1/tasks", json=payload, headers=commander_headers)
    assert resp.status_code == 201
    task_id = uuid.UUID(resp.json()["id"])

    async with async_session_maker() as session:
        t = await session.get(Task, task_id)
        if t is not None:
            t.code = f"T-8888-{uuid.uuid4().hex[:6].upper()}"
            await session.commit()

    async def _is_assigned() -> bool:
        async with async_session_maker() as session:
            t = await session.get(Task, task_id)
            return t is not None and t.status == "ASSIGNED"

    assert await wait_until(_is_assigned, timeout=10.0)

    # 2) 找出实际被分配的旧机器人（不一定是 r_old_id 那台，看出价）
    async with async_session_maker() as session:
        active = (
            await session.execute(
                select(TaskAssignment).where(
                    TaskAssignment.task_id == task_id,
                    TaskAssignment.is_active.is_(True),
                )
            )
        ).scalar_one()
        original_robot_id = active.robot_id

    # 3) 选改派目标：r_old_id / r_new_id 中不是 original_robot_id 的那台
    target_robot_id = r_new_id if original_robot_id == r_old_id else r_old_id

    # 4) 抓 WS 事件：临时 monkeypatch event_bus.publish 收集 task.reassigned +
    #    intervention.recorded
    bus = get_event_bus()
    captured: list[tuple[str, dict]] = []
    real_publish = bus.publish

    async def _capture(evt_type: str, payload: dict) -> None:
        captured.append((evt_type, dict(payload)))
        await real_publish(evt_type, payload)

    bus.publish = _capture  # type: ignore[assignment]
    try:
        resp = await client.post(
            "/api/v1/dispatch/reassign",
            json={
                "task_id": str(task_id),
                "new_robot_id": str(target_robot_id),
                "reason": "E2E reassign test",
            },
            headers=commander_headers,
        )
    finally:
        bus.publish = real_publish  # type: ignore[assignment]

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["task"]["id"] == str(task_id)
    intervention_id = uuid.UUID(body["intervention_id"])

    # 5) DB 验证
    async with async_session_maker() as session:
        # 旧 assignment 已 is_active=False + released_at 不为空
        assignments = (
            await session.execute(
                select(TaskAssignment).where(TaskAssignment.task_id == task_id)
            )
        ).scalars().all()
        actives = [a for a in assignments if a.is_active]
        inactives = [a for a in assignments if not a.is_active]
        assert len(actives) == 1
        assert actives[0].robot_id == target_robot_id
        assert actives[0].auction_id is None  # 人工指派
        assert len(inactives) >= 1
        assert all(a.released_at is not None for a in inactives)

        # human_interventions 写入 + before/after_state 字段完整
        iv = (
            await session.execute(
                select(HumanIntervention).where(HumanIntervention.id == intervention_id)
            )
        ).scalar_one()
        assert iv.intervention_type == "reassign"
        assert iv.target_task_id == task_id
        assert iv.target_robot_id == target_robot_id
        bs = iv.before_state
        as_ = iv.after_state
        assert {"task_id", "task_code", "assigned_robot_ids", "algorithm_used", "timestamp"} <= set(bs.keys())
        assert {"task_id", "task_code", "assigned_robot_ids", "algorithm_used", "timestamp"} <= set(as_.keys())
        assert as_["assigned_robot_ids"] == [str(target_robot_id)]
        assert as_["algorithm_used"] == "MANUAL_OVERRIDE"

    # 6) WS 双事件验证
    types = [t for t, _ in captured]
    assert "task.reassigned" in types
    assert "intervention.recorded" in types

    tr = next(p for (t, p) in captured if t == "task.reassigned")
    assert {
        "task_id",
        "task_code",
        "from_robot_id",
        "from_robot_code",
        "to_robot_id",
        "to_robot_code",
        "reassigned_by_user_id",
        "reason",
        "intervention_id",
    } == set(tr.keys())
    assert tr["task_id"] == str(task_id)
    assert tr["to_robot_id"] == str(target_robot_id)

    ir = next(p for (t, p) in captured if t == "intervention.recorded")
    assert {
        "intervention_id",
        "user_id",
        "intervention_type",
        "target_task_id",
        "target_robot_id",
        "reason",
    } == set(ir.keys())
    assert ir["intervention_type"] == "reassign"
    assert ir["target_task_id"] == str(task_id)


def _ts_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
