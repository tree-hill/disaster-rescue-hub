"""告警 REST 路由（P7.1）。

对照：
- API_SPEC §6
  - GET /alerts (severity / type / source / status / start_time / end_time / search / page / page_size)
  - GET /alerts/{id}
  - POST /alerts/{id}/acknowledge {note?}
  - POST /alerts/{id}/ignore {reason}
  - POST /alerts/batch-acknowledge {alert_ids[]}
- BUSINESS_RULES §6.7（404_ALERT_NOT_FOUND_001 / 409_ALERT_ALREADY_ACKED_001 / 409_ALERT_ALREADY_IGNORED_001）

权限模型：
- 全部 GET → alert:read
- POST acknowledge / ignore / batch-acknowledge → alert:handle

response_model 全部 AlertRead（DATA_CONTRACTS §5）。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.db.session import get_db
from app.repositories.alert import AlertRepository
from app.schemas.alert import (
    AlertBatchAcknowledgeRequest,
    AlertBatchAcknowledgeResponse,
    AlertIgnoreRequest,
    AlertNoteRequest,
    AlertRead,
)
from app.schemas.auth import CurrentUser
from app.schemas.pagination import Page
from app.services.alert_service import AlertService

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=Page[AlertRead])
async def list_alerts(
    severity: str | None = Query(None, description="info/warn/critical"),
    type: str | None = Query(None, description="alerts.type 精确匹配"),
    source: str | None = Query(None, description="alerts.source 精确匹配"),
    status: str | None = Query(None, description="unack/ack/ignored"),
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    search: str | None = Query(None, description="code/message/source 模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current: CurrentUser = Depends(require_permission("alert:read")),
) -> Page[AlertRead]:
    repo = AlertRepository(db)
    items, total = await repo.find_paginated(
        severity=severity,
        type_=type,
        source=source,
        status=status,
        start_time=start_time,
        end_time=end_time,
        search=search,
        page=page,
        page_size=page_size,
    )
    return Page[AlertRead](
        items=[AlertRead.model_validate(a) for a in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{alert_id}", response_model=AlertRead)
async def get_alert(
    alert_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current: CurrentUser = Depends(require_permission("alert:read")),
) -> AlertRead:
    alert = await AlertService(db).get(alert_id)
    return AlertRead.model_validate(alert)


@router.post("/batch-acknowledge", response_model=AlertBatchAcknowledgeResponse)
async def batch_acknowledge(
    request: AlertBatchAcknowledgeRequest,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("alert:handle")),
) -> AlertBatchAcknowledgeResponse:
    """批量确认；不存在 / 已 ack 的并入 failed 计数。"""
    acknowledged, failed = await AlertService(db).batch_acknowledge(
        request.alert_ids, user_id=current.id
    )
    return AlertBatchAcknowledgeResponse(acknowledged=acknowledged, failed=failed)


@router.post("/{alert_id}/acknowledge", response_model=AlertRead)
async def acknowledge_alert(
    alert_id: UUID,
    request: AlertNoteRequest,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("alert:handle")),
) -> AlertRead:
    alert = await AlertService(db).acknowledge(
        alert_id, user_id=current.id, note=request.note
    )
    return AlertRead.model_validate(alert)


@router.post("/{alert_id}/ignore", response_model=AlertRead)
async def ignore_alert(
    alert_id: UUID,
    request: AlertIgnoreRequest,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("alert:handle")),
) -> AlertRead:
    alert = await AlertService(db).ignore(
        alert_id, user_id=current.id, reason=request.reason
    )
    return AlertRead.model_validate(alert)
