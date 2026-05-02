"""Source documents and their embedding-friendly chunks."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPKMixin

logger = logging.getLogger(__name__)

# Optional pgvector column. We import lazily so the package imports cleanly even
# if pgvector isn't installed; falling back to JSON in that case keeps the
# schema usable with vanilla Postgres.
try:
    from pgvector.sqlalchemy import Vector  # type: ignore

    EMBEDDING_DIM = 1536
    EmbeddingType: Any = Vector(EMBEDDING_DIM)
    HAS_PGVECTOR = True
except Exception:  # noqa: BLE001
    EmbeddingType = JSON
    HAS_PGVECTOR = False
    logger.debug("pgvector not available; embeddings stored as JSON.")


class SourceDocument(Base, UUIDPKMixin, TimestampMixin):
    """A file or transcript ingested into Mycelium."""

    __tablename__ = "source_documents"

    source_type: Mapped[str] = mapped_column(String(64), nullable=False)  # doc | transcript | repo_file
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    project_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    related_task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    doc_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class DocumentChunk(Base, UUIDPKMixin, TimestampMixin):
    """An individual chunk of a SourceDocument, suitable for embedding/search."""

    __tablename__ = "document_chunks"

    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding = mapped_column(EmbeddingType, nullable=True)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)

    document: Mapped[SourceDocument] = relationship(back_populates="chunks")
