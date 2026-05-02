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
    from mycelium_agent_runtime.learning_client import LearningClient

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


def _create_executor(
    backend: ExecutionBackend,
    learning_client: LearningClient | None = None,
) -> ActionExecutor:
    """Create the action executor with permission guard."""
    from mycelium_agent_runtime.actions.executor import ActionExecutor
    from mycelium_agent_runtime.permissions import PermissionGuard, get_default_rules

    guard = PermissionGuard(rules=get_default_rules())
    return ActionExecutor(
        backend=backend,
        guard=guard,
        learning_client=learning_client,
    )


def _create_learning_client() -> LearningClient | None:
    """Create the learning client, or None if disabled."""
    from mycelium_agent_runtime.learning_client import LearningClient, LEARNING_ENABLED

    if not LEARNING_ENABLED:
        return None
    return LearningClient()


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


def _is_pending_approval(result: dict[str, Any] | None, executor: ActionExecutor) -> bool:
    """Detect whether a skill result or execution history indicates pending approval."""
    if isinstance(result, dict) and result.get("pending_approval"):
        return True

    for _action, action_result in executor.get_history():
        if action_result.metadata.get("pending_approval"):
            return True

    return False


def _extract_pending_actions(executor: ActionExecutor) -> list[dict[str, Any]]:
    """Extract pending approval actions from executor history."""
    pending: list[dict[str, Any]] = []
    for action, action_result in executor.get_history():
        if action_result.metadata.get("pending_approval"):
            pending.append({
                "action_id": action.id,
                "type": action.type.value,
                "payload": action.payload,
                "reasoning": action.reasoning,
                "reason": action_result.metadata.get("reason"),
            })
    return pending


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


async def _publish_approval_request(
    bus: EventBus,
    task: dict[str, Any],
    pending_actions: list[dict[str, Any]],
) -> None:
    """Publish an approval request on workflows.approvals.

    Uses `decision="requested"` to distinguish from approve/reject decisions
    published by the API. Downstream consumers (UI, Julian's orchestration)
    can present the pending actions to a human for approval.
    """
    payload = {
        "id": f"approval-{task['task_id']}",
        "workflow_id": task["task_id"],
        "decision": "requested",
        "task_id": task["task_id"],
        "agent_id": task.get("agent_id"),
        "pending_actions": pending_actions,
        "correlation_id": task["correlation_id"],
        "parent_correlation_id": task.get("parent_correlation_id"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await bus.publish(
        Topic.WORKFLOWS_APPROVALS, payload, correlation_id=task["correlation_id"]
    )


async def run_task_worker(
    backend: ExecutionBackend | None = None,
    executor: ActionExecutor | None = None,
    learning_client: LearningClient | None = None,
) -> None:
    """Run the agent task worker.

    Args:
        backend: Optional execution backend (creates default if not provided)
        executor: Optional action executor (creates default if not provided)
        learning_client: Optional learning client (creates default if not provided)
    """
    bus = _bus()

    if backend is None:
        backend = _create_backend()

    if learning_client is None:
        learning_client = _create_learning_client()

    if executor is None:
        executor = _create_executor(backend, learning_client=learning_client)

    logger.info(
        "agent-runtime worker starting (backend=%s, learning=%s)",
        type(backend).__name__,
        "on" if learning_client and learning_client.enabled else "off",
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

            input_data = payload.get("input_data") or {}
            auto_approve_ids = input_data.get("auto_approve_action_ids") or []
            if auto_approve_ids:
                executor.set_auto_approve_action_ids(auto_approve_ids)
                logger.info(
                    "Task %s has %d pre-approved actions",
                    task_id,
                    len(auto_approve_ids),
                )

            executor.set_user_id(input_data.get("user_id"))

            context = await _query_knowledge(input_data.get("prompt", ""))
            result = await _execute(payload, executor, context)

            if _is_pending_approval(result, executor):
                pending_actions = _extract_pending_actions(executor)
                enriched_result = {
                    **(result if isinstance(result, dict) else {}),
                    "pending_actions": pending_actions,
                    "pending_approval": True,
                    "resume_instructions": (
                        "POST /workflows/approvals with workflow_id=<task_id> and decision=approve|reject "
                        "to unblock this task."
                    ),
                }
                await _publish_result(
                    bus, payload, AgentTaskStatus.PENDING_APPROVAL, enriched_result, None
                )
                await _publish_approval_request(bus, payload, pending_actions)
                logger.info(
                    "Task pending approval: %s (%d actions)",
                    task_id,
                    len(pending_actions),
                )
            else:
                await _publish_result(bus, payload, AgentTaskStatus.SUCCEEDED, result, None)
                logger.info("Task succeeded: %s", task_id)

            executor.clear_history()
            executor.clear_auto_approve()
            executor.set_user_id(None)

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
