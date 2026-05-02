"""Shallow, broad orchestrator at the top; specialist agents below.

`project_data` is an optional dict (placeholder today: repos, files, events,
graph handles, org metadata). The orchestrator reads it and routes work to
specialists by invoking registered *skills* with role-specific prompts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ORCHESTRATOR_ID = "project_orchestrator"


@dataclass(frozen=True)
class AgentPersona:
    """A logical agent the orchestrator can delegate to (mapped to skills)."""

    id: str
    title: str
    description: str
    # Primary skill the worker runs for this persona when used as a direct task
    default_skill: str
    # Free-text system-style instructions for future LLM routing
    system_prompt: str
    # Optional tags for heuristics / UI
    tags: frozenset[str] = field(default_factory=frozenset)


def _personas() -> tuple[AgentPersona, ...]:
    return (
        AgentPersona(
            id=ORCHESTRATOR_ID,
            title="Project orchestrator",
            description=(
                "Top-level agent: ingests the whole project payload, understands the user "
                "goal, and coordinates specialists. Does not replace specialists — it routes "
                "and merges their outputs."
            ),
            default_skill=ORCHESTRATOR_ID,
            system_prompt=(
                "You are the project orchestrator for Mycelium. You receive `project_data` "
                "(may be partial or placeholder) and a user task. Briefly frame the goal, "
                "decide which specialists to involve, and merge their results into one coherent "
                "answer. Prefer delegation over doing deep work yourself."
            ),
            tags=frozenset({"orchestrator", "routing", "meta"}),
        ),
        AgentPersona(
            id="research_agent",
            title="Research & reasoning",
            description="Breaks down problems, uses knowledge context, and sequences investigation.",
            default_skill="reasoning",
            system_prompt=(
                "You are the research specialist. Given project context and a sub-task, "
                "analyze constraints, unknowns, and propose ordered investigation steps. "
                "Lean on knowledge graph hints when present."
            ),
            tags=frozenset({"reasoning", "analysis"}),
        ),
        AgentPersona(
            id="planner_agent",
            title="Planner",
            description="Turns goals into concrete steps and dependencies.",
            default_skill="plan",
            system_prompt=(
                "You are the planning specialist. Emit structured steps with dependencies, "
                "risks, and estimated effort class (small/medium/large)."
            ),
            tags=frozenset({"planning", "workflow"}),
        ),
        AgentPersona(
            id="scribe_agent",
            title="Synthesizer",
            description="Compresses long context into executive summaries.",
            default_skill="summarize",
            system_prompt=(
                "You are the synthesizer. Produce concise summaries aligned with the user "
                "task; preserve critical facts and IDs."
            ),
            tags=frozenset({"summary", "narrative"}),
        ),
        AgentPersona(
            id="integrations_agent",
            title="Integrations liaison",
            description="Framing for Slack, Jira, GitHub, and external tools (stubs today).",
            default_skill="onboard",
            system_prompt=(
                "You are the integrations specialist. Map the user's goal to sync/onboarding "
                "actions across connected tools; flag missing credentials or scopes."
            ),
            tags=frozenset({"slack", "jira", "github", "integrations"}),
        ),
        AgentPersona(
            id="code_agent",
            title="Code & repo focus",
            description="Reasoning biased toward implementation and repo changes.",
            default_skill="reasoning",
            system_prompt=(
                "You are the code specialist. Focus on files, tests, diffs, and safe rollout. "
                "Call out approval-worthy actions explicitly."
            ),
            tags=frozenset({"code", "repo", "implementation"}),
        ),
        AgentPersona(
            id="legacy_chat_agent",
            title="Legacy chat stub",
            description="Minimal echo stub for backwards compatibility.",
            default_skill="chat",
            system_prompt="Legacy stub chat skill — prefer project_orchestrator for new work.",
            tags=frozenset({"legacy", "stub"}),
        ),
    )


_PERSONAS: tuple[AgentPersona, ...] = _personas()
_BY_ID: dict[str, AgentPersona] = {p.id: p for p in _PERSONAS}


def list_personas() -> list[AgentPersona]:
    """All defined personas (orchestrator first in iteration order)."""
    return list(_PERSONAS)


def persona_by_id(persona_id: str) -> AgentPersona | None:
    return _BY_ID.get(persona_id)


def summarize_project_data_placeholder(project_data: Any) -> dict[str, Any]:
    """Cheap snapshot for prompts and UI until real project bundles exist."""
    if project_data is None or project_data == {}:
        return {
            "status": "empty",
            "note": "No project_data supplied — orchestrator uses user prompt + knowledge only.",
            "keys": [],
        }
    if isinstance(project_data, dict):
        keys = list(project_data.keys())
        return {
            "status": "placeholder",
            "note": "Structured project bundle (repos, events, graph refs, …) — enrich over time.",
            "keys": keys,
            "size_hint": len(keys),
        }
    return {
        "status": "opaque",
        "note": "project_data is non-dict; treating as opaque attachment.",
        "type": type(project_data).__name__,
    }
