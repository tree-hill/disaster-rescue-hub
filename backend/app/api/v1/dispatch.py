"""调度 REST 路由（P5.5）。

对照：
- API_SPEC §4（/dispatch/* 5 个接口；本任务实现 5 个；POST /dispatch/reassign
  属于 P5.6 HITL 改派，单独路由文件）。
- BUSINESS_RULES §1.4 / §1.5（拍卖闭环写库审计）+ §4.5（algorithm_switch HITL）。
- WS_EVENTS §5：auction.* 与 dispatch.algorithm_changed 在 service 层 publish，
  本路由不直接接 WS。

权限模型：
- POST /dispatch/auction：task:create（commander 触发拍卖）
- GET /dispatch/algorithm：task:read（指挥员 / 观察员都能查）
- POST /dispatch/algorithm：algorithm:switch（commander HITL）
- GET /dispatch/auctions[/{id}]：task:read
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.db.session import get_db
from app.dispatch.algorithms import KNOWN_ALGORITHMS
from app.repositories.bid import BidRepository
from app.schemas.auth import CurrentUser
from app.schemas.dispatch import (
    AlgorithmInfoResponse,
    AlgorithmSwitchRequest,
    AlgorithmSwitchResponse,
    AuctionRead,
    AuctionTriggerRequest,
    BidRead,
    ReassignRequest,
    ReassignResponse,
)
from app.schemas.pagination import Page
from app.schemas.task import TaskRead
from app.services.dispatch_service import DispatchService, get_dispatch_settings

router = APIRouter(prefix="/dispatch", tags=["dispatch"])


# ---------- 拍卖（POST /dispatch/auction） ----------


@router.post(
    "/auction",
    response_model=AuctionRead,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_auction(
    payload: AuctionTriggerRequest,
    _current: CurrentUser = Depends(require_permission("task:create")),
    db: AsyncSession = Depends(get_db),
) -> AuctionRead:
    """手动触发一次拍卖。对照 API_SPEC §4 POST /dispatch/auction。

    错误码：
    - 404_TASK_NOT_FOUND_001
    - 409_TASK_STATUS_CONFLICT_001（任务状态非 PENDING）

    成功副作用（同事务）：写 auctions + bids + task_assignments + 状态机
    PENDING→ASSIGNED；commit 后 commander 房间广播 auction.started →
    auction.bid_submitted×N → auction.completed（无 eligible 时仅 auction.failed）。

    响应包含 bids（同事务下已 flush 的全部出价记录），便于前端「触发即看到拍卖
    全貌」，与 GET /dispatch/auctions/{id} 字段一致。
    """
    svc = DispatchService(db)
    auction = await svc.start_auction(payload.task_id)
    # 取出本次拍卖的全部 bid（同事务 flush 后已可读；无 bid 时返回 []，例如
    # auction.failed 路径）。
    bids = await BidRepository(db).find_by_auction(auction.id)
    return _to_auction_read(auction, bids)


# ---------- 算法管理 ----------


@router.get("/algorithm", response_model=AlgorithmInfoResponse)
async def get_algorithm_info(
    _current: CurrentUser = Depends(require_permission("task:read")),
) -> AlgorithmInfoResponse:
    """GET /dispatch/algorithm：当前生效算法 + 可选清单。"""
    return AlgorithmInfoResponse(
        current=get_dispatch_settings().current_algorithm,  # type: ignore[arg-type]
        available=sorted(KNOWN_ALGORITHMS),  # type: ignore[arg-type]
    )


@router.post("/algorithm", response_model=AlgorithmSwitchResponse)
async def switch_algorithm(
    payload: AlgorithmSwitchRequest,
    current: CurrentUser = Depends(require_permission("algorithm:switch")),
    db: AsyncSession = Depends(get_db),
) -> AlgorithmSwitchResponse:
    """POST /dispatch/algorithm：HITL 切换全局调度算法。

    错误码：
    - 422_INTERVENTION_REASON_INVALID_001（reason < 5 非空白字符）
    - 422_VALIDATION_FAILED_001（algorithm 不在 KNOWN_ALGORITHMS；schema Literal
      已挡，service 层兜底）
    - 403_AUTH_PERMISSION_DENIED_001（缺 algorithm:switch）

    成功副作用：DispatchSettings 全局立即生效 + 同事务写 human_interventions +
    commit 后 commander + admin 两房间广播 dispatch.algorithm_changed。
    """
    svc = DispatchService(db)
    previous, current_algo, intervention_id = await svc.switch_algorithm(
        payload.algorithm,
        user_id=current.id,
        reason=payload.reason,
    )
    return AlgorithmSwitchResponse(
        previous=previous,  # type: ignore[arg-type]
        current=current_algo,  # type: ignore[arg-type]
        intervention_id=intervention_id,
    )


# ---------- 拍卖查询 ----------


@router.get("/auctions", response_model=Page[AuctionRead])
async def list_auctions(
    task_id: UUID | None = Query(None),
    algorithm: str | None = Query(
        None, description="AUCTION_HUNGARIAN / GREEDY / RANDOM 之一"
    ),
    start_time: datetime | None = Query(
        None, description="筛选 started_at >= start_time"
    ),
    end_time: datetime | None = Query(None, description="筛选 started_at <= end_time"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _current: CurrentUser = Depends(require_permission("task:read")),
    db: AsyncSession = Depends(get_db),
) -> Page[AuctionRead]:
    """GET /dispatch/auctions：分页查询拍卖会话历史。

    列表项不带 bids（详情页再单独拉，避免 N+1 输出）。
    """
    items, total = await DispatchService(db).list_auctions(
        task_id=task_id,
        algorithm=algorithm,
        start_time=start_time,
        end_time=end_time,
        page=page,
        page_size=page_size,
    )
    return Page[AuctionRead](
        items=[_to_auction_read(a, bids=None) for a in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/auctions/{auction_id}", response_model=AuctionRead)
async def get_auction(
    auction_id: UUID,
    _current: CurrentUser = Depends(require_permission("task:read")),
    db: AsyncSession = Depends(get_db),
) -> AuctionRead:
    """GET /dispatch/auctions/{id}：含全部出价（bid_value DESC 排序）。"""
    auction, bids = await DispatchService(db).get_auction_with_bids(auction_id)
    return _to_auction_read(auction, bids)


# ---------- HITL 改派（POST /dispatch/reassign，P5.6） ----------


@router.post(
    "/reassign",
    response_model=ReassignResponse,
    status_code=status.HTTP_200_OK,
)
async def reassign_task(
    payload: ReassignRequest,
    current: CurrentUser = Depends(require_permission("robot:reassign")),
    db: AsyncSession = Depends(get_db),
) -> ReassignResponse:
    """HITL 改派任务到新机器人。对照 API_SPEC §4 + BUSINESS_RULES §4.3.3。

    错误码：
    - 422_INTERVENTION_REASON_INVALID_001（reason < 5 非空白字符）
    - 404_TASK_NOT_FOUND_001
    - 404_ROBOT_NOT_FOUND_001
    - 409_TASK_STATUS_CONFLICT_001（任务非 ASSIGNED/EXECUTING）
    - 409_ROBOT_INELIGIBLE_001（新机器人 RuleEngine 不合格，details 含 fail_reason）
    - 403_AUTH_PERMISSION_DENIED_001（缺 robot:reassign）

    成功副作用（同事务）：FOR UPDATE 锁 task → 释放原 active assignment + 创建新
    TaskAssignment(auction_id=NULL) + 写 human_interventions(intervention_type=
    'reassign')；commit 后广播 task.reassigned (commander) + intervention.recorded
    (admin)。任务状态字面保持不变（ASSIGNED→ASSIGNED 或 EXECUTING→EXECUTING）。
    """
    task, intervention_id = await DispatchService(db).reassign_task(
        task_id=payload.task_id,
        new_robot_id=payload.new_robot_id,
        user_id=current.id,
        reason=payload.reason,
    )
    return ReassignResponse(
        task=TaskRead.model_validate(task),
        intervention_id=intervention_id,
    )


# ---------- 助手 ----------


def _to_auction_read(auction, bids) -> AuctionRead:
    """ORM Auction + list[Bid] → AuctionRead，bids=None 时返回空列表（列表接口）。"""
    base = AuctionRead.model_validate(auction)
    if bids is not None:
        base.bids = [BidRead.model_validate(b) for b in bids]
    return base
