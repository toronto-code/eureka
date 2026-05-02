"""Memory abstraction + default Postgres+pgvector implementation.

The abstraction matches the "ingest / search / get_related_context / entity"
operations the orchestrator and ingestion services need. Concrete graph or
vector providers can implement the same surface later.
"""
from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.llm_client import OpenAIClient, get_llm_client
from app.models import (
    DocumentChunk,
    Entity,
    Relationship,
    SourceDocument,
)
from app.models.documents import HAS_PGVECTOR

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers: chunking
# ---------------------------------------------------------------------------


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 80) -> list[str]:
    """Naive whitespace-aware chunker.

    Avoids sentence-splitting libs to keep the MVP lightweight. Good enough for
    transcripts/READMEs in the demo path.
    """
    if not text:
        return []
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    step = max(1, chunk_size - overlap)
    for start in range(0, len(words), step):
        end = min(len(words), start + chunk_size)
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
    return chunks


# ---------------------------------------------------------------------------
# Backend protocol
# ---------------------------------------------------------------------------


class _SessionFactory(Protocol):
    def __call__(self) -> Session: ...


class MemoryBackend(ABC):
    """Abstract memory backend."""

    @abstractmethod
    def ingest_document(
        self,
        *,
        source_type: str,
        source_id: str | None,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        related_task_id: str | None = None,
        project_key: str | None = None,
    ) -> str:
        """Ingest a document and return its id."""

    @abstractmethod
    def search(
        self, query: str, *, filters: dict[str, Any] | None = None, top_k: int = 5
    ) -> list[dict[str, Any]]:
        """Return scored chunks matching the query."""

    @abstractmethod
    def get_related_context(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        """Return chunks/entities that look relevant to the given task."""

    @abstractmethod
    def create_entity(
        self, entity_type: str, name: str, metadata: dict[str, Any] | None = None
    ) -> str: ...

    @abstractmethod
    def create_relationship(
        self,
        source_entity: str,
        relation: str,
        target_entity: str,
        metadata: dict[str, Any] | None = None,
    ) -> str: ...


# ---------------------------------------------------------------------------
# PostgreSQL backend
# ---------------------------------------------------------------------------


class PostgresMemoryBackend(MemoryBackend):
    """Default backend using Postgres + (optional) pgvector.

    If pgvector + an OpenAI key are both available, embeddings are stored and
    cosine similarity is used for search. Otherwise falls back to plain
    `LIKE` lexical search.
    """

    def __init__(
        self,
        session_factory: _SessionFactory,
        llm: OpenAIClient | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._llm = llm or get_llm_client()

    # -- ingest ----------------------------------------------------------

    def ingest_document(
        self,
        *,
        source_type: str,
        source_id: str | None,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        related_task_id: str | None = None,
        project_key: str | None = None,
    ) -> str:
        with self._session_factory() as session:
            doc = SourceDocument(
                source_type=source_type,
                source_id=source_id,
                title=title,
                content=content,
                doc_metadata=metadata or {},
                related_task_id=related_task_id,
                project_key=project_key,
            )
            session.add(doc)
            session.flush()
            for idx, piece in enumerate(chunk_text(content)):
                embedding = self._embed(piece) if HAS_PGVECTOR else None
                chunk = DocumentChunk(
                    document_id=doc.id,
                    chunk_index=idx,
                    content=piece,
                    token_count=len(piece.split()),
                    embedding=embedding,
                    chunk_metadata={"source_type": source_type, "title": title},
                )
                session.add(chunk)
            session.commit()
            return doc.id

    def _embed(self, text: str) -> list[float] | None:
        if not self._llm.configured:
            return None
        vec = self._llm.generate_embedding(text)
        return vec or None

    # -- search ---------------------------------------------------------

    def search(
        self, query: str, *, filters: dict[str, Any] | None = None, top_k: int = 5
    ) -> list[dict[str, Any]]:
        if not query:
            return []
        with self._session_factory() as session:
            if HAS_PGVECTOR and self._llm.configured:
                vec = self._llm.generate_embedding(query)
                if vec:
                    return self._vector_search(session, vec, top_k)
            return self._lexical_search(session, query, top_k)

    def _vector_search(
        self, session: Session, vec: list[float], top_k: int
    ) -> list[dict[str, Any]]:
        try:
            stmt = (
                select(DocumentChunk)
                .where(DocumentChunk.embedding.is_not(None))
                .order_by(DocumentChunk.embedding.cosine_distance(vec))
                .limit(top_k)
            )
            rows = session.execute(stmt).scalars().all()
            return [self._chunk_to_hit(c, score=None) for c in rows]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vector search failed, falling back to lexical: %s", exc)
            return self._lexical_search(session, "", top_k)

    def _lexical_search(
        self, session: Session, query: str, top_k: int
    ) -> list[dict[str, Any]]:
        like = f"%{query}%"
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.content.ilike(like))
            .limit(top_k)
        )
        rows = session.execute(stmt).scalars().all()
        if not rows:
            stmt2 = select(DocumentChunk).limit(top_k)
            rows = session.execute(stmt2).scalars().all()
        return [self._chunk_to_hit(c, score=None) for c in rows]

    @staticmethod
    def _chunk_to_hit(chunk: DocumentChunk, *, score: float | None) -> dict[str, Any]:
        return {
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "score": score if score is not None else math.nan,
            "metadata": chunk.chunk_metadata or {},
        }

    # -- related context ------------------------------------------------

    def get_related_context(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        title = task.get("title") or task.get("summary") or ""
        return self.search(title, top_k=5)

    # -- entities + relationships --------------------------------------

    def create_entity(
        self, entity_type: str, name: str, metadata: dict[str, Any] | None = None
    ) -> str:
        with self._session_factory() as session:
            entity = Entity(entity_type=entity_type, name=name, entity_metadata=metadata or {})
            session.add(entity)
            session.commit()
            return entity.id

    def create_relationship(
        self,
        source_entity: str,
        relation: str,
        target_entity: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        with self._session_factory() as session:
            rel = Relationship(
                source_entity_id=source_entity,
                target_entity_id=target_entity,
                relation=relation,
                relation_metadata=metadata or {},
            )
            session.add(rel)
            session.commit()
            return rel.id


# ---------------------------------------------------------------------------
# Accessor
# ---------------------------------------------------------------------------


_memory: MemoryBackend | None = None


def get_memory() -> MemoryBackend:
    """Return the default memory backend (lazily constructed)."""
    global _memory
    if _memory is None:
        from app.db import SessionLocal

        _memory = PostgresMemoryBackend(session_factory=SessionLocal)
    return _memory
