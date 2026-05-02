"""Execution backend protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from mycelium_agent_runtime.actions.types import Action, ActionResult
    from mycelium_agent_runtime.execution.result import ExecutionResult, ExecutionStatus
    from mycelium_shared_types import AgentTask


class ExecutionBackend(Protocol):
    """Protocol for execution backends.

    Backends handle the actual execution of agent tasks and individual actions.
    Implementations can run locally or delegate to external services like OpenClaw.
    """

    async def execute_task(
        self, task: AgentTask, context: dict
    ) -> ExecutionResult:
        """Execute an entire agent task.

        Args:
            task: The agent task to execute
            context: Additional context (knowledge graph data, etc.)

        Returns:
            ExecutionResult with the outcome
        """
        ...

    async def execute_action(self, action: Action) -> ActionResult:
        """Execute a single action.

        Args:
            action: The action to execute

        Returns:
            ActionResult with the outcome
        """
        ...

    async def get_status(self, execution_id: str) -> ExecutionStatus:
        """Get the status of an execution.

        Args:
            execution_id: The ID of the execution to check

        Returns:
            Current ExecutionStatus
        """
        ...

    async def cancel(self, execution_id: str) -> bool:
        """Cancel an execution.

        Args:
            execution_id: The ID of the execution to cancel

        Returns:
            True if cancelled, False if not found or already complete
        """
        ...
