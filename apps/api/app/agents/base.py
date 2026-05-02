"""Base agent contracts: enums, IO models, BaseAgent class.

Every agent in Mycelium implements `BaseAgent.run` with typed inputs/outputs and
returns structured JSON. This file defines the shared shapes and validation
helpers so the orchestrator and workers stay consistent.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agents.llm_client import OpenAIClient, get_llm_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AgentType(str, Enum):
    """Canonical agent identifiers."""

    ORCHESTRATOR = "orchestrator"
    JIRA_ANALYST = "jira_analyst"
    CODEBASE_ANALYST = "codebase_analyst"
    TRANSCRIPT_ANALYST = "transcript_analyst"
    DOCS_ANALYST = "docs_analyst"
    PLANNER = "planner"
    RISK_SAFETY = "risk_safety"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"


class RiskLevel(str, Enum):
    """Risk classification for any proposed action."""

    READ_ONLY = "READ_ONLY"
    LOW_RISK_WRITE = "LOW_RISK_WRITE"
    HIGH_RISK_WRITE = "HIGH_RISK_WRITE"


class AgentRunStatus(str, Enum):
    """Lifecycle states for an agent_runs row."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# IO models
# ---------------------------------------------------------------------------


class AgentInput(BaseModel):
    """Input given to an agent on each run."""

    model_config = ConfigDict(extra="allow")

    task: dict[str, Any] | None = None
    project_data_subset: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    extra_instructions: str | None = None
    parent_run_id: str | None = None
    orchestrator_run_id: str | None = None


class AgentOutput(BaseModel):
    """Wrapper around any agent's structured JSON output."""

    model_config = ConfigDict(extra="allow")

    agent_type: AgentType
    agent_name: str
    status: AgentRunStatus = AgentRunStatus.COMPLETED
    summary: str = ""
    structured_output: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    model: str = "gpt-4o"
    full_prompt: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def safe_parse_json(text: str) -> dict[str, Any]:
    """Parse a JSON string from an LLM, tolerating fenced ```json blocks.

    Returns `{}` if parsing fails so callers can degrade gracefully.
    """
    if not text:
        return {}
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Strip markdown fences like ```json ... ```
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    # If the model wrapped the object in extra prose, try to slice between braces.
    if not cleaned.startswith("{"):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse agent JSON output: %s", exc)
        return {}


def coerce_risk(value: str | None) -> RiskLevel:
    """Coerce a free-form string into a RiskLevel, defaulting to READ_ONLY."""
    if not value:
        return RiskLevel.READ_ONLY
    upper = value.upper().replace(" ", "_")
    try:
        return RiskLevel(upper)
    except ValueError:
        return RiskLevel.READ_ONLY


# ---------------------------------------------------------------------------
# BaseAgent
# ---------------------------------------------------------------------------


class BaseAgent(ABC):
    """Abstract base for every Mycelium agent.

    Subclasses set `agent_type`, `agent_name`, `system_prompt`, and `output_schema_hint`,
    then either override `run()` or rely on `_default_run` which:
      1. builds the user prompt from inputs,
      2. calls the LLM client,
      3. parses structured JSON,
      4. returns an `AgentOutput`.
    """

    agent_type: AgentType
    agent_name: str = "BaseAgent"
    system_prompt: str = "You are a helpful agent."
    default_model: str = "gpt-4o"
    output_schema_hint: dict[str, Any] | None = None

    def __init__(self, llm: OpenAIClient | None = None, model: str | None = None) -> None:
        self.llm = llm or get_llm_client()
        self.model = model or self.default_model

    # -- public API -------------------------------------------------------

    def run(self, agent_input: AgentInput) -> AgentOutput:
        """Run the agent. Default implementation is a single LLM round-trip."""
        return self._default_run(agent_input)

    # -- helpers for subclasses ------------------------------------------

    def build_user_prompt(self, agent_input: AgentInput) -> str:
        """Default user-prompt format. Subclasses can override for richer prompts."""
        parts: list[str] = []
        if agent_input.reason:
            parts.append(f"Reason for spawning: {agent_input.reason}")
        if agent_input.task:
            parts.append("Task context:\n" + json.dumps(agent_input.task, indent=2, default=str))
        if agent_input.project_data_subset:
            parts.append(
                "Focused project_data subset:\n"
                + json.dumps(agent_input.project_data_subset, indent=2, default=str)
            )
        if agent_input.extra_instructions:
            parts.append(f"Additional instructions: {agent_input.extra_instructions}")
        parts.append(
            "Respond ONLY with a JSON object that matches the schema described in the system "
            "prompt. Do not include any prose outside the JSON."
        )
        return "\n\n".join(parts)

    def _default_run(self, agent_input: AgentInput) -> AgentOutput:
        started = datetime.now(timezone.utc)
        user_prompt = self.build_user_prompt(agent_input)
        try:
            payload = self.llm.generate_json(
                system_prompt=self.system_prompt,
                user_prompt=user_prompt,
                schema_hint=self.output_schema_hint,
                model=self.model,
                fallback=self.fallback_output(agent_input),
            )
            summary = self.summarise_output(payload)
            risk = self.extract_risk(payload)
            return AgentOutput(
                agent_type=self.agent_type,
                agent_name=self.agent_name,
                status=AgentRunStatus.COMPLETED,
                summary=summary,
                structured_output=payload,
                risk_level=risk,
                started_at=started,
                completed_at=datetime.now(timezone.utc),
                model=self.model,
                full_prompt=user_prompt,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Agent %s failed", self.agent_name)
            return AgentOutput(
                agent_type=self.agent_type,
                agent_name=self.agent_name,
                status=AgentRunStatus.FAILED,
                summary=f"{self.agent_name} failed: {exc}",
                structured_output={},
                error=str(exc),
                started_at=started,
                completed_at=datetime.now(timezone.utc),
                model=self.model,
                full_prompt=user_prompt,
            )

    # -- subclass hooks ---------------------------------------------------

    @abstractmethod
    def fallback_output(self, agent_input: AgentInput) -> dict[str, Any]:
        """Deterministic fallback used when the LLM is unavailable.

        This MUST return a dict matching the agent's output schema so the demo
        works without an OpenAI API key.
        """

    def summarise_output(self, payload: dict[str, Any]) -> str:
        """Default summary: take the first short string-valued field."""
        for key in ("summary", "task_summary", "overall_risk", "action_taken"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value[:300]
        return f"{self.agent_name} completed"

    def extract_risk(self, payload: dict[str, Any]) -> RiskLevel | None:
        """Default risk extraction: look for `risk_level` or `overall_risk`."""
        for key in ("risk_level", "overall_risk"):
            value = payload.get(key)
            if isinstance(value, str):
                return coerce_risk(value)
        return None
