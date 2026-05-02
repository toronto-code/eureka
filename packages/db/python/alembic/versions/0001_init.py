"""Initial schema: events, integration_syncs, agents, agent_tasks, audit_log, learning_signals.

Revision ID: 0001_init
Revises:
Create Date: 2026-05-01

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ---- events ----
    op.create_table(
        "events",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("actor", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("object", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("schema_version", sa.String, nullable=False, server_default="1.0"),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("correlation_id", sa.String, nullable=False),
        sa.Column("parent_correlation_id", sa.String, nullable=True),
    )
    op.create_index("ix_events_type", "events", ["type"])
    op.create_index("ix_events_source", "events", ["source"])
    op.create_index("ix_events_timestamp", "events", ["timestamp"])
    op.create_index("ix_events_correlation_id", "events", ["correlation_id"])
    op.create_index("ix_events_parent_correlation_id", "events", ["parent_correlation_id"])
    op.create_index("ix_events_type_timestamp", "events", ["type", "timestamp"])
    op.create_index("ix_events_source_timestamp", "events", ["source", "timestamp"])

    # ---- integration_syncs ----
    op.create_table(
        "integration_syncs",
        sa.Column("connector", sa.String, primary_key=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default="ok"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ---- agents ----
    op.create_table(
        "agents",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("owner_user_id", sa.String, nullable=False),
        sa.Column("capabilities", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("status", sa.String, nullable=False, server_default="idle"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agents_owner_user_id", "agents", ["owner_user_id"])

    # ---- agent_tasks ----
    op.create_table(
        "agent_tasks",
        sa.Column("task_id", sa.String, primary_key=True),
        sa.Column("agent_id", sa.String, sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("agent_type", sa.String, nullable=False),
        sa.Column("input_data", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("correlation_id", sa.String, nullable=False),
        sa.Column("parent_correlation_id", sa.String, nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default="queued"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("result", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_index("ix_agent_tasks_agent_id", "agent_tasks", ["agent_id"])
    op.create_index("ix_agent_tasks_status", "agent_tasks", ["status"])
    op.create_index("ix_agent_tasks_correlation_id", "agent_tasks", ["correlation_id"])

    # ---- audit_log ----
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("agent_id", sa.String, nullable=False),
        sa.Column("task_id", sa.String, nullable=True),
        sa.Column("action", sa.String, nullable=False),
        sa.Column("actor_user_id", sa.String, nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("correlation_id", sa.String, nullable=False),
        sa.Column("parent_correlation_id", sa.String, nullable=True),
        sa.Column("details", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_audit_agent_id", "audit_log", ["agent_id"])
    op.create_index("ix_audit_task_id", "audit_log", ["task_id"])
    op.create_index("ix_audit_action", "audit_log", ["action"])
    op.create_index("ix_audit_actor_user_id", "audit_log", ["actor_user_id"])
    op.create_index("ix_audit_timestamp", "audit_log", ["timestamp"])
    op.create_index("ix_audit_correlation_id", "audit_log", ["correlation_id"])

    # ---- learning_signals ----
    op.create_table(
        "learning_signals",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("task_id", sa.String, nullable=True),
        sa.Column("agent_id", sa.String, nullable=True),
        sa.Column("signal_type", sa.String, nullable=False),
        sa.Column("correlation_id", sa.String, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_learning_task_id", "learning_signals", ["task_id"])
    op.create_index("ix_learning_agent_id", "learning_signals", ["agent_id"])
    op.create_index("ix_learning_signal_type", "learning_signals", ["signal_type"])


def downgrade() -> None:
    op.drop_table("learning_signals")
    op.drop_table("audit_log")
    op.drop_table("agent_tasks")
    op.drop_table("agents")
    op.drop_table("integration_syncs")
    op.drop_table("events")
