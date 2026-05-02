"""Add pgvector columns for semantic search.

- events.embedding (1536-dim, nullable) — embed event summaries for similarity search.
- document_embeddings table — chunks of any text artifact (code, docs, Slack messages)
  indexed by the knowledge service.
- cosine similarity index (IVFFlat) on both — suitable for ~10-dev scale.

Revision ID: 0002_add_vectors
Revises: 0001_init
Create Date: 2026-05-01

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_add_vectors"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Dimension used by OpenAI text-embedding-3-small and most small embedding models.
# Change this constant if you switch models — then also update the IVFFlat index.
EMBEDDING_DIM = 1536


def upgrade() -> None:
    # ------------------------------------------------------------------
    # events: optional embedding on each event for semantic lookup
    # ------------------------------------------------------------------
    op.add_column(
        "events",
        sa.Column(
            "embedding",
            sa.Text,  # stored as text; the pgvector extension casts via the operator
            nullable=True,
            comment=f"pgvector({EMBEDDING_DIM}) — null until the knowledge service embeds it",
        ),
    )
    # Real pgvector DDL — execute raw because SQLAlchemy Core doesn't model it natively.
    op.execute(
        f"ALTER TABLE events ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM}) "
        f"USING embedding::vector({EMBEDDING_DIM})"
    )
    # IVFFlat cosine index. lists=10 is fine for ≤100k rows (10-dev company).
    # Increase lists and run VACUUM ANALYZE before switching to production.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_events_embedding_cosine "
        f"ON events USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)"
    )

    # ------------------------------------------------------------------
    # document_embeddings — generic chunk store for the knowledge service
    # ------------------------------------------------------------------
    op.create_table(
        "document_embeddings",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("source_type", sa.String, nullable=False, index=True,
                  comment="code | slack | github | jira | doc | ..."),
        sa.Column("source_id", sa.String, nullable=False, index=True,
                  comment="natural id of the parent object"),
        sa.Column("chunk_index", sa.Integer, nullable=False,
                  comment="position of this chunk within the source doc"),
        sa.Column("content", sa.Text, nullable=False,
                  comment="the raw text that was embedded"),
        sa.Column("metadata", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    # Add vector column + index via raw DDL
    op.execute(
        f"ALTER TABLE document_embeddings "
        f"ADD COLUMN embedding vector({EMBEDDING_DIM}) NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_doc_embeddings_cosine "
        f"ON document_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)"
    )
    op.create_index("ix_doc_embeddings_source", "document_embeddings", ["source_type", "source_id"])


def downgrade() -> None:
    op.drop_table("document_embeddings")
    op.drop_column("events", "embedding")
