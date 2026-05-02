"""Skill registry. Each skill is a callable + a small descriptor.

Skills are registered on import. Both legacy callable skills and new
BaseSkill-derived skills are supported.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from mycelium_agent_runtime.actions.executor import ActionExecutor

SkillFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class SkillProtocol(Protocol):
    """Protocol for skills that support the new executor-based execution."""

    name: str
    description: str

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        ...


@dataclass
class Skill:
    """Legacy skill wrapper - simple callable handler."""

    name: str
    description: str
    handler: SkillFn


class SkillRegistry:
    """Registry for skills - supports both legacy and new-style skills."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill | SkillProtocol] = {}

    def register(self, skill: Skill | SkillProtocol) -> None:
        """Register a skill by name."""
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | SkillProtocol | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def describe(self) -> list[dict[str, str]]:
        """Describe all registered skills."""
        descriptions = []
        for s in self._skills.values():
            desc = {"name": s.name, "description": s.description}
            if hasattr(s, "required_capabilities"):
                desc["capabilities"] = [c.value for c in s.required_capabilities]
            descriptions.append(desc)
        return descriptions

    def list_names(self) -> list[str]:
        """List all skill names."""
        return list(self._skills.keys())


registry = SkillRegistry()


# ---- Register new-style skills ---------------------------------------------

from mycelium_agent_runtime.skills.shell import ShellSkill, MultiShellSkill
from mycelium_agent_runtime.skills.file_ops import (
    FileReadSkill,
    FileWriteSkill,
    FileDeleteSkill,
    FileOpsSkill,
)
from mycelium_agent_runtime.skills.git import (
    GitSkill,
    GitStatusSkill,
    GitCommitSkill,
    GitDiffSkill,
)
from mycelium_agent_runtime.skills.search import GrepSkill, FindSkill, SearchSkill
from mycelium_agent_runtime.skills.reasoning import (
    ReasoningSkill,
    PlanSkill,
    SummarizeSkill,
)
from mycelium_agent_runtime.skills.project_orchestrator import ProjectOrchestratorSkill

registry.register(ShellSkill())
registry.register(MultiShellSkill())
registry.register(FileReadSkill())
registry.register(FileWriteSkill())
registry.register(FileDeleteSkill())
registry.register(FileOpsSkill())
registry.register(GitSkill())
registry.register(GitStatusSkill())
registry.register(GitCommitSkill())
registry.register(GitDiffSkill())
registry.register(GrepSkill())
registry.register(FindSkill())
registry.register(SearchSkill())
registry.register(ReasoningSkill())
registry.register(PlanSkill())
registry.register(SummarizeSkill())
registry.register(ProjectOrchestratorSkill())


# ---- Legacy stub skills (kept for backward compatibility) ------------------


async def _triage(input_data: dict) -> dict:
    """Categorize and route an item."""
    return {"label": "needs-review", "confidence": 0.8, "stub": True}


async def _onboard(input_data: dict) -> dict:
    """Produce an onboarding briefing for a service."""
    target = input_data.get("service") or input_data.get("repo") or "unknown"
    return {"briefing": f"(stub) here's how {target} works…", "stub": True}


async def _chat(input_data: dict) -> dict:
    """Handle chat interactions.

    Uses the shared LLM client when a key is configured; falls back to an
    echo response so the demo still works with no API key.
    """
    from mycelium_agent_runtime.llm import LLMClient

    prompt = input_data.get("prompt", "")
    if not prompt:
        return {"response": "", "stub": False}

    llm = LLMClient()
    if llm.enabled:
        recent = input_data.get("recent_turns", "")
        memories = input_data.get("relevant_memories", [])
        mem_block = ""
        if isinstance(memories, list) and memories:
            mem_block = "\n".join(
                f"- {(m.get('summary') or m.get('content') or str(m))[:200]}"
                for m in memories[:3]
                if isinstance(m, dict)
            )
        user_msg = prompt
        system = (
            "You are Mycelium, a concise engineering-focused assistant. "
            "Answer directly. Use prior context when helpful."
            + (f"\n\nRecent turns:\n{recent}" if recent else "")
            + (f"\n\nRelevant memories:\n{mem_block}" if mem_block else "")
        )
        resp = await llm.complete(user_msg, system=system)
        if not resp.stub and resp.text:
            return {
                "response": resp.text.strip(),
                "model": resp.model,
                "provider": resp.provider,
                "stub": False,
            }

    return {
        "response": f"(stub) I received your message: {prompt[:100]}",
        "stub": True,
        "provider": "stub",
    }


registry.register(Skill("triage", "Categorize and route an item.", _triage))
registry.register(Skill("onboard", "Produce an onboarding briefing for a service.", _onboard))
registry.register(Skill("chat", "Handle chat interactions.", _chat))
