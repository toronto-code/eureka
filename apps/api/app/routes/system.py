"""System / health / settings routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.schemas.api import IntegrationStatusOut

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/settings/integrations", response_model=IntegrationStatusOut)
def integration_status(session: Session = Depends(get_db)) -> IntegrationStatusOut:
    settings = get_settings()
    db_ok = True
    try:
        session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False
    return IntegrationStatusOut(
        openai=settings.openai_configured,
        jira=settings.jira_configured,
        github=settings.github_configured,
        database=db_ok,
        bot_jira_user=settings.mycelium_bot_jira_user,
        auto_execute_enabled=settings.bot_auto_execute_enabled,
        github_real_mode=settings.github_configured and settings.mycelium_allow_real_github,
        jira_watcher_enabled=settings.jira_watcher_enabled,
    )


@router.get("/settings/project_data")
def current_project_data() -> dict[str, Any]:
    """Return the seeded project_data preview (used by the Ingestion page)."""
    from app.seed import build_demo_project_data

    return build_demo_project_data().model_dump()
