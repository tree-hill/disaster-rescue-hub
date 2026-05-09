"""协同通信黑板（P6.1）。

对照：
- BUILD_ORDER §P6.1：内存 dict[str, BlackboardEntry] 主 + 异步写库（后台 task） +
  get/set/fuse/query/subscribe 方法
- DATA_CONTRACTS §1.13 / §4.9 / §4.10 / §5：blackboard_entries 表结构 + value/
  fused_from JSONB 形态
- BUSINESS_RULES INV-5：confidence < 0.5 写入静默拒绝；§7 阈值表：视觉数据 TTL 300s /
  告警 TTL 600s / 状态 TTL 30s（按 value.type 取默认值，调用方可显式覆盖）

设计边界：
- **进程级单例**（Blackboard + get_blackboard()），与 EventBus / AgentManager / dispatch
  PendingAuctionScanner 同款。
- **内存为主**：set() 立刻把最新值写进 _entries[key]，订阅者立刻收到回调。DB 写入
  通过 asyncio.create_task 异步发起（fire-and-forget），失败仅 logger.exception，不
  影响内存视图，符合「黑板可丢，最新数据优先」语义。
- **同 key 后写覆盖前写**：内存 dict 的语义；DB 不上唯一约束（DATA_CONTRACTS §1.13），
  保留全量历史用于审计。BlackboardRepository.find_latest_by_key 通过 updated_at DESC
  返回最新值。
- **fuse 仅落基础替换语义**：P6.2 信息融合会改写为 weighted_average + resolve_conflict。
  这里只保留 API 形状（key + 新值 + source + 旧 fused_from），并把新 source 追加到
  fused_from 末尾，避免 P6.2 时再改方法签名。
- **subscribe 用 await 串行**：subscriber 数量预期 ≤ 3（P6.3 push WS、P6.6 写告警等），
  全部是轻量异步 IO，串行调用即可；与 EventBus 的 fan-out 模型不同（这里是「黑板内部
  事件」，不需要再过一遍 bus）。
- **TTL 默认按 value.type 取**（BUSINESS_RULES §7）；显式 expires_at > ttl_sec > 默认值。
  默认表里没有的 type（含 None）→ TTL=None（永久），由 cleanup_expired 不动它。
- **haversine 复用 dispatch.rule_engine.haversine_km**：与 R7 / 距离分量同一份数学定义，
  避免重写。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from app.db.session import async_session_maker
from app.dispatch.rule_engine import haversine_km
from app.models.blackboard import BlackboardEntry as BlackboardEntryModel
from app.repositories.blackboard import BlackboardRepository
from app.schemas.blackboard import BlackboardValue
from app.schemas.common import Position

logger = logging.getLogger(__name__)

# BUSINESS_RULES INV-5：写入下限。
MIN_BLACKBOARD_CONFIDENCE = 0.5

# BUSINESS_RULES §7：默认 TTL（按 value.type 取；未在表中的 type → 永久）。
DEFAULT_TTL_SEC_BY_TYPE: dict[str, float] = {
    "survivor": 300.0,           # 视觉数据 5min
    "fire": 300.0,
    "smoke": 300.0,
    "collapsed_building": 300.0,
    "weather": 30.0,             # 状态数据 30s
    # custom 不给默认 TTL，调用方需显式传 ttl_sec / expires_at
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class BlackboardEntrySnapshot:
    """内存条目（也是 subscribe 回调入参）。

    字段与 ORM model + DATA_CONTRACTS §5 BlackboardEntryRead 一一对应。
    `db_id` 在 DB 写入完成后回填；落库失败时为 None（仍可被读，但无 DB 持久化）。
    `is_fused` 标识本条是 fuse 产出（P6.2 / P6.3 WS payload 用）。
    """

    key: str
    value: dict[str, Any]
    confidence: float
    source_robot_id: UUID | None
    fused_from: list[dict[str, Any]] = field(default_factory=list)
    expires_at: datetime | None = None
    updated_at: datetime = field(default_factory=_now_utc)
    created_at: datetime = field(default_factory=_now_utc)
    db_id: UUID | None = None
    is_fused: bool = False

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return self.expires_at <= (now or _now_utc())


# subscribe 回调签名：异步函数，入参为 snapshot。
BlackboardSubscriber = Callable[[BlackboardEntrySnapshot], Awaitable[None]]


# ---------- 单例容器 ----------


class Blackboard:
    """协同通信黑板服务（进程级单例）。

    使用方式（P6.1）：
        bb = get_blackboard()
        await bb.set(key="survivor:120.51_30.21", value={...}, confidence=0.92,
                     source_robot_id=uav_id)
        snap = bb.get("survivor:120.51_30.21")
        nearby = bb.query_by_proximity(center=Position(...), radius_m=200,
                                       type_filter="survivor", min_confidence=0.8)

    P6.2 / P6.3 / P6.6 后续会复用本接口（fuse 改实现 / push WS / 写告警）。
    """

    def __init__(self) -> None:
        self._entries: dict[str, BlackboardEntrySnapshot] = {}
        self._subscribers: list[BlackboardSubscriber] = []
        # 锁保护内存 dict + subscribers 列表的并发改写；读不加锁（dict 读原子）。
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        # asyncio.Lock 必须在 running loop 内创建；singleton 跨 pytest event loop 时
        # 第一次 await 会先拿不到 loop。延迟到 set/fuse/cleanup 入口创建。
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    # ---------- 写 ----------

    async def set(
        self,
        *,
        key: str,
        value: dict[str, Any] | BlackboardValue,
        confidence: float,
        source_robot_id: UUID | None = None,
        ttl_sec: float | None = None,
        expires_at: datetime | None = None,
        fused_from: list[dict[str, Any]] | None = None,
        is_fused: bool = False,
    ) -> BlackboardEntrySnapshot | None:
        """写入或覆盖一条黑板条目。

        confidence < 0.5（INV-5）→ 静默拒绝（logger.info），返回 None。
        其他失败（DB 异常）不影响内存写入，仅 logger.exception。
        """
        if confidence < MIN_BLACKBOARD_CONFIDENCE:
            logger.info(
                "blackboard_write_rejected_low_confidence",
                extra={"key": key, "confidence": confidence},
            )
            return None

        value_dict = _normalize_value(value)
        now = _now_utc()
        resolved_expires = _resolve_expires_at(
            value_dict=value_dict,
            ttl_sec=ttl_sec,
            expires_at=expires_at,
            now=now,
        )

        snap = BlackboardEntrySnapshot(
            key=key,
            value=value_dict,
            confidence=float(confidence),
            source_robot_id=source_robot_id,
            fused_from=list(fused_from or []),
            expires_at=resolved_expires,
            updated_at=now,
            created_at=now,
            is_fused=bool(is_fused),
        )

        async with self._get_lock():
            self._entries[key] = snap

        # 落库异步发起；不等其结果，与「内存主」语义一致。
        asyncio.create_task(self._persist_async(snap))

        # 通知订阅者（P6.3 / P6.6 接入）。
        await self._notify_subscribers(snap)

        return snap

    async def fuse(
        self,
        *,
        key: str,
        value: dict[str, Any] | BlackboardValue,
        confidence: float,
        source_robot_id: UUID | None = None,
        ttl_sec: float | None = None,
        expires_at: datetime | None = None,
    ) -> BlackboardEntrySnapshot | None:
        """融合写入（P6.1 仅落基础替换语义；P6.2 改 weighted_average + resolve_conflict）。

        当前实现：
        - 若 key 不存在 → 等价 set()，fused_from=[新 source]
        - 若 key 已存在 → 复制旧 fused_from + 追加新 source；新值直接覆盖（P6.2 会改成
          按 confidence 加权平均）。

        签名与 set 兼容；P6.2 不改方法签名。
        """
        if confidence < MIN_BLACKBOARD_CONFIDENCE:
            logger.info(
                "blackboard_fuse_rejected_low_confidence",
                extra={"key": key, "confidence": confidence},
            )
            return None

        existing = self._entries.get(key)
        new_source = {
            "robot_id": str(source_robot_id) if source_robot_id else None,
            "confidence": float(confidence),
            "timestamp": _now_utc().isoformat(),
            "weight": 1.0,  # P6.2 改为加权
        }
        if existing is None or existing.is_expired():
            merged_fused_from: list[dict[str, Any]] = [new_source]
        else:
            merged_fused_from = list(existing.fused_from) + [new_source]

        return await self.set(
            key=key,
            value=value,
            confidence=confidence,
            source_robot_id=source_robot_id,
            ttl_sec=ttl_sec,
            expires_at=expires_at,
            fused_from=merged_fused_from,
            is_fused=True,
        )

    async def _persist_async(self, snap: BlackboardEntrySnapshot) -> None:
        """fire-and-forget DB 写入。失败仅 exception 日志，不影响内存视图。"""
        try:
            async with async_session_maker() as session:
                model = BlackboardEntryModel(
                    key=snap.key,
                    value=snap.value,
                    confidence=snap.confidence,
                    source_robot_id=snap.source_robot_id,
                    fused_from=snap.fused_from,
                    expires_at=snap.expires_at,
                )
                saved = await BlackboardRepository(session).save(model)
                await session.commit()
                snap.db_id = saved.id
        except Exception:
            logger.exception(
                "blackboard_persist_failed",
                extra={"key": snap.key},
            )

    # ---------- 读 ----------

    def get(self, key: str, *, include_expired: bool = False) -> BlackboardEntrySnapshot | None:
        """按 key 精确查（仅内存）。过期条目默认隐藏。"""
        snap = self._entries.get(key)
        if snap is None:
            return None
        if not include_expired and snap.is_expired():
            return None
        return snap

    def query(
        self,
        *,
        type_filter: str | None = None,
        key_prefix: str | None = None,
        min_confidence: float = MIN_BLACKBOARD_CONFIDENCE,
        include_expired: bool = False,
    ) -> list[BlackboardEntrySnapshot]:
        """内存层条件查询（updated_at DESC）。

        过滤维度对齐 API_SPEC §5 GET /blackboard/entries。P6.3 REST 在此基础上加分页。
        """
        now = _now_utc()
        items: list[BlackboardEntrySnapshot] = []
        for snap in self._entries.values():
            if not include_expired and snap.is_expired(now=now):
                continue
            if snap.confidence < min_confidence:
                continue
            if type_filter is not None and snap.value.get("type") != type_filter:
                continue
            if key_prefix is not None and not snap.key.startswith(key_prefix):
                continue
            items.append(snap)
        items.sort(key=lambda s: s.updated_at, reverse=True)
        return items

    def query_by_proximity(
        self,
        *,
        center: Position,
        radius_m: float,
        type_filter: str | None = None,
        min_confidence: float = MIN_BLACKBOARD_CONFIDENCE,
        include_expired: bool = False,
    ) -> list[BlackboardEntrySnapshot]:
        """按距离查询（用于 BUSINESS_RULES §1.3 vision_boost：拍卖时调）。

        距离用 haversine 球面距离（与 R7 / 距离分量同源）。无 position 字段的条目
        被跳过。返回列表按距离升序。
        """
        now = _now_utc()
        radius_km = float(radius_m) / 1000.0
        scored: list[tuple[float, BlackboardEntrySnapshot]] = []
        for snap in self._entries.values():
            if not include_expired and snap.is_expired(now=now):
                continue
            if snap.confidence < min_confidence:
                continue
            if type_filter is not None and snap.value.get("type") != type_filter:
                continue
            pos = snap.value.get("position")
            if not isinstance(pos, dict):
                continue
            try:
                dist_km = haversine_km(center.lat, center.lng, float(pos["lat"]), float(pos["lng"]))
            except (KeyError, TypeError, ValueError):
                continue
            if dist_km <= radius_km:
                scored.append((dist_km, snap))
        scored.sort(key=lambda kv: kv[0])
        return [snap for _, snap in scored]

    # ---------- 订阅 / 清理 ----------

    def subscribe(self, callback: BlackboardSubscriber) -> None:
        """注册写入/融合回调（去重）。P6.3 在此挂 push_event('blackboard.updated', ...)。"""
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: BlackboardSubscriber) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def _notify_subscribers(self, snap: BlackboardEntrySnapshot) -> None:
        for cb in list(self._subscribers):
            try:
                await cb(snap)
            except Exception:
                logger.exception(
                    "blackboard_subscriber_failed",
                    extra={"key": snap.key, "callback": getattr(cb, "__name__", repr(cb))},
                )

    async def cleanup_expired(self) -> tuple[int, int]:
        """清理过期条目：内存 + DB。返回 (内存清理数, DB 清理数)。

        BUILD_ORDER §P6.1：定时任务每分钟调一次（见 services/blackboard_cleanup.py）。
        DB 清理失败 → 仅日志，内存仍清掉（保持读视图最新）。
        """
        now = _now_utc()
        async with self._get_lock():
            expired_keys = [k for k, snap in self._entries.items() if snap.is_expired(now=now)]
            for k in expired_keys:
                self._entries.pop(k, None)

        db_deleted = 0
        try:
            async with async_session_maker() as session:
                db_deleted = await BlackboardRepository(session).delete_expired(now=now)
                await session.commit()
        except Exception:
            logger.exception("blackboard_cleanup_db_failed")

        if expired_keys or db_deleted:
            logger.info(
                "blackboard_cleanup_done",
                extra={"mem_deleted": len(expired_keys), "db_deleted": db_deleted},
            )
        return len(expired_keys), db_deleted

    # ---------- 测试辅助 ----------

    def reset_for_tests(self) -> None:
        """仅测试用：清空内存 + subscribers。DB 不动。"""
        self._entries.clear()
        self._subscribers.clear()


# ---------- 进程单例访问器 ----------


_blackboard_singleton: Blackboard | None = None


def get_blackboard() -> Blackboard:
    global _blackboard_singleton
    if _blackboard_singleton is None:
        _blackboard_singleton = Blackboard()
    return _blackboard_singleton


def reset_blackboard_for_tests() -> None:
    """仅测试用：清空单例（含订阅者），便于隔离用例。"""
    global _blackboard_singleton
    _blackboard_singleton = None


# ---------- 工具函数 ----------


def _normalize_value(value: dict[str, Any] | BlackboardValue) -> dict[str, Any]:
    """统一把 value 转成 dict（写库 / 内存共用）。

    BlackboardValue → model_dump(mode='json') 让 datetime / UUID 这类嵌套类型变为
    可被 JSONB 接受的 JSON-friendly 类型（P6.1 当前 schema 内层无此类字段，但保留鲁棒
    性：P6.2 / P6.6 自由扩展字段可能含 datetime）。
    """
    if isinstance(value, BlackboardValue):
        return value.model_dump(mode="json", exclude_none=False)
    # dict 走深拷贝，避免调用方后续修改影响内存条目。
    return deepcopy(dict(value))


def _resolve_expires_at(
    *,
    value_dict: dict[str, Any],
    ttl_sec: float | None,
    expires_at: datetime | None,
    now: datetime,
) -> datetime | None:
    """expires_at > ttl_sec > value.type 默认 TTL > None（永久）。"""
    if expires_at is not None:
        return expires_at
    if ttl_sec is not None:
        return now + timedelta(seconds=float(ttl_sec))
    type_key = value_dict.get("type")
    default_ttl = DEFAULT_TTL_SEC_BY_TYPE.get(type_key) if isinstance(type_key, str) else None
    if default_ttl is not None:
        return now + timedelta(seconds=default_ttl)
    return None
