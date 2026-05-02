"""PlannerAgent: turn merged findings into a concrete implementation plan."""
from __future__ import annotations

from typing import Any

from app.agents.base import AgentInput, AgentType, BaseAgent
from app.prompts import PLANNER_PROMPT, PLANNER_SCHEMA


class PlannerAgent(BaseAgent):
    agent_type = AgentType.PLANNER
    agent_name = "PlannerAgent"
    system_prompt = PLANNER_PROMPT
    output_schema_hint = PLANNER_SCHEMA

    def fallback_output(self, agent_input: AgentInput) -> dict[str, Any]:
        return {
            "steps": [
                {
                    "step": 1,
                    "description": "Gather repo, doc, and transcript context for the target service.",
                    "risk_level": "READ_ONLY",
                    "requires_approval": False,
                },
                {
                    "step": 2,
                    "description": "Draft an onboarding guide markdown file scoped to the service.",
                    "risk_level": "LOW_RISK_WRITE",
                    "requires_approval": False,
                },
                {
                    "step": 3,
                    "description": "Open a PR with the new doc and request review.",
                    "risk_level": "HIGH_RISK_WRITE",
                    "requires_approval": True,
                },
                {
                    "step": 4,
                    "description": "Post a Jira comment summarising the draft and linking the PR.",
                    "risk_level": "HIGH_RISK_WRITE",
                    "requires_approval": True,
                },
            ],
            "dependency_order": ["context", "draft", "review", "publish"],
            "estimated_complexity": "Low (mostly documentation).",
            "definition_of_done": [
                "Onboarding doc exists in docs/ tree.",
                "Doc references key files, services, and contacts.",
                "PR opened with reviewers assigned.",
                "Jira ticket links to the PR.",
            ],
        }
