"""Permission preference model - learns which actions users approve vs reject."""

from __future__ import annotations

from typing import Any

from mycelium_learning.config import (
    AUTO_APPROVE_THRESHOLD,
    AUTO_BLOCK_THRESHOLD,
    MIN_DECISIONS_FOR_SUGGESTION,
)
from mycelium_learning.models.base import BaseModel, ModelKind
from mycelium_learning.signals.types import Signal, SignalKind


class PermissionModel(BaseModel):
    """Tracks approval/rejection rates per (user, action_type).

    Data structure in state.data:
        {
            "by_action": {
                "shell_command": {"approved": 5, "rejected": 2, "total": 7},
                "git_write": {"approved": 10, "rejected": 0, "total": 10},
                ...
            }
        }

    Queries:
        - Should action X be auto-approved for this user?
        - What's the approval rate for action X?
        - What are the user's preferences?
    """

    kind = ModelKind.PERMISSIONS

    def _incorporate(self, signal: Signal) -> bool:
        if signal.kind != SignalKind.APPROVAL_DECISION:
            return False
        if not signal.action_type:
            all_types = signal.metadata.get("all_action_types") or []
            if not all_types:
                return False
            for action_type in all_types:
                self._update_action(action_type, signal.is_positive, signal.weight)
            return True

        self._update_action(signal.action_type, signal.is_positive, signal.weight)
        return True

    def _update_action(self, action_type: str, approved: bool, weight: float) -> None:
        by_action = self._state.data.setdefault("by_action", {})
        entry = by_action.setdefault(
            action_type, {"approved": 0.0, "rejected": 0.0, "total": 0.0}
        )
        if approved:
            entry["approved"] += weight
        else:
            entry["rejected"] += weight
        entry["total"] += weight

    def approval_rate(self, action_type: str) -> float | None:
        """Get approval rate for an action type. Returns None if no data."""
        entry = self._state.data.get("by_action", {}).get(action_type)
        if not entry or entry["total"] == 0:
            return None
        return entry["approved"] / entry["total"]

    def get_suggestion(self, action_type: str) -> dict[str, Any]:
        """Get permission suggestion for an action type.

        Returns:
            {
                "action_type": str,
                "suggestion": "auto" | "requires_approval" | "blocked" | "insufficient_data",
                "approval_rate": float | None,
                "decision_count": int,
                "confidence": float (0.0 - 1.0)
            }
        """
        entry = self._state.data.get("by_action", {}).get(action_type)

        if not entry or entry["total"] < MIN_DECISIONS_FOR_SUGGESTION:
            return {
                "action_type": action_type,
                "suggestion": "insufficient_data",
                "approval_rate": entry["approved"] / entry["total"] if entry and entry["total"] > 0 else None,
                "decision_count": int(entry["total"]) if entry else 0,
                "confidence": 0.0,
            }

        rate = entry["approved"] / entry["total"]

        if rate >= AUTO_APPROVE_THRESHOLD:
            suggestion = "auto"
        elif rate <= AUTO_BLOCK_THRESHOLD:
            suggestion = "blocked"
        else:
            suggestion = "requires_approval"

        confidence = min(1.0, entry["total"] / 20.0)

        return {
            "action_type": action_type,
            "suggestion": suggestion,
            "approval_rate": rate,
            "decision_count": int(entry["total"]),
            "confidence": confidence,
        }

    def summary(self) -> dict[str, Any]:
        by_action = self._state.data.get("by_action", {})
        suggestions = {
            action_type: self.get_suggestion(action_type)
            for action_type in by_action
        }
        return {
            "kind": "permissions",
            "signal_count": self.signal_count,
            "version": self._state.version,
            "action_types_tracked": len(by_action),
            "suggestions": suggestions,
        }
