"""ProjectChunk: the canonical search corpus for OL.

One row per chunk. Canonical raw data lives in typed tables (repositories,
repo_files, commits, pull_requests, jira_tickets, project_events) — this table
holds searchable text slices + optional pgvector embeddings + metadata.

Why not reuse `document_chunks`? The legacy table is shaped around a single
SourceDocument parent. ProjectChunk is polymorphic: a chunk can belong to a
code file, a PR, a commit, a Jira ticket, or a raw doc, and needs to preserve
code-specific fields (language, line range, branch, commit SHA) as first-class
filterable columns — not buried in a JSON blob.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPKMixin

logger = logging.getLogger(__name__)

# Optional pgvector column — falls back to JSON when pgvector isn't available
# so the app boots cleanly on plain Postgres or SQLite (tests).
try:
    from pgvector.sqlalchemy import Vector  # type: ignore

    EMBEDDING_DIM = 1536
    EmbeddingType: Any = Vector(EMBEDDING_DIM)
    HAS_PGVECTOR = True
except Exception:  # noqa: BLE001
    EmbeddingType = JSON
    HAS_PGVECTOR = False
    logger.debug("pgvector not available; ProjectChunk.embedding stored as JSON.")


class ProjectChunk(Base, UUIDPKMixin, TimestampMixin):
    """One searchable chunk of project memory."""

    __tablename__ = "project_chunks"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # What kind of artifact this chunk came from. Allowed values in code:
    #   code_file | doc | jira_ticket | pr | commit | comment
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # Stable id of the source artifact (e.g. repo_files.id, jira_tickets.id,
    # pull_requests.id). Opaque string so we can point at rows or external ids.
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    repo_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    jira_ticket_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("jira_tickets.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Code-specific fields (first-class for filtering, not metadata).
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True, index=True)
    language: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    branch: Mapped[str | None] = mapped_column(String(128), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)

    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Free-form extras: PR review state, commit stats, Jira labels, etc.
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Ephemeral: populated by retrieval queries so callers can sort/limit.
    score: Mapped[float | None] = mapped_column(Float, nullable=True)

    embedding = mapped_column(EmbeddingType, nullable=True)

    __table_args__ = (
        Index("ix_project_chunks_project_source", "project_id", "source_type"),
        Index("ix_project_chunks_project_repo_path", "project_id", "repo_id", "file_path"),
    )
