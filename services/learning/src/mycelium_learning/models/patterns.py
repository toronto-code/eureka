"""Action pattern model - learns which action patterns lead to success."""

from __future__ import annotations

from typing import Any

from mycelium_learning.models.base import BaseModel, ModelKind
from mycelium_learning.signals.types import Signal, SignalKind


class PatternModel(BaseModel):
    """Tracks action patterns and their success rates.

    A "pattern" is derived from metadata - currently just the list of actions
    from pending_actions in an approval signal, joined as a string.

    Data structure in state.data:
        {
            "by_pattern": {
                "shell_command|file_write": {"success": 5, "failure": 1, "total": 6},
                ...
            },
            "by_agent_type": {
                "chat": {
                    "common_actions": {"shell_command": 10, "file_read": 8, ...}
                }
            }
        }

    Queries:
        - What action sequences succeed for this task type?
        - What's the "typical" action set for agent type X?
    """

    kind = ModelKind.PATTERNS

    def _incorporate(self, signal: Signal) -> bool:
        incorporated = False

        if signal.kind == SignalKind.APPROVAL_DECISION:
            action_types = signal.metadata.get("all_action_types") or []
            if action_types:
                pattern = "|".join(sorted(set(action_types)))
                self._update_pattern(
                    pattern,
                    success=signal.is_positive,
                    weight=signal.weight,
                )
                incorporated = True

        if signal.kind == SignalKind.TASK_RESULT and signal.agent_type:
            if signal.is_positive or signal.is_negative:
                self._track_agent_type(signal.agent_type, signal.is_positive, signal.weight)
                incorporated = True

        return incorporated

    def _update_pattern(self, pattern: str, success: bool, weight: float) -> None:
        by_pattern = self._state.data.setdefault("by_pattern", {})
        entry = by_pattern.setdefault(
            pattern, {"success": 0.0, "failure": 0.0, "total": 0.0}
        )
        if success:
            entry["success"] += weight
        else:
            entry["failure"] += weight
        entry["total"] += weight

    def _track_agent_type(self, agent_type: str, success: bool, weight: float) -> None:
        by_agent = self._state.data.setdefault("by_agent_type", {})
        entry = by_agent.setdefault(
            agent_type, {"success": 0.0, "failure": 0.0, "total": 0.0}
        )
        if success:
            entry["success"] += weight
        else:
            entry["failure"] += weight
        entry["total"] += weight

    def pattern_success_rate(self, pattern: str) -> float | None:
        entry = self._state.data.get("by_pattern", {}).get(pattern)
        if not entry or entry["total"] == 0:
            return None
        return entry["success"] / entry["total"]

    def top_patterns(self, top_n: int = 10, min_total: int = 3) -> list[dict[str, Any]]:
        """Return the top-performing patterns with enough data."""
        by_pattern = self._state.data.get("by_pattern", {})

        patterns = []
        for pattern, entry in by_pattern.items():
            if entry["total"] < min_total:
                continue
            patterns.append({
                "pattern": pattern,
                "success_rate": entry["success"] / entry["total"],
                "total": int(entry["total"]),
                "success_count": int(entry["success"]),
                "failure_count": int(entry["failure"]),
            })

        patterns.sort(key=lambda p: (p["success_rate"], p["total"]), reverse=True)
        return patterns[:top_n]

    def agent_type_stats(self, agent_type: str) -> dict[str, Any] | None:
        entry = self._state.data.get("by_agent_type", {}).get(agent_type)
        if not entry:
            return None
        total = entry["total"]
        return {
            "agent_type": agent_type,
            "success_rate": entry["success"] / total if total > 0 else 0,
            "total": int(total),
        }

    def summary(self) -> dict[str, Any]:
        by_pattern = self._state.data.get("by_pattern", {})
        by_agent = self._state.data.get("by_agent_type", {})
        return {
            "kind": "patterns",
            "signal_count": self.signal_count,
            "version": self._state.version,
            "patterns_tracked": len(by_pattern),
            "agent_types_tracked": len(by_agent),
            "top_patterns": self.top_patterns(),
            "agent_types": [
                self.agent_type_stats(at) for at in by_agent
            ],
        }
