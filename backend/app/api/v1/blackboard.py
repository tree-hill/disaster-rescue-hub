"""黑板 REST 路由（P6.3）。

对照：
- API_SPEC §5：
  - GET /blackboard/entries（type / key_prefix / min_confidence / include_expired / page / page_size）
  - GET /blackboard/entries/{key}（404 不存在或已过期）
  - GET /blackboard/stats
- DATA_CONTRACTS §5（BlackboardEntryRead / BlackboardStats）

权限模型（seed.py 已扩 commander/admin/observer 三角色）：
- 全部 GET → blackboard:read

数据源：
- /entries / /entries/{key} 走**内存** Blackboard.query / get（live state，单进程下与 WS
  blackboard.updated 推送严格一致）；DB 全量历史留给后续审计接口（不在 P6.3 范围）。
- /stats 调 Blackboard.stats()（throughput_per_min 60s 滑窗 + 平均 fuse 延迟 + 订阅者数）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import require_permission
from app.communication.blackboard import get_blackboard
from app.core.exceptions import BusinessError
from app.schemas.auth import CurrentUser
from app.schemas.blackboard import BlackboardEntryRead, BlackboardStats
from app.schemas.pagination import Page

router = APIRouter(prefix="/blackboard", tags=["blackboard"])


def _snapshot_to_read(snap) -> BlackboardEntryRead:
    """BlackboardEntrySnapshot → BlackboardEntryRead；id 走 db_id（落库前可能为 None）。"""
    return BlackboardEntryRead(
        id=snap.db_id,
        key=snap.key,
        value=snap.value,
        confidence=snap.confidence,
        source_robot_id=snap.source_robot_id,
        fused_from=snap.fused_from,
        expires_at=snap.expires_at,
        updated_at=snap.updated_at,
    )


@router.get("/entries", response_model=Page[BlackboardEntryRead])
async def list_entries(
    type: str | None = Query(
        None, description="value.type 精确匹配（survivor/fire/smoke/...）"
    ),
    key_prefix: str | None = Query(None, description="key 前缀匹配"),
    min_confidence: float = Query(0.5, ge=0.0, le=1.0, description="confidence 下限"),
    include_expired: bool = Query(False, description="是否含过期条目"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _current: CurrentUser = Depends(require_permission("blackboard:read")),
) -> Page[BlackboardEntryRead]:
    """列表（内存 live state，按 updated_at DESC）。"""
    snapshots = get_blackboard().query(
        type_filter=type,
        key_prefix=key_prefix,
        min_confidence=min_confidence,
        include_expired=include_expired,
    )
    total = len(snapshots)
    start = (page - 1) * page_size
    page_items = snapshots[start : start + page_size]
    return Page[BlackboardEntryRead](
        items=[_snapshot_to_read(s) for s in page_items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/entries/{key:path}", response_model=BlackboardEntryRead)
async def get_entry(
    key: str,
    include_expired: bool = Query(False),
    _current: CurrentUser = Depends(require_permission("blackboard:read")),
) -> BlackboardEntryRead:
    """按 key 精确查询。404 = 不存在或已过期（include_expired=False 时）。"""
    snap = get_blackboard().get(key, include_expired=include_expired)
    if snap is None:
        raise BusinessError(
            code="404_BLACKBOARD_KEY_NOT_FOUND_001",
            message=f"黑板条目 '{key}' 不存在或已过期",
            http_status=404,
        )
    return _snapshot_to_read(snap)


@router.get("/stats", response_model=BlackboardStats)
async def get_stats(
    _current: CurrentUser = Depends(require_permission("blackboard:read")),
) -> BlackboardStats:
    """运行时统计。throughput_per_min 走 60s 滑窗。"""
    return BlackboardStats(**get_blackboard().stats())
