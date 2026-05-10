from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.experiments.runner import ExperimentRunner
from app.replay.timeline_player import filter_key_events, filter_snapshots
from app.schemas.experiment import ExperimentRunRead, build_charts, compute_stats


def test_filter_snapshots_applies_time_window_and_interval() -> None:
    base = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    snapshots = [{"ts": (base + timedelta(seconds=i)).isoformat()} for i in range(6)]

    result = filter_snapshots(
        snapshots,
        start_time=base + timedelta(seconds=1),
        end_time=base + timedelta(seconds=5),
        interval_sec=2.0,
    )

    assert [item["ts"] for item in result] == [
        (base + timedelta(seconds=1)).isoformat(),
        (base + timedelta(seconds=3)).isoformat(),
        (base + timedelta(seconds=5)).isoformat(),
    ]


def test_filter_key_events_skips_invalid_timestamps() -> None:
    base = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    events = [
        {"ts": "bad", "type": "alert"},
        {"ts": base.isoformat(), "type": "alert"},
        {"ts": (base + timedelta(seconds=3)).isoformat(), "type": "task_completed"},
    ]

    result = filter_key_events(events, end_time=base + timedelta(seconds=1))

    assert result == [{"ts": base.isoformat(), "type": "alert"}]


def _run(algorithm: str, run_index: int, *, latency_ms: int) -> ExperimentRunRead:
    return ExperimentRunRead(
        id=uuid4(),
        batch_id=uuid4(),
        scenario_id=uuid4(),
        algorithm=algorithm,
        run_index=run_index,
        completion_rate=100.0,
        avg_response_sec=latency_ms / 1000.0,
        total_path_km=10.0 + run_index,
        load_std_dev=0.5,
        decision_latency_ms=latency_ms,
        raw_metrics={
            "per_robot_load": [],
            "per_task_response_sec": [],
            "total_decisions": 10,
            "hitl_interventions": 0,
            "vision_assisted_count": 0,
        },
        started_at=datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 5, 10, 12, 1, tzinfo=timezone.utc),
    )


def test_experiment_stats_and_charts_group_by_algorithm() -> None:
    runs = [
        _run("AUCTION_HUNGARIAN", 1, latency_ms=10),
        _run("AUCTION_HUNGARIAN", 2, latency_ms=20),
        _run("GREEDY", 1, latency_ms=30),
    ]

    stats = compute_stats(runs)
    charts = build_charts(runs)

    assert stats["AUCTION_HUNGARIAN"].run_count == 2
    assert stats["AUCTION_HUNGARIAN"].avg_decision_latency_ms == 15.0
    assert charts.decision_latency_chart.labels == ["Run 1", "Run 2"]
    assert [d.label for d in charts.decision_latency_chart.datasets] == [
        "AUCTION_HUNGARIAN",
        "GREEDY",
    ]
    assert charts.decision_latency_chart.datasets[0].data == [10.0, 20.0]


@pytest.mark.asyncio
async def test_experiment_runner_publish_progress_uses_ws_contract(monkeypatch) -> None:
    captured: list[tuple[str, dict]] = []

    class FakeBus:
        async def publish(self, event_type: str, payload: dict) -> None:
            captured.append((event_type, payload))

    monkeypatch.setattr("app.experiments.runner.get_event_bus", lambda: FakeBus())

    batch_id = uuid4()
    await ExperimentRunner()._publish_progress(
        batch_id=batch_id,
        completed_runs=2,
        total_runs=5,
        current_algorithm="GREEDY",
    )

    assert captured == [
        (
            "experiment.progress",
            {
                "batch_id": str(batch_id),
                "completed_runs": 2,
                "total_runs": 5,
                "current_algorithm": "GREEDY",
                "estimated_remaining_sec": 15,
            },
        )
    ]
