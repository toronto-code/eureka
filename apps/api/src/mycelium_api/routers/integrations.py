"""GET /integrations, POST /integrations/ingest.

API is READ-ONLY on integration_syncs. Only services/integrations writes that
table. We never UPDATE/INSERT here.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from mycelium_api.auth import CurrentUser, get_current_user
from mycelium_api.event_bus_client import get_event_bus
from mycelium_db import IntegrationSyncRow, get_session
from mycelium_event_bus import Topic
from mycelium_shared_types.correlation import derive_correlation_id

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("")
async def list_syncs(user: CurrentUser = Depends(get_current_user)):
    async with get_session() as session:
        rows = (await session.execute(select(IntegrationSyncRow))).scalars().all()
    return [
        {
            "connector": r.connector,
            "last_sync_at": r.last_sync_at.isoformat() if r.last_sync_at else None,
            "status": r.status,
            "error_message": r.error_message,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


class IngestEvent(BaseModel):
    """Producer entrypoint for events that don't go via the bus directly.

    The API will publish to events.raw and assign a correlation_id fallback
    (rule 3) if the producer omits one.
    """

    id: str | None = None
    type: str
    source: str
    actor: dict[str, Any]
    object: dict[str, Any]
    timestamp: str | None = None
    schema_version: str = "1.0"
    metadata: dict[str, Any] = {}
    correlation_id: str | None = None
    parent_correlation_id: str | None = None


@router.post("/ingest")
async def ingest(req: IngestEvent, user: CurrentUser = Depends(get_current_user)):
    if not req.actor or not req.object:
        raise HTTPException(400, "actor and object are required")

    cid = req.correlation_id or derive_correlation_id(
        source=req.source, object_id=str(req.object.get("id", "unknown"))
    )

    payload = req.model_dump()
    payload["id"] = req.id or str(uuid.uuid4())
    payload["correlation_id"] = cid
    if not payload.get("timestamp"):
        from datetime import datetime, timezone
        payload["timestamp"] = datetime.now(timezone.utc).isoformat()

    bus = get_event_bus()
    await bus.publish(Topic.EVENTS_RAW, payload, correlation_id=cid)
    return {"id": payload["id"], "correlation_id": cid, "status": "accepted"}
