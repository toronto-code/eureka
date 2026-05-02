"""ReviewerAgent: review other agents' outputs."""
from __future__ import annotations

from typing import Any

from app.agents.base import AgentInput, AgentType, BaseAgent
from app.prompts import REVIEWER_PROMPT, REVIEWER_SCHEMA


class ReviewerAgent(BaseAgent):
    agent_type = AgentType.REVIEWER
    agent_name = "ReviewerAgent"
    system_prompt = REVIEWER_PROMPT
    output_schema_hint = REVIEWER_SCHEMA

    def fallback_output(self, agent_input: AgentInput) -> dict[str, Any]:
        subset = agent_input.project_data_subset or {}
        outputs = subset.get("worker_outputs") or {}
        issues: list[str] = []
        missing: list[str] = []
        if not outputs.get("jira_analyst"):
            missing.append("No JiraAnalyst output captured.")
        if not outputs.get("codebase_analyst"):
            missing.append("No CodebaseAnalyst output captured.")
        return {
            "pass_fail": "PASS" if not missing else "FAIL",
            "issues_found": issues,
            "missing_context": missing,
            "hallucination_risks": [
                "Verify referenced files actually exist before publishing.",
            ],
            "corrections": [],
            "confidence_score": 0.7 if not missing else 0.45,
        }
