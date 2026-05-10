"""复盘 REST 路由（P8.1）。

对照 API_SPEC §7：
- GET /replay/sessions
- GET /replay/sessions/{id}
- GET /replay/sessions/{id}/snapshots
- GET /replay/sessions/{id}/key-events

权限：全部 replay:read。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.pagination import Page
from app.schemas.replay import ReplaySessionRead
from app.services.replay_service import ReplayService

router = APIRouter(prefix="/replay", tags=["replay"])


@router.get("/sessions", response_model=Page[ReplaySessionRead])
async def list_sessions(
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    algorithm: str | None = Query(None),
    scenario_id: UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current: CurrentUser = Depends(require_permission("replay:read")),
) -> Page[ReplaySessionRead]:
    items, total = await ReplayService(db).list_paginated(
        start_time=start_time,
        end_time=end_time,
        algorithm=algorithm,
        scenario_id=scenario_id,
        page=page,
        page_size=page_size,
    )
    return Page[ReplaySessionRead](
        items=[ReplaySessionRead.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/sessions/{session_id}", response_model=ReplaySessionRead)
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current: CurrentUser = Depends(require_permission("replay:read")),
) -> ReplaySessionRead:
    obj = await ReplayService(db).get(session_id)
    return ReplaySessionRead.model_validate(obj)


@router.get("/sessions/{session_id}/snapshots")
async def get_snapshots(
    session_id: UUID,
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    interval_sec: float = Query(1.0, ge=0.1, le=600.0),
    db: AsyncSession = Depends(get_db),
    _current: CurrentUser = Depends(require_permission("replay:read")),
) -> list[dict[str, Any]]:
    return await ReplayService(db).get_snapshots(
        session_id,
        start_time=start_time,
        end_time=end_time,
        interval_sec=interval_sec,
    )


@router.get("/sessions/{session_id}/key-events")
async def get_key_events(
    session_id: UUID,
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _current: CurrentUser = Depends(require_permission("replay:read")),
) -> list[dict[str, Any]]:
    return await ReplayService(db).get_key_events(
        session_id, start_time=start_time, end_time=end_time
    )
