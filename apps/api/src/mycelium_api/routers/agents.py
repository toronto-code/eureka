"""GET /agents, POST /agents/{id}/tasks."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from mycelium_api.auth import CurrentUser, get_current_user
from mycelium_api.event_bus_client import get_event_bus
from mycelium_db import AgentRow, AgentTaskRow, get_session
from mycelium_event_bus import Topic
from mycelium_shared_types.correlation import derive_correlation_id

router = APIRouter(prefix="/agents", tags=["agents"])


class TaskCreate(BaseModel):
    agent_type: str = "triage"
    input_data: dict[str, Any] = {}
    correlation_id: str | None = None
    parent_correlation_id: str | None = None


@router.get("")
async def list_agents(user: CurrentUser = Depends(get_current_user)):
    async with get_session() as session:
        rows = (
            await session.execute(select(AgentRow).where(AgentRow.owner_user_id == user.id))
        ).scalars().all()
    return [
        {
            "id": r.id,
            "owner_user_id": r.owner_user_id,
            "capabilities": r.capabilities,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/{agent_id}/tasks")
async def create_task(
    agent_id: str,
    req: TaskCreate,
    user: CurrentUser = Depends(get_current_user),
):
    task_id = f"task-{uuid.uuid4()}"
    correlation_id = req.correlation_id or derive_correlation_id(
        source="api.agents", object_id=task_id
    )

    payload = {
        "task_id": task_id,
        "agent_id": agent_id,
        "agent_type": req.agent_type,
        "input_data": req.input_data,
        "correlation_id": correlation_id,
        "parent_correlation_id": req.parent_correlation_id,
        "status": "queued",
    }
    bus = get_event_bus()
    await bus.publish(Topic.AGENTS_TASKS, payload, correlation_id=correlation_id)
    return {"task_id": task_id, "correlation_id": correlation_id, "status": "queued"}


@router.get("/{agent_id}/tasks")
async def list_tasks(agent_id: str, user: CurrentUser = Depends(get_current_user)):
    async with get_session() as session:
        rows = (
            await session.execute(
                select(AgentTaskRow)
                .where(AgentTaskRow.agent_id == agent_id)
                .order_by(AgentTaskRow.created_at.desc())
                .limit(50)
            )
        ).scalars().all()
    return [
        {
            "task_id": r.task_id,
            "agent_id": r.agent_id,
            "agent_type": r.agent_type,
            "status": r.status,
            "correlation_id": r.correlation_id,
            "parent_correlation_id": r.parent_correlation_id,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
            "result": r.result,
            "error": r.error,
        }
        for r in rows
    ]
