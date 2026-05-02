"""Base skill protocol and types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from mycelium_agent_runtime.actions.executor import ActionExecutor
    from mycelium_agent_runtime.permissions.rules import ActionType


@dataclass
class SkillResult:
    """Result from executing a skill."""

    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    actions_taken: int = 0
    actions_blocked: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "actions_taken": self.actions_taken,
            "actions_blocked": self.actions_blocked,
        }


class BaseSkill(ABC):
    """Base class for skills that use the action executor.

    Skills should inherit from this class and implement the execute method.
    Use self.run_action() to execute actions through the permission guard.
    """

    name: str
    description: str
    required_capabilities: list[ActionType] = []

    def __init__(self) -> None:
        self._executor: ActionExecutor | None = None
        self._context: dict[str, Any] = {}

    @abstractmethod
    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        """Execute the skill.

        Args:
            input_data: Input data from the task
            context: Context from knowledge graph
            executor: Action executor for running actions

        Returns:
            Result dictionary
        """
        ...

    async def run_action(
        self,
        executor: ActionExecutor,
        action: Any,
    ) -> Any:
        """Run an action through the executor.

        Convenience method for skills to execute actions.
        """
        from mycelium_agent_runtime.actions.types import Action

        if not isinstance(action, Action):
            raise TypeError(f"Expected Action, got {type(action)}")

        return await executor.execute(action)
