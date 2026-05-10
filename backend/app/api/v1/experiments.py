"""实验模块 REST 路由（P8.2）。

对照 API_SPEC §7：
- POST /experiments            启动对比实验（异步，202）
- GET  /experiments/{batch_id} 查询批次状态与结果
- GET  /experiments/{batch_id}/charts  获取图表数据（ECharts 格式）
- GET  /experiments/{batch_id}/export  导出 CSV / JSON

权限：POST 要求 experiment:run；GET 要求 replay:read。
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.db.session import get_db
from app.dispatch.algorithms.base import KNOWN_ALGORITHMS
from app.experiments.runner import get_batch_status, get_experiment_runner
from app.repositories.experiment import ExperimentRunRepository
from app.schemas.experiment import (
    ExperimentBatchRequest,
    ExperimentBatchStart,
    ExperimentBatchStatus,
    ExperimentChartsResponse,
    ExperimentRunRead,
    build_charts,
    compute_stats,
)

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.post("", status_code=202, response_model=ExperimentBatchStart)
async def start_experiment(
    payload: ExperimentBatchRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_permission("experiment:run")),
) -> ExperimentBatchStart:
    """启动一次对比实验批次，异步执行，立即返回 batch_id。"""
    # 校验算法名
    unknown = [a for a in payload.algorithms if a not in KNOWN_ALGORITHMS]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown algorithms: {unknown}. Valid: {sorted(KNOWN_ALGORITHMS)}",
        )

    batch_id = uuid4()
    estimated = len(payload.algorithms) * payload.repetitions * 5  # ~5s per run

    runner = get_experiment_runner()
    background_tasks.add_task(
        runner.run_batch,
        batch_id=batch_id,
        scenario_id=payload.scenario_id,
        algorithms=payload.algorithms,
        repetitions=payload.repetitions,
    )

    return ExperimentBatchStart(
        batch_id=batch_id,
        status="running",
        estimated_duration_sec=estimated,
    )


@router.get("/{batch_id}", response_model=ExperimentBatchStatus)
async def get_experiment_batch(
    batch_id: UUID,
    session: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission("replay:read")),
) -> ExperimentBatchStatus:
    """获取实验批次状态与各次运行结果。"""
    mem = get_batch_status(batch_id)

    runs_orm = await ExperimentRunRepository(session).find_by_batch(batch_id)
    runs = [ExperimentRunRead.model_validate(r) for r in runs_orm]

    if mem is None:
        # 批次不在内存（可能重启后），从 DB 推断状态
        if not runs:
            raise HTTPException(status_code=404, detail="Experiment batch not found")
        status = "completed"
        total = len(runs)
        completed = len(runs)
    else:
        status = mem["status"]
        total = mem["total"]
        completed = mem["completed"]

    progress_pct = round(completed / total * 100, 1) if total > 0 else 0.0
    stats = compute_stats(runs)

    return ExperimentBatchStatus(
        batch_id=batch_id,
        status=status,
        progress_pct=progress_pct,
        runs=runs,
        stats=stats,
    )


@router.get("/{batch_id}/charts", response_model=ExperimentChartsResponse)
async def get_experiment_charts(
    batch_id: UUID,
    session: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission("replay:read")),
) -> ExperimentChartsResponse:
    """获取实验图表数据（ECharts 折线/柱状图格式）。"""
    runs_orm = await ExperimentRunRepository(session).find_by_batch(batch_id)
    if not runs_orm:
        raise HTTPException(status_code=404, detail="Experiment batch not found or has no data yet")

    runs = [ExperimentRunRead.model_validate(r) for r in runs_orm]
    return build_charts(runs)


@router.get("/{batch_id}/export")
async def export_experiment(
    batch_id: UUID,
    format: str = Query("json", pattern="^(json|csv)$"),
    session: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission("replay:read")),
) -> Response:
    """导出实验结果（json 或 csv）。"""
    runs_orm = await ExperimentRunRepository(session).find_by_batch(batch_id)
    if not runs_orm:
        raise HTTPException(status_code=404, detail="Experiment batch not found or has no data yet")

    runs = [ExperimentRunRead.model_validate(r) for r in runs_orm]

    if format == "json":
        content = json.dumps(
            [r.model_dump(mode="json") for r in runs],
            ensure_ascii=False,
            indent=2,
        )
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=experiment_{batch_id}.json"},
        )

    # CSV
    buf = io.StringIO()
    fieldnames = [
        "id", "batch_id", "algorithm", "run_index",
        "completion_rate", "avg_response_sec", "total_path_km",
        "load_std_dev", "decision_latency_ms", "started_at", "finished_at",
    ]
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in runs:
        row = r.model_dump(mode="json")
        writer.writerow({k: row.get(k, "") for k in fieldnames})

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=experiment_{batch_id}.csv"},
    )
