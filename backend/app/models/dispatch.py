from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.db.base import Base


class Auction(Base):
    __tablename__ = "auctions"
    __table_args__ = (
        CheckConstraint(
            "algorithm IN ('AUCTION_HUNGARIAN','GREEDY','RANDOM')",
            name="auctions_algo_check",
        ),
        CheckConstraint(
            "status IN ('OPEN','CLOSED','FAILED')",
            name="auctions_status_check",
        ),
        Index("idx_auctions_task", "task_id", text("started_at DESC")),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    algorithm = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, server_default=text("'OPEN'"))
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)
    winner_robot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("robots.id"),
        nullable=True,
    )
    decision_latency_ms = Column(Integer, nullable=True)
    auction_metadata = Column("metadata", JSONB, nullable=True, server_default="{}")


class Bid(Base):
    __tablename__ = "bids"
    __table_args__ = (
        UniqueConstraint("auction_id", "robot_id"),
        Index("idx_bids_auction", "auction_id", text("bid_value DESC")),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    auction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auctions.id", ondelete="CASCADE"),
        nullable=False,
    )
    robot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("robots.id"),
        nullable=False,
    )
    bid_value = Column(Numeric(10, 4), nullable=False)
    breakdown = Column(JSONB, nullable=False)
    vision_boost = Column(Numeric(4, 2), nullable=True, server_default=text("1.0"))
    submitted_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
