"""Consume ``workflows.approvals`` decisions and resume paused tasks.

Flow:
    1. Worker detects action needing approval, publishes PENDING_APPROVAL
       and an approval request to workflows.approvals (decision="requested").
    2. UI shows the pending action; user approves/rejects via
       POST /workflows/approvals.
    3. That publishes a decision (approve|reject) to workflows.approvals.
    4. This consumer picks up the decision:
       - approve: re-publishes the task to agents.tasks with
         ``auto_approve_action_ids`` so the guard auto-allows previously
         pending actions.
       - reject: publishes FAILED result for the task.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from mycelium_event_bus import EventBus, Topic
from mycelium_event_bus.bus import EventBusConfig
from mycelium_shared_types.agent import AgentTaskStatus

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


def _bus() -> EventBus:
    return EventBus(EventBusConfig(redis_url=REDIS_URL))


async def _publish_task_failed(
    bus: EventBus,
    task_id: str,
    agent_id: str | None,
    correlation_id: str,
    reason: str,
) -> None:
    payload = {
        "task_id": task_id,
        "agent_id": agent_id,
        "status": AgentTaskStatus.FAILED.value,
        "result": None,
        "error": f"Rejected by approval: {reason}",
        "correlation_id": correlation_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await bus.publish(Topic.AGENTS_RESULTS, payload, correlation_id=correlation_id)


async def _republish_task(
    bus: EventBus,
    task_id: str,
    agent_id: str | None,
    correlation_id: str,
    approved_action_ids: list[str],
    original_input: dict[str, Any] | None = None,
    agent_type: str | None = None,
) -> None:
    """Re-publish the task to agents.tasks with approved actions pre-authorized."""
    payload = {
        "task_id": task_id,
        "agent_id": agent_id,
        "agent_type": agent_type or "chat",
        "input_data": {
            **(original_input or {}),
            "auto_approve_action_ids": approved_action_ids,
        },
        "correlation_id": correlation_id,
        "status": AgentTaskStatus.QUEUED.value,
        "resumed_from_approval": True,
    }
    await bus.publish(Topic.AGENTS_TASKS, payload, correlation_id=correlation_id)


async def run_approvals_consumer() -> None:
    """Consume approval decisions from workflows.approvals.

    Only processes messages with decision in {"approve", "reject"}.
    Ignores "requested" (which we publish ourselves).
    """
    bus = _bus()
    logger.info("agent-runtime approvals consumer starting")

    async def handle(message_id: str, payload: dict[str, Any]) -> None:
        try:
            decision = payload.get("decision")

            if decision not in ("approve", "reject"):
                return

            workflow_id = payload.get("workflow_id")
            task_id = payload.get("task_id") or workflow_id
            if not task_id:
                logger.warning("Approval decision missing task_id: %s", payload)
                return

            correlation_id = payload.get("correlation_id", "")
            agent_id = payload.get("agent_id")

            logger.info(
                "Processing approval decision: task=%s decision=%s",
                task_id,
                decision,
            )

            if decision == "reject":
                await _publish_task_failed(
                    bus,
                    task_id=task_id,
                    agent_id=agent_id,
                    correlation_id=correlation_id,
                    reason=payload.get("notes") or "rejected by reviewer",
                )
                return

            approved_action_ids = [
                a["action_id"]
                for a in payload.get("pending_actions", [])
                if isinstance(a, dict) and a.get("action_id")
            ]
            if not approved_action_ids and payload.get("approved_action_ids"):
                approved_action_ids = payload["approved_action_ids"]

            await _republish_task(
                bus,
                task_id=task_id,
                agent_id=agent_id,
                correlation_id=correlation_id,
                approved_action_ids=approved_action_ids,
                original_input=payload.get("original_input"),
                agent_type=payload.get("agent_type"),
            )
            logger.info("Task resumed: %s (approved %d actions)", task_id, len(approved_action_ids))

        finally:
            await bus.ack(Topic.WORKFLOWS_APPROVALS, "agent-runtime-approvals", message_id)

    await bus.consume(
        Topic.WORKFLOWS_APPROVALS,
        group="agent-runtime-approvals",
        consumer_name="agent-runtime-approvals-1",
        handler=handle,
    )
