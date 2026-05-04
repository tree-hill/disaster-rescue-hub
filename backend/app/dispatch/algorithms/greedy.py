"""贪心算法（对照算法）。

对照 BUSINESS_RULES §1.4.2：
- 按任务优先级升序（1=最高，2=普通，3=最低）依次处理
- 每个任务从「尚未被分配 + bid 字典中出现」的候选中挑 final_bid 最大者
- 机器人在本轮拍卖中**不重用**（多任务批量调度场景）

复杂度 O(m·n)；不保证全局最优，作为论文实验中的 baseline。
"""
from __future__ import annotations

from typing import ClassVar
from uuid import UUID

from app.dispatch.algorithms.base import ALGORITHM_GREEDY, AuctionAlgorithm
from app.dispatch.rule_engine import RobotEvalInput, TaskEvalInput
from app.schemas.dispatch import BidBreakdown


class GreedyAuction(AuctionAlgorithm):
    """贪心算法求解器。task.priority 升序处理，每任务挑最高 bid。"""

    name: ClassVar[str] = ALGORITHM_GREEDY

    def solve(
        self,
        robots: list[RobotEvalInput],
        tasks: list[TaskEvalInput],
        bids: dict[tuple[UUID, UUID], BidBreakdown],
    ) -> dict[UUID, UUID]:
        if not robots or not tasks or not bids:
            return {}

        # 任务优先级升序：1=最高，2=普通，3=最低；同级保持输入顺序（Python sort 稳定）。
        sorted_tasks = sorted(tasks, key=lambda t: t.priority)

        assignments: dict[UUID, UUID] = {}
        used_robots: set[UUID] = set()
        for task in sorted_tasks:
            candidates = [
                r
                for r in robots
                if r.id not in used_robots and (r.id, task.id) in bids
            ]
            if not candidates:
                continue
            # 同最高 bid 时，max() 返回首个达到该值的元素 → 稳定地保持输入顺序。
            best = max(candidates, key=lambda r: bids[(r.id, task.id)].final_bid)
            assignments[task.id] = best.id
            used_robots.add(best.id)
        return assignments
