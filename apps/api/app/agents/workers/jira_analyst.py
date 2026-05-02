"""JiraAnalystAgent: analyse a Jira-style task into structured findings."""
from __future__ import annotations

from typing import Any

from app.agents.base import AgentInput, AgentType, BaseAgent
from app.prompts import JIRA_ANALYST_PROMPT, JIRA_ANALYST_SCHEMA


class JiraAnalystAgent(BaseAgent):
    agent_type = AgentType.JIRA_ANALYST
    agent_name = "JiraAnalystAgent"
    system_prompt = JIRA_ANALYST_PROMPT
    output_schema_hint = JIRA_ANALYST_SCHEMA

    def fallback_output(self, agent_input: AgentInput) -> dict[str, Any]:
        task = agent_input.task or {}
        title = task.get("title") or "Unnamed Jira task"
        description = task.get("description") or ""
        return {
            "task_summary": f"{title}. {description[:240]}".strip(),
            "ambiguity_list": [
                "Acceptance criteria not yet confirmed with stakeholders.",
            ],
            "acceptance_criteria": task.get("acceptance_criteria")
            or [
                "Deliverable matches the task description.",
                "All listed labels are addressed.",
            ],
            "blockers": task.get("dependencies") or [],
            "suggested_jira_comment": (
                f"Started analysis for '{title}'. Will share findings shortly."
            ),
        }
