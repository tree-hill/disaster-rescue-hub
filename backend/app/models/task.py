from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.db.base import Base


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','ASSIGNED','EXECUTING','COMPLETED','FAILED','CANCELLED')",
            name="tasks_status_check",
        ),
        CheckConstraint("priority IN (1,2,3)", name="tasks_priority_check"),
        Index("idx_tasks_status", "status", text("created_at DESC")),
        Index(
            "idx_tasks_priority",
            "priority",
            "created_at",
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index("idx_tasks_parent", "parent_id"),
        Index("idx_tasks_capabilities", "required_capabilities", postgresql_using="gin"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    type = Column(String(30), nullable=False)
    priority = Column(SmallInteger, nullable=False, server_default=text("2"))
    status = Column(String(20), nullable=False, server_default=text("'PENDING'"))
    target_area = Column(JSONB, nullable=False)
    required_capabilities = Column(JSONB, nullable=False, server_default="[]")
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=True,
    )
    progress = Column(Numeric(5, 2), nullable=False, server_default=text("0"))
    sla_deadline = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TaskAssignment(Base):
    __tablename__ = "task_assignments"
    __table_args__ = (
        UniqueConstraint("task_id", "robot_id", "assigned_at"),
        Index("idx_assignments_task", "task_id", postgresql_where=text("is_active = TRUE")),
        Index("idx_assignments_robot", "robot_id", postgresql_where=text("is_active = TRUE")),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    robot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("robots.id"),
        nullable=False,
    )
    auction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auctions.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    released_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=text("TRUE"))
