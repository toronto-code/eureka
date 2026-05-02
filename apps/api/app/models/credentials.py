"""Integration credential rows.

GitHub PAT may be stored Fernet-encrypted in ``secret_ciphertext`` when
``MYCELIUM_CREDENTIALS_KEY`` is set; ``GITHUB_TOKEN`` env still overrides at runtime.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPKMixin


class IntegrationCredential(Base, UUIDPKMixin, TimestampMixin):
    """Integration rows + optional Fernet-encrypted PAT (GitHub).

    Plain tokens never appear in API responses — only ``secret_hint`` (last chars).
    """

    __tablename__ = "integration_credentials"

    integration: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="not_configured", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    secret_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    secret_hint: Mapped[str | None] = mapped_column(String(32), nullable=True)
