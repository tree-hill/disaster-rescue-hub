from __future__ import annotations

import uuid

import pytest

from app.dispatch.rule_engine import TaskEvalInput
from app.models.task import Task
from app.schemas.common import Position
from app.schemas.task import TargetArea, TaskRequiredCapabilities
from app.services.dispatch_service import DispatchService


class _FakeAgent:
    def __init__(self) -> None:
        self.calls: list[tuple[uuid.UUID, dict[str, float | None]]] = []

    def accept_assignment(
        self,
        *,
        task_id: uuid.UUID,
        target_position: dict[str, float | None],
    ) -> None:
        self.calls.append((task_id, target_position))


class _FakeManager:
    started = True

    def __init__(self, agent: _FakeAgent) -> None:
        self.agent = agent

    def get(self, robot_id: uuid.UUID) -> _FakeAgent:
        return self.agent


@pytest.mark.asyncio
async def test_dispatch_sync_winner_agent_calls_accept_assignment(monkeypatch) -> None:
    task_id = uuid.uuid4()
    robot_id = uuid.uuid4()
    agent = _FakeAgent()

    monkeypatch.setattr(
        "app.services.dispatch_service.get_agent_manager",
        lambda: _FakeManager(agent),
    )

    svc = DispatchService(session=object())  # type: ignore[arg-type]
    task = Task(id=task_id, code="T-UNIT-001")
    task_view = TaskEvalInput(
        id=task_id,
        required_capabilities=TaskRequiredCapabilities(),
        target_area=TargetArea(
            type="circle",
            center=Position(lat=30.225, lng=120.525),
            radius_m=200.0,
            area_km2=0.5,
            center_point=Position(lat=30.225, lng=120.525),
        ),
    )

    await svc._sync_winner_agent(
        winner_robot_id=robot_id,
        task=task,
        task_view=task_view,
    )

    assert agent.calls == [
        (
            task_id,
            {"lat": 30.225, "lng": 120.525, "altitude_m": None},
        )
    ]
