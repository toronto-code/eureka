"""POST /chat — routes prompts to the agent-runtime via agents.tasks."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from mycelium_api.agent_dispatch import persist_and_publish_task
from mycelium_api.auth import CurrentUser, get_current_user
from mycelium_api.event_bus_client import get_event_bus
from mycelium_shared_types.correlation import derive_correlation_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

# Orchestrator + specialists the runtime may run under one logical agent
_CHAT_AGENT_CAPS = [
    "project_orchestrator",
    "chat",
    "summarize",
    "triage",
    "onboard",
    "reasoning",
    "plan",
]


class ChatRequest(BaseModel):
    prompt: str
    agent_id: str | None = None
    agent_type: str = Field(
        default="project_orchestrator",
        description="Skill name in agent-runtime. Use `chat` for the legacy echo stub.",
    )
    project_data: dict[str, Any] | None = Field(
        default=None,
        description="Optional whole-project bundle (placeholder until unified project API exists).",
    )
    correlation_id: str | None = None
    parent_correlation_id: str | None = None


class ChatResponse(BaseModel):
    task_id: str
    agent_id: str
    correlation_id: str
    status: str = "queued"
    message: str = "task dispatched"


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, user: CurrentUser = Depends(get_current_user)) -> ChatResponse:
    """Dispatch a chat prompt to the agent-runtime.

    Inserts ``agent_tasks`` (``queued``) before publishing — required so the API
    consumer on ``agents.results`` can persist outcomes. Poll
    ``GET /agents/{agent_id}/tasks/{task_id}`` for terminal status and ``result``.
    """
    task_id = f"task-{uuid.uuid4()}"
    agent_id = req.agent_id or f"agent-{user.id}"
    correlation_id = req.correlation_id or derive_correlation_id(
        source="api.chat", object_id=task_id
    )

    input_data: dict[str, Any] = {"prompt": req.prompt, "user_id": user.id}
    if req.project_data is not None:
        input_data["project_data"] = req.project_data

    bus = get_event_bus()
    await persist_and_publish_task(
        bus=bus,
        task_id=task_id,
        agent_id=agent_id,
        agent_type=req.agent_type,
        input_data=input_data,
        correlation_id=correlation_id,
        parent_correlation_id=req.parent_correlation_id,
        owner_user_id=user.id,
        agent_capabilities_when_created=_CHAT_AGENT_CAPS,
    )
    logger.info("chat dispatched task=%s user=%s", task_id, user.id)
    return ChatResponse(task_id=task_id, agent_id=agent_id, correlation_id=correlation_id)
