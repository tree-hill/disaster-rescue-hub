"""init schema

Revision ID: 26cff1e230e8
Revises:
Create Date: 2026-05-02 05:26:28.802809

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision: str = "26cff1e230e8"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── extensions ──────────────────────────────────────────────────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    # ── 1. users ─────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("username", sa.String(50), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(100), unique=True, nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_users_username", "users", ["username"],
                    postgresql_where=sa.text("is_active = TRUE"))

    # ── 2. roles ─────────────────────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(50), unique=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("permissions", JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # ── 3. user_roles ─────────────────────────────────────────────────────────
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("role_id", sa.UUID(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # ── 4. robot_groups ───────────────────────────────────────────────────────
    op.create_table(
        "robot_groups",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("leader_robot_id", sa.UUID(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # ── 5. robots ─────────────────────────────────────────────────────────────
    op.create_table(
        "robots",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(50), unique=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("capability", JSONB(), nullable=False, server_default="{}"),
        sa.Column("group_id", sa.UUID(), sa.ForeignKey("robot_groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("type IN ('uav', 'ugv', 'usv')", name="robots_type_check"),
    )
    op.create_index("idx_robots_type", "robots", ["type"],
                    postgresql_where=sa.text("is_active = TRUE"))
    op.create_index("idx_robots_group", "robots", ["group_id"])
    op.create_index("idx_robots_capability", "robots", ["capability"], postgresql_using="gin")

    # ── 6. scenarios ──────────────────────────────────────────────────────────
    op.create_table(
        "scenarios",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("disaster_type", sa.String(30), nullable=False),
        sa.Column("map_bounds", JSONB(), nullable=False),
        sa.Column("initial_state", JSONB(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # ── 7. tasks ──────────────────────────────────────────────────────────────
    op.create_table(
        "tasks",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(50), unique=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="2"),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("target_area", JSONB(), nullable=False),
        sa.Column("required_capabilities", JSONB(), nullable=False, server_default="[]"),
        sa.Column("parent_id", sa.UUID(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True),
        sa.Column("progress", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("sla_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('PENDING','ASSIGNED','EXECUTING','COMPLETED','FAILED','CANCELLED')",
            name="tasks_status_check",
        ),
        sa.CheckConstraint("priority IN (1,2,3)", name="tasks_priority_check"),
    )
    op.create_index("idx_tasks_status", "tasks", ["status", "created_at"])
    op.create_index("idx_tasks_priority", "tasks", ["priority", "created_at"],
                    postgresql_where=sa.text("status = 'PENDING'"))
    op.create_index("idx_tasks_parent", "tasks", ["parent_id"])
    op.create_index("idx_tasks_capabilities", "tasks", ["required_capabilities"], postgresql_using="gin")

    # ── 8. auctions ───────────────────────────────────────────────────────────
    op.create_table(
        "auctions",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("task_id", sa.UUID(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("algorithm", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("winner_robot_id", sa.UUID(), sa.ForeignKey("robots.id"), nullable=True),
        sa.Column("decision_latency_ms", sa.Integer(), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True, server_default="{}"),
        sa.CheckConstraint("algorithm IN ('AUCTION_HUNGARIAN','GREEDY','RANDOM')", name="auctions_algo_check"),
        sa.CheckConstraint("status IN ('OPEN','CLOSED','FAILED')", name="auctions_status_check"),
    )
    op.create_index("idx_auctions_task", "auctions", ["task_id", "started_at"])

    # ── 9. task_assignments ───────────────────────────────────────────────────
    op.create_table(
        "task_assignments",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("task_id", sa.UUID(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("robot_id", sa.UUID(), sa.ForeignKey("robots.id"), nullable=False),
        sa.Column("auction_id", sa.UUID(), sa.ForeignKey("auctions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.UniqueConstraint("task_id", "robot_id", "assigned_at"),
    )
    op.create_index("idx_assignments_task", "task_assignments", ["task_id"],
                    postgresql_where=sa.text("is_active = TRUE"))
    op.create_index("idx_assignments_robot", "task_assignments", ["robot_id"],
                    postgresql_where=sa.text("is_active = TRUE"))

    # ── 10. robot_states ──────────────────────────────────────────────────────
    op.create_table(
        "robot_states",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("robot_id", sa.UUID(), sa.ForeignKey("robots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("fsm_state", sa.String(20), nullable=False),
        sa.Column("position", JSONB(), nullable=False),
        sa.Column("battery", sa.Numeric(5, 2), nullable=False),
        sa.Column("sensor_data", JSONB(), nullable=False, server_default="{}"),
        sa.Column("current_task_id", sa.UUID(), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint(
            "fsm_state IN ('IDLE','BIDDING','EXECUTING','RETURNING','FAULT')",
            name="robot_states_fsm_check",
        ),
    )
    op.create_index("idx_robot_states_robot_time", "robot_states", ["robot_id", "recorded_at"])
    op.create_index("idx_robot_states_time", "robot_states", ["recorded_at"])
    op.create_index("idx_robot_states_sensor", "robot_states", ["sensor_data"], postgresql_using="gin")

    # ── 11. robot_faults ──────────────────────────────────────────────────────
    op.create_table(
        "robot_faults",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("robot_id", sa.UUID(), sa.ForeignKey("robots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fault_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detail", JSONB(), nullable=True, server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint("severity IN ('info','warn','critical')", name="faults_severity_check"),
    )
    op.create_index("idx_faults_robot", "robot_faults", ["robot_id", "occurred_at"])
    op.create_index("idx_faults_unresolved", "robot_faults", ["occurred_at"],
                    postgresql_where=sa.text("resolved_at IS NULL"))

    # ── 12. bids ──────────────────────────────────────────────────────────────
    op.create_table(
        "bids",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("auction_id", sa.UUID(), sa.ForeignKey("auctions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("robot_id", sa.UUID(), sa.ForeignKey("robots.id"), nullable=False),
        sa.Column("bid_value", sa.Numeric(10, 4), nullable=False),
        sa.Column("breakdown", JSONB(), nullable=False),
        sa.Column("vision_boost", sa.Numeric(4, 2), nullable=True, server_default="1.0"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("auction_id", "robot_id"),
    )
    op.create_index("idx_bids_auction", "bids", ["auction_id", "bid_value"])

    # ── 13. human_interventions ───────────────────────────────────────────────
    op.create_table(
        "human_interventions",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("intervention_type", sa.String(30), nullable=False),
        sa.Column("target_task_id", sa.UUID(), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_robot_id", sa.UUID(), sa.ForeignKey("robots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("before_state", JSONB(), nullable=False),
        sa.Column("after_state", JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "intervention_type IN ('reassign','recall','cancel_task','algorithm_switch')",
            name="interventions_type_check",
        ),
    )
    op.create_index("idx_interventions_user", "human_interventions", ["user_id", "occurred_at"])
    op.create_index("idx_interventions_task", "human_interventions", ["target_task_id"])
    op.create_index("idx_interventions_time", "human_interventions", ["occurred_at"])

    # ── 14. blackboard_entries ────────────────────────────────────────────────
    op.create_table(
        "blackboard_entries",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("source_robot_id", sa.UUID(), sa.ForeignKey("robots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fused_from", JSONB(), nullable=True, server_default="[]"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_blackboard_key", "blackboard_entries", ["key"])
    # NOW() 不是 IMMUTABLE，无法用于部分索引谓词，改为全量索引
    op.create_index("idx_blackboard_active", "blackboard_entries", ["expires_at"])
    op.create_index("idx_blackboard_value", "blackboard_entries", ["value"], postgresql_using="gin")

    # ── 15. alerts ────────────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(50), unique=True, nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=True, server_default="{}"),
        sa.Column("related_task_id", sa.UUID(), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("related_robot_id", sa.UUID(), sa.ForeignKey("robots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_ignored", sa.Boolean(), nullable=False, server_default="false"),
        sa.CheckConstraint("severity IN ('info','warn','critical')", name="alerts_severity_check"),
    )
    op.create_index("idx_alerts_unack", "alerts", ["raised_at"],
                    postgresql_where=sa.text("acknowledged_at IS NULL AND is_ignored = FALSE"))
    op.create_index("idx_alerts_severity", "alerts", ["severity", "raised_at"])

    # ── 16. replay_sessions ───────────────────────────────────────────────────
    op.create_table(
        "replay_sessions",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("scenario_id", sa.UUID(), sa.ForeignKey("scenarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("algorithm", sa.String(30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("completion_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("summary", JSONB(), nullable=True, server_default="{}"),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_replay_created", "replay_sessions", ["created_at"])

    # ── 17. experiment_runs ───────────────────────────────────────────────────
    op.create_table(
        "experiment_runs",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("batch_id", sa.UUID(), nullable=False),
        sa.Column("scenario_id", sa.UUID(), sa.ForeignKey("scenarios.id"), nullable=False),
        sa.Column("algorithm", sa.String(30), nullable=False),
        sa.Column("run_index", sa.Integer(), nullable=False),
        sa.Column("completion_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("avg_response_sec", sa.Numeric(8, 2), nullable=True),
        sa.Column("total_path_km", sa.Numeric(8, 3), nullable=True),
        sa.Column("load_std_dev", sa.Numeric(6, 3), nullable=True),
        sa.Column("decision_latency_ms", sa.Integer(), nullable=True),
        sa.Column("raw_metrics", JSONB(), nullable=True, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("batch_id", "algorithm", "run_index"),
    )
    op.create_index("idx_exp_batch", "experiment_runs", ["batch_id"])
    op.create_index("idx_exp_algo", "experiment_runs", ["algorithm", "scenario_id"])

    # ── triggers: auto update updated_at ─────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION trigger_set_timestamp()
        RETURNS TRIGGER AS $$
        BEGIN
          NEW.updated_at = NOW();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    for tbl in ("users", "robots", "tasks", "blackboard_entries"):
        op.execute(f"""
            CREATE TRIGGER set_timestamp_{tbl}
            BEFORE UPDATE ON {tbl}
            FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp()
        """)


def downgrade() -> None:
    for tbl in ("users", "robots", "tasks", "blackboard_entries"):
        op.execute(f"DROP TRIGGER IF EXISTS set_timestamp_{tbl} ON {tbl}")
    op.execute("DROP FUNCTION IF EXISTS trigger_set_timestamp()")

    op.drop_table("experiment_runs")
    op.drop_table("replay_sessions")
    op.drop_table("alerts")
    op.drop_table("blackboard_entries")
    op.drop_table("human_interventions")
    op.drop_table("bids")
    op.drop_table("robot_faults")
    op.drop_table("robot_states")
    op.drop_table("task_assignments")
    op.drop_table("auctions")
    op.drop_table("tasks")
    op.drop_table("scenarios")
    op.drop_table("robots")
    op.drop_table("robot_groups")
    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_table("users")
