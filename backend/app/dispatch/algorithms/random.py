"""随机分配（基线算法）。

对照 BUSINESS_RULES §1.4.3：
- 用独立 `random.Random(seed)` 实例，避免污染全局 RNG（CPU bound 论文实验需要
  可复现）
- `rng.sample(tasks, len(tasks))` 打乱任务处理顺序
- 每任务在合格机器人中 rng.choice 随机选 1
- 机器人在本轮拍卖中不重用

仅用于实验对照，证明 Hungarian / Greedy 的有效性。

注意：本文件名 `random.py` 与 stdlib 的 `random` 同名。Python 3 默认绝对导入下
本文件 `import random` 仍解析到 stdlib（不会自递归）；为可读性显式 `as _random`。
"""
from __future__ import annotations

import random as _random
from typing import ClassVar
from uuid import UUID

from app.dispatch.algorithms.base import ALGORITHM_RANDOM, AuctionAlgorithm
from app.dispatch.rule_engine import RobotEvalInput, TaskEvalInput
from app.schemas.dispatch import BidBreakdown


class RandomAuction(AuctionAlgorithm):
    """随机分配求解器。仅作为论文 baseline；可选 seed 注入便于复现。"""

    name: ClassVar[str] = ALGORITHM_RANDOM

    def __init__(self, seed: int | None = None) -> None:
        # 工厂 get_algorithm 默认不传 seed → None → 真随机；
        # 测试 / 实验脚本传固定 seed → 同输入产出相同分配。
        self._seed = seed

    def solve(
        self,
        robots: list[RobotEvalInput],
        tasks: list[TaskEvalInput],
        bids: dict[tuple[UUID, UUID], BidBreakdown],
    ) -> dict[UUID, UUID]:
        if not robots or not tasks or not bids:
            return {}

        rng = _random.Random(self._seed)
        # 任务处理顺序随机化：sample 返回新列表，不改原 tasks。
        shuffled_tasks = rng.sample(list(tasks), len(tasks))

        assignments: dict[UUID, UUID] = {}
        used_robots: set[UUID] = set()
        for task in shuffled_tasks:
            candidates = [
                r
                for r in robots
                if r.id not in used_robots and (r.id, task.id) in bids
            ]
            if not candidates:
                continue
            chosen = rng.choice(candidates)
            assignments[task.id] = chosen.id
            used_robots.add(chosen.id)
        return assignments
