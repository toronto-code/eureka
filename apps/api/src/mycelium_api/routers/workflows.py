"""GET /workflows, POST /workflows/approvals."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from mycelium_api.auth import CurrentUser, get_current_user
from mycelium_api.event_bus_client import get_event_bus
from mycelium_event_bus import Topic
from mycelium_shared_types.correlation import derive_correlation_id

router = APIRouter(prefix="/workflows", tags=["workflows"])


class ApprovalRequest(BaseModel):
    workflow_id: str
    decision: str  # "approve" | "reject"
    correlation_id: str | None = None
    parent_correlation_id: str | None = None
    notes: str | None = None


# In-memory placeholder. Real implementation reads from Postgres.
_FAKE_WORKFLOWS: list[dict[str, Any]] = []


@router.get("")
async def list_workflows(user: CurrentUser = Depends(get_current_user)):
    return _FAKE_WORKFLOWS


@router.post("/approvals")
async def submit_approval(req: ApprovalRequest, user: CurrentUser = Depends(get_current_user)):
    cid = req.correlation_id or derive_correlation_id(
        source="api.workflows", object_id=req.workflow_id, natural_id=req.workflow_id
    )
    payload = {
        "id": str(uuid.uuid4()),
        "workflow_id": req.workflow_id,
        "decision": req.decision,
        "actor_user_id": user.id,
        "correlation_id": cid,
        "parent_correlation_id": req.parent_correlation_id,
        "notes": req.notes,
    }
    bus = get_event_bus()
    await bus.publish(Topic.WORKFLOWS_APPROVALS, payload, correlation_id=cid)
    return {"status": "submitted", "correlation_id": cid}
