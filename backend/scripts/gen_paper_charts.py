"""
P8.5 论文素材：从 experiment_runs 表生成 5 张算法对比图（PNG）。

输出目录：docs/paper_assets/
图表：
  fig1_completion_rate.png  — 任务完成率对比
  fig2_response_time.png    — 平均响应时间对比
  fig3_path_length.png      — 总路径长度对比
  fig4_load_balance.png     — 负载均衡标准差对比
  fig5_decision_latency.png — 决策延迟对比

使用方式（在 backend/ 目录下）：
  .venv\\Scripts\\python.exe scripts/gen_paper_charts.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 确保 backend/ 在 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import warnings
import matplotlib
matplotlib.use("Agg")  # 无 GUI 模式
import matplotlib.pyplot as plt
warnings.filterwarnings("ignore", message="Tight layout not applied")
import matplotlib.patches as mpatches
import numpy as np
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.replay import ExperimentRun

OUTPUT_DIR = Path(__file__).parent.parent.parent / "docs" / "paper_assets"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 论文风格配置
ALGO_LABELS = {
    "AUCTION_HUNGARIAN": "匈牙利拍卖算法",
    "GREEDY": "贪心算法",
    "RANDOM": "随机算法",
}
ALGO_COLORS = {
    "AUCTION_HUNGARIAN": "#3B82F6",  # 蓝
    "GREEDY": "#10B981",             # 绿
    "RANDOM": "#F59E0B",             # 橙
}
FONT_SIZE_TITLE = 14
FONT_SIZE_LABEL = 12
FONT_SIZE_TICK = 10
DPI = 150
FIG_W, FIG_H = 8, 5


def set_paper_style() -> None:
    plt.rcParams.update({
        "font.family": ["SimHei", "Microsoft YaHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.linestyle": "--",
    })


def bar_chart(
    algos: list[str],
    values: list[float],
    errors: list[float] | None,
    title: str,
    ylabel: str,
    filename: str,
    *,
    ylim: tuple[float, float] | None = None,
    fmt: str = ".2f",
) -> None:
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
    x = np.arange(len(algos))
    width = 0.5
    colors = [ALGO_COLORS[a] for a in algos]
    labels = [ALGO_LABELS[a] for a in algos]

    bars = ax.bar(
        x, values, width,
        color=colors,
        yerr=errors if errors else None,
        capsize=6,
        error_kw={"linewidth": 1.5, "ecolor": "gray"},
        zorder=3,
    )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=FONT_SIZE_TICK)
    ax.set_ylabel(ylabel, fontsize=FONT_SIZE_LABEL)
    ax.set_title(title, fontsize=FONT_SIZE_TITLE, pad=12)
    if ylim:
        ax.set_ylim(*ylim)

    # 在柱顶标注数值
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + (ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.01,
            f"{val:{fmt}}",
            ha="center", va="bottom", fontsize=FONT_SIZE_TICK, fontweight="bold",
        )

    try:
        fig.tight_layout(pad=1.5)
    except Exception:
        pass
    out = OUTPUT_DIR / filename
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  OK {out.name}")


async def fetch_stats() -> dict[str, dict]:
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    stats: dict[str, dict] = {}
    algo_order = ["AUCTION_HUNGARIAN", "GREEDY", "RANDOM"]

    async with async_session() as session:
        for algo in algo_order:
            result = await session.execute(
                text("""
                    SELECT
                        AVG(completion_rate)        AS avg_cr,
                        STDDEV(completion_rate)     AS std_cr,
                        AVG(avg_response_sec)       AS avg_resp,
                        STDDEV(avg_response_sec)    AS std_resp,
                        AVG(total_path_km)          AS avg_path,
                        STDDEV(total_path_km)       AS std_path,
                        AVG(load_std_dev)           AS avg_load,
                        STDDEV(load_std_dev)        AS std_load,
                        AVG(decision_latency_ms)    AS avg_lat,
                        STDDEV(decision_latency_ms) AS std_lat,
                        COUNT(*)                    AS run_count
                    FROM experiment_runs
                    WHERE algorithm = :algo
                      AND completion_rate IS NOT NULL
                """),
                {"algo": algo},
            )
            row = result.mappings().one()
            stats[algo] = {k: (float(v) if v is not None else 0.0) for k, v in row.items()}
            print(f"  {algo}: n={stats[algo]['run_count']:.0f}  avg_cr={stats[algo]['avg_cr']:.3f}  avg_lat={stats[algo]['avg_lat']:.1f}ms  avg_path={stats[algo]['avg_path']:.3f}km  avg_load={stats[algo]['avg_load']:.3f}")

    await engine.dispose()
    return stats


def generate_charts(stats: dict[str, dict]) -> None:
    algos = ["AUCTION_HUNGARIAN", "GREEDY", "RANDOM"]

    # 图1 任务完成率
    bar_chart(
        algos=algos,
        values=[stats[a]["avg_cr"] * 100 for a in algos],
        errors=[stats[a]["std_cr"] * 100 for a in algos],
        title="图3-1  三种调度算法任务完成率对比",
        ylabel="平均任务完成率 (%)",
        filename="fig1_completion_rate.png",
        ylim=(0, 115),
        fmt=".1f",
    )

    # 图2 平均响应时间
    bar_chart(
        algos=algos,
        values=[stats[a]["avg_resp"] for a in algos],
        errors=[stats[a]["std_resp"] for a in algos],
        title="图3-2  三种调度算法平均响应时间对比",
        ylabel="平均响应时间 (s)",
        filename="fig2_response_time.png",
        fmt=".2f",
    )

    # 图3 总路径长度
    bar_chart(
        algos=algos,
        values=[stats[a]["avg_path"] for a in algos],
        errors=[stats[a]["std_path"] for a in algos],
        title="图3-3  三种调度算法总路径长度对比",
        ylabel="平均总路径长度 (km)",
        filename="fig3_path_length.png",
        fmt=".3f",
    )

    # 图4 负载均衡标准差
    bar_chart(
        algos=algos,
        values=[stats[a]["avg_load"] for a in algos],
        errors=[stats[a]["std_load"] for a in algos],
        title="图3-4  三种调度算法负载均衡标准差对比 (越小越均衡)",
        ylabel="任务分配标准差",
        filename="fig4_load_balance.png",
        fmt=".4f",
    )

    # 图5 决策延迟
    bar_chart(
        algos=algos,
        values=[stats[a]["avg_lat"] for a in algos],
        errors=[stats[a]["std_lat"] for a in algos],
        title="图3-5  三种调度算法决策延迟对比",
        ylabel="平均决策延迟 (ms)",
        filename="fig5_decision_latency.png",
        fmt=".1f",
    )


async def main() -> None:
    set_paper_style()
    print("正在从数据库读取实验数据...")
    stats = await fetch_stats()
    print("\n正在生成论文图表...")
    generate_charts(stats)
    print(f"\n完成！5 张图表已保存到 {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
