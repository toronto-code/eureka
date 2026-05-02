"""Project-level orchestrator: shallow breadth, delegates to specialist skills."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from mycelium_agent_runtime.agents.catalog import (
    ORCHESTRATOR_ID,
    summarize_project_data_placeholder,
)
from mycelium_agent_runtime.skills import registry
from mycelium_agent_runtime.skills.base import BaseSkill

if TYPE_CHECKING:
    from mycelium_agent_runtime.actions.executor import ActionExecutor


@dataclass
class Delegation:
    role_id: str
    skill_name: str
    sub_prompt: str
    rationale: str


def _plan_delegations(prompt: str, project_data: Any) -> list[Delegation]:
    """Heuristic router; replace with LLM classification in production."""
    p = (prompt or "").lower()
    out: list[Delegation] = []

    def add(role: str, skill: str, sub: str, why: str) -> None:
        out.append(Delegation(role_id=role, skill_name=skill, sub_prompt=sub, rationale=why))

    # Always include reasoning + plan as the core team spine
    add(
        "research_agent",
        "reasoning",
        f"User goal: {prompt}\nFocus on constraints and what is unknown.",
        "Baseline analysis for any task.",
    )
    add(
        "planner_agent",
        "plan",
        f"Task to plan: {prompt}",
        "Structured steps support execution and review.",
    )

    if re.search(
        r"\b(jira|slack|github|integration|webhook|ticket|pr|pull request)\b", p
    ):
        add(
            "integrations_agent",
            "onboard",
            f"Map this goal to integration/onboarding actions: {prompt}",
            "User language suggests external tools.",
        )

    if re.search(
        r"\b(code|refactor|bug|test|implement|commit|diff|repo)\b", p
    ):
        add(
            "code_agent",
            "reasoning",
            f"From a code/repo perspective: {prompt}",
            "User language suggests implementation work.",
        )

    add(
        "scribe_agent",
        "summarize",
        f"Synthesize an executive summary for: {prompt}",
        "Closing synthesis for the user.",
    )

    # Dedupe by (role, skill) keeping first sub_prompt
    seen: set[tuple[str, str]] = set()
    deduped: list[Delegation] = []
    for d in out:
        key = (d.role_id, d.skill_name)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(d)
    return deduped


class ProjectOrchestratorSkill(BaseSkill):
    """Ingest project-wide context, route to specialists, merge outputs.

    Input:
        prompt: User task (required).
        project_data: Optional dict (placeholder bundle for repos/events/graph IDs).
        run_team: If True (default), invoke specialist skills in-process.
        max_delegations: Cap fan-out (default 5).
    """

    name = ORCHESTRATOR_ID
    description = (
        "Project orchestrator: reads project_data, plans a specialist team, runs mapped skills"
    )
    required_capabilities = []

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        prompt = input_data.get("prompt", "")
        project_data = input_data.get("project_data")
        run_team = input_data.get("run_team", True)
        max_del = int(input_data.get("max_delegations", 5))

        snapshot = summarize_project_data_placeholder(project_data)
        delegations = _plan_delegations(prompt, project_data)[:max_del]

        team_outputs: list[dict[str, Any]] = []
        if run_team:
            base_knowledge = input_data.get("knowledge", context)
            for d in delegations:
                skill = registry.get(d.skill_name)
                if skill is None:
                    team_outputs.append(
                        {
                            "role": d.role_id,
                            "skill": d.skill_name,
                            "error": "skill not registered",
                            "skipped": True,
                        }
                    )
                    continue

                sub_input: dict[str, Any] = {
                    "prompt": d.sub_prompt,
                    "task": d.sub_prompt,
                    "knowledge": base_knowledge,
                    "recent_turns": input_data.get("recent_turns", ""),
                    "relevant_memories": input_data.get("relevant_memories", []),
                    "project_data": project_data,
                    "_delegated_from": ORCHESTRATOR_ID,
                    "_delegation_role": d.role_id,
                }

                if hasattr(skill, "execute"):
                    result = await skill.execute(sub_input, context, executor)
                else:
                    result = await skill.handler(sub_input)

                team_outputs.append(
                    {
                        "role": d.role_id,
                        "skill": d.skill_name,
                        "rationale": d.rationale,
                        "result": result,
                    }
                )

        merged_summary = self._merge(prompt, snapshot, team_outputs)

        return {
            "success": True,
            "summary": merged_summary,
            "orchestrator_id": ORCHESTRATOR_ID,
            "project_data_snapshot": snapshot,
            "user_task": prompt,
            "delegations": [
                {
                    "role": d.role_id,
                    "skill": d.skill_name,
                    "sub_prompt": d.sub_prompt,
                    "rationale": d.rationale,
                }
                for d in delegations
            ],
            "team_outputs": team_outputs,
            "run_team": run_team,
            "stub": True,
            "note": (
                "Heuristic routing today; plug an LLM planner here to choose personas/skills "
                "and optionally emit child Redis tasks per delegation."
            ),
        }

    def _merge(
        self,
        prompt: str,
        snapshot: dict[str, Any],
        team_outputs: list[dict[str, Any]],
    ) -> str:
        if not team_outputs:
            return (
                f"(orchestrator) Goal: {prompt[:300]}. "
                f"Project snapshot: {snapshot.get('status', '?')}. "
                "Enable run_team or supply prompts to invoke specialists."
            )
        parts: list[str] = [
            f"Goal: {prompt[:500]}",
            f"Project bundle: {snapshot.get('status', 'unknown')} keys={snapshot.get('keys', [])}",
        ]
        for row in team_outputs:
            if row.get("skipped"):
                continue
            res = row.get("result") or {}
            snippet = (
                res.get("summary")
                or res.get("response")
                or res.get("briefing")
                or str(res)[:400]
            )
            parts.append(f"[{row.get('role')} via {row.get('skill')}] {snippet}")
        return "\n".join(parts)[:8000]
