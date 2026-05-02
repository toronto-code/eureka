"""RetrievalService: hybrid search over `project_chunks`.

Combines:
- pgvector cosine similarity (when the DB has it + a query vector)
- keyword / full-text scoring (ILIKE-based; Postgres-portable + SQLite-friendly)
- explicit filters (source_type, repo_id, file_path, jira_ticket_id)
- recent activity bias (small boost for recently-updated rows)

Embeddings alone are not enough for code — lexical signal (symbol / path /
identifier matches) is first-class. Results get a blended score and callers
can ask for the top-N plus a per-source cap so no single artefact dominates.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.memory.embeddings import EmbeddingService, get_embedding_service
from app.models import ProjectChunk

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Public shapes
# -----------------------------------------------------------------------------


@dataclass
class RetrievalQuery:
    project_id: str
    text: str = ""
    source_types: list[str] = field(default_factory=list)
    file_paths: list[str] = field(default_factory=list)
    repo_ids: list[str] = field(default_factory=list)
    jira_ticket_ids: list[str] = field(default_factory=list)
    max_chunks: int = 10
    recency_bias: bool = True
    per_source_cap: int = 5
    include_embedding: bool = True


@dataclass
class RetrievedChunk:
    id: str
    project_id: str
    source_type: str
    source_id: str | None
    repo_id: str | None
    jira_ticket_id: str | None
    file_path: str | None
    language: str | None
    start_line: int | None
    end_line: int | None
    branch: str | None
    commit_sha: str | None
    chunk_text: str
    score: float
    semantic_score: float
    keyword_score: float
    recency_score: float
    chunk_metadata: dict[str, Any]
    updated_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "repo_id": self.repo_id,
            "jira_ticket_id": self.jira_ticket_id,
            "file_path": self.file_path,
            "language": self.language,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "branch": self.branch,
            "commit_sha": self.commit_sha,
            "chunk_text": self.chunk_text,
            "score": self.score,
            "semantic_score": self.semantic_score,
            "keyword_score": self.keyword_score,
            "recency_score": self.recency_score,
            "chunk_metadata": self.chunk_metadata,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# -----------------------------------------------------------------------------
# Service
# -----------------------------------------------------------------------------


_CODE_SCORE_WEIGHT = 1.2
_DEFAULT_SEMANTIC_WEIGHT = 0.55
_DEFAULT_KEYWORD_WEIGHT = 0.40
_DEFAULT_RECENCY_WEIGHT = 0.05


class RetrievalService:
    """Hybrid search over project_chunks."""

    def __init__(self, embeddings: EmbeddingService | None = None) -> None:
        self._embeddings = embeddings or get_embedding_service()

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def search(
        self, session: Session, query: RetrievalQuery
    ) -> list[RetrievedChunk]:
        """Execute the hybrid query. Returns results sorted by blended score."""
        # 1. Pull a candidate pool that satisfies filters. Keep this wide but
        #    bounded so we can re-rank in Python without loading everything.
        candidates = self._load_candidates(session, query)
        if not candidates:
            return []

        # 2. Score each candidate.
        query_vec = self._embed_query(query.text) if query.text else []
        keyword_tokens = _keyword_tokens(query.text)

        scored: list[RetrievedChunk] = []
        now = datetime.now(tz=timezone.utc)
        for row in candidates:
            semantic = self._cosine(query_vec, _as_vector(row.embedding))
            keyword = _keyword_score(row, keyword_tokens)
            recency = _recency_score(row.updated_at, now) if query.recency_bias else 0.0
            base = (
                _DEFAULT_SEMANTIC_WEIGHT * semantic
                + _DEFAULT_KEYWORD_WEIGHT * keyword
                + _DEFAULT_RECENCY_WEIGHT * recency
            )
            # Code wins ties on pure lexical matches.
            if row.source_type == "code_file" and keyword > 0:
                base *= _CODE_SCORE_WEIGHT
            scored.append(
                RetrievedChunk(
                    id=row.id,
                    project_id=row.project_id,
                    source_type=row.source_type,
                    source_id=row.source_id,
                    repo_id=row.repo_id,
                    jira_ticket_id=row.jira_ticket_id,
                    file_path=row.file_path,
                    language=row.language,
                    start_line=row.start_line,
                    end_line=row.end_line,
                    branch=row.branch,
                    commit_sha=row.commit_sha,
                    chunk_text=row.chunk_text,
                    score=round(base, 6),
                    semantic_score=round(semantic, 6),
                    keyword_score=round(keyword, 6),
                    recency_score=round(recency, 6),
                    chunk_metadata=row.chunk_metadata or {},
                    updated_at=row.updated_at,
                )
            )

        scored.sort(key=lambda c: c.score, reverse=True)
        return self._apply_per_source_cap(scored, query)

    # ------------------------------------------------------------------
    # Candidate load (DB-side filtering)
    # ------------------------------------------------------------------

    def _load_candidates(
        self, session: Session, query: RetrievalQuery
    ) -> Sequence[ProjectChunk]:
        stmt = select(ProjectChunk).where(ProjectChunk.project_id == query.project_id)
        if query.source_types:
            stmt = stmt.where(ProjectChunk.source_type.in_(query.source_types))
        if query.repo_ids:
            stmt = stmt.where(ProjectChunk.repo_id.in_(query.repo_ids))
        if query.jira_ticket_ids:
            stmt = stmt.where(
                ProjectChunk.jira_ticket_id.in_(query.jira_ticket_ids)
            )
        if query.file_paths:
            # Path prefix OR glob-ish match.
            path_clauses = [ProjectChunk.file_path.ilike(p.rstrip("*") + "%")
                            for p in query.file_paths]
            stmt = stmt.where(or_(*path_clauses))

        # If we have a query text, add a cheap ILIKE shortlist so we don't
        # scan everything. Semantic re-rank still runs over the shortlist.
        if query.text:
            tokens = _keyword_tokens(query.text)[:6]
            if tokens:
                text_clauses = [
                    ProjectChunk.chunk_text.ilike(f"%{t}%") for t in tokens
                ]
                path_clauses = [
                    ProjectChunk.file_path.ilike(f"%{t}%") for t in tokens
                ]
                stmt = stmt.where(
                    or_(
                        *text_clauses,
                        *(c for c in path_clauses if c is not None),
                    )
                )

        # Bound the pool; vector rerank happens in Python.
        stmt = stmt.order_by(ProjectChunk.updated_at.desc()).limit(
            max(query.max_chunks * 8, 80)
        )
        return session.execute(stmt).scalars().all()

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _embed_query(self, text: str) -> list[float]:
        try:
            return self._embeddings.embed(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Query embedding failed: %s", exc)
            return []

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return max(0.0, min(1.0, dot / (na * nb)))

    def _apply_per_source_cap(
        self, scored: list[RetrievedChunk], query: RetrievalQuery
    ) -> list[RetrievedChunk]:
        out: list[RetrievedChunk] = []
        per_source: dict[str, int] = {}
        for chunk in scored:
            if per_source.get(chunk.source_type, 0) >= query.per_source_cap:
                continue
            out.append(chunk)
            per_source[chunk.source_type] = per_source.get(chunk.source_type, 0) + 1
            if len(out) >= query.max_chunks:
                break
        return out


# -----------------------------------------------------------------------------
# Module-level helpers
# -----------------------------------------------------------------------------


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _keyword_tokens(text: str) -> list[str]:
    """Lowercased alphanumeric tokens, sorted by (length desc, occurrence)."""
    if not text:
        return []
    seen: dict[str, int] = {}
    for match in _TOKEN_RE.findall(text):
        low = match.lower()
        if len(low) < 3 or low in _STOPWORDS:
            continue
        seen[low] = seen.get(low, 0) + 1
    return sorted(seen.keys(), key=lambda t: (-len(t), -seen[t]))


_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "have",
    "has", "had", "are", "was", "were", "been", "being", "but", "not",
    "any", "can", "will", "would", "should", "could", "all", "new", "use",
    "used", "using", "see", "also", "just", "get", "got", "set", "make",
    "made", "about", "over", "onto", "our", "your", "their",
}


def _keyword_score(row: ProjectChunk, tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    haystack_parts: list[str] = []
    if row.chunk_text:
        haystack_parts.append(row.chunk_text.lower())
    if row.file_path:
        haystack_parts.append(row.file_path.lower())
    haystack = " \n ".join(haystack_parts)
    hits = sum(1 for t in tokens if t in haystack)
    return min(1.0, hits / max(1, len(tokens)))


def _recency_score(updated_at: datetime | None, now: datetime) -> float:
    if not updated_at:
        return 0.0
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    age = now - updated_at
    if age < timedelta(hours=1):
        return 1.0
    if age < timedelta(days=1):
        return 0.8
    if age < timedelta(days=7):
        return 0.5
    if age < timedelta(days=30):
        return 0.25
    return 0.0


def _as_vector(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, list):
        return [float(x) for x in value]
    # pgvector returns an array-like; convert.
    try:
        return [float(x) for x in value]
    except Exception:  # noqa: BLE001
        return []
