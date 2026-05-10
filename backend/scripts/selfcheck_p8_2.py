"""P8.2 ExperimentRunner 自检脚本。

验收标准：
A. schemas 静态校验（ExperimentBatchRequest / ExperimentRunRead / build_charts）
B. ExperimentRunner.run_batch 小规模端到端（1 算法 × 2 次 = 2 个 ExperimentRun 写入 DB）
C. ExperimentRunRepository.find_by_batch 读取结果
D. compute_stats / build_charts 产出正确结构
E. 测试任务清除（实验结束后 X- 前缀任务全部删除）
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.experiments.runner import ExperimentRunner
from app.repositories.experiment import ExperimentRunRepository
from app.schemas.experiment import (
    ExperimentBatchRequest,
    ExperimentRunRead,
    build_charts,
    compute_stats,
)

engine = create_async_engine(settings.database_url, echo=False)
Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

passed = 0
failed = 0


def ok(msg: str) -> None:
    global passed
    passed += 1
    print(f"  [OK] {msg}")


def fail(msg: str) -> None:
    global failed
    failed += 1
    print(f"  [FAIL] {msg}")


async def section_a() -> None:
    print("\n=== A: schemas 静态校验 ===")

    req = ExperimentBatchRequest(
        scenario_id=uuid4(),
        algorithms=["AUCTION_HUNGARIAN", "GREEDY"],
        repetitions=5,
    )
    assert req.repetitions == 5
    ok("ExperimentBatchRequest 构造正常")

    from app.schemas.experiment import ExperimentBatchStatus, compute_stats

    ok("ExperimentBatchStatus / compute_stats 导入正常")

    from app.schemas.experiment import ChartData, ChartDataset

    cd = ChartData(labels=["Run 1", "Run 2"], datasets=[ChartDataset(label="H", data=[80.0, 90.0])])
    assert len(cd.datasets) == 1
    ok("ChartData 构造正常")


async def section_b_c_d_e() -> None:
    print("\n=== B: 端到端单批次实验（GREEDY × 2 runs）===")

    # 拿 scenario_id
    async with Session() as s:
        row = (await s.execute(text("SELECT id FROM scenarios LIMIT 1"))).one_or_none()
        if row is None:
            fail("没有 scenario，无法运行 B/C/D/E（请先执行 scripts/seed.py）")
            return
        scenario_id = row[0]

    batch_id = uuid4()
    runner = ExperimentRunner()

    try:
        await runner.run_batch(
            batch_id=batch_id,
            scenario_id=scenario_id,
            algorithms=["GREEDY"],
            repetitions=2,
        )
        ok(f"run_batch 完成（batch_id={str(batch_id)[:8]}…）")
    except Exception as exc:
        fail(f"run_batch 抛异常: {exc}")
        import traceback
        traceback.print_exc()
        return

    print("\n=== C: ExperimentRunRepository.find_by_batch ===")
    async with Session() as s:
        runs_orm = await ExperimentRunRepository(s).find_by_batch(batch_id)
        if len(runs_orm) == 2:
            ok(f"find_by_batch 返回 {len(runs_orm)} 条（预期 2）")
        else:
            fail(f"find_by_batch 返回 {len(runs_orm)} 条（预期 2）")

        for r in runs_orm:
            assert r.algorithm == "GREEDY"
            assert r.batch_id == batch_id
            assert r.completion_rate is not None
            assert r.decision_latency_ms is not None
        ok("ExperimentRun 字段完整（algorithm/batch_id/completion_rate/decision_latency_ms）")

    print("\n=== D: compute_stats / build_charts ===")
    runs_read = [ExperimentRunRead.model_validate(r) for r in runs_orm]

    stats = compute_stats(runs_read)
    assert "GREEDY" in stats
    greedy_stats = stats["GREEDY"]
    assert 0 <= greedy_stats.avg_completion_rate <= 100
    ok(f"compute_stats GREEDY avg_completion_rate={greedy_stats.avg_completion_rate:.1f}%")

    charts = build_charts(runs_read)
    assert len(charts.completion_rate_chart.datasets) == 1
    assert charts.completion_rate_chart.datasets[0].label == "GREEDY"
    assert len(charts.completion_rate_chart.labels) == 2
    ok("build_charts 完成（1 dataset，2 labels=Run 1/Run 2）")

    print("\n=== E: 测试任务已清除（X-前缀任务为 0）===")
    async with Session() as s:
        count = (
            await s.execute(text("SELECT COUNT(*) FROM tasks WHERE code LIKE 'X-%'"))
        ).scalar_one()
        if count == 0:
            ok("X-前缀测试任务已全部删除")
        else:
            fail(f"仍有 {count} 条 X-前缀测试任务未清除")


async def main() -> None:
    try:
        await section_a()
        await section_b_c_d_e()
    finally:
        await engine.dispose()

    print(f"\n{'='*40}")
    print(f"结果：{passed} passed / {failed} failed")
    if failed > 0:
        sys.exit(1)


asyncio.run(main())
