"""Lightweight ALTERs for existing Postgres volumes (no Alembic in MVP)."""

from __future__ import annotations

import logging

from sqlalchemy import text

from app.db.session import engine

logger = logging.getLogger(__name__)


def ensure_integration_credentials_secret_columns() -> None:
    """Add encrypted PAT columns if missing."""
    stmts = [
        "ALTER TABLE integration_credentials ADD COLUMN IF NOT EXISTS secret_ciphertext BYTEA",
        "ALTER TABLE integration_credentials ADD COLUMN IF NOT EXISTS secret_hint VARCHAR(32)",
    ]
    try:
        with engine.begin() as conn:
            for sql in stmts:
                conn.execute(text(sql))
    except Exception as exc:  # noqa: BLE001
        logger.warning("integration_credentials schema patch failed: %s", exc)
