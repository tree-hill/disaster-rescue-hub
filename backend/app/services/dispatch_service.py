"""调度编排服务（P5.4）。

对照：
- BUILD_ORDER §P5.4：start_auction(task_id) → Auction，候选 → 规则引擎过滤
  → 收集 bids → 算法求解 → 写 task_assignments → 发事件，**同事务原子写入**，
  测量 `decision_latency_ms`。
- BUSINESS_RULES §1.4 / §1.5（算法 + 写库审计）+ §3（规则引擎硬约束）+ §3.4
  （拍卖失败处理：status=FAILED，任务保持 PENDING，发 auction.failed）+ §2.1
  （PENDING → ASSIGNED 状态转移）。
- DATA_CONTRACTS §1.10 / §1.11 / §1.9（auctions / bids / task_assignments 表）
  + §4.7（BidBreakdown 结构）。
- WS_EVENTS §5：auction.started / auction.bid_submitted / auction.completed /
  auction.failed 四个事件，commander 房间。

设计取舍：
- **数据合并三处来源构造 RobotEvalInput**：robots 表（is_active/type/capability）
  + 最新 robot_states（fsm_state/position/battery）+ task_assignments active
  计数。无最新 state 的机器人（刚注册、Agent 还没上报过）默认 IDLE / battery=100
  / position=base。这一兜底让 RuleEngine.check 不会因数据稀疏抛 None。
- **算法实例由全局 `DispatchSettings.current_algorithm` 决定**（默认 HUNGARIAN）；
  P5.5 POST /dispatch/algorithm 切换接口直接改这个全局；本任务只读不写。
- **decision_latency_ms 测量边界**：从「数据已取齐 + filter 完毕」到「solve 返
  回」，纯算法决策时间，与论文 NFR 「< 2 秒」对应；不含 I/O / DB 写入。
- **vision_boost 当前传 0**（P6.1 黑板未建）；compute_full_bid 已设计为整数注入
  默认 0；写库时 `bids.vision_boost` 字段按实际 vision_boosted 标志存 1.5 / 1.0。
- **事件 commit 后才 publish**：避免事务回滚后已发出 WS 幻觉，与 P4.5 task.* 同
  款模式（service 不直接调 WS，只调 event_bus.publish；bridge 转推到 commander）。
- **不发 task.status_changed**：本任务范围外（WS_EVENTS §4 通用任务事件契约），
  留给后续模块统一接入；此处仅完成 PENDING → ASSIGNED 的状态机转移本身。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import get_event_bus
from app.core.exceptions import BusinessError
from app.dispatch.algorithms import (
    ALGORITHM_HUNGARIAN,
    KNOWN_ALGORITHMS,
    AuctionAlgorithm,
    get_algorithm,
)
from app.dispatch.bidding import (
    VISION_BOOST_FACTOR,
    compute_full_bid,
)
from app.dispatch.rule_engine import (
    RobotEvalInput,
    RuleEngine,
    TaskEvalInput,
)
from app.models.dispatch import Auction, Bid
from app.models.robot import Robot, RobotState
from app.models.task import Task, TaskAssignment
from app.repositories.auction import AuctionRepository
from app.repositories.bid import BidRepository
from app.repositories.robot import RobotRepository
from app.repositories.robot_state import RobotStateRepository
from app.repositories.task import TaskRepository
from app.repositories.task_assignment import TaskAssignmentRepository
from app.schemas.common import Position, RobotCapability
from app.schemas.dispatch import BidBreakdown
from app.schemas.task import TargetArea, TaskRequiredCapabilities
from app.services.task_status_machine import transit as transit_task

logger = logging.getLogger(__name__)


# === 事件名（领域事件，bridge 转推到 commander 房间） ===
EVT_AUCTION_STARTED = "auction.started"
EVT_AUCTION_BID_SUBMITTED = "auction.bid_submitted"
EVT_AUCTION_COMPLETED = "auction.completed"
EVT_AUCTION_FAILED = "auction.failed"

# === 默认兜底（无最新 robot_state 时使用）===
# 与 seed.py / RobotAgent 启动初值一致，避免规则引擎对稀疏数据返回错误结果。
_DEFAULT_FSM_STATE = "IDLE"
_DEFAULT_BATTERY = 100.0


# ---------- 全局算法配置 ----------


class DispatchSettings:
    """当前生效的调度算法（HITL 切换的全局开关）。

    设计：进程内单例 + 简单字符串字段。P5.5 POST /dispatch/algorithm 接口落地
    时调用 set_algorithm 切换；本任务只在 start_auction 中读取。

    重启不持久化（毕设场景每次启动按 settings.dispatch_default 或字面默认）。
    """

    _instance: "DispatchSettings | None" = None

    def __init__(self) -> None:
        self._algorithm: str = ALGORITHM_HUNGARIAN

    @classmethod
    def get_instance(cls) -> "DispatchSettings":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_for_tests(cls) -> None:
        cls._instance = None

    @property
    def current_algorithm(self) -> str:
        return self._algorithm

    def set_algorithm(self, name: str) -> None:
        if name not in KNOWN_ALGORITHMS:
            raise ValueError(
                f"unknown algorithm: {name!r}; must be one of {sorted(KNOWN_ALGORITHMS)}"
            )
        self._algorithm = name


def get_dispatch_settings() -> DispatchSettings:
    return DispatchSettings.get_instance()


# ---------- 错误工厂 ----------


def _task_not_found(task_id: UUID) -> BusinessError:
    return BusinessError(
        code="404_TASK_NOT_FOUND_001",
        message="任务不存在",
        http_status=404,
        details=[{"field": "task_id", "code": "not_found", "message": str(task_id)}],
    )


def _task_not_pending(task: Task) -> BusinessError:
    """API_SPEC §4 POST /dispatch/auction：任务非 PENDING → 409。"""
    return BusinessError(
        code="409_TASK_STATUS_CONFLICT_001",
        message=f"任务状态 {task.status} 不允许触发拍卖（仅 PENDING 可拍）",
        http_status=409,
        details=[
            {
                "field": "task.status",
                "code": "current_status",
                "message": task.status,
            },
            {
                "field": "task.status",
                "code": "expected_status",
                "message": "PENDING",
            },
        ],
    )


# ---------- 视图构造辅助 ----------


def _robot_to_eval_input(
    robot: Robot,
    state: RobotState | None,
    active_count: int,
) -> RobotEvalInput:
    """合并 robots 表 + 最新 robot_states + active 分配计数构造 RuleEngine 入参。

    state=None（机器人刚入库 / Agent 未上报）的兜底：
    - fsm_state="IDLE"、battery=100（与 RobotAgent 启动初值一致）
    - position 取 capability 兜底不可行 → 用 (0,0)；这种情况下 R7 距离硬约束
      会报 out_of_range，机器人自然被过滤，不会假赢
    """
    if state is not None:
        fsm = str(state.fsm_state)
        battery = float(state.battery)
        position = Position.model_validate(state.position)
    else:
        fsm = _DEFAULT_FSM_STATE
        battery = _DEFAULT_BATTERY
        position = Position(lat=0.0, lng=0.0)

    capability = RobotCapability.model_validate(robot.capability or {})
    return RobotEvalInput(
        id=robot.id,
        is_active=bool(robot.is_active),
        type=str(robot.type),  # type: ignore[arg-type]
        fsm_state=fsm,  # type: ignore[arg-type]
        battery=battery,
        position=position,
        capability=capability,
        active_assignments_count=int(active_count),
    )


def _task_to_eval_input(task: Task) -> TaskEvalInput:
    """tasks 表行 → TaskEvalInput（priority 透传供 GreedyAuction 使用）。"""
    target_area = TargetArea.model_validate(task.target_area)
    required = TaskRequiredCapabilities.model_validate(task.required_capabilities or {})
    return TaskEvalInput(
        id=task.id,
        required_capabilities=required,
        target_area=target_area,
        priority=int(task.priority),
    )


# ---------- DispatchService ----------


class DispatchService:
    """拍卖编排服务，对外暴露 `start_auction(task_id)`。

    依赖注入按 session 走（与 TaskService / RecallService 同款），便于单测构造。
    内部 RuleEngine / 算法实例每次调用新建（无状态，开销可忽略），避免与
    DispatchSettings.set_algorithm 的运行时切换出现陈旧引用。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tasks = TaskRepository(session)
        self.assignments = TaskAssignmentRepository(session)
        self.robots = RobotRepository(session)
        self.robot_states = RobotStateRepository(session)
        self.auctions = AuctionRepository(session)
        self.bids = BidRepository(session)
        self._engine = RuleEngine()

    async def start_auction(
        self,
        task_id: UUID,
        *,
        algorithm: str | None = None,
    ) -> Auction:
        """启动一次拍卖，返回写入完成的 Auction。

        参数:
            task_id: 待拍任务 id（必须 status=PENDING）。
            algorithm: 可选覆盖（仅本次拍卖使用，不影响全局设置）；不传则取
                DispatchSettings.current_algorithm，默认 HUNGARIAN。

        抛出:
            404_TASK_NOT_FOUND_001：task_id 不存在。
            409_TASK_STATUS_CONFLICT_001：任务非 PENDING。
            ValueError：algorithm 字符串不在 KNOWN_ALGORITHMS 中。

        副作用（同一事务原子写入）:
            - auctions 表新增 1 行（成功或失败）
            - bids 表新增 N 行（仅当有 eligible 机器人）
            - task_assignments 表新增 1 行（仅当有 winner）
            - tasks.status: PENDING → ASSIGNED（仅当有 winner）

        commit 之后再 publish（commit 失败不会留 WS 幻觉）：
            - 无 eligible: auction.failed（reason=no_eligible_robot）
            - 无 winner（极端罕见，bids 全 INF）: auction.failed（reason=no_winner）
            - 有 winner: auction.started → auction.bid_submitted ×N → auction.completed
        """
        task = await self.tasks.find_by_id(task_id)
        if task is None:
            raise _task_not_found(task_id)
        if task.status != "PENDING":
            raise _task_not_pending(task)

        algorithm_name = algorithm or get_dispatch_settings().current_algorithm
        algo: AuctionAlgorithm = get_algorithm(algorithm_name)

        # === 1) 取候选机器人（active=TRUE）+ 最新 state + active 分配计数 ===
        all_robots = await self.robots.find_all(only_active=True)
        if not all_robots:
            # 全无 active 机器人：等价于 filter 后 eligible=[]，走失败路径。
            return await self._fail_no_eligible(
                task=task,
                algorithm_name=algorithm_name,
                stats={"inactive": 0},  # 没人参选，统计为空字段
                filtered_out_count=0,
                latency_ms=0,
            )

        robot_ids = [r.id for r in all_robots]
        active_counts = await self.assignments.count_active_by_robot_bulk(robot_ids)

        robot_views: list[RobotEvalInput] = []
        # robot 列表中下标 → Robot ORM 对象的映射，后续要靠 winner_id 拿 robot.code
        view_to_robot: dict[UUID, Robot] = {}
        for r in all_robots:
            latest_state = await self.robot_states.find_latest_by_robot(r.id)
            view = _robot_to_eval_input(r, latest_state, active_counts.get(r.id, 0))
            robot_views.append(view)
            view_to_robot[r.id] = r

        # === 2) 构造任务视图 + RuleEngine.filter ===
        task_view = _task_to_eval_input(task)

        # 决策延迟测量起点：数据已齐，从这里开始算「决策时间」
        t0 = time.perf_counter()
        eligible, filter_stats = self._engine.filter(robot_views, task_view)

        if not eligible:
            # § 3.4 规则引擎全过滤掉 → 写 FAILED auction，发 auction.failed
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return await self._fail_no_eligible(
                task=task,
                algorithm_name=algorithm_name,
                stats=filter_stats,
                filtered_out_count=len(robot_views),
                latency_ms=latency_ms,
            )

        # === 3) 计算 bids（vision_boost 暂传 0：P6.1 黑板未建）===
        bids_map: dict[tuple[UUID, UUID], BidBreakdown] = {
            (rv.id, task_view.id): compute_full_bid(rv, task_view, nearby_survivor_count=0)
            for rv in eligible
        }

        # === 4) 写 Auction(OPEN) + Bid 行（同事务） ===
        auction = Auction(
            task_id=task.id,
            algorithm=algorithm_name,
            status="OPEN",
            auction_metadata={
                "candidate_robot_count": len(eligible),
                "filter_stats": filter_stats,
            },
        )
        await self.auctions.save(auction)  # flush → auction.id 可读

        bid_rows: list[Bid] = []
        for rv in eligible:
            breakdown = bids_map[(rv.id, task_view.id)]
            bid_rows.append(
                Bid(
                    auction_id=auction.id,
                    robot_id=rv.id,
                    bid_value=Decimal(str(round(breakdown.final_bid, 4))),
                    breakdown=breakdown.model_dump(),
                    vision_boost=Decimal(
                        "1.5" if breakdown.vision_boosted else "1.0"
                    ),
                )
            )
        await self.bids.save_many(bid_rows)

        # === 5) 算法求解 + decision_latency_ms 终点 ===
        assignments_dict = algo.solve(eligible, [task_view], bids_map)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        winner_robot_id: UUID | None = assignments_dict.get(task_view.id)

        if winner_robot_id is None:
            # 极端：所有 eligible 都被算法拒（理论上不应发生，因为 bids 都是真实
            # 代价；但 hungarian 在 INF guard 后可能跳过）→ 写 FAILED auction。
            auction.status = "FAILED"
            auction.closed_at = datetime.now(timezone.utc)
            auction.decision_latency_ms = latency_ms
            await self.session.flush()
            await self.session.commit()
            await self.session.refresh(auction)
            await self._publish_failed(
                auction=auction,
                task=task,
                reason="no_winner",
                filtered_out_count=len(robot_views) - len(eligible),
            )
            return auction

        # === 6) 有 winner：写 task_assignment + transit task → ASSIGNED ===
        winner_breakdown = bids_map[(winner_robot_id, task_view.id)]
        auction.status = "CLOSED"
        auction.closed_at = datetime.now(timezone.utc)
        auction.winner_robot_id = winner_robot_id
        auction.decision_latency_ms = latency_ms

        assignment = TaskAssignment(
            task_id=task.id,
            robot_id=winner_robot_id,
            auction_id=auction.id,
            is_active=True,
        )
        await self.assignments.save(assignment)

        # 状态机转移（同事务，仅修 ORM 字段，不 commit）
        transit_task(task, "ASSIGNED", reason=f"auction:{auction.id}")

        await self.session.commit()
        await self.session.refresh(auction)

        # === 7) commit 之后发 WS 事件链 ===
        winner_robot = view_to_robot[winner_robot_id]
        await self._publish_started(
            auction=auction,
            task=task,
            algorithm_name=algorithm_name,
            candidate_count=len(eligible),
        )
        await self._publish_bid_events(
            auction=auction,
            eligible=eligible,
            view_to_robot=view_to_robot,
            bids_map=bids_map,
            task_id=task_view.id,
        )
        await self._publish_completed(
            auction=auction,
            task=task,
            winner_robot=winner_robot,
            winner_breakdown=winner_breakdown,
            total_bidders=len(eligible),
            latency_ms=latency_ms,
        )

        return auction

    # ---------- 失败路径 ----------

    async def _fail_no_eligible(
        self,
        *,
        task: Task,
        algorithm_name: str,
        stats: dict[str, int],
        filtered_out_count: int,
        latency_ms: int,
    ) -> Auction:
        """写 Auction(status=FAILED) + commit + publish auction.failed。"""
        now = datetime.now(timezone.utc)
        auction = Auction(
            task_id=task.id,
            algorithm=algorithm_name,
            status="FAILED",
            closed_at=now,
            decision_latency_ms=latency_ms,
            auction_metadata={
                "candidate_robot_count": 0,
                "filter_stats": stats,
                "reason": "no_eligible_robot",
            },
        )
        await self.auctions.save(auction)
        await self.session.commit()
        await self.session.refresh(auction)
        await self._publish_failed(
            auction=auction,
            task=task,
            reason="no_eligible_robot",
            filtered_out_count=filtered_out_count,
            reason_breakdown=stats,
        )
        return auction

    # ---------- 事件发布 ----------

    async def _publish_started(
        self,
        *,
        auction: Auction,
        task: Task,
        algorithm_name: str,
        candidate_count: int,
    ) -> None:
        await self._publish(
            EVT_AUCTION_STARTED,
            {
                "auction_id": str(auction.id),
                "task_id": str(task.id),
                "task_code": task.code,
                "algorithm": algorithm_name,
                "candidate_robot_count": candidate_count,
            },
        )

    async def _publish_bid_events(
        self,
        *,
        auction: Auction,
        eligible: list[RobotEvalInput],
        view_to_robot: dict[UUID, Robot],
        bids_map: dict[tuple[UUID, UUID], BidBreakdown],
        task_id: UUID,
    ) -> None:
        for rv in eligible:
            breakdown = bids_map[(rv.id, task_id)]
            robot = view_to_robot[rv.id]
            await self._publish(
                EVT_AUCTION_BID_SUBMITTED,
                {
                    "auction_id": str(auction.id),
                    "robot_id": str(rv.id),
                    "robot_code": robot.code,
                    "bid_value": float(round(breakdown.final_bid, 4)),
                    "vision_boosted": bool(breakdown.vision_boosted),
                },
            )

    async def _publish_completed(
        self,
        *,
        auction: Auction,
        task: Task,
        winner_robot: Robot,
        winner_breakdown: BidBreakdown,
        total_bidders: int,
        latency_ms: int,
    ) -> None:
        await self._publish(
            EVT_AUCTION_COMPLETED,
            {
                "auction_id": str(auction.id),
                "task_id": str(task.id),
                "winner_robot_id": str(winner_robot.id),
                "winner_robot_code": winner_robot.code,
                "winning_bid": float(round(winner_breakdown.final_bid, 4)),
                "decision_latency_ms": latency_ms,
                "total_bidders": total_bidders,
                "vision_boost_applied": bool(winner_breakdown.vision_boosted),
                "vision_boost_factor": (
                    VISION_BOOST_FACTOR if winner_breakdown.vision_boosted else 1.0
                ),
            },
        )

    async def _publish_failed(
        self,
        *,
        auction: Auction,
        task: Task,
        reason: str,
        filtered_out_count: int,
        reason_breakdown: dict[str, int] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "auction_id": str(auction.id),
            "task_id": str(task.id),
            "reason": reason,
            "filtered_out_count": filtered_out_count,
        }
        if reason_breakdown is not None:
            payload["reason_breakdown"] = reason_breakdown
        await self._publish(EVT_AUCTION_FAILED, payload)

    async def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        """统一容错 publish：bus 异常仅日志，不影响 HTTP 响应。"""
        try:
            await get_event_bus().publish(event_type, payload)
        except Exception:
            logger.exception(
                "auction_publish_failed",
                extra={"event_type": event_type, "payload": payload},
            )
