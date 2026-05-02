"""GET /graph — backed by Neo4j via mycelium_knowledge.graph.store."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from mycelium_knowledge.graph.store import query_subgraph
from mycelium_security_filter import QueryContext, SecurityFilter, SensitivityLevel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["graph"])

# Defense-in-depth: agent queries also pass through the filter here.
_filter = SecurityFilter.from_env()


@router.get("/graph")
async def get_graph(
    limit: int = Query(50, ge=1, le=500),
    depth: int = Query(2, ge=1, le=5),
    node_id: str | None = Query(None),
    via_agent: bool = Query(False, description="Set true when called by agent-runtime"),
    agent_user_id: str | None = Query(None, description="Owner of the calling agent."),
):
    try:
        snapshot = await query_subgraph(limit=limit, depth=depth, node_id=node_id)
    except Exception as exc:
        logger.warning("neo4j unavailable, returning empty: %s", exc)
        return {"nodes": [], "edges": [], "warning": "neo4j unavailable"}

    if via_agent and agent_user_id:
        ctx = QueryContext(user_id=agent_user_id, role="agent",
                           clearance=SensitivityLevel.INTERNAL, via_agent=True)
        snapshot["nodes"] = _filter.filter(snapshot["nodes"], context=ctx).allowed
        snapshot["edges"] = _filter.filter(snapshot["edges"], context=ctx).allowed

    return snapshot
