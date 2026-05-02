"""Resolve GitHub PAT: ``GITHUB_TOKEN`` env wins over encrypted DB row."""

from __future__ import annotations

from app.config import get_settings
from app.db import SessionLocal
from app.services.github_pat_store import load_github_pat


def resolve_github_token() -> str | None:
    settings = get_settings()
    env_tok = (settings.github_token or "").strip()
    if env_tok:
        return env_tok
    try:
        with SessionLocal() as db:
            return load_github_pat(db, settings=settings)
    except Exception:  # noqa: BLE001 — DB down during startup
        return None
