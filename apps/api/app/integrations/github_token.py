"""Resolve GitHub PAT: ``GITHUB_TOKEN`` env wins over encrypted DB row."""

from __future__ import annotations

from app.config import get_settings
from app.db import SessionLocal
from app.services.github_pat_store import load_github_pat


def is_usable_github_token(token: str | None) -> bool:
    t = (token or "").strip()
    if not t:
        return False
    # Common placeholder values that appear in dev env wiring.
    if t in {"...", "***", "changeme", "replace-me"}:
        return False
    # PATs are much longer than this; short values are almost always placeholders.
    if len(t) < 20:
        return False
    return True


def resolve_github_token() -> str | None:
    settings = get_settings()
    env_tok = (settings.github_token or "").strip()
    if is_usable_github_token(env_tok):
        return env_tok
    try:
        with SessionLocal() as db:
            db_tok = load_github_pat(db, settings=settings)
            return db_tok if is_usable_github_token(db_tok) else None
    except Exception:  # noqa: BLE001 — DB down during startup
        return None
