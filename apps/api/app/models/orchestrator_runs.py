"""OrchestratorRun: one end-to-end OL run.

Purpose-built for the OL-based system. Captures the full audit trail required
by the spec (classification, retrieval plan, directives, lane, results) in
typed columns so the UI and operators can browse without JSON diving.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPKMixin


class OrchestratorRun(Base, UUIDPKMixin, TimestampMixin):
    """A single OL run from user-request -> lane result."""

    __tablename__ = "orchestrator_runs"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Where the request came from
    #   manual | jira_webhook | jira_polling | github_webhook | github_polling | api
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="manual", index=True)
    origin_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Optional anchors (any/all may be null)
    jira_ticket_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("jira_tickets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    repo_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    triggering_event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("project_events.id", ondelete="SET NULL"), nullable=True
    )

    user_request: Mapped[str] = mapped_column(Text, nullable=False)

    # --- OL classifier output --------------------------------------
    route: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    retrieval_plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    worker_directives: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    retrieved_chunk_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    # --- Lane execution --------------------------------------------
    lane_used: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    lane_status: Mapped[str | None] = mapped_column(String(32), nullable=True)  # pending|running|completed|blocked|error
    lane_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # --- External artefacts ----------------------------------------
    pr_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    jira_comment_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Run lifecycle ---------------------------------------------
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Free-form extras (model name, token counts, lane-specific metrics, …)
    run_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
