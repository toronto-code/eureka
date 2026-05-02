"""Human approvals for risky agent actions."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPKMixin


class Approval(Base, UUIDPKMixin, TimestampMixin):
    """An approval record for a recommended agent action."""

    __tablename__ = "approvals"

    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), default="READ_ONLY", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="REQUIRED", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approver: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
