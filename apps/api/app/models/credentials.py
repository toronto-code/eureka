"""Placeholder integration credentials.

For now we never store real secrets in DB. This table simply records which
integrations are configured + last-known status; real tokens stay in `.env`.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPKMixin


class IntegrationCredential(Base, UUIDPKMixin, TimestampMixin):
    """A non-secret-bearing placeholder for future integration metadata."""

    __tablename__ = "integration_credentials"

    integration: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="not_configured", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
