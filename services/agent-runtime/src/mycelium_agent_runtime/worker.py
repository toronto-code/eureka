"""Consumes ``agents.tasks``, runs the appropriate skill, and publishes
to ``agents.results``. Knowledge graph queries go via HTTP — never direct DB.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

import httpx

from mycelium_agent_runtime.skills import registry
from mycelium_event_bus import EventBus, Topic
from mycelium_event_bus.bus import EventBusConfig
from mycelium_shared_types.agent import AgentTaskStatus

if TYPE_CHECKING:
    from mycelium_agent_runtime.execution.backend import ExecutionBackend
    from mycelium_agent_runtime.actions.executor import ActionExecutor

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
KNOWLEDGE_URL = os.getenv("KNOWLEDGE_URL", "http://knowledge:8001")
EXECUTION_BACKEND = os.getenv("EXECUTION_BACKEND", "local")
WORKING_DIRECTORY = os.getenv("WORKING_DIRECTORY", "/tmp/agent-workspace")


def _bus() -> EventBus:
    return EventBus(EventBusConfig(redis_url=REDIS_URL))


def _create_backend() -> ExecutionBackend:
    """Create the execution backend based on environment config."""
    from mycelium_agent_runtime.execution.local import LocalBackend

    if EXECUTION_BACKEND == "openclaw":
        from mycelium_agent_runtime.execution.openclaw import OpenClawBackend

        api_key = os.getenv("OPENCLAW_API_KEY", "")
        api_url = os.getenv("OPENCLAW_API_URL", "https://api.openclaw.ai")
        return OpenClawBackend(api_key=api_key, api_url=api_url)

    return LocalBackend(working_directory=WORKING_DIRECTORY)


def _create_executor(backend: ExecutionBackend) -> ActionExecutor:
    """Create the action executor with permission guard."""
    from mycelium_agent_runtime.actions.executor import ActionExecutor
    from mycelium_agent_runtime.permissions import PermissionGuard, get_default_rules

    guard = PermissionGuard(rules=get_default_rules())
    return ActionExecutor(backend=backend, guard=guard)


async def _query_knowledge(prompt: str) -> dict[str, Any]:
    """Query the knowledge service over HTTP. Stub-friendly."""
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            r = await client.get(f"{KNOWLEDGE_URL}/graph", params={"limit": 10})
            return r.json()
        except Exception as exc:
            logger.warning("knowledge unreachable: %s", exc)
            return {"nodes": [], "edges": []}


async def _execute(
    task: dict[str, Any],
    executor: ActionExecutor,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Execute a task using the skill registry and action executor."""
    skill_name = task.get("agent_type", "summarize")
    skill = registry.get(skill_name)

    if skill is None:
        skill = registry.get("summarize")

    if skill is None:
        return {"error": f"No skill found for: {skill_name}"}

    input_data = {**task.get("input_data", {}), "knowledge": context}

    if hasattr(skill, "execute"):
        result = await skill.execute(input_data, context, executor)
    else:
        result = await skill.handler(input_data)

    return result


async def _publish_result(
    bus: EventBus,
    task: dict[str, Any],
    status: AgentTaskStatus,
    result: dict[str, Any] | None,
    error: str | None,
) -> None:
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


async def run_task_worker(
    backend: ExecutionBackend | None = None,
    executor: ActionExecutor | None = None,
) -> None:
    """Run the agent task worker.

    Args:
        backend: Optional execution backend (creates default if not provided)
        executor: Optional action executor (creates default if not provided)
    """
    bus = _bus()

    if backend is None:
        backend = _create_backend()

    if executor is None:
        executor = _create_executor(backend)

    logger.info(
        "agent-runtime worker starting (backend=%s)",
        type(backend).__name__,
    )

    async def handle(message_id: str, payload: dict[str, Any]) -> None:
        if not payload.get("correlation_id") or not payload.get("task_id"):
            logger.warning("Dropping task without correlation_id or task_id")
            await bus.ack(Topic.AGENTS_TASKS, "agent-runtime", message_id)
            return

        task_id = payload.get("task_id")
        logger.info("Processing task: %s", task_id)

        try:
            await _publish_result(bus, payload, AgentTaskStatus.RUNNING, None, None)

            context = await _query_knowledge(
                payload.get("input_data", {}).get("prompt", "")
            )
            result = await _execute(payload, executor, context)

            executor.clear_history()

            await _publish_result(bus, payload, AgentTaskStatus.SUCCEEDED, result, None)
            logger.info("Task succeeded: %s", task_id)

        except Exception as exc:
            logger.exception("Task failed: %s", task_id)
            await _publish_result(bus, payload, AgentTaskStatus.FAILED, None, str(exc))

        finally:
            await bus.ack(Topic.AGENTS_TASKS, "agent-runtime", message_id)

    await bus.consume(
        Topic.AGENTS_TASKS,
        group="agent-runtime",
        consumer_name="agent-runtime-1",
        handler=handle,
    )
