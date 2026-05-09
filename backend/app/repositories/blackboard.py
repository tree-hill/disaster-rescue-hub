"""黑板条目数据访问层（P6.1）。

对照：
- BUILD_ORDER §P6.1：app/repositories/blackboard.py 数据库读写
- DATA_CONTRACTS §1.13：blackboard_entries 表（id / key / value / confidence /
  source_robot_id / fused_from / expires_at / updated_at / created_at）
- API_SPEC §5：GET /blackboard/entries 过滤维度（type / key_prefix / min_confidence /
  include_expired）—— P6.1 先落 find_active 接口，P6.3 在此之上加分页/排序

事务边界：与本项目其他 repo 一致 —— add+flush，commit / rollback 由调用方控制。
DELETE 操作（delete_expired）也只 execute，不 commit，由 cleanup scanner 持有的
独立 session 在调用后 commit。
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blackboard import BlackboardEntry


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class BlackboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, entry: BlackboardEntry) -> BlackboardEntry:
        """新增黑板条目（不在此 commit）。

        flush 后服务端默认值（id / created_at / updated_at）会被回填到 ORM 对象上，
        便于内存 Blackboard 同步「DB id」回写到内存条目。
        """
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def find_by_id(self, entry_id: UUID) -> BlackboardEntry | None:
        return await self.session.get(BlackboardEntry, entry_id)

    async def find_latest_by_key(
        self, key: str, *, include_expired: bool = False
    ) -> BlackboardEntry | None:
        """按 key 查最新的一条（updated_at DESC），可选过滤过期条目。

        与内存 Blackboard.get(key) 配合：内存 miss 时回查 DB。
        """
        stmt = select(BlackboardEntry).where(BlackboardEntry.key == key)
        if not include_expired:
            now = _now_utc()
            stmt = stmt.where(
                or_(
                    BlackboardEntry.expires_at.is_(None),
                    BlackboardEntry.expires_at > now,
                )
            )
        stmt = stmt.order_by(BlackboardEntry.updated_at.desc()).limit(1)
        return (await self.session.execute(stmt)).scalars().first()

    async def find_active(
        self,
        *,
        type_filter: str | None = None,
        key_prefix: str | None = None,
        min_confidence: float = 0.5,
        include_expired: bool = False,
    ) -> list[BlackboardEntry]:
        """列出符合条件的条目（updated_at DESC）。

        - type_filter：过滤 value->>'type'（用 JSONB ->> 操作符）
        - key_prefix：key LIKE prefix%
        - min_confidence：confidence >= 阈值（INV-5 默认 0.5）
        - include_expired=False：仅返回未过期或永久条目（expires_at IS NULL）

        P6.1 不分页（数据量少）；P6.3 REST 接口在外层加 page/page_size。
        """
        conds = [BlackboardEntry.confidence >= min_confidence]
        if type_filter is not None:
            conds.append(BlackboardEntry.value["type"].astext == type_filter)
        if key_prefix is not None:
            conds.append(BlackboardEntry.key.like(f"{key_prefix}%"))
        if not include_expired:
            now = _now_utc()
            conds.append(
                or_(
                    BlackboardEntry.expires_at.is_(None),
                    BlackboardEntry.expires_at > now,
                )
            )
        stmt = (
            select(BlackboardEntry)
            .where(and_(*conds))
            .order_by(BlackboardEntry.updated_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete_by_ids(self, ids: Sequence[UUID]) -> int:
        """按主键批量删除，返回删除行数。供 cleanup scanner 在 DB 写入失败回滚时使用。"""
        if not ids:
            return 0
        stmt = delete(BlackboardEntry).where(BlackboardEntry.id.in_(list(ids)))
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)

    async def delete_expired(self, *, now: datetime | None = None) -> int:
        """删除已过期条目（expires_at IS NOT NULL AND expires_at < now）。

        BUILD_ORDER §P6.1：定时任务每分钟清理过期条目。
        返回删除行数，便于 scanner 日志统计。
        """
        cutoff = now if now is not None else _now_utc()
        stmt = delete(BlackboardEntry).where(
            and_(
                BlackboardEntry.expires_at.is_not(None),
                BlackboardEntry.expires_at < cutoff,
            )
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)
