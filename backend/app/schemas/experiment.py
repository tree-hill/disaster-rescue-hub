"""实验模块 Pydantic v2 Schemas（P8.2）。

对照 API_SPEC §7 POST/GET /experiments 和 DATA_CONTRACTS §4.13 raw_metrics。
"""
from __future__ import annotations

import statistics
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.dispatch.algorithms.base import KNOWN_ALGORITHMS


class ExperimentBatchRequest(BaseModel):
    """POST /experiments 请求体。"""

    scenario_id: UUID
    algorithms: list[str] = Field(
        default=["AUCTION_HUNGARIAN", "GREEDY", "RANDOM"],
        min_length=1,
    )
    repetitions: int = Field(default=10, ge=1, le=30)


class ExperimentBatchStart(BaseModel):
    """POST /experiments 202 响应体。"""

    batch_id: UUID
    status: str = "running"
    estimated_duration_sec: int


class ExperimentRunRead(BaseModel):
    """单次实验运行结果。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    batch_id: UUID
    scenario_id: UUID
    algorithm: str
    run_index: int
    completion_rate: float | None = None
    avg_response_sec: float | None = None
    total_path_km: float | None = None
    load_std_dev: float | None = None
    decision_latency_ms: int | None = None
    raw_metrics: dict[str, Any] = {}
    started_at: datetime
    finished_at: datetime | None = None


class AlgorithmStats(BaseModel):
    """单个算法的汇总统计。"""

    avg_completion_rate: float
    avg_response_sec: float
    avg_total_path_km: float
    avg_load_std_dev: float
    avg_decision_latency_ms: float
    std_decision_latency_ms: float
    run_count: int


class ExperimentBatchStatus(BaseModel):
    """GET /experiments/{batch_id} 响应体。"""

    batch_id: UUID
    status: str
    progress_pct: float
    runs: list[ExperimentRunRead]
    stats: dict[str, AlgorithmStats]


class ChartDataset(BaseModel):
    label: str
    data: list[float]


class ChartData(BaseModel):
    labels: list[str]
    datasets: list[ChartDataset]


class ExperimentChartsResponse(BaseModel):
    """GET /experiments/{batch_id}/charts 响应体。"""

    completion_rate_chart: ChartData
    response_time_chart: ChartData
    path_length_chart: ChartData
    load_balance_chart: ChartData
    decision_latency_chart: ChartData


def _avg(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _std(vals: list[float]) -> float:
    return statistics.stdev(vals) if len(vals) >= 2 else 0.0


def compute_stats(runs: list[ExperimentRunRead]) -> dict[str, AlgorithmStats]:
    """按算法汇总统计，返回 {algorithm: AlgorithmStats}。"""
    by_algo: dict[str, list[ExperimentRunRead]] = {}
    for r in runs:
        by_algo.setdefault(r.algorithm, []).append(r)

    result: dict[str, AlgorithmStats] = {}
    for algo, algo_runs in by_algo.items():
        latencies = [r.decision_latency_ms for r in algo_runs if r.decision_latency_ms]
        result[algo] = AlgorithmStats(
            avg_completion_rate=_avg([r.completion_rate for r in algo_runs if r.completion_rate is not None]),
            avg_response_sec=_avg([r.avg_response_sec for r in algo_runs if r.avg_response_sec is not None]),
            avg_total_path_km=_avg([r.total_path_km for r in algo_runs if r.total_path_km is not None]),
            avg_load_std_dev=_avg([r.load_std_dev for r in algo_runs if r.load_std_dev is not None]),
            avg_decision_latency_ms=_avg([float(l) for l in latencies]),
            std_decision_latency_ms=_std([float(l) for l in latencies]),
            run_count=len(algo_runs),
        )
    return result


def build_charts(runs: list[ExperimentRunRead]) -> ExperimentChartsResponse:
    """从 runs 构造 ECharts 数据格式。labels=Run 1..N，每算法一条折线。"""
    by_algo: dict[str, list[ExperimentRunRead]] = {}
    for r in runs:
        by_algo.setdefault(r.algorithm, []).append(r)

    max_runs = max((len(v) for v in by_algo.values()), default=0)
    labels = [f"Run {i}" for i in range(1, max_runs + 1)]

    def _make_chart(field: str) -> ChartData:
        datasets: list[ChartDataset] = []
        for algo, algo_runs in sorted(by_algo.items()):
            sorted_runs = sorted(algo_runs, key=lambda r: r.run_index)
            data = []
            for r in sorted_runs:
                val = getattr(r, field)
                data.append(round(float(val), 3) if val is not None else 0.0)
            datasets.append(ChartDataset(label=algo, data=data))
        return ChartData(labels=labels, datasets=datasets)

    return ExperimentChartsResponse(
        completion_rate_chart=_make_chart("completion_rate"),
        response_time_chart=_make_chart("avg_response_sec"),
        path_length_chart=_make_chart("total_path_km"),
        load_balance_chart=_make_chart("load_std_dev"),
        decision_latency_chart=_make_chart("decision_latency_ms"),
    )
