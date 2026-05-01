from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.db.base import Base


class Scenario(Base):
    __tablename__ = "scenarios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)
    disaster_type = Column(String(30), nullable=False)
    map_bounds = Column(JSONB, nullable=False)
    initial_state = Column(JSONB, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ReplaySession(Base):
    __tablename__ = "replay_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    scenario_id = Column(
        UUID(as_uuid=True),
        ForeignKey("scenarios.id", ondelete="SET NULL"),
        nullable=True,
    )
    algorithm = Column(String(30), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_sec = Column(Integer, nullable=True)
    completion_rate = Column(Numeric(5, 2), nullable=True)
    summary = Column(JSONB, nullable=True, server_default="{}")
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ExperimentRun(Base):
    __tablename__ = "experiment_runs"
    __table_args__ = (
        UniqueConstraint("batch_id", "algorithm", "run_index"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(UUID(as_uuid=True), nullable=False)
    scenario_id = Column(
        UUID(as_uuid=True),
        ForeignKey("scenarios.id"),
        nullable=False,
    )
    algorithm = Column(String(30), nullable=False)
    run_index = Column(Integer, nullable=False)
    completion_rate = Column(Numeric(5, 2), nullable=True)
    avg_response_sec = Column(Numeric(8, 2), nullable=True)
    total_path_km = Column(Numeric(8, 3), nullable=True)
    load_std_dev = Column(Numeric(6, 3), nullable=True)
    decision_latency_ms = Column(Integer, nullable=True)
    raw_metrics = Column(JSONB, nullable=True, server_default="{}")
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
