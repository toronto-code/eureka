"""Jira entity snapshots.

Stored separately from the legacy `tasks` table so the new OL-based system
can evolve its schema without breaking the existing /tasks UI. Canonical
tickets for OL live here.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPKMixin


class JiraTicket(Base, UUIDPKMixin, TimestampMixin):
    """One Jira ticket, scoped to a project."""

    __tablename__ = "jira_tickets"
    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_jira_project_key"),)

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    assignee: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    assignee_email: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    assignee_account_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reporter: Mapped[str | None] = mapped_column(String(256), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(64), nullable=True)
    labels: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    last_jira_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
