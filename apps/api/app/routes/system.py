"""System / health / settings routes."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto_credentials import fernet_from_settings
from app.db import get_db
from app.schemas.api import IntegrationDiagnostic, IntegrationStatusOut
from app.services.github_pat_store import github_pat_row

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _github_diagnostic(
    *, token_present: bool, env_token: bool, pat_saved: bool,
    owner: str | None, repo: str | None,
) -> IntegrationDiagnostic:
    now = datetime.now(timezone.utc)
    missing: list[str] = []
    if not token_present:
        missing.append("GITHUB_TOKEN (or encrypted PAT via Settings)")
    if not owner:
        missing.append("GITHUB_OWNER")
    if not repo:
        missing.append("GITHUB_REPO")
    if not missing:
        source = "encrypted PAT in database" if (pat_saved and not env_token) else "GITHUB_TOKEN env"
        return IntegrationDiagnostic(
            ok=True,
            status="operational",
            missing=[],
            detail=f"Authenticated via {source}. Pulling from {owner}/{repo}.",
            last_checked_at=now,
        )
    return IntegrationDiagnostic(
        ok=False,
        status="not_configured",
        missing=missing,
        detail="GitHub integration is not fully configured. Set the variables above to start pulling commits, PRs, and issues.",
        last_checked_at=now,
    )


def _jira_diagnostic() -> IntegrationDiagnostic:
    now = datetime.now(timezone.utc)
    base_url = os.getenv("JIRA_BASE_URL", "").strip()
    email = os.getenv("JIRA_EMAIL", "").strip()
    token = os.getenv("JIRA_API_TOKEN", "").strip()
    # chat_intel.py uses JIRA_DOMAIN/JIRA_TOKEN as an alternate scheme — accept either.
    alt_domain = os.getenv("JIRA_DOMAIN", "").strip()
    alt_token = os.getenv("JIRA_TOKEN", "").strip()
    has_primary = bool(base_url and email and token)
    has_alt = bool(alt_domain and email and alt_token)

    missing: list[str] = []
    if not (base_url or alt_domain):
        missing.append("JIRA_BASE_URL (or JIRA_DOMAIN)")
    if not email:
        missing.append("JIRA_EMAIL")
    if not (token or alt_token):
        missing.append("JIRA_API_TOKEN (or JIRA_TOKEN)")

    if has_primary or has_alt:
        host = base_url or f"https://{alt_domain}"
        return IntegrationDiagnostic(
            ok=True,
            status="operational",
            missing=[],
            detail=f"Authenticated as {email} against {host}. Pulling issues via JQL.",
            last_checked_at=now,
        )
    return IntegrationDiagnostic(
        ok=False,
        status="not_configured",
        missing=missing,
        detail="Jira integration is not configured. Set JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN.",
        last_checked_at=now,
    )


def _slack_diagnostic() -> IntegrationDiagnostic:
    now = datetime.now(timezone.utc)
    token = os.getenv("SLACK_TOKEN", "").strip()
    if not token:
        return IntegrationDiagnostic(
            ok=False,
            status="not_configured",
            missing=["SLACK_TOKEN"],
            detail="Slack integration requires a bot/user token with conversations.history, users.list, and channels.read scopes.",
            last_checked_at=now,
        )
    # Format sanity check — Slack tokens start with xox?-
    if not token.startswith("xox"):
        return IntegrationDiagnostic(
            ok=False,
            status="error",
            missing=[],
            detail="SLACK_TOKEN is set but does not look like a valid Slack token (expected it to start with 'xox').",
            last_checked_at=now,
        )
    return IntegrationDiagnostic(
        ok=True,
        status="operational",
        missing=[],
        detail="Authenticated via SLACK_TOKEN. Pulling public channel history and file metadata.",
        last_checked_at=now,
    )


def _openai_diagnostic() -> IntegrationDiagnostic:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if not settings.openai_configured:
        return IntegrationDiagnostic(
            ok=False,
            status="not_configured",
            missing=["OPENAI_API_KEY"],
            detail="OpenAI is required for agent reasoning and summarisation.",
            last_checked_at=now,
        )
    return IntegrationDiagnostic(
        ok=True,
        status="operational",
        missing=[],
        detail=f"Default model: {settings.openai_default_model}.",
        last_checked_at=now,
    )


def _database_diagnostic(session: Session) -> IntegrationDiagnostic:
    now = datetime.now(timezone.utc)
    try:
        session.execute(text("SELECT 1"))
        return IntegrationDiagnostic(
            ok=True,
            status="operational",
            missing=[],
            detail="Postgres + pgvector reachable.",
            last_checked_at=now,
        )
    except Exception as exc:  # noqa: BLE001
        return IntegrationDiagnostic(
            ok=False,
            status="error",
            missing=[],
            detail=f"Database unreachable: {exc!s}",
            last_checked_at=now,
        )


@router.get("/settings/integrations", response_model=IntegrationStatusOut)
def integration_status(session: Session = Depends(get_db)) -> IntegrationStatusOut:
    settings = get_settings()
    db_diag = _database_diagnostic(session)

    row = github_pat_row(session)
    pat_saved = bool(row and row.secret_ciphertext)
    env_token = bool((settings.github_token or "").strip())
    token_present = env_token or pat_saved
    owner = settings.effective_github_owner
    github_ready = token_present and bool(owner and settings.github_repo)
    pat_hint = row.secret_hint if pat_saved else None

    github_diag = _github_diagnostic(
        token_present=token_present,
        env_token=env_token,
        pat_saved=pat_saved,
        owner=owner,
        repo=settings.github_repo,
    )
    jira_diag = _jira_diagnostic()
    slack_diag = _slack_diagnostic()
    openai_diag = _openai_diagnostic()

    return IntegrationStatusOut(
        openai=settings.openai_configured,
        jira=jira_diag.ok,
        github=github_ready,
        slack=slack_diag.ok,
        database=db_diag.ok,
        bot_jira_user=settings.mycelium_bot_jira_user,
        auto_execute_enabled=settings.bot_auto_execute_enabled,
        github_real_mode=github_ready and settings.mycelium_allow_real_github,
        jira_watcher_enabled=settings.jira_watcher_enabled,
        github_pat_storage_enabled=bool(fernet_from_settings(settings)),
        github_pat_saved_in_database=pat_saved,
        github_pat_hint=pat_hint,
        diagnostics={
            "github": github_diag,
            "jira": jira_diag,
            "slack": slack_diag,
            "openai": openai_diag,
            "database": db_diag,
        },
    )


@router.get("/settings/project_data")
def current_project_data() -> dict[str, Any]:
    """Return the seeded project_data preview (used by the Ingestion page)."""
    from app.seed import build_demo_project_data

    return build_demo_project_data().model_dump()


@router.get("/observability")
def observability_summary(session: Session = Depends(get_db)) -> dict[str, Any]:
    """Return system observability status."""
    from datetime import datetime, timezone

    settings = get_settings()
    
    # Check database
    db_status = "ok"
    try:
        session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_status = "error"
    
    # Check integrations
    integrations = {
        "openai": "ok" if settings.openai_configured else "not_configured",
        "github": "ok" if settings.effective_github_owner and settings.github_repo else "not_configured",
        "jira": "ok" if settings.jira_configured else "not_configured",
    }
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": [
            {"service": "database", "status": db_status},
            {"service": "api", "status": "ok"},
        ],
        "integrations": integrations,
        "watchers": {
            "jira_watcher": {
                "enabled": settings.jira_watcher_enabled,
                "interval": settings.jira_watcher_interval_seconds,
            },
        },
        "config": {
            "auto_execute": settings.bot_auto_execute_enabled,
            "github_real_mode": settings.mycelium_allow_real_github,
        },
    }
