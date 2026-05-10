"""复盘时间轴查询辅助（P8.1）。

无 IO 纯函数：在 service 层从 ReplaySession.summary 取出 snapshots / key_events
后做时间窗 + 抽样过滤。

API_SPEC §7 GET /replay/sessions/{id}/snapshots 支持
`start_time / end_time / interval_sec` 三个查询参数。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            # 兼容 'Z' 后缀（fromisoformat 3.11+ 已支持，但保险起见处理）
            v = value.replace("Z", "+00:00") if value.endswith("Z") else value
            return datetime.fromisoformat(v)
        except ValueError:
            return None
    return None


def filter_snapshots(
    snapshots: list[dict[str, Any]],
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    interval_sec: float = 1.0,
) -> list[dict[str, Any]]:
    """按时间窗 + 抽样间隔筛选 snapshots（已按 ts 升序入参）。

    抽样规则：从首个保留帧的 ts 起，下一个保留帧需 ts ≥ prev + interval_sec。
    interval_sec ≤ 1 视为不抽样（每帧保留）。
    """
    if not snapshots:
        return []
    out: list[dict[str, Any]] = []
    last_kept_ts: datetime | None = None
    for snap in snapshots:
        ts = _parse_ts(snap.get("ts"))
        if ts is None:
            continue
        if start_time is not None and ts < start_time:
            continue
        if end_time is not None and ts > end_time:
            continue
        if (
            interval_sec > 1.0
            and last_kept_ts is not None
            and (ts - last_kept_ts).total_seconds() < interval_sec
        ):
            continue
        out.append(snap)
        last_kept_ts = ts
    return out


def filter_key_events(
    events: list[dict[str, Any]],
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> list[dict[str, Any]]:
    """按时间窗筛选 key_events（已按 ts 升序入参）。"""
    if not events:
        return []
    out: list[dict[str, Any]] = []
    for ev in events:
        ts = _parse_ts(ev.get("ts"))
        if ts is None:
            continue
        if start_time is not None and ts < start_time:
            continue
        if end_time is not None and ts > end_time:
            continue
        out.append(ev)
    return out
