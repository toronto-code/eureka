"""SQLAlchemy ORM models. Mirror the Pydantic schemas in mycelium-shared-types."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# events  — sole writer: apps/api ingestion worker
# ---------------------------------------------------------------------------


class EventRow(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String, index=True)
    source: Mapped[str] = mapped_column(String, index=True)
    actor: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    object: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    schema_version: Mapped[str] = mapped_column(String, default="1.0")
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    correlation_id: Mapped[str] = mapped_column(String, index=True)
    parent_correlation_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    __table_args__ = (
        Index("ix_events_type_timestamp", "type", "timestamp"),
        Index("ix_events_source_timestamp", "source", "timestamp"),
    )


# ---------------------------------------------------------------------------
# integration_syncs — sole writer: services/integrations
# ---------------------------------------------------------------------------


class IntegrationSyncRow(Base):
    __tablename__ = "integration_syncs"

    connector: Mapped[str] = mapped_column(String, primary_key=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, default="ok")  # "ok" | "error"
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


# ---------------------------------------------------------------------------
# agents / agent_tasks
# ---------------------------------------------------------------------------


class AgentRow(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String, index=True)
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="idle")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AgentTaskRow(Base):
    __tablename__ = "agent_tasks"

    task_id: Mapped[str] = mapped_column(String, primary_key=True)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agents.id"), index=True)
    agent_type: Mapped[str] = mapped_column(String, index=True)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    correlation_id: Mapped[str] = mapped_column(String, index=True)
    parent_correlation_id: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[str] = mapped_column(String, default="queued", index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# audit_log
# ---------------------------------------------------------------------------


class AuditRow(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    task_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    correlation_id: Mapped[str] = mapped_column(String, index=True)
    parent_correlation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


# ---------------------------------------------------------------------------
# learning_signals — written by services/learning when a human overrides an agent
# ---------------------------------------------------------------------------


class LearningSignalRow(Base):
    __tablename__ = "learning_signals"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    signal_type: Mapped[str] = mapped_column(String, index=True)  # "override" | "approve" | "reject"
    correlation_id: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
