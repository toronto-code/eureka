"""CodebaseAnalystAgent: surface relevant code context for the task."""
from __future__ import annotations

from typing import Any

from app.agents.base import AgentInput, AgentType, BaseAgent
from app.prompts import CODEBASE_ANALYST_PROMPT, CODEBASE_ANALYST_SCHEMA


class CodebaseAnalystAgent(BaseAgent):
    agent_type = AgentType.CODEBASE_ANALYST
    agent_name = "CodebaseAnalystAgent"
    system_prompt = CODEBASE_ANALYST_PROMPT
    output_schema_hint = CODEBASE_ANALYST_SCHEMA

    def fallback_output(self, agent_input: AgentInput) -> dict[str, Any]:
        subset = agent_input.project_data_subset or {}
        files: list[dict[str, Any]] = subset.get("code_files", []) or []
        repos: list[dict[str, Any]] = subset.get("github_repositories", []) or []
        relevant_files = [f.get("path", "") for f in files if f.get("path")]
        services = list(
            {
                f.get("metadata", {}).get("service")
                for f in files
                if f.get("metadata", {}).get("service")
            }
        )
        if not services and repos:
            services = [r.get("name", "") for r in repos if r.get("name")]
        return {
            "relevant_files": relevant_files[:25],
            "relevant_services": services[:10],
            "important_functions_or_classes": [
                f"{f.get('path','?')}::main"
                for f in files[:5]
            ],
            "architecture_notes": (
                "Service appears to follow a layered API + worker pattern based on "
                "supplied files."
            ),
            "implementation_risks": [
                "Changes touching billing/payment flows require risk review.",
            ],
            "suggested_code_approach": (
                "Add a new module/handler scoped to the smallest blast radius and add "
                "tests next to it. Avoid touching shared config."
            ),
        }
