"""Alert 数据访问层（P7.1）。

对照 DATA_CONTRACTS §1.14（alerts 表）+ API_SPEC §6（GET /alerts 过滤参数）。

事务边界：本仓库只 add + flush，不 commit / rollback；事务由调用方
（service / alert_engine 后台协程）控制，与 RobotRepository / TaskRepository 一致。

排序：raised_at DESC（与 idx_alerts_unack / idx_alerts_severity 一致，最新告警靠前）。

code 生成策略：
- 业务编码 `ALERT-YYYY-NNN`（DATA_CONTRACTS §1.14 字面 'ALERT-2024-018' 风格）
- AlertEngine 在写库前先按当年 max(code) + 1 算 NNN；并发由 alerts.code UNIQUE
  约束兜底 + IntegrityError 重试 3 次。这套思路与 task_service 的 task code 同款。
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import Integer, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert


class AlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, alert: Alert) -> Alert:
        """新增或附加；不在此 commit，调用方控制事务边界。"""
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def find_by_id(self, alert_id: UUID) -> Alert | None:
        return await self.session.get(Alert, alert_id)

    async def find_by_ids(self, alert_ids: Sequence[UUID]) -> list[Alert]:
        ids = list(alert_ids)
        if not ids:
            return []
        stmt = select(Alert).where(Alert.id.in_(ids))
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_active(self) -> int:
        """KPI: 未确认且未忽略的告警数（与 idx_alerts_unack 部分索引对齐）。"""
        stmt = select(func.count()).select_from(Alert).where(
            Alert.acknowledged_at.is_(None),
            Alert.is_ignored.is_(False),
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def max_year_seq(self, year: int) -> int:
        """返回当年 alerts.code 'ALERT-YYYY-NNN' 中已出现的最大 NNN（无则 0）。

        实现：按前缀 'ALERT-{year:04d}-' 过滤，substr 取后段并 cast int 求 max。
        与 task code 思路一致；并发兜底是 alerts.code UNIQUE。
        """
        prefix = f"ALERT-{year:04d}-"
        stmt = select(
            func.max(func.cast(func.substr(Alert.code, len(prefix) + 1), Integer))
        ).where(Alert.code.like(f"{prefix}%"))
        val = (await self.session.execute(stmt)).scalar_one_or_none()
        return int(val or 0)

    async def find_paginated(
        self,
        *,
        severity: str | None = None,
        type_: str | None = None,
        source: str | None = None,
        status: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Alert], int]:
        """分页查询，支持 severity / type / source / status / 时间窗 / 模糊搜索。

        - status: unack / ack / ignored；其他值视为不过滤
        - search: 对 code / message / source 做 ILIKE '%search%'
        - 排序：critical > warn > info（severity 桶）+ raised_at DESC
        """
        filters = []
        if severity is not None:
            filters.append(Alert.severity == severity)
        if type_ is not None:
            filters.append(Alert.type == type_)
        if source is not None:
            filters.append(Alert.source == source)
        if status == "unack":
            filters.append(Alert.acknowledged_at.is_(None))
            filters.append(Alert.is_ignored.is_(False))
        elif status == "ack":
            filters.append(Alert.acknowledged_at.is_not(None))
        elif status == "ignored":
            filters.append(Alert.is_ignored.is_(True))
        if start_time is not None:
            filters.append(Alert.raised_at >= start_time)
        if end_time is not None:
            filters.append(Alert.raised_at <= end_time)
        if search:
            pattern = f"%{search}%"
            filters.append(
                or_(
                    Alert.code.ilike(pattern),
                    Alert.message.ilike(pattern),
                    Alert.source.ilike(pattern),
                )
            )

        count_stmt = select(func.count()).select_from(Alert)
        for f in filters:
            count_stmt = count_stmt.where(f)
        total = int((await self.session.execute(count_stmt)).scalar_one())

        severity_rank = case(
            (Alert.severity == "critical", 0),
            (Alert.severity == "warn", 1),
            else_=2,
        )
        stmt = select(Alert)
        for f in filters:
            stmt = stmt.where(f)
        stmt = (
            stmt.order_by(severity_rank.asc(), Alert.raised_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await self.session.execute(stmt)).scalars().all())
        return items, total
