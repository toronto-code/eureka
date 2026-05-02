"""Agent run + agent action tables.

`agent_runs` supports parent-child relationships so the UI can visualise which
worker agents an orchestrator run spawned.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPKMixin


class AgentRun(Base, UUIDPKMixin, TimestampMixin):
    """A single invocation of any agent (orchestrator or worker)."""

    __tablename__ = "agent_runs"

    orchestrator_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_agent_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    spawned_by_agent_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )

    agent_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)

    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    full_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_data_subset_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    structured_output_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )

    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    model: Mapped[str] = mapped_column(String(64), default="gpt-4o", nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    actions: Mapped[list["AgentAction"]] = relationship(
        back_populates="agent_run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class AgentAction(Base, UUIDPKMixin, TimestampMixin):
    """A discrete action proposed (or executed) by an agent."""

    __tablename__ = "agent_actions"

    agent_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(32), default="READ_ONLY", nullable=False)
    requires_approval: Mapped[bool] = mapped_column(default=False, nullable=False)
    approval_status: Mapped[str] = mapped_column(
        String(32), default="NOT_REQUIRED", nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    agent_run: Mapped[AgentRun] = relationship(back_populates="actions")
