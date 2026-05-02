"""EventIngestionService: raw event persistence + project-memory updates.

Webhooks and polling both land here. Flow per event:

1. Resolve the project for this event (by repo full_name, jira project_key,
   or explicit project_id passed in).
2. Persist the raw event + normalized payload as a `project_events` row.
3. Delegate to `ProjectDataService.upsert_*` for the typed entity so
   canonical rows + chunks stay fresh.

Returning an IngestionResult means callers (webhook handlers, sync service)
can log / audit without re-reading the DB.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.github_normalizer import NormalizedEvent
from app.memory.project_data import ProjectDataService
from app.models import Project, ProjectEvent, Repository

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    event_id: str | None
    project_id: str | None
    entity_row_id: str | None
    chunks_written: int
    skipped_reason: str | None = None


class EventIngestionService:
    """Turns NormalizedEvents into persistent state."""

    def __init__(self, project_data: ProjectDataService | None = None) -> None:
        self.project_data = project_data or ProjectDataService()

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def ingest(
        self,
        session: Session,
        event: NormalizedEvent,
        *,
        project_id_override: str | None = None,
    ) -> IngestionResult:
        project = self._resolve_project(
            session, event, project_id_override=project_id_override
        )
        if project is None:
            return IngestionResult(
                event_id=None,
                project_id=None,
                entity_row_id=None,
                chunks_written=0,
                skipped_reason="no_matching_project",
            )

        row = ProjectEvent(
            project_id=project.id,
            source=event.source,
            event_type=event.event_type,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            actor=event.actor,
            delivery_id=event.delivery_id,
            raw_payload=event.raw_payload,
            normalized_payload=event.normalized_payload,
            origin=event.origin,
            occurred_at=event.occurred_at,
            ingested_at=datetime.now(tz=timezone.utc),
        )
        session.add(row)
        session.flush()

        try:
            entity_row_id, chunks_written = self._apply_to_memory(
                session, project_id=project.id, event=event
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Event ingestion failure: %s", exc)
            row.ingest_error = str(exc)[:1000]
            session.flush()
            return IngestionResult(
                event_id=row.id,
                project_id=project.id,
                entity_row_id=None,
                chunks_written=0,
                skipped_reason=f"apply_failed:{exc}",
            )

        return IngestionResult(
            event_id=row.id,
            project_id=project.id,
            entity_row_id=entity_row_id,
            chunks_written=chunks_written,
        )

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def _apply_to_memory(
        self, session: Session, *, project_id: str, event: NormalizedEvent
    ) -> tuple[str | None, int]:
        payload = event.normalized_payload or {}
        if event.source == "github":
            return self._apply_github(session, project_id, event, payload)
        if event.source == "jira":
            return self._apply_jira(session, project_id, event, payload)
        return None, 0

    def _apply_github(
        self,
        session: Session,
        project_id: str,
        event: NormalizedEvent,
        payload: dict[str, Any],
    ) -> tuple[str | None, int]:
        repo = self._resolve_repo(session, project_id, event)
        if repo is None:
            return None, 0

        if event.entity_type == "commit":
            res = self.project_data.upsert_commit(
                session,
                project_id=project_id,
                repo_id=repo.id,
                sha=payload.get("sha") or event.entity_id or "",
                message=payload.get("message"),
                author_name=payload.get("author_name"),
                author_email=payload.get("author_email"),
                branch=payload.get("branch"),
                html_url=payload.get("html_url"),
                committed_at=event.occurred_at,
            )
            return res.row_id, res.chunks_written

        if event.entity_type == "pull_request":
            res = self.project_data.upsert_pull_request(
                session,
                project_id=project_id,
                repo_id=repo.id,
                number=int(payload.get("number") or event.entity_id or 0),
                title=payload.get("title") or "(untitled PR)",
                body=payload.get("body"),
                state=payload.get("state") or "open",
                author=payload.get("author"),
                head_branch=payload.get("head_branch"),
                base_branch=payload.get("base_branch"),
                html_url=payload.get("html_url"),
                opened_at=_parse_iso(payload.get("opened_at")),
                merged_at=_parse_iso(payload.get("merged_at")),
                closed_at=_parse_iso(payload.get("closed_at")),
            )
            return res.row_id, res.chunks_written

        # Comments, reviews, issue openings → not typed tables yet; just the
        # raw event is persisted above. Return the project_events row we
        # already wrote.
        return None, 0

    def _apply_jira(
        self,
        session: Session,
        project_id: str,
        event: NormalizedEvent,
        payload: dict[str, Any],
    ) -> tuple[str | None, int]:
        if event.entity_type == "issue":
            res = self.project_data.upsert_jira_ticket(
                session,
                project_id=project_id,
                key=payload.get("key") or event.entity_id or "",
                title=payload.get("title") or "(untitled)",
                description=payload.get("description"),
                status=payload.get("status"),
                assignee=payload.get("assignee"),
                assignee_email=payload.get("assignee_email"),
                assignee_account_id=payload.get("assignee_account_id"),
                reporter=payload.get("reporter"),
                priority=payload.get("priority"),
                labels=payload.get("labels") or [],
                comments=payload.get("comments"),
                last_jira_updated_at=_parse_iso(payload.get("last_jira_updated_at")),
                raw_payload=event.raw_payload,
            )
            return res.row_id, res.chunks_written
        # Comment-only events re-chunk via the next issue update; nothing to do here.
        return None, 0

    # ------------------------------------------------------------------
    # Project / repo resolution
    # ------------------------------------------------------------------

    def _resolve_project(
        self,
        session: Session,
        event: NormalizedEvent,
        *,
        project_id_override: str | None,
    ) -> Project | None:
        if project_id_override:
            return session.get(Project, project_id_override)

        if event.source == "github" and event.repo_full_name:
            owner, _, name = event.repo_full_name.partition("/")
            repo = session.execute(
                select(Repository).where(
                    Repository.owner == owner, Repository.name == name
                )
            ).scalar_one_or_none()
            if repo:
                return session.get(Project, repo.project_id)

        if event.source == "jira":
            project_key = (event.normalized_payload or {}).get("project_key")
            if project_key:
                project = session.execute(
                    select(Project).where(Project.jira_project_key == project_key)
                ).scalar_one_or_none()
                if project:
                    return project

        return None

    def _resolve_repo(
        self, session: Session, project_id: str, event: NormalizedEvent
    ) -> Repository | None:
        if not event.repo_full_name:
            return None
        owner, _, name = event.repo_full_name.partition("/")
        return session.execute(
            select(Repository).where(
                Repository.project_id == project_id,
                Repository.owner == owner,
                Repository.name == name,
            )
        ).scalar_one_or_none()


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None
