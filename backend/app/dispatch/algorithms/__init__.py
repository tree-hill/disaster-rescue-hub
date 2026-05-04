"""拍卖算法包。

公开接口：
- `AuctionAlgorithm` 抽象基类
- `HungarianAuction / GreedyAuction / RandomAuction` 三种实现
- `get_algorithm(name)` 工厂方法（P5.5 REST 切换 + P5.4 dispatch_service 默认装配会用）
- 三个算法名常量 `ALGORITHM_HUNGARIAN / ALGORITHM_GREEDY / ALGORITHM_RANDOM`
- `KNOWN_ALGORITHMS` 集合（API 入参校验）

对照 BUILD_ORDER §P5.3。
"""
from __future__ import annotations

from app.dispatch.algorithms.base import (
    ALGORITHM_GREEDY,
    ALGORITHM_HUNGARIAN,
    ALGORITHM_RANDOM,
    KNOWN_ALGORITHMS,
    AuctionAlgorithm,
)
from app.dispatch.algorithms.greedy import GreedyAuction
from app.dispatch.algorithms.hungarian import HungarianAuction
from app.dispatch.algorithms.random import RandomAuction

__all__ = [
    "ALGORITHM_GREEDY",
    "ALGORITHM_HUNGARIAN",
    "ALGORITHM_RANDOM",
    "KNOWN_ALGORITHMS",
    "AuctionAlgorithm",
    "GreedyAuction",
    "HungarianAuction",
    "RandomAuction",
    "get_algorithm",
]


def get_algorithm(name: str, *, seed: int | None = None) -> AuctionAlgorithm:
    """按名取算法实例。

    `seed` 仅对 RandomAuction 生效；Hungarian / Greedy 是确定性算法，传 seed
    无副作用。未知 name 抛 ValueError；P5.5 REST 接口若需要业务错误码，由 API
    层翻译为 BusinessError（例如 422_VALIDATION_FAILED_001 / 自定义码）。
    """
    if name == ALGORITHM_HUNGARIAN:
        return HungarianAuction()
    if name == ALGORITHM_GREEDY:
        return GreedyAuction()
    if name == ALGORITHM_RANDOM:
        return RandomAuction(seed=seed)
    raise ValueError(
        f"unknown algorithm: {name!r}; must be one of {sorted(KNOWN_ALGORITHMS)}"
    )
