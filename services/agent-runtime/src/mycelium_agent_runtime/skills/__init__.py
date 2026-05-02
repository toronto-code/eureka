"""Skill registry. Each skill is a callable + a small descriptor.

Real impl: skills are loaded from disk + a Claworc-curated catalog.
This stub registers a few placeholders so the surface area is visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

SkillFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class Skill:
    name: str
    description: str
    handler: SkillFn


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def describe(self) -> list[dict[str, str]]:
        return [{"name": s.name, "description": s.description} for s in self._skills.values()]


registry = SkillRegistry()


# ---- Stub skills -----------------------------------------------------------


async def _summarize(input_data: dict) -> dict:
    return {
        "summary": f"(stub) summary of: {input_data.get('prompt', '')[:80]}",
        "tokens": 42,
    }


async def _triage(input_data: dict) -> dict:
    return {"label": "needs-review", "confidence": 0.8, "stub": True}


async def _onboard(input_data: dict) -> dict:
    target = input_data.get("service") or input_data.get("repo") or "unknown"
    return {"briefing": f"(stub) here's how {target} works…", "stub": True}


registry.register(Skill("summarize", "Summarize a prompt or document.", _summarize))
registry.register(Skill("triage", "Categorize and route an item.", _triage))
registry.register(Skill("onboard", "Produce an onboarding briefing for a service.", _onboard))
