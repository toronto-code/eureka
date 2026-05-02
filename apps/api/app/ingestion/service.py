"""High-level ingestion service.

Wraps the memory backend and adds:
- best-effort linking of new documents to existing tasks/repos/people based on
  simple text matching (Jira keys, repo names, @mentions),
- placeholders for future GitHub/Slack ingestion paths.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.parsers import parse_text_or_markdown
from app.memory import MemoryBackend, get_memory
from app.models import Entity, SourceDocument, Task

logger = logging.getLogger(__name__)


JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
SERVICE_RE = re.compile(r"\b\w+-service\b")
MENTION_RE = re.compile(r"@(\w+)")


class IngestionService:
    """Co-ordinates parse → memory.ingest → entity linking."""

    def __init__(self, memory: MemoryBackend | None = None) -> None:
        self.memory = memory or get_memory()

    def ingest_document(
        self,
        *,
        session: Session,
        source_type: str,
        title: str,
        content: bytes | str,
        source_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        project_key: str | None = None,
    ) -> str:
        text = parse_text_or_markdown(content)
        related_task_id = self._link_to_task(session, text)
        doc_id = self.memory.ingest_document(
            source_type=source_type,
            source_id=source_id,
            title=title,
            content=text,
            metadata=metadata or {},
            related_task_id=related_task_id,
            project_key=project_key,
        )
        self._link_lightweight_entities(text)
        return doc_id

    def list_documents(self, session: Session) -> list[SourceDocument]:
        return list(session.execute(select(SourceDocument).order_by(SourceDocument.created_at.desc())).scalars())

    def get_document(self, session: Session, doc_id: str) -> SourceDocument | None:
        return session.get(SourceDocument, doc_id)

    # ------------------------------------------------------------------
    # Linking helpers
    # ------------------------------------------------------------------

    def _link_to_task(self, session: Session, text: str) -> str | None:
        keys = JIRA_KEY_RE.findall(text or "")
        if not keys:
            return None
        for key in keys:
            task = session.execute(
                select(Task).where(Task.external_id == key)
            ).scalar_one_or_none()
            if task is not None:
                return task.id
        return None

    def _link_lightweight_entities(self, text: str) -> None:
        seen: set[tuple[str, str]] = set()
        for service in SERVICE_RE.findall(text or ""):
            key = ("service", service)
            if key in seen:
                continue
            seen.add(key)
            try:
                self.memory.create_entity("service", service, {})
            except Exception as exc:  # noqa: BLE001
                logger.debug("Failed to create service entity %s: %s", service, exc)
        for person in MENTION_RE.findall(text or ""):
            key = ("person", person)
            if key in seen:
                continue
            seen.add(key)
            try:
                self.memory.create_entity("person", person, {})
            except Exception as exc:  # noqa: BLE001
                logger.debug("Failed to create person entity %s: %s", person, exc)

    # ------------------------------------------------------------------
    # Placeholders for future integrations
    # ------------------------------------------------------------------

    def ingest_from_github(self, *_: Any, **__: Any) -> None:
        """Placeholder. Wire up `app.integrations.github` when ready."""
        raise NotImplementedError(
            "GitHub ingestion is a placeholder. See app/integrations/github.py."
        )

    def ingest_from_slack(self, *_: Any, **__: Any) -> None:
        """Placeholder. Slack/docs ingestion lands here when integration is added."""
        raise NotImplementedError(
            "Slack ingestion is a placeholder for the MVP. Add the integration when ready."
        )


def ingest_local_document(
    session: Session,
    *,
    title: str,
    content: bytes | str,
    project_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    return IngestionService().ingest_document(
        session=session,
        source_type="doc",
        title=title,
        content=content,
        project_key=project_key,
        metadata=metadata,
    )


def ingest_local_transcript(
    session: Session,
    *,
    title: str,
    content: bytes | str,
    metadata: dict[str, Any] | None = None,
) -> str:
    return IngestionService().ingest_document(
        session=session,
        source_type="transcript",
        title=title,
        content=content,
        metadata=metadata,
    )
