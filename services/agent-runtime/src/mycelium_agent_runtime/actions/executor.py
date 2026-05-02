"""ActionExecutor - bridges skills to permission guard and execution backend."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, Callable, Awaitable

from mycelium_agent_runtime.actions.types import Action, ActionResult, ActionStatus
from mycelium_agent_runtime.permissions import (
    PermissionGuard,
    PermissionLevel,
    get_default_rules,
)

if TYPE_CHECKING:
    from mycelium_agent_runtime.execution.backend import ExecutionBackend

logger = logging.getLogger(__name__)


class ApprovalCallback(Protocol):
    """Callback for handling actions that require approval."""

    async def __call__(self, action: Action) -> bool:
        """Request approval for an action. Returns True if approved."""
        ...


class ActionExecutor:
    """Executes actions through the permission guard.

    Skills use this to propose and execute actions. The executor:
    1. Checks permissions via the guard
    2. Handles blocked actions (returns denial)
    3. Handles approval flow (if callback provided)
    4. Executes allowed actions via the backend
    """

    def __init__(
        self,
        backend: ExecutionBackend,
        guard: PermissionGuard | None = None,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        self._backend = backend
        self._guard = guard or PermissionGuard(rules=get_default_rules())
        self._approval_callback = approval_callback
        self._action_history: list[tuple[Action, ActionResult]] = []

    async def execute(self, action: Action) -> ActionResult:
        """Execute an action through the permission system.

        Returns the result of the action execution.
        """
        decision = self._guard.check(action)

        if decision.is_blocked:
            logger.warning(
                "Action %s blocked: %s",
                action.type.value,
                decision.reason,
            )
            action.status = ActionStatus.BLOCKED
            result = ActionResult.blocked(action.id, decision.reason)
            self._action_history.append((action, result))
            return result

        if decision.needs_approval:
            if self._approval_callback:
                logger.info(
                    "Action %s requires approval: %s",
                    action.type.value,
                    decision.reason,
                )
                action.status = ActionStatus.PENDING_APPROVAL

                approved = await self._approval_callback(action)
                if not approved:
                    action.status = ActionStatus.DENIED
                    result = ActionResult.failure(
                        action.id,
                        f"Action denied by approval: {decision.reason}",
                    )
                    self._action_history.append((action, result))
                    return result

                action.status = ActionStatus.APPROVED
            else:
                action.status = ActionStatus.PENDING_APPROVAL
                result = ActionResult.pending_approval(action.id, decision.reason)
                self._action_history.append((action, result))
                return result

        action.status = ActionStatus.EXECUTING
        logger.debug("Executing action %s: %s", action.type.value, action.payload)

        try:
            result = await self._backend.execute_action(action)
            action.status = (
                ActionStatus.SUCCEEDED if result.success else ActionStatus.FAILED
            )
        except Exception as e:
            logger.exception("Action execution failed: %s", e)
            action.status = ActionStatus.FAILED
            result = ActionResult.failure(action.id, str(e))

        self._action_history.append((action, result))
        return result

    async def execute_many(self, actions: list[Action]) -> list[ActionResult]:
        """Execute multiple actions in sequence."""
        results = []
        for action in actions:
            result = await self.execute(action)
            results.append(result)
            if not result.success and not result.metadata.get("pending_approval"):
                break
        return results

    def get_history(self) -> list[tuple[Action, ActionResult]]:
        """Get the action execution history."""
        return list(self._action_history)

    def clear_history(self) -> None:
        """Clear the action execution history."""
        self._action_history.clear()

    @property
    def guard(self) -> PermissionGuard:
        """Get the permission guard."""
        return self._guard

    @property
    def backend(self) -> ExecutionBackend:
        """Get the execution backend."""
        return self._backend
