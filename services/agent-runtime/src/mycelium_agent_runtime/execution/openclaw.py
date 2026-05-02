"""OpenClaw execution backend - delegates to OpenClaw API for production use.

This is a stub implementation ready for when API keys are available.
The interface matches LocalBackend so they can be swapped seamlessly.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from uuid import uuid4

import httpx

from mycelium_agent_runtime.actions.types import Action, ActionResult
from mycelium_agent_runtime.execution.result import ExecutionResult, ExecutionStatus

logger = logging.getLogger(__name__)

OPENCLAW_API_URL = os.getenv("OPENCLAW_API_URL", "https://api.openclaw.ai")
OPENCLAW_API_KEY = os.getenv("OPENCLAW_API_KEY", "")
CLAWORC_API_URL = os.getenv("CLAWORC_API_URL", "https://api.claworc.ai")
CLAWORC_API_KEY = os.getenv("CLAWORC_API_KEY", "")


class OpenClawBackend:
    """OpenClaw execution backend for production agent execution.

    Delegates task execution to OpenClaw's managed-agents API.
    Claworc manages agent instances per employee.

    This is a stub implementation - replace with real API calls when ready.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_url: str | None = None,
        claworc_api_key: str | None = None,
        claworc_api_url: str | None = None,
    ) -> None:
        self._api_key = api_key or OPENCLAW_API_KEY
        self._api_url = api_url or OPENCLAW_API_URL
        self._claworc_api_key = claworc_api_key or CLAWORC_API_KEY
        self._claworc_api_url = claworc_api_url or CLAWORC_API_URL
        self._executions: dict[str, ExecutionStatus] = {}
        self._http_client: httpx.AsyncClient | None = None

        if not self._api_key:
            logger.warning(
                "OpenClaw API key not configured. "
                "Set OPENCLAW_API_KEY environment variable."
            )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=30,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def execute_task(self, task: Any, context: dict) -> ExecutionResult:
        """Execute a task via OpenClaw API.

        In production, this would:
        1. POST to OpenClaw managed-agents API
        2. Poll for completion or use webhooks
        3. Return the result

        For now, returns a stub response.
        """
        execution_id = str(uuid4())
        self._executions[execution_id] = ExecutionStatus.RUNNING

        if not self._api_key:
            self._executions[execution_id] = ExecutionStatus.FAILED
            return ExecutionResult.failure(
                execution_id=execution_id,
                error="OpenClaw API key not configured",
            )

        task_id = task.task_id if hasattr(task, "task_id") else str(task)
        logger.info("Submitting task %s to OpenClaw (execution_id=%s)", task_id, execution_id)

        self._executions[execution_id] = ExecutionStatus.SUCCEEDED
        return ExecutionResult.success(
            execution_id=execution_id,
            result={
                "task_id": task_id,
                "openclaw_execution_id": execution_id,
                "stub": True,
                "message": "OpenClaw integration pending API key configuration",
            },
        )

    async def execute_action(self, action: Action) -> ActionResult:
        """Execute a single action via OpenClaw.

        In production, this would delegate to an OpenClaw agent instance.
        For now, returns a stub response.
        """
        if not self._api_key:
            return ActionResult.failure(
                action.id,
                "OpenClaw API key not configured",
            )

        logger.info(
            "Submitting action %s (%s) to OpenClaw",
            action.id,
            action.type.value,
        )

        return ActionResult.success(
            action.id,
            output=f"(OpenClaw stub) Action {action.type.value} would be executed",
            openclaw_action_id=str(uuid4()),
            stub=True,
        )

    async def get_status(self, execution_id: str) -> ExecutionStatus:
        """Get execution status from OpenClaw.

        In production, this would poll the OpenClaw API.
        """
        return self._executions.get(execution_id, ExecutionStatus.PENDING)

    async def cancel(self, execution_id: str) -> bool:
        """Cancel an execution via OpenClaw.

        In production, this would call the OpenClaw cancellation API.
        """
        if execution_id not in self._executions:
            return False

        if self._executions[execution_id] in (
            ExecutionStatus.SUCCEEDED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        ):
            return False

        logger.info("Cancelling OpenClaw execution: %s", execution_id)
        self._executions[execution_id] = ExecutionStatus.CANCELLED
        return True

    async def spawn_agent(self, owner_user_id: str) -> dict[str, Any]:
        """Spawn a new agent instance via Claworc.

        Claworc manages one agent instance per employee.

        In production, this would:
        1. POST to Claworc API to create/get an agent instance
        2. Return the agent ID and connection details

        For now, returns a stub response.
        """
        if not self._claworc_api_key:
            return {
                "error": "Claworc API key not configured",
                "stub": True,
            }

        agent_id = f"openclaw-agent-{owner_user_id}"
        logger.info("Spawning Claworc agent for user: %s", owner_user_id)

        return {
            "agent_id": agent_id,
            "owner_user_id": owner_user_id,
            "status": "spawned",
            "claworc_instance_id": str(uuid4()),
            "stub": True,
            "message": "Claworc integration pending API key configuration",
        }

    async def get_agent_status(self, agent_id: str) -> dict[str, Any]:
        """Get agent instance status from Claworc.

        In production, this would query the Claworc API.
        """
        return {
            "agent_id": agent_id,
            "status": "active",
            "stub": True,
        }
