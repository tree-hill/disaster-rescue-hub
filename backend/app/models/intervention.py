from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.db.base import Base


class HumanIntervention(Base):
    __tablename__ = "human_interventions"
    __table_args__ = (
        CheckConstraint(
            "intervention_type IN ('reassign','recall','cancel_task','algorithm_switch')",
            name="interventions_type_check",
        ),
        Index("idx_interventions_user", "user_id", text("occurred_at DESC")),
        Index("idx_interventions_task", "target_task_id"),
        Index("idx_interventions_time", text("occurred_at DESC")),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    intervention_type = Column(String(30), nullable=False)
    target_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_robot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("robots.id", ondelete="SET NULL"),
        nullable=True,
    )
    before_state = Column(JSONB, nullable=False)
    after_state = Column(JSONB, nullable=False)
    reason = Column(Text, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
