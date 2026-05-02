"""TranscriptAnalystAgent: extract decisions and context from working sessions."""
from __future__ import annotations

import re
from typing import Any

from app.agents.base import AgentInput, AgentType, BaseAgent
from app.prompts import TRANSCRIPT_ANALYST_PROMPT, TRANSCRIPT_ANALYST_SCHEMA


class TranscriptAnalystAgent(BaseAgent):
    agent_type = AgentType.TRANSCRIPT_ANALYST
    agent_name = "TranscriptAnalystAgent"
    system_prompt = TRANSCRIPT_ANALYST_PROMPT
    output_schema_hint = TRANSCRIPT_ANALYST_SCHEMA

    def fallback_output(self, agent_input: AgentInput) -> dict[str, Any]:
        subset = agent_input.project_data_subset or {}
        transcripts: list[dict[str, Any]] = subset.get("transcripts", []) or []
        all_text = "\n".join(t.get("content", "") for t in transcripts)
        decisions = [
            line.strip("- ").strip()
            for line in all_text.splitlines()
            if "decided" in line.lower() or "agreed" in line.lower()
        ][:10]
        mentioned_files = list({m for m in re.findall(r"[\w/_-]+\.(?:py|ts|tsx|md|sql)", all_text)})[
            :15
        ]
        services = list({m for m in re.findall(r"\b\w+-service\b", all_text)})[:10]
        people: list[str] = []
        for t in transcripts:
            people.extend(t.get("participants", []) or [])
        return {
            "decisions_made": decisions,
            "mentioned_files": mentioned_files,
            "mentioned_services": services,
            "mentioned_people": list(dict.fromkeys(people))[:15],
            "unresolved_questions": [
                "Confirm which doc location the onboarding guide should live in.",
            ],
            "useful_context_for_task": (
                "Engineers discussed the target service's structure; capture cross-references "
                "in the deliverable."
            ),
        }
