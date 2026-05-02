"""GET /dashboard/web — rich integration data for the dashboard graph.

Returns repos, jira tickets, slack channels so the cytoscape network can show
the actual ecosystem the user is plugged into (matches the old mycelium UI).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends

from app.supabase_client import SupabaseUser, get_supabase_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/web")
async def web_data(user: SupabaseUser = Depends(get_supabase_user)) -> dict[str, Any]:
    from app.routes.chat_intel import fetch_github, fetch_slack, fetch_jira
    try:
        async with httpx.AsyncClient() as client:
            gh, slack, jira = await asyncio.gather(
                fetch_github(client, None),
                fetch_slack(client),
                fetch_jira(client),
            )
        channels = sorted({m["channel"] for m in (slack.get("messages") or [])})
        return {
            "repos": [{"owner": r["owner"], "name": r["name"], "language": r.get("language")} for r in gh.get("repos") or []][:12],
            "channels": channels[:10],
            "jira": [{"key": j["key"], "status": j.get("status"), "assignee": j.get("assignee")} for j in (jira or [])][:15],
        }
    except Exception as e:
        logger.warning("dashboard/web failed: %s", e)
        return {"repos": [], "channels": [], "jira": []}
