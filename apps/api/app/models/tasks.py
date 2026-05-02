"""Local mirror of Jira-style tasks."""
from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPKMixin


class Task(Base, UUIDPKMixin, TimestampMixin):
    """A unit of work, mirrored from Jira (or seeded for the demo)."""

    __tablename__ = "tasks"

    external_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="jira", nullable=False)
    project_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="To Do", nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reporter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    labels: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    priority: Mapped[str | None] = mapped_column(String(32), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    approval_status: Mapped[str] = mapped_column(
        String(32), default="NOT_REQUIRED", nullable=False
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
