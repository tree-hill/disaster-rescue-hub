"""复盘服务（P8.1）。

对照：
- API_SPEC §7 GET /replay/sessions /sessions/{id} /sessions/{id}/snapshots /key-events
- BUSINESS_RULES §6.7（404_REPLAY_SESSION_NOT_FOUND_001 缺省）

权限：全部 GET 走 replay:read（路由层校验）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError
from app.models.replay import ReplaySession
from app.replay.timeline_player import filter_key_events, filter_snapshots
from app.repositories.replay import ReplaySessionRepository


class ReplayService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ReplaySessionRepository(db)

    async def list_paginated(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        algorithm: str | None = None,
        scenario_id: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ReplaySession], int]:
        return await self.repo.find_paginated(
            start_time=start_time,
            end_time=end_time,
            algorithm=algorithm,
            scenario_id=scenario_id,
            page=page,
            page_size=page_size,
        )

    async def get(self, session_id: UUID) -> ReplaySession:
        obj = await self.repo.find_by_id(session_id)
        if obj is None:
            raise BusinessError(
                code="404_REPLAY_SESSION_NOT_FOUND_001",
                message=f"复盘会话不存在：{session_id}",
                http_status=404,
            )
        return obj

    async def get_snapshots(
        self,
        session_id: UUID,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        interval_sec: float = 1.0,
    ) -> list[dict[str, Any]]:
        obj = await self.get(session_id)
        snaps = list((obj.summary or {}).get("snapshots", []) or [])
        return filter_snapshots(
            snaps,
            start_time=start_time,
            end_time=end_time,
            interval_sec=interval_sec,
        )

    async def get_key_events(
        self,
        session_id: UUID,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        obj = await self.get(session_id)
        evs = list((obj.summary or {}).get("key_events", []) or [])
        return filter_key_events(evs, start_time=start_time, end_time=end_time)
