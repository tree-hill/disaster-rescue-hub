from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.db.base import Base


class BlackboardEntry(Base):
    __tablename__ = "blackboard_entries"
    __table_args__ = (
        Index("idx_blackboard_key", "key"),
        # full index; partial (WHERE expires_at > NOW()) not possible — NOW() is not IMMUTABLE
        Index("idx_blackboard_active", "expires_at"),
        Index("idx_blackboard_value", "value", postgresql_using="gin"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    key = Column(String(200), nullable=False)
    value = Column(JSONB, nullable=False)
    confidence = Column(Numeric(4, 3), nullable=False)
    source_robot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("robots.id", ondelete="SET NULL"),
        nullable=True,
    )
    fused_from = Column(JSONB, nullable=True, server_default="[]")
    expires_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
