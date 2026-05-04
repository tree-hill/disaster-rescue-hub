"""拍卖算法抽象基类。

对照 BUSINESS_RULES §1.4（三种拍卖求解算法）+ DATA_CONTRACTS §5（auctions.algorithm
Literal["AUCTION_HUNGARIAN", "GREEDY", "RANDOM"]）。

设计边界：
- 所有算法都是**纯求解器**：输入 robots / tasks / 已计算 bids（dict[(robot_id,
  task_id), BidBreakdown]），输出 {task_id: robot_id} 分配字典。
- 算法**不查库、不调 RuleEngine、不调 compute_full_bid**；这些预处理由 P5.4
  dispatch_service 完成（一次性算好 bids 字典传进来），保证：
    1. 三种算法接口一致，dispatch_service 流程单一可读
    2. 算法可在 ALGORITHM_TESTCASES.md 的 TC-1~TC-10 中被纯函数式覆盖
    3. 写库时（auctions + bids 表）所需的全部出价数据已经在 bids 字典里
- 不合格 (r, t) 对就「不出现在 bids 字典里」即可。算法不需要单独的 eligible_pairs
  参数。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar
from uuid import UUID

from app.dispatch.rule_engine import RobotEvalInput, TaskEvalInput
from app.schemas.dispatch import BidBreakdown

# 算法名常量，与 DATA_CONTRACTS auctions.algorithm Literal 字面对齐。
# P5.5 REST 切换接口（POST /dispatch/algorithm）会接收这三个字符串。
ALGORITHM_HUNGARIAN = "AUCTION_HUNGARIAN"
ALGORITHM_GREEDY = "GREEDY"
ALGORITHM_RANDOM = "RANDOM"

# 集合形式，便于 dispatch_service / API 校验。
KNOWN_ALGORITHMS: frozenset[str] = frozenset(
    {ALGORITHM_HUNGARIAN, ALGORITHM_GREEDY, ALGORITHM_RANDOM}
)


class AuctionAlgorithm(ABC):
    """拍卖求解算法抽象基类。

    子类约定：
    - 类属性 `name` 必须是 KNOWN_ALGORITHMS 中的一个常量字符串
    - solve() 为纯函数：相同输入产出相同输出（Random 算法依赖 seed 注入）
    """

    name: ClassVar[str]

    @abstractmethod
    def solve(
        self,
        robots: list[RobotEvalInput],
        tasks: list[TaskEvalInput],
        bids: dict[tuple[UUID, UUID], BidBreakdown],
    ) -> dict[UUID, UUID]:
        """求解 (robots, tasks) 的最优分配。

        参数:
            robots: 候选机器人列表（已通过 RuleEngine 过滤；顺序由调用方决定，
                算法应保持稳定性以便 ALGORITHM_TESTCASES 复现）
            tasks: 待分配任务列表（每个 task 至少有一个合格机器人；无任何合格
                的任务由调用方在外层处理为 auction.failed）
            bids: 预计算 BidBreakdown 字典，键为 (robot_id, task_id)。**字典里有
                = 合格 + 已出价**；字典里没有 = 不合格 / 跳过。算法不再单独
                判断合格性。

        返回:
            {task_id: robot_id} 字典；某个 task 没找到匹配则不出现在结果中（调
            用方据此判断该 task 本轮拍卖失败、保持 PENDING 等下一轮）。
        """
