"""Observers for ``agents.results`` and ``workflows.approvals``.

When a human overrides or rejects an agent action we log a training signal.
This service is observe-only — it never publishes back to the bus.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from mycelium_db import get_session
from mycelium_db.models import LearningSignalRow
from mycelium_event_bus import EventBus, Topic
from mycelium_event_bus.bus import EventBusConfig

logger = logging.getLogger(__name__)


def _bus() -> EventBus:
    return EventBus(EventBusConfig(redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0")))


async def _record(signal_type: str, payload: dict[str, Any], *,
                  task_id: str | None, agent_id: str | None, correlation_id: str) -> None:
    async with get_session() as session:
        session.add(
            LearningSignalRow(
                id=str(uuid.uuid4()),
                task_id=task_id,
                agent_id=agent_id,
                signal_type=signal_type,
                correlation_id=correlation_id,
                payload=payload,
            )
        )


async def run_results_observer() -> None:
    bus = _bus()
    logger.info("learning results observer starting")

    async def handle(message_id: str, payload: dict[str, Any]) -> None:
        try:
            if payload.get("status") == "failed":
                await _record(
                    "agent_failed",
                    payload,
                    task_id=payload.get("task_id"),
                    agent_id=payload.get("agent_id"),
                    correlation_id=payload.get("correlation_id", ""),
                )
        finally:
            await bus.ack(Topic.AGENTS_RESULTS, "learning-results", message_id)

    await bus.consume(
        Topic.AGENTS_RESULTS,
        group="learning-results",
        consumer_name="learning-results-1",
        handler=handle,
    )


async def run_approvals_observer() -> None:
    bus = _bus()
    logger.info("learning approvals observer starting")

    async def handle(message_id: str, payload: dict[str, Any]) -> None:
        try:
            decision = payload.get("decision", "approve")
            signal_type = "human_override" if decision == "reject" else "human_approve"
            await _record(
                signal_type,
                payload,
                task_id=payload.get("workflow_id"),
                agent_id=None,
                correlation_id=payload.get("correlation_id", ""),
            )
        finally:
            await bus.ack(Topic.WORKFLOWS_APPROVALS, "learning-approvals", message_id)

    await bus.consume(
        Topic.WORKFLOWS_APPROVALS,
        group="learning-approvals",
        consumer_name="learning-approvals-1",
        handler=handle,
    )
