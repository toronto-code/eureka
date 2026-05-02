"""GitHub entity snapshots: Commit + PullRequest.

Stored separately from ProjectEvent so retrieval can filter on typed fields
without scanning the raw event payload.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPKMixin


class Commit(Base, UUIDPKMixin, TimestampMixin):
    """A Git commit observed via webhook or sync."""

    __tablename__ = "commits"
    __table_args__ = (UniqueConstraint("repo_id", "sha", name="uq_commit_repo_sha"),)

    repo_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sha: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    short_sha: Mapped[str | None] = mapped_column(String(16), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    author_email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(128), nullable=True)
    html_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    commit_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class PullRequest(Base, UUIDPKMixin, TimestampMixin):
    """A GitHub pull request snapshot."""

    __tablename__ = "pull_requests"
    __table_args__ = (UniqueConstraint("repo_id", "number", name="uq_pr_repo_number"),)

    repo_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    author: Mapped[str | None] = mapped_column(String(256), nullable=True)
    head_branch: Mapped[str | None] = mapped_column(String(256), nullable=True)
    base_branch: Mapped[str | None] = mapped_column(String(256), nullable=True)
    html_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pr_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
