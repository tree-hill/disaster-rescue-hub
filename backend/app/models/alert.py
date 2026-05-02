from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.db.base import Base


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('info','warn','critical')",
            name="alerts_severity_check",
        ),
        Index(
            "idx_alerts_unack",
            text("raised_at DESC"),
            postgresql_where=text("acknowledged_at IS NULL AND is_ignored = FALSE"),
        ),
        Index("idx_alerts_severity", "severity", text("raised_at DESC")),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    code = Column(String(50), unique=True, nullable=False)
    type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    source = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=True, server_default="{}")
    related_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    related_robot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("robots.id", ondelete="SET NULL"),
        nullable=True,
    )
    raised_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_ignored = Column(Boolean, nullable=False, server_default=text("FALSE"))
