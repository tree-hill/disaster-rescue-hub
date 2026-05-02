from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.db.base import Base


class RobotGroup(Base):
    """编队 — 在 Robot 之前定义，因为 robots.group_id 引用本表。"""

    __tablename__ = "robot_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name = Column(String(100), nullable=False)
    leader_robot_id = Column(UUID(as_uuid=True), nullable=True)  # 不加 FK，允许失效
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Robot(Base):
    __tablename__ = "robots"
    __table_args__ = (
        CheckConstraint("type IN ('uav', 'ugv', 'usv')", name="robots_type_check"),
        Index("idx_robots_type", "type", postgresql_where=text("is_active = TRUE")),
        Index("idx_robots_group", "group_id"),
        Index("idx_robots_capability", "capability", postgresql_using="gin"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False)
    model = Column(String(100), nullable=True)
    capability = Column(JSONB, nullable=False, server_default="{}")
    group_id = Column(
        UUID(as_uuid=True),
        ForeignKey("robot_groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active = Column(Boolean, nullable=False, server_default=text("TRUE"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class RobotState(Base):
    """高频写入时序表，使用 BIGSERIAL 主键。"""

    __tablename__ = "robot_states"
    __table_args__ = (
        CheckConstraint(
            "fsm_state IN ('IDLE','BIDDING','EXECUTING','RETURNING','FAULT')",
            name="robot_states_fsm_check",
        ),
        Index("idx_robot_states_robot_time", "robot_id", text("recorded_at DESC")),
        Index("idx_robot_states_time", text("recorded_at DESC")),
        Index("idx_robot_states_sensor", "sensor_data", postgresql_using="gin"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    robot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("robots.id", ondelete="CASCADE"),
        nullable=False,
    )
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    fsm_state = Column(String(20), nullable=False)
    position = Column(JSONB, nullable=False)
    battery = Column(Numeric(5, 2), nullable=False)
    sensor_data = Column(JSONB, nullable=False, server_default="{}")
    current_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )


class RobotFault(Base):
    __tablename__ = "robot_faults"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('info','warn','critical')",
            name="faults_severity_check",
        ),
        Index("idx_faults_robot", "robot_id", text("occurred_at DESC")),
        Index(
            "idx_faults_unresolved",
            text("occurred_at DESC"),
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    robot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("robots.id", ondelete="CASCADE"),
        nullable=False,
    )
    fault_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    detail = Column(JSONB, nullable=True, server_default="{}")
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
