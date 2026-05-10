"""显示实验结果统计。"""
import asyncio, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(str(Path(__file__).parent.parent))
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import settings
engine = create_async_engine(settings.database_url, echo=False)
Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def main():
    async with Session() as s:
        rows = list((await s.execute(text(
            "SELECT algorithm, "
            "ROUND(AVG(completion_rate),1) as avg_cr, "
            "ROUND(AVG(decision_latency_ms),1) as avg_lat, "
            "ROUND(STDDEV(decision_latency_ms),1) as std_lat, "
            "ROUND(AVG(load_std_dev),3) as avg_load_std, "
            "ROUND(AVG(total_path_km),3) as avg_path, "
            "COUNT(*) as runs "
            "FROM experiment_runs GROUP BY algorithm ORDER BY algorithm"
        ))).all())
        print("algorithm              | avg_cr% | avg_lat_ms | std_lat | avg_load_std | avg_path_km | runs")
        print("-"*90)
        for r in rows:
            print(f"{r[0]:<22} | {r[1]:>6}% | {r[2]:>10}ms | {r[3]:>7} | {r[4]:>12} | {r[5]:>11} | {r[6]:>4}")
        total = sum(r[6] for r in rows)
        print(f"\nTotal experiment_runs: {total}")
    await engine.dispose()

asyncio.run(main())
