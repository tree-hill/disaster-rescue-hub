"""调度编排服务（P5.4 拍卖闭环 + P5.5 查询 / HITL 算法切换）。

对照：
- BUILD_ORDER §P5.4：start_auction(task_id) → Auction，候选 → 规则引擎过滤
  → 收集 bids → 算法求解 → 写 task_assignments → 发事件，**同事务原子写入**，
  测量 `decision_latency_ms`。
- BUILD_ORDER §P5.5：list_auctions / get_auction_with_bids / switch_algorithm。
- BUSINESS_RULES §1.4 / §1.5（算法 + 写库审计）+ §3（规则引擎硬约束）+ §3.4
  （拍卖失败处理：status=FAILED，任务保持 PENDING，发 auction.failed）+ §2.1
  （PENDING → ASSIGNED 状态转移）+ §4.1 / §4.5（algorithm_switch HITL 流程）。
- DATA_CONTRACTS §1.10 / §1.11 / §1.9 / §1.12（auctions / bids / task_assignments
  / human_interventions 表）+ §4.7（BidBreakdown 结构）+ §4.8（before/after_state）。
- WS_EVENTS §4 / §5：task.status_changed、auction.started、auction.bid_submitted、
  auction.completed、auction.failed、dispatch.algorithm_changed 事件。

设计取舍：
- **数据合并三处来源构造 RobotEvalInput**：robots 表（is_active/type/capability）
  + 最新 robot_states（fsm_state/position/battery）+ task_assignments active
  计数。无最新 state 的机器人（刚注册、Agent 还没上报过）默认 IDLE / battery=100
  / position=base。这一兜底让 RuleEngine.check 不会因数据稀疏抛 None。
- **算法实例由全局 `DispatchSettings.current_algorithm` 决定**（默认 HUNGARIAN）；
  P5.5 POST /dispatch/algorithm 切换接口直接改这个全局；本任务只读不写。
- **decision_latency_ms 测量边界**：从「数据已取齐 + filter 完毕」到「solve 返
  回」，纯算法决策时间，与论文 NFR 「< 2 秒」对应；不含 I/O / DB 写入。
- **vision_boost 来自黑板邻近幸存者信息**；compute_full_bid 通过
  `nearby_survivor_count` 注入加成，写库时 `bids.vision_boost` 字段按实际
  vision_boosted 标志存 1.5 / 1.0。
- **事件 commit 后才 publish**：避免事务回滚后已发出 WS 幻觉，与 P4.5 task.* 同
  款模式（service 不直接调 WS，只调 event_bus.publish；bridge 转推到 commander）。
- **task.status_changed commit 后发布**：任务 PENDING → ASSIGNED 与 auction.completed
  同样在事务提交后发出，避免前端收到回滚后的幻觉状态。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.manager import get_agent_manager
from app.core.event_bus import get_event_bus
from app.core.exceptions import BusinessError
from app.dispatch.algorithms import (
    ALGORITHM_HUNGARIAN,
    KNOWN_ALGORITHMS,
    AuctionAlgorithm,
    get_algorithm,
)
from app.communication.blackboard import get_blackboard
from app.dispatch.bidding import (
    VISION_BOOST_FACTOR,
    VISION_CONFIDENCE_THRESHOLD,
    VISION_PROXIMITY_RADIUS_M,
    compute_full_bid,
)
from app.dispatch.rule_engine import (
    RobotEvalInput,
    RuleEngine,
    TaskEvalInput,
)
from app.core.constants import RECALL_REASON_MIN_LEN
from app.models.dispatch import Auction, Bid
from app.models.intervention import HumanIntervention
from app.models.robot import Robot, RobotState
from app.models.task import Task, TaskAssignment
from app.repositories.auction import AuctionRepository
from app.repositories.bid import BidRepository
from app.repositories.intervention import InterventionRepository
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
EVT_DISPATCH_ALGORITHM_CHANGED = "dispatch.algorithm_changed"
EVT_TASK_STATUS_CHANGED = "task.status_changed"
EVT_TASK_REASSIGNED = "task.reassigned"
EVT_INTERVENTION_RECORDED = "intervention.recorded"

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


def _auction_not_found(auction_id: UUID) -> BusinessError:
    return BusinessError(
        code="404_AUCTION_NOT_FOUND_001",
        message="拍卖会话不存在",
        http_status=404,
        details=[
            {"field": "auction_id", "code": "not_found", "message": str(auction_id)}
        ],
    )


def _validate_reason(reason: str) -> None:
    """BUSINESS_RULES §4.3.1 + §6.5：reason ≥ 5 字符且非纯空白。

    特化错误码 422_INTERVENTION_REASON_INVALID_001（与 cancel_task / recall 同款）。
    """
    if not isinstance(reason, str) or len(reason.strip()) < RECALL_REASON_MIN_LEN:
        raise BusinessError(
            code="422_INTERVENTION_REASON_INVALID_001",
            message=f"reason 至少 {RECALL_REASON_MIN_LEN} 个非空白字符",
            http_status=422,
            details=[
                {
                    "field": "reason",
                    "code": "too_short_or_blank",
                    "message": f"strip 后长度 {len(reason.strip()) if isinstance(reason, str) else 0}",
                }
            ],
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


def _robot_to_live_eval_input(
    robot: Robot,
    agent: Any,
    active_count: int,
) -> RobotEvalInput:
    """Build a RuleEngine view from a running RobotAgent.

    The database robot_states table is written once per tick. During a busy demo,
    an auction can run between two ticks, so the DB snapshot may still say IDLE
    while the in-memory agent has already accepted another task. When agents are
    running, the live agent state is the fresher source of truth for dispatch.
    """
    capability = RobotCapability.model_validate(robot.capability or {})
    position = Position.model_validate(agent.position)
    return RobotEvalInput(
        id=robot.id,
        is_active=bool(robot.is_active),
        type=str(robot.type),  # type: ignore[arg-type]
        fsm_state=str(agent.fsm_state),  # type: ignore[arg-type]
        battery=float(agent.battery),
        position=position,
        capability=capability,
        active_assignments_count=int(active_count),
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
        self.interventions = InterventionRepository(session)
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
        stmt = select(Task).where(Task.id == task_id).with_for_update()
        task = (await self.session.execute(stmt)).scalar_one_or_none()
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
        agent_manager = get_agent_manager()
        for r in all_robots:
            live_agent = agent_manager.get(r.id) if agent_manager.started else None
            if live_agent is not None:
                view = _robot_to_live_eval_input(
                    r, live_agent, active_counts.get(r.id, 0)
                )
            else:
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

        # === 3) 计算 bids（P6.8：黑板查附近高置信度幸存者，触发 vision_boost）===
        # BUSINESS_RULES §1.3：仅 has_yolo=True 机器人且任务中心 200 m 内有
        # confidence ≥ 0.8 的 survivor 条目时，base_score × 1.5。本服务在 filter
        # 之后、solve 之前查一次黑板（per-task），与 BUSINESS_RULES §5.4「不能用缓存
        # 的旧数据」一致。
        nearby_survivor_count = len(
            get_blackboard().query_by_proximity(
                center=task_view.target_area.center_point,
                radius_m=VISION_PROXIMITY_RADIUS_M,
                type_filter="survivor",
                min_confidence=VISION_CONFIDENCE_THRESHOLD,
            )
        )
        bids_map: dict[tuple[UUID, UUID], BidBreakdown] = {
            (rv.id, task_view.id): compute_full_bid(
                rv, task_view, nearby_survivor_count=nearby_survivor_count
            )
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
        await self._sync_winner_agent(
            winner_robot_id=winner_robot_id,
            task=task,
            task_view=task_view,
        )
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
        await self._publish_task_status_changed(
            task=task,
            from_status="PENDING",
            to_status="ASSIGNED",
            assigned_robot_ids=[winner_robot_id],
        )

        return auction

    async def _sync_winner_agent(
        self,
        *,
        winner_robot_id: UUID,
        task: Task,
        task_view: TaskEvalInput,
    ) -> None:
        """Hand the committed assignment to the running mock RobotAgent."""
        manager = get_agent_manager()
        if not manager.started:
            return
        agent = manager.get(winner_robot_id)
        if agent is None:
            logger.warning(
                "dispatch_winner_agent_missing",
                extra={"robot_id": str(winner_robot_id), "task_id": str(task.id)},
            )
            return

        center = task_view.target_area.center_point
        try:
            agent.accept_assignment(
                task_id=task.id,
                target_position={
                    "lat": float(center.lat),
                    "lng": float(center.lng),
                    "altitude_m": None,
                },
            )
        except Exception:
            logger.exception(
                "dispatch_winner_agent_sync_failed",
                extra={"robot_id": str(winner_robot_id), "task_id": str(task.id)},
            )

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

    async def _publish_task_status_changed(
        self,
        *,
        task: Task,
        from_status: str,
        to_status: str,
        assigned_robot_ids: list[UUID],
    ) -> None:
        await self._publish(
            EVT_TASK_STATUS_CHANGED,
            {
                "task_id": str(task.id),
                "task_code": task.code,
                "from_status": from_status,
                "to_status": to_status,
                "assigned_robot_ids": [str(rid) for rid in assigned_robot_ids],
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

    # ---------- P5.5 查询接口 ----------

    async def list_auctions(
        self,
        *,
        task_id: UUID | None,
        algorithm: str | None,
        start_time: datetime | None,
        end_time: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Auction], int]:
        """GET /dispatch/auctions：分页查询拍卖会话列表。

        列表接口返回的每条 Auction **不带 bids**（前端展开详情时再单独拉，
        见 get_auction_with_bids）。
        """
        return await self.auctions.find_paginated(
            task_id=task_id,
            algorithm=algorithm,
            start_time=start_time,
            end_time=end_time,
            page=page,
            page_size=page_size,
        )

    async def get_auction_with_bids(
        self, auction_id: UUID
    ) -> tuple[Auction, list[Bid]]:
        """GET /dispatch/auctions/{id}：含 bids 详情。

        404_AUCTION_NOT_FOUND_001 → auction_id 不存在；bids 按 bid_value DESC 排序。
        """
        auction = await self.auctions.find_by_id(auction_id)
        if auction is None:
            raise _auction_not_found(auction_id)
        bids = await self.bids.find_by_auction(auction_id)
        return auction, bids

    # ---------- P5.6 HITL 改派 ----------

    async def reassign_task(
        self,
        *,
        task_id: UUID,
        new_robot_id: UUID,
        user_id: UUID,
        reason: str,
    ) -> tuple[Task, UUID]:
        """POST /dispatch/reassign：HITL 改派任务到新机器人（BUSINESS_RULES §4.3.3）。

        7 步严格对照 §4.3.3 伪代码：
          1. 加锁（行级 FOR UPDATE on tasks，事务结束自动释放）
          2. 任务状态校验（仅 ASSIGNED / EXECUTING 可改派）
          3. 新机器人存在性 + RuleEngine.check（合并 robots/最新 state/active 计数）
          4. before_state（assigned_robot_ids 取自当前 active assignments；
             algorithm_used 取自 active assignment 关联的 auction.algorithm，
             无关联则用 'MANUAL_OVERRIDE'，与 after_state 区分）
          5. 释放原 active assignments（is_active=FALSE, released_at=NOW）+
             创建新 TaskAssignment(auction_id=NULL，人工指派标记)
          6. after_state（assigned_robot_ids=[new_robot_id], algorithm_used=
             'MANUAL_OVERRIDE'）
          7. 写 human_interventions(intervention_type='reassign')，同事务 commit
          8. commit 后 publish task.reassigned (commander) + intervention.recorded
             (admin)；publish 失败仅日志，不影响 HTTP 响应

        关键约束：
        - reason ≥5 非空白字符 → 422_INTERVENTION_REASON_INVALID_001
        - 任务不存在 → 404_TASK_NOT_FOUND_001
        - 任务非 ASSIGNED/EXECUTING → 409_TASK_STATUS_CONFLICT_001
        - 新机器人不存在 → 404_ROBOT_NOT_FOUND_001
        - 新机器人 RuleEngine 不合格 → 409_ROBOT_INELIGIBLE_001（含 fail_reason）

        注意：本服务不修改 task.status —— ASSIGNED→ASSIGNED / EXECUTING→EXECUTING
        都属于「同状态改派」，状态机只校验「from→to」转移；这里不调 transit
        （TASK_TRANSITIONS[ASSIGNED] 不含 ASSIGNED 自循环；EXECUTING 含
        EXECUTING 自循环但仅在「无缝切换」语义下使用，本任务保留状态字面不变
        即可）。

        返回 (task, intervention_id) 供 API 层组装 ReassignResponse。
        """
        _validate_reason(reason)

        # === 1) 加锁：FOR UPDATE on tasks 行，避免并发改派（pseudo-code §4.3.3 步 1）
        # session.get 不支持 FOR UPDATE，用 select(...).with_for_update()
        stmt = select(Task).where(Task.id == task_id).with_for_update()
        task = (await self.session.execute(stmt)).scalar_one_or_none()
        if task is None:
            raise _task_not_found(task_id)

        # === 2) 任务状态校验
        if task.status not in {"ASSIGNED", "EXECUTING"}:
            raise BusinessError(
                code="409_TASK_STATUS_CONFLICT_001",
                message=f"任务状态 {task.status} 不允许改派（仅 ASSIGNED/EXECUTING 可改派）",
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
                        "message": "ASSIGNED|EXECUTING",
                    },
                ],
            )

        # === 3) 新机器人存在 + RuleEngine 合格性
        new_robot = await self.robots.find_by_id(new_robot_id)
        if new_robot is None:
            raise BusinessError(
                code="404_ROBOT_NOT_FOUND_001",
                message="目标机器人不存在",
                http_status=404,
                details=[
                    {
                        "field": "new_robot_id",
                        "code": "not_found",
                        "message": str(new_robot_id),
                    }
                ],
            )

        latest_state = await self.robot_states.find_latest_by_robot(new_robot.id)
        active_counts = await self.assignments.count_active_by_robot_bulk(
            [new_robot.id]
        )
        new_view = _robot_to_eval_input(
            new_robot, latest_state, active_counts.get(new_robot.id, 0)
        )
        task_view = _task_to_eval_input(task)
        ok, fail_reason = self._engine.check(new_view, task_view)
        if not ok:
            raise BusinessError(
                code="409_ROBOT_INELIGIBLE_001",
                message=f"目标机器人不合格：{fail_reason}",
                http_status=409,
                details=[
                    {
                        "field": "new_robot_id",
                        "code": "rule_engine_reject",
                        "message": fail_reason,
                    }
                ],
            )

        # === 4) before_state（DATA_CONTRACTS §4.8）
        old_assignments = await self.assignments.find_by_task(
            task_id, only_active=True
        )
        # algorithm_used：取最近一条 active assignment 关联的 auction.algorithm；
        # 若无 active 或 auction_id=None（之前已是人工指派）→ MANUAL_OVERRIDE。
        algorithm_used = "MANUAL_OVERRIDE"
        for a in old_assignments:
            if a.auction_id is not None:
                auc = await self.auctions.find_by_id(a.auction_id)
                if auc is not None:
                    algorithm_used = str(auc.algorithm)
                    break

        before_robot_ids = [str(a.robot_id) for a in old_assignments]
        before_state: dict[str, Any] = {
            "task_id": str(task.id),
            "task_code": task.code,
            "assigned_robot_ids": before_robot_ids,
            "algorithm_used": algorithm_used,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # === 5) 释放原 active assignments + 创建新 TaskAssignment（auction_id=None）
        now = datetime.now(timezone.utc)
        await self.assignments.release_active_for_task(task_id, released_at=now)
        new_assignment = TaskAssignment(
            task_id=task.id,
            robot_id=new_robot.id,
            auction_id=None,  # 人工指派，无拍卖关联
            is_active=True,
        )
        await self.assignments.save(new_assignment)

        # === 6) after_state
        after_state: dict[str, Any] = {
            "task_id": str(task.id),
            "task_code": task.code,
            "assigned_robot_ids": [str(new_robot.id)],
            "algorithm_used": "MANUAL_OVERRIDE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # === 7) 写 human_interventions（同事务）
        intervention = HumanIntervention(
            user_id=user_id,
            intervention_type="reassign",
            target_task_id=task.id,
            target_robot_id=new_robot.id,
            before_state=before_state,
            after_state=after_state,
            reason=reason,
        )
        await self.interventions.save(intervention)

        await self.session.commit()
        await self.session.refresh(task)
        await self.session.refresh(intervention)

        # === 8) 事务外推送 WS 事件（commit 之后；publish 失败仅日志）
        # 同步 live Agent：HITL 改派与自动拍卖一样，需要把新 active assignment
        # 交给机器人协程，否则任务会停留在 DB 已改派、Agent 仍执行旧目标的割裂状态。
        await self._sync_winner_agent(
            winner_robot_id=new_robot.id,
            task=task,
            task_view=task_view,
        )

        # task.reassigned → commander：from_robot 取释放前第一条 active；多机协同时
        # 仍只挑一条便于前端展示，audit 完整链路看 intervention.before_state。
        from_robot_id: UUID | None = (
            old_assignments[0].robot_id if old_assignments else None
        )
        from_robot_code: str | None = None
        if from_robot_id is not None:
            from_robot = await self.robots.find_by_id(from_robot_id)
            from_robot_code = from_robot.code if from_robot is not None else None

        await self._publish(
            EVT_TASK_REASSIGNED,
            {
                "task_id": str(task.id),
                "task_code": task.code,
                "from_robot_id": str(from_robot_id) if from_robot_id else None,
                "from_robot_code": from_robot_code,
                "to_robot_id": str(new_robot.id),
                "to_robot_code": new_robot.code,
                "reassigned_by_user_id": str(user_id),
                "reason": reason,
                "intervention_id": str(intervention.id),
            },
        )
        # intervention.recorded → admin（WS_EVENTS §8 审计事件）
        await self._publish(
            EVT_INTERVENTION_RECORDED,
            {
                "intervention_id": str(intervention.id),
                "user_id": str(user_id),
                "intervention_type": "reassign",
                "target_task_id": str(task.id),
                "target_robot_id": str(new_robot.id),
                "reason": reason,
            },
        )

        return task, intervention.id

    # ---------- P5.5 HITL 算法切换 ----------

    async def switch_algorithm(
        self,
        new_algorithm: str,
        *,
        user_id: UUID,
        reason: str,
    ) -> tuple[str, str, UUID]:
        """POST /dispatch/algorithm：HITL 切换调度算法（BUSINESS_RULES §4.5）。

        流程：
          1. reason ≥5 字符且非纯空白 → 422_INTERVENTION_REASON_INVALID_001
          2. new_algorithm ∈ KNOWN_ALGORITHMS（schema 层 Literal 已挡，service 兜底）
          3. before_state = {algorithm: 旧}
          4. DispatchSettings.set_algorithm(new)（进程内全局立即生效；
             已 OPEN 的拍卖不受影响 — BUSINESS_RULES §4.5）
          5. after_state = {algorithm: 新}
          6. 写 human_interventions(intervention_type='algorithm_switch')，同事务
          7. commit
          8. publish dispatch.algorithm_changed（commander + admin 两房间）

        返回 (previous, current, intervention_id) 供 API 层组装响应。
        切换前后是同一算法名也允许（写 intervention 留痕，便于审计「谁尝试过切到
        相同名」），与 cancel_task 同款审计哲学。
        """
        _validate_reason(reason)

        if new_algorithm not in KNOWN_ALGORITHMS:
            raise BusinessError(
                code="422_VALIDATION_FAILED_001",
                message=f"未知算法 {new_algorithm}",
                http_status=422,
                details=[
                    {
                        "field": "algorithm",
                        "code": "unknown_algorithm",
                        "message": new_algorithm,
                    },
                    {
                        "field": "algorithm",
                        "code": "expected_one_of",
                        "message": ",".join(sorted(KNOWN_ALGORITHMS)),
                    },
                ],
            )

        settings = get_dispatch_settings()
        previous = settings.current_algorithm

        now_iso = datetime.now(timezone.utc).isoformat()
        before_state: dict[str, Any] = {"algorithm": previous, "timestamp": now_iso}

        # 4) 内存切换 — service 提交事务前把全局先改了；即便 commit 失败也能 rollback
        # 全局回写。但如果 commit 失败、外层 catch 后调 set_algorithm(previous) 即可。
        settings.set_algorithm(new_algorithm)

        try:
            after_state: dict[str, Any] = {
                "algorithm": new_algorithm,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            intervention = HumanIntervention(
                user_id=user_id,
                intervention_type="algorithm_switch",
                target_task_id=None,
                target_robot_id=None,
                before_state=before_state,
                after_state=after_state,
                reason=reason,
            )
            await self.interventions.save(intervention)
            await self.session.commit()
            await self.session.refresh(intervention)
        except Exception:
            # commit 失败 → 把全局算法切回原值，避免「内存改了但 DB 没记录」
            settings.set_algorithm(previous)
            await self.session.rollback()
            raise

        # 8) commit 成功后 publish；commander + admin 两房间
        await self._publish(
            EVT_DISPATCH_ALGORITHM_CHANGED,
            {
                "from_algorithm": previous,
                "to_algorithm": new_algorithm,
                "switched_by_user_id": str(user_id),
                "reason": reason,
                "intervention_id": str(intervention.id),
            },
        )

        return previous, new_algorithm, intervention.id
