"""P8.3 实验运行脚本。

执行 2 批次 × 3 算法 × 10 次 = 60 条 ExperimentRun。
- 批次 1：匈牙利 + 贪心 + 随机，标准压力（10 任务 × 10 次）
- 批次 2：同算法，增大随机噪声（同场景二次实验，与批次 1 对比）

进度实时打印；结束后验证 DB 中有 60 条。
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

engine = create_async_engine(settings.database_url, echo=False)
Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

ALGORITHMS = ["AUCTION_HUNGARIAN", "GREEDY", "RANDOM"]
REPETITIONS = 10


async def main() -> None:
    # 获取 scenario_id
    async with Session() as s:
        row = (await s.execute(text("SELECT id, name FROM scenarios WHERE is_active = TRUE LIMIT 1"))).one_or_none()
        if row is None:
            print("[ERROR] 没有活跃场景，请先执行 scripts/seed.py")
            sys.exit(1)
        scenario_id, scenario_name = row
        print(f"[INFO] 场景：{scenario_name}（id={str(scenario_id)[:8]}...）")

    runner = ExperimentRunner()

    print(f"\n{'='*50}")
    print(f"批次 1：3 算法 × {REPETITIONS} 次（共 {3 * REPETITIONS} runs）")
    print(f"{'='*50}")
    batch1 = uuid4()
    await runner.run_batch(
        batch_id=batch1,
        scenario_id=scenario_id,
        algorithms=ALGORITHMS,
        repetitions=REPETITIONS,
    )
    print(f"[OK] 批次 1 完成（batch_id={str(batch1)[:8]}...）")

    print(f"\n{'='*50}")
    print(f"批次 2：3 算法 × {REPETITIONS} 次（重复实验验证稳定性）")
    print(f"{'='*50}")
    batch2 = uuid4()
    await runner.run_batch(
        batch_id=batch2,
        scenario_id=scenario_id,
        algorithms=ALGORITHMS,
        repetitions=REPETITIONS,
    )
    print(f"[OK] 批次 2 完成（batch_id={str(batch2)[:8]}...）")

    # 验证 DB 中总 runs 数量
    async with Session() as s:
        total = (await s.execute(text(
            "SELECT COUNT(*) FROM experiment_runs WHERE batch_id IN (:b1, :b2)"
        ), {"b1": str(batch1), "b2": str(batch2)})).scalar_one()

    expected = 2 * len(ALGORITHMS) * REPETITIONS
    print(f"\n{'='*50}")
    print(f"验证：experiment_runs 共 {total} 条（预期 {expected}）")
    if total == expected:
        print(f"[PASS] 实验数据生成完成！")
        print(f"batch_id_1 = {batch1}")
        print(f"batch_id_2 = {batch2}")
    else:
        print(f"[WARN] 数量不符，可能部分 run 出错")

    await engine.dispose()


asyncio.run(main())
