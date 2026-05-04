"""匈牙利算法（主算法）。

对照 BUSINESS_RULES §1.4.1：
- 构建 n×m 代价矩阵 `C[i][j] = -bid_value`（取负转最小化）
- 不合格的 (r, t) 对设代价为 1e6（极大值），算法不会真的把它选中
- 调 scipy.optimize.linear_sum_assignment 求解
- 解出后过滤 cost ≥ 1e5 的「占位」分配（这些其实是「无可匹配」）

复杂度 O((n+m)³)，n=机器人数 m=任务数。本系统毕设场景 n≤25 / m≤10，决策延
迟 NFR < 2 秒（BUILD_ORDER §P5.8 验收）。
"""
from __future__ import annotations

from typing import ClassVar
from uuid import UUID

import numpy as np
from scipy.optimize import linear_sum_assignment

from app.dispatch.algorithms.base import ALGORITHM_HUNGARIAN, AuctionAlgorithm
from app.dispatch.rule_engine import RobotEvalInput, TaskEvalInput
from app.schemas.dispatch import BidBreakdown

# 不合格 (r, t) 对的代价。1e6 远大于任何真实 -bid（real bids ∈ [-1.35, 0.15]
# 经 vision_boost 1.5 倍最大放大后仍远小于 1e5），故 1e5 这一中间阈值能可靠
# 区分「真实分配」与「占位分配」。
INF_COST = 1e6
INF_COST_GUARD = 1e5  # >= INF_COST_GUARD 视为占位，需过滤


class HungarianAuction(AuctionAlgorithm):
    """匈牙利算法求解器。最优全局分配，论文主对照算法。"""

    name: ClassVar[str] = ALGORITHM_HUNGARIAN

    def solve(
        self,
        robots: list[RobotEvalInput],
        tasks: list[TaskEvalInput],
        bids: dict[tuple[UUID, UUID], BidBreakdown],
    ) -> dict[UUID, UUID]:
        n, m = len(robots), len(tasks)
        if n == 0 or m == 0 or not bids:
            return {}

        # 默认全 INF；只有 bids 字典里出现的 (r, t) 才填真实代价。
        cost = np.full((n, m), INF_COST, dtype=float)
        for i, robot in enumerate(robots):
            for j, task in enumerate(tasks):
                bid = bids.get((robot.id, task.id))
                if bid is not None:
                    cost[i, j] = -bid.final_bid  # 取负：最大化 bid = 最小化 cost

        # scipy 对非方阵自动按 min(n, m) 做匹配，多余行/列被忽略。
        row_ind, col_ind = linear_sum_assignment(cost)

        assignments: dict[UUID, UUID] = {}
        for i, j in zip(row_ind, col_ind):
            if cost[i, j] >= INF_COST_GUARD:
                # 该 (i, j) 是 INF 占位，意味着 task[j] 没真实可匹配机器人；
                # 跳过即可，让 task[j] 保持 PENDING 等下一轮拍卖。
                continue
            assignments[tasks[j].id] = robots[i].id
        return assignments
