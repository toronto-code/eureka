"""RiskSafetyAgent: classify the proposed work and gate writes behind approvals."""
from __future__ import annotations

from typing import Any

from app.agents.base import AgentInput, AgentType, BaseAgent, RiskLevel
from app.prompts import RISK_SAFETY_PROMPT, RISK_SAFETY_SCHEMA


HIGH_RISK_KEYWORDS = (
    "modify",
    "post",
    "open pr",
    "open a pr",
    "change status",
    "send message",
    "delete",
    "secret",
    "config",
    "production",
    "publish",
    "deploy",
)
LOW_RISK_KEYWORDS = (
    "draft",
    "suggest",
    "proposal",
    "summarise",
    "summarize",
)


class RiskSafetyAgent(BaseAgent):
    agent_type = AgentType.RISK_SAFETY
    agent_name = "RiskSafetyAgent"
    system_prompt = RISK_SAFETY_PROMPT
    output_schema_hint = RISK_SAFETY_SCHEMA

    def fallback_output(self, agent_input: AgentInput) -> dict[str, Any]:
        subset = agent_input.project_data_subset or {}
        plan = subset.get("implementation_plan") or []
        plan_text = " ".join(
            (step.get("description") if isinstance(step, dict) else str(step)) or ""
            for step in plan
        ).lower()

        risk_level = RiskLevel.READ_ONLY
        blocked: list[str] = []
        if any(k in plan_text for k in HIGH_RISK_KEYWORDS):
            risk_level = RiskLevel.HIGH_RISK_WRITE
            blocked = [
                step.get("description", "")
                for step in plan
                if isinstance(step, dict)
                and any(k in (step.get("description") or "").lower() for k in HIGH_RISK_KEYWORDS)
            ]
        elif any(k in plan_text for k in LOW_RISK_KEYWORDS):
            risk_level = RiskLevel.LOW_RISK_WRITE

        approval_required = risk_level == RiskLevel.HIGH_RISK_WRITE

        return {
            "risk_level": risk_level.value,
            "approval_required": approval_required,
            "reasons": [
                "Conservative classification based on plan keywords.",
                f"Detected risk level: {risk_level.value}.",
            ],
            "blocked_actions": blocked,
            "rollback_plan": (
                "Revert any drafts before publish. For doc commits, drop the branch. For Jira, "
                "delete the agent-authored comment."
            ),
        }
