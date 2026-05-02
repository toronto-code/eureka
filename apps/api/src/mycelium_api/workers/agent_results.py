"""Consumes ``agents.results`` and updates AgentTask rows + audit log."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from mycelium_api.event_bus_client import get_event_bus
from mycelium_db import AgentTaskRow, AuditRow, get_session
from mycelium_event_bus import Topic
from mycelium_shared_types.agent import AgentTaskStatus
from mycelium_shared_types.transitions import is_valid_agent_task_transition

logger = logging.getLogger(__name__)


async def _handle(message_id: str, payload: dict[str, Any]) -> None:
    bus = get_event_bus()
    task_id = payload.get("task_id")
    new_status = payload.get("status")
    if not task_id or not new_status:
        await bus.ack(Topic.AGENTS_RESULTS, "api-results", message_id)
        return

    async with get_session() as session:
        row = (
            await session.execute(select(AgentTaskRow).where(AgentTaskRow.task_id == task_id))
        ).scalar_one_or_none()

        if row is None:
            logger.warning("agent result for unknown task %s", task_id)
            await bus.ack(Topic.AGENTS_RESULTS, "api-results", message_id)
            return

        try:
            current = AgentTaskStatus(row.status)
            target = AgentTaskStatus(new_status)
        except ValueError:
            logger.warning("invalid status transition for %s: %s -> %s",
                           task_id, row.status, new_status)
            await bus.ack(Topic.AGENTS_RESULTS, "api-results", message_id)
            return

        if not is_valid_agent_task_transition(current, target):
            logger.warning("forbidden transition %s -> %s for task %s",
                           current, target, task_id)
            await bus.ack(Topic.AGENTS_RESULTS, "api-results", message_id)
            return

        row.status = target.value
        row.result = payload.get("result")
        row.error = payload.get("error")
        row.updated_at = datetime.now(timezone.utc)

        session.add(
            AuditRow(
                id=str(uuid.uuid4()),
                agent_id=row.agent_id,
                task_id=task_id,
                action=f"task.{target.value}",
                actor_user_id=None,
                correlation_id=row.correlation_id,
                parent_correlation_id=row.parent_correlation_id,
                details={"result": payload.get("result"), "error": payload.get("error")},
            )
        )

    await bus.ack(Topic.AGENTS_RESULTS, "api-results", message_id)


async def run_agent_results_consumer() -> None:
    bus = get_event_bus()
    logger.info("agent-results consumer starting")
    await bus.consume(
        Topic.AGENTS_RESULTS,
        group="api-results",
        consumer_name="api-results-1",
        handler=_handle,
    )
