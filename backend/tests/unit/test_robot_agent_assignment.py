from __future__ import annotations

import uuid

import pytest

from app.agents.robot_agent import RobotAgent


def _agent(*, fsm_state: str = "IDLE") -> RobotAgent:
    return RobotAgent(
        robot_id=uuid.uuid4(),
        code="UAV-UNIT-001",
        type_="uav",
        capability={
            "sensors": ["camera_4k"],
            "payloads": [],
            "max_speed_mps": 20.0,
            "max_battery_min": 60,
            "max_range_km": 50.0,
            "has_yolo": True,
            "weight_kg": 5.0,
        },
        fsm_state=fsm_state,
        tick_hz=1.0,
    )


def test_accept_assignment_from_idle_enters_executing_with_task_and_target() -> None:
    agent = _agent(fsm_state="IDLE")
    task_id = uuid.uuid4()

    agent.accept_assignment(
        task_id=task_id,
        target_position={"lat": 30.225, "lng": 120.525, "altitude_m": None},
    )

    assert agent.fsm_state == "EXECUTING"
    assert agent.current_task_id == task_id
    assert agent.target_position is not None
    assert agent.target_position["lat"] == pytest.approx(30.225)
    assert agent.target_position["lng"] == pytest.approx(120.525)


def test_accept_assignment_interrupts_returning_robot() -> None:
    agent = _agent(fsm_state="EXECUTING")
    agent.request_recall(user_id=uuid.uuid4(), reason="unit test recall")
    assert agent.fsm_state == "RETURNING"

    task_id = uuid.uuid4()
    agent.accept_assignment(
        task_id=task_id,
        target_position={"lat": 30.226, "lng": 120.526, "altitude_m": None},
    )

    assert agent.fsm_state == "EXECUTING"
    assert agent.current_task_id == task_id
    assert agent.target_position is not None
    assert agent.target_position["lat"] == pytest.approx(30.226)

