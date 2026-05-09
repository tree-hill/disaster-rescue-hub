"""告警业务服务（P7.1）。

对照：
- API_SPEC §6（POST /alerts/{id}/acknowledge / ignore / batch-acknowledge）
- WS_EVENTS §7（alert.acknowledged / alert.ignored 推送字段）
- BUSINESS_RULES §6.7 通用错误码（404_ALERT_NOT_FOUND_001 / 409_ALERT_ALREADY_ACKED_001）

事务模式：service 层 commit；commit 之后再 publish bus 事件，避免事务回滚后产生
幻觉事件（与 task_service 同款）。

权限：API 层用 require_permission("alert:handle") 守卫；service 不再做角色判断。
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import get_event_bus
from app.core.exceptions import BusinessError
from app.models.alert import Alert
from app.repositories.alert import AlertRepository

logger = logging.getLogger(__name__)


_ALERT_NOT_FOUND = "404_ALERT_NOT_FOUND_001"
_ALERT_ALREADY_ACKED = "409_ALERT_ALREADY_ACKED_001"
_ALERT_ALREADY_IGNORED = "409_ALERT_ALREADY_IGNORED_001"


def _not_found(alert_id: UUID) -> BusinessError:
    return BusinessError(
        code=_ALERT_NOT_FOUND,
        message=f"告警 {alert_id} 不存在",
        http_status=404,
    )


class AlertService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.alerts = AlertRepository(session)

    async def get(self, alert_id: UUID) -> Alert:
        alert = await self.alerts.find_by_id(alert_id)
        if alert is None:
            raise _not_found(alert_id)
        return alert

    async def acknowledge(
        self,
        alert_id: UUID,
        *,
        user_id: UUID,
        note: str | None = None,
    ) -> Alert:
        """确认单条告警。已确认 → 409；已忽略仍允许确认（业务上是允许覆盖的状态）。"""
        alert = await self.alerts.find_by_id(alert_id)
        if alert is None:
            raise _not_found(alert_id)
        if alert.acknowledged_at is not None:
            raise BusinessError(
                code=_ALERT_ALREADY_ACKED,
                message=f"告警 {alert.code} 已被确认",
                http_status=409,
            )

        now = datetime.now(timezone.utc)
        alert.acknowledged_at = now
        alert.acknowledged_by = user_id
        if note:
            payload = dict(alert.payload or {})
            payload["acknowledge_note"] = note
            alert.payload = payload

        await self.session.commit()
        await self.session.refresh(alert)

        await self._publish(
            "alert.acknowledged",
            {
                "alert_id": str(alert.id),
                "alert_code": alert.code,
                "acknowledged_by_user_id": str(user_id),
                "acknowledged_at": now.isoformat(),
            },
        )
        return alert

    async def ignore(
        self,
        alert_id: UUID,
        *,
        user_id: UUID,
        reason: str,
    ) -> Alert:
        """忽略告警。已忽略 → 409。"""
        alert = await self.alerts.find_by_id(alert_id)
        if alert is None:
            raise _not_found(alert_id)
        if alert.is_ignored:
            raise BusinessError(
                code=_ALERT_ALREADY_IGNORED,
                message=f"告警 {alert.code} 已被忽略",
                http_status=409,
            )

        alert.is_ignored = True
        payload = dict(alert.payload or {})
        payload["ignore_reason"] = reason
        payload["ignored_by"] = str(user_id)
        alert.payload = payload

        await self.session.commit()
        await self.session.refresh(alert)

        await self._publish(
            "alert.ignored",
            {
                "alert_id": str(alert.id),
                "alert_code": alert.code,
                "ignored_by_user_id": str(user_id),
                "reason": reason,
            },
        )
        return alert

    async def batch_acknowledge(
        self,
        alert_ids: Sequence[UUID],
        *,
        user_id: UUID,
    ) -> tuple[int, int]:
        """批量确认；忽略已确认 / 不存在的；返回 (acknowledged, failed)。

        失败 = 不存在 OR 已经 ack（视为「无需再 ack」并入失败计数，与 API_SPEC §6
        响应字段 acknowledged/failed 字面对齐）。
        """
        rows = await self.alerts.find_by_ids(list(alert_ids))
        rows_by_id = {a.id: a for a in rows}
        now = datetime.now(timezone.utc)
        acknowledged = 0
        failed = 0
        ack_payloads: list[dict] = []
        for aid in alert_ids:
            a = rows_by_id.get(aid)
            if a is None or a.acknowledged_at is not None:
                failed += 1
                continue
            a.acknowledged_at = now
            a.acknowledged_by = user_id
            acknowledged += 1
            ack_payloads.append(
                {
                    "alert_id": str(a.id),
                    "alert_code": a.code,
                    "acknowledged_by_user_id": str(user_id),
                    "acknowledged_at": now.isoformat(),
                }
            )

        if acknowledged:
            await self.session.commit()
            for p in ack_payloads:
                await self._publish("alert.acknowledged", p)
        return acknowledged, failed

    @staticmethod
    async def _publish(event_type: str, payload: dict) -> None:
        try:
            await get_event_bus().publish(event_type, payload)
        except Exception:
            logger.exception(
                "alert_event_publish_failed",
                extra={"event_type": event_type, "payload": payload},
            )
