"""场景 REST 路由（P8.4 补丁）。

供前端实验配置面板获取可用场景列表。
权限：replay:read（读权限，与复盘一致）。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.replay import Scenario

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


class ScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    disaster_type: str
    is_active: bool


@router.get("", response_model=list[ScenarioRead])
async def list_scenarios(
    session: AsyncSession = Depends(get_db),
    _: None = Depends(require_permission("replay:read")),
) -> list[Scenario]:
    """获取所有活跃场景（供实验配置面板使用）。"""
    result = await session.execute(select(Scenario).where(Scenario.is_active.is_(True)))
    return list(result.scalars().all())
