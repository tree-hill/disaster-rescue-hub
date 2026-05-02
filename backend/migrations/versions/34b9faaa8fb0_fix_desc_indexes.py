"""fix desc indexes

Revision ID: 34b9faaa8fb0
Revises: 26cff1e230e8
Create Date: 2026-05-02 12:31:34.755237

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "34b9faaa8fb0"
down_revision: Union[str, None] = "26cff1e230e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop ASC indexes created by the initial migration, then recreate as DESC.
    # 12 indexes across 7 tables.

    # ── tasks ────────────────────────────────────────────────────────────────
    op.drop_index("idx_tasks_status", table_name="tasks")
    op.create_index("idx_tasks_status", "tasks", ["status", sa.text("created_at DESC")])

    # ── robot_states ──────────────────────────────────────────────────────────
    op.drop_index("idx_robot_states_robot_time", table_name="robot_states")
    op.create_index(
        "idx_robot_states_robot_time",
        "robot_states",
        ["robot_id", sa.text("recorded_at DESC")],
    )

    op.drop_index("idx_robot_states_time", table_name="robot_states")
    op.create_index(
        "idx_robot_states_time",
        "robot_states",
        [sa.text("recorded_at DESC")],
    )

    # ── robot_faults ──────────────────────────────────────────────────────────
    op.drop_index("idx_faults_robot", table_name="robot_faults")
    op.create_index(
        "idx_faults_robot",
        "robot_faults",
        ["robot_id", sa.text("occurred_at DESC")],
    )

    op.drop_index("idx_faults_unresolved", table_name="robot_faults")
    op.create_index(
        "idx_faults_unresolved",
        "robot_faults",
        [sa.text("occurred_at DESC")],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )

    # ── auctions ──────────────────────────────────────────────────────────────
    op.drop_index("idx_auctions_task", table_name="auctions")
    op.create_index(
        "idx_auctions_task",
        "auctions",
        ["task_id", sa.text("started_at DESC")],
    )

    # ── bids ──────────────────────────────────────────────────────────────────
    op.drop_index("idx_bids_auction", table_name="bids")
    op.create_index(
        "idx_bids_auction",
        "bids",
        ["auction_id", sa.text("bid_value DESC")],
    )

    # ── human_interventions ───────────────────────────────────────────────────
    op.drop_index("idx_interventions_user", table_name="human_interventions")
    op.create_index(
        "idx_interventions_user",
        "human_interventions",
        ["user_id", sa.text("occurred_at DESC")],
    )

    op.drop_index("idx_interventions_time", table_name="human_interventions")
    op.create_index(
        "idx_interventions_time",
        "human_interventions",
        [sa.text("occurred_at DESC")],
    )

    # ── alerts ────────────────────────────────────────────────────────────────
    op.drop_index("idx_alerts_unack", table_name="alerts")
    op.create_index(
        "idx_alerts_unack",
        "alerts",
        [sa.text("raised_at DESC")],
        postgresql_where=sa.text("acknowledged_at IS NULL AND is_ignored = FALSE"),
    )

    op.drop_index("idx_alerts_severity", table_name="alerts")
    op.create_index(
        "idx_alerts_severity",
        "alerts",
        ["severity", sa.text("raised_at DESC")],
    )

    # ── replay_sessions ───────────────────────────────────────────────────────
    op.drop_index("idx_replay_created", table_name="replay_sessions")
    op.create_index(
        "idx_replay_created",
        "replay_sessions",
        [sa.text("created_at DESC")],
    )


def downgrade() -> None:
    # Drop DESC indexes and recreate the original ASC versions.

    # ── replay_sessions ───────────────────────────────────────────────────────
    op.drop_index("idx_replay_created", table_name="replay_sessions")
    op.create_index("idx_replay_created", "replay_sessions", ["created_at"])

    # ── alerts ────────────────────────────────────────────────────────────────
    op.drop_index("idx_alerts_severity", table_name="alerts")
    op.create_index("idx_alerts_severity", "alerts", ["severity", "raised_at"])

    op.drop_index("idx_alerts_unack", table_name="alerts")
    op.create_index(
        "idx_alerts_unack",
        "alerts",
        ["raised_at"],
        postgresql_where=sa.text("acknowledged_at IS NULL AND is_ignored = FALSE"),
    )

    # ── human_interventions ───────────────────────────────────────────────────
    op.drop_index("idx_interventions_time", table_name="human_interventions")
    op.create_index("idx_interventions_time", "human_interventions", ["occurred_at"])

    op.drop_index("idx_interventions_user", table_name="human_interventions")
    op.create_index(
        "idx_interventions_user", "human_interventions", ["user_id", "occurred_at"]
    )

    # ── bids ──────────────────────────────────────────────────────────────────
    op.drop_index("idx_bids_auction", table_name="bids")
    op.create_index("idx_bids_auction", "bids", ["auction_id", "bid_value"])

    # ── auctions ──────────────────────────────────────────────────────────────
    op.drop_index("idx_auctions_task", table_name="auctions")
    op.create_index("idx_auctions_task", "auctions", ["task_id", "started_at"])

    # ── robot_faults ──────────────────────────────────────────────────────────
    op.drop_index("idx_faults_unresolved", table_name="robot_faults")
    op.create_index(
        "idx_faults_unresolved",
        "robot_faults",
        ["occurred_at"],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )

    op.drop_index("idx_faults_robot", table_name="robot_faults")
    op.create_index("idx_faults_robot", "robot_faults", ["robot_id", "occurred_at"])

    # ── robot_states ──────────────────────────────────────────────────────────
    op.drop_index("idx_robot_states_time", table_name="robot_states")
    op.create_index("idx_robot_states_time", "robot_states", ["recorded_at"])

    op.drop_index("idx_robot_states_robot_time", table_name="robot_states")
    op.create_index(
        "idx_robot_states_robot_time", "robot_states", ["robot_id", "recorded_at"]
    )

    # ── tasks ────────────────────────────────────────────────────────────────
    op.drop_index("idx_tasks_status", table_name="tasks")
    op.create_index("idx_tasks_status", "tasks", ["status", "created_at"])
