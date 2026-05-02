"""Project + Repository + RepoFile models.

A **Project** is the top-level container that binds one or more Repositories and
one or more Jira ticket sources together under a single searchable memory.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPKMixin


class Project(Base, UUIDPKMixin, TimestampMixin):
    """Top-level project container: binds repos + Jira project + docs together."""

    __tablename__ = "projects"

    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    jira_project_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    project_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    repositories: Mapped[list["Repository"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )


class Repository(Base, UUIDPKMixin, TimestampMixin):
    """One Git repository bound to a project."""

    __tablename__ = "repositories"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), default="github", nullable=False)
    owner: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(128), default="main", nullable=False)
    # GitHub App installation id (when the App flow is wired in). Until then,
    # auth falls back to the PAT in settings.
    installation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    html_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    repo_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    project: Mapped[Project] = relationship(back_populates="repositories")
    files: Mapped[list["RepoFile"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan", lazy="noload"
    )


class RepoFile(Base, UUIDPKMixin, TimestampMixin):
    """A known file in a repo at a particular commit.

    We don't mirror the full repo tree — only files we've chunked/embedded or
    files referenced by an orchestrator run. New versions of a file create a new
    row so history is preserved.
    """

    __tablename__ = "repo_files"

    repo_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(128), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    repository: Mapped[Repository] = relationship(back_populates="files")
