"""DocsAnalystAgent: pull facts/constraints/procedures out of docs."""
from __future__ import annotations

from typing import Any

from app.agents.base import AgentInput, AgentType, BaseAgent
from app.prompts import DOCS_ANALYST_PROMPT, DOCS_ANALYST_SCHEMA


class DocsAnalystAgent(BaseAgent):
    agent_type = AgentType.DOCS_ANALYST
    agent_name = "DocsAnalystAgent"
    system_prompt = DOCS_ANALYST_PROMPT
    output_schema_hint = DOCS_ANALYST_SCHEMA

    def fallback_output(self, agent_input: AgentInput) -> dict[str, Any]:
        subset = agent_input.project_data_subset or {}
        docs: list[dict[str, Any]] = subset.get("docs", []) or []
        titles = [d.get("title", "") for d in docs if d.get("title")]
        return {
            "relevant_facts": [
                f"Doc '{t}' is part of the project context." for t in titles[:5]
            ],
            "constraints": [
                "Follow existing docs style (Markdown, short sections, examples)."
            ],
            "procedures": [
                "Drop new onboarding guides under docs/onboarding/<service>.md.",
            ],
            "cited_sources": titles,
            "useful_context_for_task": (
                "Existing docs establish naming conventions and section structure to mirror."
            ),
        }
