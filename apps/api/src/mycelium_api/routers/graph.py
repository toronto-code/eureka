"""GET /graph — proxies to services/knowledge with security filter applied."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from mycelium_api.auth import CurrentUser, get_current_user
from mycelium_api.config import KNOWLEDGE_URL
from mycelium_security_filter import QueryContext, SecurityFilter, SensitivityLevel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/graph", tags=["graph"])

_filter = SecurityFilter.from_env()


@router.get("")
async def get_graph(
    limit: int = Query(50, ge=1, le=500),
    depth: int = Query(2, ge=1, le=5),
    node_id: str | None = Query(None),
    user: CurrentUser = Depends(get_current_user),
):
    """Query the knowledge graph.

    Security enforcement for user-facing queries lives in this gateway — it's
    applied to the response before returning it to the user.
    """
    params = {"limit": limit, "depth": depth}
    if node_id:
        params["node_id"] = node_id

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f"{KNOWLEDGE_URL}/graph", params=params)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("knowledge service unreachable: %s", exc)
            return {"nodes": [], "edges": [], "warning": "knowledge service unavailable"}

    data = r.json()
    ctx = QueryContext(user_id=user.id, role=user.role, clearance=SensitivityLevel.INTERNAL)
    nodes = _filter.filter(data.get("nodes", []), context=ctx).allowed
    edges = _filter.filter(data.get("edges", []), context=ctx).allowed
    return {"nodes": nodes, "edges": edges}
