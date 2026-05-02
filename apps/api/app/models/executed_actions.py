"""ExecutedAction: a record of a real write Mycelium actually performed.

Each row represents ONE real external side-effect (GitHub PR, Jira comment,
Jira transition). Never used to replay actions — purely an audit/observability
log with URLs so operators can trace what the bot did.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPKMixin


class ExecutedAction(Base, UUIDPKMixin, TimestampMixin):
    """One real side-effect performed by an agent (GitHub PR, Jira comment, …)."""

    __tablename__ = "executed_actions"

    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Categorisation
    integration: Mapped[str] = mapped_column(String(32), nullable=False)  # github | jira
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)  # create_branch | create_file | open_pr | post_comment | transition
    status: Mapped[str] = mapped_column(String(32), default="succeeded", nullable=False)
    dry_run: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Human-readable + URL for the UI
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    target_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Full request/response shape for debugging
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
