"""Permission guard that checks actions against rules."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mycelium_agent_runtime.permissions.rules import (
    ActionType,
    PermissionDecision,
    PermissionLevel,
    PermissionRule,
)

if TYPE_CHECKING:
    from mycelium_agent_runtime.actions.types import Action

logger = logging.getLogger(__name__)


class PermissionGuard:
    """Guards agent actions by checking against permission rules.

    Rules are evaluated in priority order (highest first). The first matching
    rule determines the permission level. If no rule matches, the default
    level is used.
    """

    def __init__(
        self,
        rules: list[PermissionRule] | None = None,
        default_level: PermissionLevel = PermissionLevel.REQUIRES_APPROVAL,
    ) -> None:
        self._rules: list[PermissionRule] = []
        self._default_level = default_level

        if rules:
            for rule in rules:
                self.add_rule(rule)

    def add_rule(self, rule: PermissionRule) -> None:
        """Add a rule and maintain priority ordering."""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, name: str) -> bool:
        """Remove a rule by name. Returns True if found and removed."""
        for i, rule in enumerate(self._rules):
            if rule.name == name:
                self._rules.pop(i)
                return True
        return False

    def check(self, action: Action) -> PermissionDecision:
        """Check an action against all rules.

        Returns the permission decision for the action.
        """
        for rule in self._rules:
            if rule.matches(action.type, action.payload):
                logger.debug(
                    "Action %s matched rule %s -> %s",
                    action.type.value,
                    rule.name,
                    rule.level.value,
                )
                return PermissionDecision(
                    level=rule.level,
                    reason=rule.description or f"Matched rule: {rule.name}",
                    matched_rule=rule,
                )

        logger.debug(
            "Action %s matched no rules, using default: %s",
            action.type.value,
            self._default_level.value,
        )
        return PermissionDecision(
            level=self._default_level,
            reason=f"No matching rule, default policy: {self._default_level.value}",
            matched_rule=None,
        )

    def check_raw(
        self, action_type: ActionType, payload: dict
    ) -> PermissionDecision:
        """Check an action without requiring an Action object."""
        from mycelium_agent_runtime.actions.types import Action

        action = Action(type=action_type, payload=payload, reasoning="")
        return self.check(action)

    @property
    def rules(self) -> list[PermissionRule]:
        """Return a copy of the rules list."""
        return list(self._rules)

    def get_rules_for_type(self, action_type: ActionType) -> list[PermissionRule]:
        """Get all rules that apply to a specific action type."""
        return [r for r in self._rules if r.action_type == action_type]
