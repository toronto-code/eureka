"""Persist AgentTask (+ owning Agent row) before publishing to Redis.

The API ingestion consumer for ``agents.results`` only updates rows that
already exist; dispatch must insert ``queued`` tasks first."""

from __future__ import annotations

from fastapi import HTTPException

from mycelium_db import AgentRow, AgentTaskRow, get_session
from mycelium_event_bus import EventBus, Topic


async def ensure_agent_owned(
    session,
    *,
    agent_id: str,
    owner_user_id: str,
    default_capabilities: list[str],
) -> None:
    row = (
        await session.execute(select(AgentRow).where(AgentRow.id == agent_id))
    ).scalar_one_or_none()
    if row is None:
        session.add(
            AgentRow(
                id=agent_id,
                owner_user_id=owner_user_id,
                capabilities=default_capabilities,
                status="idle",
            )
        )
        return
    if row.owner_user_id != owner_user_id:
        raise HTTPException(status_code=403, detail="agent not accessible")


async def persist_and_publish_task(
    *,
    bus: EventBus,
    task_id: str,
    agent_id: str,
    agent_type: str,
    input_data: dict[str, Any],
    correlation_id: str,
    parent_correlation_id: str | None,
    owner_user_id: str,
    agent_capabilities_when_created: list[str],
) -> None:
    async with get_session() as session:
        await ensure_agent_owned(
            session,
            agent_id=agent_id,
            owner_user_id=owner_user_id,
            default_capabilities=agent_capabilities_when_created,
        )
        session.add(
            AgentTaskRow(
                task_id=task_id,
                agent_id=agent_id,
                agent_type=agent_type,
                input_data=input_data,
                correlation_id=correlation_id,
                parent_correlation_id=parent_correlation_id,
                status="queued",
            )
        )

    payload = {
        "task_id": task_id,
        "agent_id": agent_id,
        "agent_type": agent_type,
        "input_data": input_data,
        "correlation_id": correlation_id,
        "parent_correlation_id": parent_correlation_id,
        "status": "queued",
    }
    await bus.publish(Topic.AGENTS_TASKS, payload, correlation_id=correlation_id)
