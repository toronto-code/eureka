"""ProjectEvent: raw + normalised GitHub/Jira events.

Every webhook hit and every polled entity goes through this table. The raw
payload is preserved for replay/audit; the normalised payload is what the
event-ingestion step reads.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPKMixin


class ProjectEvent(Base, UUIDPKMixin, TimestampMixin):
    """Raw + normalised event from GitHub or Jira."""

    __tablename__ = "project_events"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # github | jira
    # Event type: for GitHub the X-GitHub-Event + action ("push", "pull_request.opened",
    # "issue_comment.created"). For Jira the webhookEvent name ("jira:issue_updated").
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # Entity this event is about: "commit" | "pull_request" | "issue" | "comment" | "review"
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    actor: Mapped[str | None] = mapped_column(String(256), nullable=True)
    delivery_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=False, index=True
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    normalized_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    origin: Mapped[str] = mapped_column(String(32), default="webhook", nullable=False)  # webhook | polling | manual
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingest_error: Mapped[str | None] = mapped_column(Text, nullable=True)
