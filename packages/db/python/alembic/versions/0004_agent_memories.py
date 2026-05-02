"""Add agent_memories table for long-term agent memory.

This is the persistent counterpart to the in-process short-term buffer
inside services/agent-runtime. Each row is a fact, preference, outcome, or
conversation summary that an agent can recall on a future task via vector
similarity search against ``embedding``.

Sole writer: services/agent-runtime (after a task succeeds, or when a skill
explicitly returns a ``remember_this`` payload).
Readers: services/agent-runtime (at task start, to inject relevant memories).

Memory types are intentionally kept loose (string column) but the canonical
vocabulary is: fact, preference, skill_outcome, conversation_summary.

Revision ID: 0004_agent_memories
Revises: 0003_updated_at_triggers
Create Date: 2026-05-01

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_agent_memories"
down_revision: Union[str, None] = "0003_updated_at_triggers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Must match EMBEDDING_DIM in mycelium_db.models and 0002_add_vectors.py.
EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.create_table(
        "agent_memories",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column(
            "agent_id",
            sa.String,
            nullable=False,
            comment="Owning agent. Memories are private to this agent unless retrieval explicitly widens scope.",
        ),
        sa.Column(
            "user_id",
            sa.String,
            nullable=True,
            comment="User the memory pertains to. Used for cross-agent recall scoped to a single user.",
        ),
        sa.Column(
            "task_id",
            sa.String,
            sa.ForeignKey("agent_tasks.task_id", ondelete="SET NULL"),
            nullable=True,
            comment="Task that produced this memory, if any. Nullable so memories survive task deletion.",
        ),
        sa.Column(
            "correlation_id",
            sa.String,
            nullable=False,
            comment="Correlation chain that produced this memory. Required, mirrors other tables.",
        ),
        sa.Column(
            "memory_type",
            sa.String,
            nullable=False,
            server_default="fact",
            comment="fact | preference | skill_outcome | conversation_summary | (free-form)",
        ),
        sa.Column(
            "content",
            sa.Text,
            nullable=False,
            comment="Human-readable memory text. This is what gets embedded.",
        ),
        sa.Column(
            "importance",
            sa.Float,
            nullable=False,
            server_default="0.5",
            comment="0.0-1.0. Used as a tiebreaker after similarity ranking.",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_accessed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Updated whenever this memory is returned by a retrieval query.",
        ),
    )
    op.create_index("ix_agent_memories_agent_id", "agent_memories", ["agent_id"])
    op.create_index("ix_agent_memories_user_id", "agent_memories", ["user_id"])
    op.create_index("ix_agent_memories_task_id", "agent_memories", ["task_id"])
    op.create_index("ix_agent_memories_correlation_id", "agent_memories", ["correlation_id"])
    op.create_index("ix_agent_memories_memory_type", "agent_memories", ["memory_type"])
    op.create_index(
        "ix_agent_memories_agent_user", "agent_memories", ["agent_id", "user_id"]
    )

    # pgvector column + IVFFlat cosine index. Same shape as document_embeddings.
    op.execute(
        f"ALTER TABLE agent_memories "
        f"ADD COLUMN embedding vector({EMBEDDING_DIM}) NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_memories_embedding_cosine "
        "ON agent_memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)"
    )


def downgrade() -> None:
    op.drop_table("agent_memories")
