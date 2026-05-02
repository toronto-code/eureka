"""Consumes ``agents.tasks``, runs the appropriate skill, and publishes
to ``agents.results``. Knowledge graph queries go via HTTP — never direct DB.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from mycelium_agent_runtime.skills import registry
from mycelium_event_bus import EventBus, Topic
from mycelium_event_bus.bus import EventBusConfig
from mycelium_shared_types.agent import AgentTaskStatus

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
KNOWLEDGE_URL = os.getenv("KNOWLEDGE_URL", "http://knowledge:8001")


def _bus() -> EventBus:
    return EventBus(EventBusConfig(redis_url=REDIS_URL))


async def _query_knowledge(prompt: str) -> dict[str, Any]:
    """Query the knowledge service over HTTP. Stub-friendly."""
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            r = await client.get(f"{KNOWLEDGE_URL}/graph", params={"limit": 10})
            return r.json()
        except Exception as exc:
            logger.warning("knowledge unreachable: %s", exc)
            return {"nodes": [], "edges": []}


async def _execute(task: dict[str, Any]) -> dict[str, Any]:
    skill_name = task.get("agent_type", "summarize")
    skill = registry.get(skill_name) or registry.get("summarize")
    assert skill is not None
    context = await _query_knowledge(task.get("input_data", {}).get("prompt", ""))
    result = await skill.handler({**task.get("input_data", {}), "knowledge": context})
    return result


async def _publish_result(bus: EventBus, task: dict[str, Any], status: AgentTaskStatus,
                          result: dict[str, Any] | None, error: str | None) -> None:
    payload = {
        "task_id": task["task_id"],
        "agent_id": task.get("agent_id"),
        "status": status.value,
        "result": result,
        "error": error,
        "correlation_id": task["correlation_id"],
        "parent_correlation_id": task.get("parent_correlation_id"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await bus.publish(Topic.AGENTS_RESULTS, payload, correlation_id=task["correlation_id"])


async def run_task_worker() -> None:
    bus = _bus()
    logger.info("agent-runtime worker starting")

    async def handle(message_id: str, payload: dict[str, Any]) -> None:
        if not payload.get("correlation_id") or not payload.get("task_id"):
            await bus.ack(Topic.AGENTS_TASKS, "agent-runtime", message_id)
            return
        try:
            await _publish_result(bus, payload, AgentTaskStatus.RUNNING, None, None)
            result = await _execute(payload)
            await _publish_result(bus, payload, AgentTaskStatus.SUCCEEDED, result, None)
        except Exception as exc:
            logger.exception("task failed: %s", payload.get("task_id"))
            await _publish_result(bus, payload, AgentTaskStatus.FAILED, None, str(exc))
        finally:
            await bus.ack(Topic.AGENTS_TASKS, "agent-runtime", message_id)

    await bus.consume(
        Topic.AGENTS_TASKS,
        group="agent-runtime",
        consumer_name="agent-runtime-1",
        handler=handle,
    )
