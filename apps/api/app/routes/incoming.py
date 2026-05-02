"""Incoming Data — live view of what the agents are pulling from integrations.

This route aggregates data from:
  - GitHub (commits, PRs, issues, repos) via chat_intel.fetch_github
  - Slack (messages, channels, users) via chat_intel.fetch_slack
  - Jira (issues) via chat_intel.fetch_jira
  - Observer events (local git activity) via chat_intel.fetch_observer_events

Nothing is mutated here — this is purely a read-only window into the live
context the orchestrator and agents see on every turn.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.routes.chat_intel import (
    fetch_github,
    fetch_jira,
    fetch_observer_events,
    fetch_slack,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/incoming", tags=["incoming"])


class IncomingSourceSummary(BaseModel):
    """High-level health/status for one source."""

    ok: bool
    configured: bool
    item_count: int
    reason: str | None = None


class IncomingOverviewResponse(BaseModel):
    fetched_at: str
    github: dict[str, Any]
    slack: dict[str, Any]
    jira: dict[str, Any]
    observer: dict[str, Any]
    summary: dict[str, IncomingSourceSummary]


def _is_github_configured() -> bool:
    return bool(
        os.getenv("GITHUB_TOKEN", "").strip()
        and (os.getenv("GITHUB_OWNER", "").strip() or os.getenv("GITHUB_ORG", "").strip())
        and os.getenv("GITHUB_REPO", "").strip()
    )


def _is_slack_configured() -> bool:
    return bool(os.getenv("SLACK_TOKEN", "").strip())


def _is_jira_configured() -> bool:
    has_primary = bool(
        os.getenv("JIRA_BASE_URL", "").strip()
        and os.getenv("JIRA_EMAIL", "").strip()
        and os.getenv("JIRA_API_TOKEN", "").strip()
    )
    has_alt = bool(
        os.getenv("JIRA_DOMAIN", "").strip()
        and os.getenv("JIRA_EMAIL", "").strip()
        and os.getenv("JIRA_TOKEN", "").strip()
    )
    return has_primary or has_alt


@router.get("/overview", response_model=IncomingOverviewResponse)
async def incoming_overview() -> IncomingOverviewResponse:
    """Aggregate a live snapshot from every configured integration."""
    gh_configured = _is_github_configured()
    slack_configured = _is_slack_configured()
    jira_configured = _is_jira_configured()

    gh_data: dict[str, Any] = {"repos": [], "commits": [], "prs": [], "issues": []}
    slack_data: dict[str, Any] = {"messages": [], "user_map": {}}
    jira_issues: list[dict[str, Any]] = []
    observer_events: list[dict[str, Any]] = []
    gh_err: str | None = None
    slack_err: str | None = None
    jira_err: str | None = None

    async with httpx.AsyncClient() as client:
        coros = []
        if gh_configured:
            coros.append(("github", fetch_github(client, None)))
        if slack_configured:
            coros.append(("slack", fetch_slack(client)))
        if jira_configured:
            coros.append(("jira", fetch_jira(client)))
        coros.append(("observer", fetch_observer_events()))

        results = await asyncio.gather(
            *(c[1] for c in coros), return_exceptions=True
        )

        for (name, _), result in zip(coros, results):
            if isinstance(result, Exception):
                logger.warning("incoming %s fetch failed: %s", name, result)
                if name == "github":
                    gh_err = str(result)
                elif name == "slack":
                    slack_err = str(result)
                elif name == "jira":
                    jira_err = str(result)
                continue
            if name == "github":
                gh_data = result  # type: ignore[assignment]
            elif name == "slack":
                slack_data = result  # type: ignore[assignment]
            elif name == "jira":
                jira_issues = result  # type: ignore[assignment]
            elif name == "observer":
                observer_events = result  # type: ignore[assignment]

    summary: dict[str, IncomingSourceSummary] = {
        "github": IncomingSourceSummary(
            ok=gh_configured and gh_err is None,
            configured=gh_configured,
            item_count=len(gh_data.get("commits", [])) + len(gh_data.get("prs", [])) + len(gh_data.get("issues", [])),
            reason=gh_err
            or (None if gh_configured else "GITHUB_TOKEN + GITHUB_OWNER + GITHUB_REPO required."),
        ),
        "slack": IncomingSourceSummary(
            ok=slack_configured and slack_err is None,
            configured=slack_configured,
            item_count=len(slack_data.get("messages", [])),
            reason=slack_err
            or (None if slack_configured else "SLACK_TOKEN is not set."),
        ),
        "jira": IncomingSourceSummary(
            ok=jira_configured and jira_err is None,
            configured=jira_configured,
            item_count=len(jira_issues),
            reason=jira_err
            or (None if jira_configured else "JIRA_BASE_URL + JIRA_EMAIL + JIRA_API_TOKEN required."),
        ),
        "observer": IncomingSourceSummary(
            ok=True,
            configured=True,
            item_count=len(observer_events),
            reason=None if observer_events else "No local git activity recorded yet. Run the observer service to populate.",
        ),
    }

    return IncomingOverviewResponse(
        fetched_at=datetime.now(timezone.utc).isoformat(),
        github=gh_data,
        slack=slack_data,
        jira={"issues": jira_issues},
        observer={"events": observer_events},
        summary=summary,
    )
