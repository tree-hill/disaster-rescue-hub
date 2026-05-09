"""态势感知 REST 路由（P7.1）。

对照：
- API_SPEC §6 GET /situation/kpi
- BUSINESS_RULES §6.7 通用错误码（缺权限 → 403_AUTH_PERMISSION_DENIED_001）

权限：alert:read（与 GET /alerts 同级）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_permission
from app.schemas.auth import CurrentUser
from app.schemas.situation import KPISnapshot
from app.situation.kpi_aggregator import get_kpi_aggregator

router = APIRouter(prefix="/situation", tags=["situation"])


@router.get("/kpi", response_model=KPISnapshot)
async def get_kpi(
    _current: CurrentUser = Depends(require_permission("alert:read")),
) -> KPISnapshot:
    """获取实时 KPI 快照（缓存优先；缓存为空 → 同步聚合一次）。"""
    return await get_kpi_aggregator().get_or_refresh()
