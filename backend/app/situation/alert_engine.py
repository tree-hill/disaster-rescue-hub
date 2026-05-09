"""告警规则引擎（P7.1）。

对照：
- BUILD_ORDER §P7.1：「12 条预置规则(电量低 / 任务超时 / YOLO 高置信度 / 故障 / ...)」
- DATA_CONTRACTS §1.14（alerts 表）+ §4.11（payload 载荷形态）
- WS_EVENTS §7（alert.raised 字段）

12 条规则（订阅 EventBus 事件 + 后台 overdue 扫描）：

| # | rule_key | 触发事件 / 条件 | type | severity |
|---|---|---|---|---|
| 1 | fire_detected | perception.high_confidence_alert (class=fire, conf≥0.7) | fire_detected | critical |
| 2 | survivor_high_confidence | perception.high_confidence_alert (class=survivor, conf≥0.8) | survivor_detected | warn |
| 3 | low_battery | robot.fault_occurred (fault_type=low_battery) | low_battery | critical |
| 4 | comm_lost | robot.fault_occurred (fault_type=comm_lost) | comm_lost | critical |
| 5 | sensor_error | robot.fault_occurred (fault_type=sensor_error) | sensor_error | warn |
| 6 | task_overdue | OverdueScanner: sla_deadline < now AND status NOT IN terminal | task_overdue | warn |
| 7 | auction_failed | auction.failed | auction_failed | warn |
| 8 | high_decision_latency | auction.completed (decision_latency_ms > 5000) | high_decision_latency | warn |
| 9 | algorithm_switched | dispatch.algorithm_changed | algorithm_switched | info |
| 10 | task_reassigned | task.reassigned | task_reassigned | info |
| 11 | task_cancelled | task.cancelled | task_cancelled | info |
| 12 | hitl_intervention | intervention.recorded | hitl_intervention | info |

设计要点：
- **bus 订阅 + 自有 session**：每个 handler 打开新 session 写库；commit 后再
  publish("alert.raised") 经 ws/event_bridge 转推 commander/admin。
- **去重**：task_overdue 在最近 10 分钟内每个 task 仅触发一次（用进程内 set + 时间戳
  滑窗）；其余规则按事件 fire-and-forget，重复事件 → 重复告警是预期（指挥员需要看到
  连续告警）。
- **code 生成**：ALERT-YYYY-NNN，按当年 max+1；UNIQUE 兜底重试 3 次。
- **OverdueScanner**：单独后台协程，与 BlackboardCleanupScanner 同款生命周期。

配置：
- `alert_overdue_scan_interval_sec`：0 禁用；默认 60s。
- `alert_overdue_dedup_window_sec`：默认 600s（10 min），避免每分钟重复告警同一任务。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core.event_bus import EventBus, get_event_bus
from app.db.session import async_session_maker
from app.models.alert import Alert
from app.models.task import Task
from app.repositories.alert import AlertRepository
from app.schemas.alert import AlertSeverity

# advisory lock 命名空间（与 task_service._CODE_LOCK_NAMESPACE 不同 ns，错开）
_ALERT_CODE_LOCK_NAMESPACE = 0x7A5C_0002

logger = logging.getLogger(__name__)


# ============== 规则元数据（rule_key → type / severity） ==============

class _RuleMeta:
    __slots__ = ("type", "severity")

    def __init__(self, type_: str, severity: AlertSeverity) -> None:
        self.type = type_
        self.severity = severity


RULES: dict[str, _RuleMeta] = {
    "fire_detected": _RuleMeta("fire_detected", "critical"),
    "survivor_high_confidence": _RuleMeta("survivor_detected", "warn"),
    "low_battery": _RuleMeta("low_battery", "critical"),
    "comm_lost": _RuleMeta("comm_lost", "critical"),
    "sensor_error": _RuleMeta("sensor_error", "warn"),
    "task_overdue": _RuleMeta("task_overdue", "warn"),
    "auction_failed": _RuleMeta("auction_failed", "warn"),
    "high_decision_latency": _RuleMeta("high_decision_latency", "warn"),
    "algorithm_switched": _RuleMeta("algorithm_switched", "info"),
    "task_reassigned": _RuleMeta("task_reassigned", "info"),
    "task_cancelled": _RuleMeta("task_cancelled", "info"),
    "hitl_intervention": _RuleMeta("hitl_intervention", "info"),
}


HIGH_DECISION_LATENCY_MS = 5000  # INV-7（DATA_CONTRACTS）


# ============== 写库 + publish 公共流程 ==============


async def _create_alert_and_publish(
    *,
    rule_key: str,
    source: str,
    message: str,
    payload: dict[str, Any] | None = None,
    related_task_id: UUID | None = None,
    related_robot_id: UUID | None = None,
) -> UUID | None:
    """开新 session 写 alerts 表 → commit → publish alert.raised。

    code = ALERT-YYYY-NNN，并发竞态由 alerts.code UNIQUE 兜底，最多重试 3 次。
    返回新 alert.id；写失败返回 None。
    """
    meta = RULES.get(rule_key)
    if meta is None:
        logger.warning("alert_engine_unknown_rule", extra={"rule_key": rule_key})
        return None

    year = datetime.now(timezone.utc).year
    last_exc: Exception | None = None
    # 第一次尝试带 FK；若 FK 校验失败（关联实体已删除 / 测试用临时 UUID）则
    # null 化重试，alert 至少能落库 + 推送出去，关联信息留在 payload 里供前端展示。
    use_fks = (related_task_id, related_robot_id)
    for attempt in range(3):
        try:
            async with async_session_maker() as session:
                # 同 task_service 风格：pg_advisory_xact_lock 串行化同年 max+1 分配，
                # 锁随事务释放；与 alerts.code UNIQUE 约束 + 重试三次双保险，避免高并发
                # AlertEngine handlers 同时写库时撞 code。
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(:ns, :y)"),
                    {"ns": _ALERT_CODE_LOCK_NAMESPACE, "y": year},
                )
                repo = AlertRepository(session)
                seq = await repo.max_year_seq(year) + 1
                code = f"ALERT-{year:04d}-{seq:03d}"
                cur_task_fk, cur_robot_fk = use_fks
                alert = Alert(
                    code=code,
                    type=meta.type,
                    severity=meta.severity,
                    source=source,
                    message=message,
                    payload=payload or {},
                    related_task_id=cur_task_fk,
                    related_robot_id=cur_robot_fk,
                )
                await repo.save(alert)
                await session.commit()
                await session.refresh(alert)
                alert_id = alert.id
                # publish 到 EventBus（bridge 转推到 commander+admin）
                try:
                    await get_event_bus().publish(
                        "alert.raised",
                        {
                            "alert_id": str(alert.id),
                            "alert_code": alert.code,
                            "severity": alert.severity,
                            "type": alert.type,
                            "source": alert.source,
                            "message": alert.message,
                            "related_task_id": (
                                str(alert.related_task_id)
                                if alert.related_task_id
                                else None
                            ),
                            "related_robot_id": (
                                str(alert.related_robot_id)
                                if alert.related_robot_id
                                else None
                            ),
                            "payload": dict(alert.payload or {}),
                        },
                    )
                except Exception:
                    logger.exception(
                        "alert_raised_publish_failed",
                        extra={"alert_id": str(alert_id)},
                    )
                return alert_id
        except IntegrityError as exc:
            last_exc = exc
            msg = str(exc)
            # FK 失败 → null 化重试一次（关联实体已删除或测试临时 UUID）
            if "foreign key constraint" in msg.lower() and use_fks != (None, None):
                logger.info(
                    "alert_engine_fk_violation_fallback_null",
                    extra={"rule_key": rule_key, "fks": str(use_fks)},
                )
                use_fks = (None, None)
                continue
            # 其他 IntegrityError（典型：code UNIQUE 撞了）→ 重试
            logger.warning(
                "alert_engine_integrity_retry",
                extra={"rule_key": rule_key, "attempt": attempt},
            )
            continue
        except Exception as exc:
            logger.exception(
                "alert_engine_create_failed",
                extra={"rule_key": rule_key, "source": source, "exception": str(exc)},
            )
            return None
    logger.error(
        "alert_engine_create_retries_exhausted",
        extra={"rule_key": rule_key, "exception": str(last_exc)},
    )
    return None


# ============== EventBus handlers ==============


def _to_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


async def _on_perception_high_confidence(payload: dict[str, Any]) -> None:
    cls = str(payload.get("class_name", ""))
    conf = float(payload.get("confidence", 0.0))
    pos = payload.get("position") or {}
    src = str(payload.get("source_robot_code", "unknown"))
    auto_task_triggered = bool(payload.get("auto_task_triggered", False))
    task_id = _to_uuid(payload.get("task_id"))
    yolo_payload = {
        "yolo_detection": {
            "class_name": cls,
            "confidence": conf,
            "source_robot": src,
            "position": pos,
        },
        "auto_task_triggered": auto_task_triggered,
    }
    if cls == "fire" and conf >= 0.7:
        await _create_alert_and_publish(
            rule_key="fire_detected",
            source=src,
            message=f"检测到火点（置信度 {conf:.2f}）",
            payload=yolo_payload,
            related_task_id=task_id,
        )
    elif cls == "survivor" and conf >= 0.8:
        await _create_alert_and_publish(
            rule_key="survivor_high_confidence",
            source=src,
            message=f"高置信度幸存者（置信度 {conf:.2f}）",
            payload=yolo_payload,
            related_task_id=task_id,
        )


async def _on_robot_fault(payload: dict[str, Any]) -> None:
    fault_type = str(payload.get("fault_type", ""))
    rule_key = {
        "low_battery": "low_battery",
        "comm_lost": "comm_lost",
        "sensor_error": "sensor_error",
    }.get(fault_type)
    if rule_key is None:
        return  # unknown / 注入故障 → P7.1 规则集不打告警
    await _create_alert_and_publish(
        rule_key=rule_key,
        source=str(payload.get("robot_code", "unknown")),
        message=str(payload.get("message", f"机器人故障 {fault_type}")),
        payload={"fault_id": payload.get("fault_id"), "fault_type": fault_type},
        related_robot_id=_to_uuid(payload.get("robot_id")),
    )


async def _on_auction_failed(payload: dict[str, Any]) -> None:
    await _create_alert_and_publish(
        rule_key="auction_failed",
        source=str(payload.get("task_code") or payload.get("auction_id") or "auction"),
        message=str(payload.get("reason", "拍卖失败")),
        payload={
            "auction_id": payload.get("auction_id"),
            "reason": payload.get("reason"),
        },
        related_task_id=_to_uuid(payload.get("task_id")),
    )


async def _on_auction_completed(payload: dict[str, Any]) -> None:
    latency_ms = int(payload.get("decision_latency_ms") or 0)
    if latency_ms <= HIGH_DECISION_LATENCY_MS:
        return
    await _create_alert_and_publish(
        rule_key="high_decision_latency",
        source=str(payload.get("auction_id") or "auction"),
        message=f"决策延迟 {latency_ms} ms 超过阈值 {HIGH_DECISION_LATENCY_MS} ms",
        payload={
            "auction_id": payload.get("auction_id"),
            "decision_latency_ms": latency_ms,
            "algorithm": payload.get("algorithm"),
        },
        related_task_id=_to_uuid(payload.get("task_id")),
    )


async def _on_algorithm_changed(payload: dict[str, Any]) -> None:
    await _create_alert_and_publish(
        rule_key="algorithm_switched",
        source=str(payload.get("changed_by_user_id") or "system"),
        message=f"调度算法切换：{payload.get('from')} → {payload.get('to')}",
        payload=dict(payload),
    )


async def _on_task_reassigned(payload: dict[str, Any]) -> None:
    await _create_alert_and_publish(
        rule_key="task_reassigned",
        source=str(payload.get("task_code") or payload.get("task_id") or "task"),
        message=(
            f"任务改派：{payload.get('from_robot_code')} → "
            f"{payload.get('to_robot_code')}"
        ),
        payload=dict(payload),
        related_task_id=_to_uuid(payload.get("task_id")),
    )


async def _on_task_cancelled(payload: dict[str, Any]) -> None:
    await _create_alert_and_publish(
        rule_key="task_cancelled",
        source=str(payload.get("task_code") or "task"),
        message=str(payload.get("reason", "任务被取消")),
        payload=dict(payload),
        related_task_id=_to_uuid(payload.get("task_id")),
    )


async def _on_intervention_recorded(payload: dict[str, Any]) -> None:
    await _create_alert_and_publish(
        rule_key="hitl_intervention",
        source=str(payload.get("user_id") or "hitl"),
        message=f"HITL 操作：{payload.get('intervention_type')}",
        payload=dict(payload),
        related_task_id=_to_uuid(payload.get("target_task_id")),
        related_robot_id=_to_uuid(payload.get("target_robot_id")),
    )


def register_alert_engine(bus: EventBus) -> None:
    """订阅 8 类事件 → 12 条规则中的 11 条；task_overdue 走 OverdueScanner。"""
    bus.subscribe("perception.high_confidence_alert", _on_perception_high_confidence)
    bus.subscribe("robot.fault_occurred", _on_robot_fault)
    bus.subscribe("auction.failed", _on_auction_failed)
    bus.subscribe("auction.completed", _on_auction_completed)
    bus.subscribe("dispatch.algorithm_changed", _on_algorithm_changed)
    bus.subscribe("task.reassigned", _on_task_reassigned)
    bus.subscribe("task.cancelled", _on_task_cancelled)
    bus.subscribe("intervention.recorded", _on_intervention_recorded)


# ============== Overdue Scanner ==============


class OverdueTaskScanner:
    """周期扫描 sla_deadline < now 的活跃任务，触发 task_overdue 告警。

    去重：进程内 dict {task_id: last_alerted_at}，同任务 dedup_window_sec 内不重复。
    生命周期：与 BlackboardCleanupScanner 同款 asyncio.Event。
    """

    def __init__(
        self,
        *,
        interval_sec: float,
        dedup_window_sec: float = 600.0,
    ) -> None:
        self.interval_sec = float(interval_sec)
        self.dedup_window_sec = float(dedup_window_sec)
        self._task: asyncio.Task[None] | None = None
        self._stop: asyncio.Event | None = None
        self._started: bool = False
        self._last_alerted: dict[UUID, datetime] = {}

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        if self._started:
            logger.warning("overdue_scanner_already_started")
            return
        if self.interval_sec <= 0:
            logger.info(
                "overdue_scanner_disabled_zero_interval",
                extra={"interval_sec": self.interval_sec},
            )
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(
            self._run_loop(), name="overdue_task_scanner"
        )
        self._started = True
        logger.info(
            "overdue_scanner_started",
            extra={"interval_sec": self.interval_sec},
        )

    async def stop(self, *, timeout_sec: float = 5.0) -> None:
        if not self._started or self._task is None or self._stop is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=timeout_sec)
        except asyncio.TimeoutError:
            logger.warning("overdue_scanner_stop_timeout, cancelling")
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, BaseException):  # noqa: BLE001
                pass
        self._task = None
        self._stop = None
        self._started = False
        logger.info("overdue_scanner_stopped")

    async def _run_loop(self) -> None:
        assert self._stop is not None
        try:
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=self.interval_sec
                    )
                    return
                except asyncio.TimeoutError:
                    pass
                try:
                    await self.scan_once()
                except Exception:
                    logger.exception("overdue_scanner_tick_failed")
        except asyncio.CancelledError:
            raise

    async def scan_once(self) -> int:
        """返回本轮新触发的告警数。公开供自检脚本直接调用。"""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.dedup_window_sec)
        # 清理过期 dedup 记录
        self._last_alerted = {
            tid: ts for tid, ts in self._last_alerted.items() if ts > cutoff
        }

        async with async_session_maker() as session:
            stmt = select(Task).where(
                Task.sla_deadline.is_not(None),
                Task.sla_deadline < now,
                Task.status.in_(("PENDING", "ASSIGNED", "EXECUTING")),
            )
            tasks = list((await session.execute(stmt)).scalars().all())

        triggered = 0
        for t in tasks:
            last_at = self._last_alerted.get(t.id)
            if last_at is not None and last_at > cutoff:
                continue
            overdue_sec = (now - t.sla_deadline).total_seconds()
            await _create_alert_and_publish(
                rule_key="task_overdue",
                source=t.code,
                message=(
                    f"任务 {t.code} 已超时 {int(overdue_sec // 60)} 分钟"
                ),
                payload={
                    "sla_alert": {
                        "task_code": t.code,
                        "deadline": t.sla_deadline.isoformat(),
                        "overdue_min": int(overdue_sec // 60),
                    },
                    "current_status": t.status,
                },
                related_task_id=t.id,
            )
            self._last_alerted[t.id] = now
            triggered += 1
        return triggered


# 进程单例（lifespan 注入）
_scanner_singleton: OverdueTaskScanner | None = None


def get_overdue_task_scanner(
    *,
    interval_sec: float,
    dedup_window_sec: float = 600.0,
) -> OverdueTaskScanner:
    global _scanner_singleton
    if _scanner_singleton is None:
        _scanner_singleton = OverdueTaskScanner(
            interval_sec=interval_sec,
            dedup_window_sec=dedup_window_sec,
        )
    return _scanner_singleton


def reset_scanner_for_tests() -> None:
    global _scanner_singleton
    _scanner_singleton = None
