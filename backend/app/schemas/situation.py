"""态势感知 Pydantic v2 Schemas（P7.1）。

对照：
- API_SPEC §6 GET /situation/kpi 200 响应字段
- WS_EVENTS §7 kpi.snapshot payload
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class BatteryDistribution(BaseModel):
    """电量分布桶（high≥60% / 30%≤mid<60% / low<30%）。"""

    high: int = Field(0, ge=0)
    mid: int = Field(0, ge=0)
    low: int = Field(0, ge=0)


class KPISnapshot(BaseModel):
    """实时 KPI 快照。

    与 WS_EVENTS §7 kpi.snapshot 完全同 schema，只是 REST 响应不包含
    event_id / timestamp（这两个字段由 push_event 注入到 WS payload）。
    """

    online_robots: int = Field(0, ge=0)
    total_robots: int = Field(0, ge=0)
    completion_rate: float = Field(0.0, ge=0.0, le=100.0)
    avg_response_sec: float = Field(0.0, ge=0.0)
    battery_distribution: BatteryDistribution
    active_alerts: int = Field(0, ge=0)
    active_tasks: int = Field(0, ge=0)
