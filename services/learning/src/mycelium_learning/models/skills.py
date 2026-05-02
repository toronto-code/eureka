"""Skill ranking model - learns which skills succeed for which task types."""

from __future__ import annotations

from typing import Any

from mycelium_learning.config import MIN_SIGNALS_FOR_RECOMMENDATION
from mycelium_learning.models.base import BaseModel, ModelKind
from mycelium_learning.signals.types import Signal, SignalKind


class SkillModel(BaseModel):
    """Tracks success rates of skills (agent_types) overall and by user.

    Data structure in state.data:
        {
            "by_skill": {
                "shell": {"success": 10, "failure": 2, "total": 12, "score": 0.83},
                "git_status": {...},
                ...
            }
        }

    Queries:
        - Which skills succeed most often?
        - What's the success rate for skill X?
        - Recommended skills for a task?
    """

    kind = ModelKind.SKILLS

    def _incorporate(self, signal: Signal) -> bool:
        if signal.kind not in (SignalKind.TASK_RESULT, SignalKind.USER_FEEDBACK):
            return False
        if not signal.agent_type:
            return False

        by_skill = self._state.data.setdefault("by_skill", {})
        entry = by_skill.setdefault(
            signal.agent_type,
            {"success": 0.0, "failure": 0.0, "total": 0.0, "score": 0.0},
        )

        if signal.is_positive:
            entry["success"] += signal.weight
        elif signal.is_negative:
            entry["failure"] += signal.weight

        entry["total"] += signal.weight
        if entry["total"] > 0:
            entry["score"] = entry["success"] / entry["total"]

        return True

    def success_rate(self, skill_name: str) -> float | None:
        """Get success rate for a skill."""
        entry = self._state.data.get("by_skill", {}).get(skill_name)
        if not entry or entry["total"] == 0:
            return None
        return entry["success"] / entry["total"]

    def rank_skills(self, skill_names: list[str] | None = None) -> list[dict[str, Any]]:
        """Rank skills by success score, with confidence.

        If skill_names is provided, only rank those. Otherwise rank all tracked.
        """
        by_skill = self._state.data.get("by_skill", {})

        if skill_names:
            entries = [(name, by_skill.get(name, {})) for name in skill_names]
        else:
            entries = list(by_skill.items())

        ranked = []
        for name, entry in entries:
            total = entry.get("total", 0)
            score = entry.get("score", 0) if total > 0 else 0
            confidence = min(1.0, total / 20.0) if total > 0 else 0.0

            ranked.append({
                "skill": name,
                "score": score,
                "success_count": int(entry.get("success", 0)),
                "failure_count": int(entry.get("failure", 0)),
                "total": int(total),
                "confidence": confidence,
                "sufficient_data": total >= MIN_SIGNALS_FOR_RECOMMENDATION,
            })

        ranked.sort(key=lambda r: (r["score"], r["confidence"]), reverse=True)
        return ranked

    def recommend(
        self, candidates: list[str] | None = None, top_n: int = 5
    ) -> list[dict[str, Any]]:
        """Recommend top N skills from candidates (or all)."""
        ranked = self.rank_skills(candidates)
        ranked_with_data = [r for r in ranked if r["sufficient_data"]]
        return ranked_with_data[:top_n] if ranked_with_data else ranked[:top_n]

    def summary(self) -> dict[str, Any]:
        by_skill = self._state.data.get("by_skill", {})
        ranked = self.rank_skills()
        return {
            "kind": "skills",
            "signal_count": self.signal_count,
            "version": self._state.version,
            "skills_tracked": len(by_skill),
            "ranked": ranked,
        }
