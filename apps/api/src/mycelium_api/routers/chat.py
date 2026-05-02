"""POST /chat — routes prompts to the agent-runtime via agents.tasks."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from mycelium_api.auth import CurrentUser, get_current_user
from mycelium_api.event_bus_client import get_event_bus
from mycelium_event_bus import Topic
from mycelium_shared_types.correlation import derive_correlation_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    prompt: str
    agent_id: str | None = None
    correlation_id: str | None = None
    parent_correlation_id: str | None = None


class ChatResponse(BaseModel):
    task_id: str
    correlation_id: str
    status: str = "queued"
    message: str = "task dispatched"


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, user: CurrentUser = Depends(get_current_user)) -> ChatResponse:
    """Dispatch a chat prompt to the agent-runtime.

    The actual response is streamed back via /agents/{id}/tasks or via SSE on
    /observability — this endpoint just queues the work.
    """
    task_id = f"task-{uuid.uuid4()}"
    agent_id = req.agent_id or f"agent-{user.id}"
    correlation_id = req.correlation_id or derive_correlation_id(
        source="api.chat", object_id=task_id
    )

    payload: dict[str, Any] = {
        "task_id": task_id,
        "agent_id": agent_id,
        "agent_type": "chat",
        "input_data": {"prompt": req.prompt, "user_id": user.id},
        "correlation_id": correlation_id,
        "parent_correlation_id": req.parent_correlation_id,
        "status": "queued",
    }

    bus = get_event_bus()
    await bus.publish(Topic.AGENTS_TASKS, payload, correlation_id=correlation_id)
    logger.info("chat dispatched task=%s user=%s", task_id, user.id)
    return ChatResponse(task_id=task_id, correlation_id=correlation_id)
