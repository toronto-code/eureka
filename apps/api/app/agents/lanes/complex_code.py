"""ComplexCodeLane.

Today: placeholder provider that produces a plan + identifies files + tests
and posts a status to Jira. NO fake PR is ever opened.

Later: swap `PlaceholderCodeExecutorProvider` for a real one (Cursor
Background Agents, Claude Code SDK, Devin) behind the same interface.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.lanes.base import BaseLane, LaneContext
from app.agents.llm_client import OpenAIClient, get_llm_client
from app.agents.ol.schemas import LaneResult
from app.memory.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Provider interface
# -----------------------------------------------------------------------------


@dataclass
class CodeExecutorInput:
    project_id: str
    repo_id: str | None
    jira_ticket_id: str | None
    user_request: str
    acceptance_criteria: list[str]
    retrieved_chunks: list[RetrievedChunk]


@dataclass
class CodeExecutorOutput:
    status: Literal["delegated", "blocked", "completed"]
    summary: str
    details: str
    pr_url: str | None = None
    extra: dict[str, Any] = None  # type: ignore[assignment]


class CodeExecutorProvider(ABC):
    """Abstract provider so we can swap Cursor / Claude Code / Devin later."""

    name: str = "abstract"

    @abstractmethod
    def execute(self, payload: CodeExecutorInput) -> CodeExecutorOutput: ...


# -----------------------------------------------------------------------------
# Placeholder provider
# -----------------------------------------------------------------------------


_COMPLEX_PLAN_PROMPT = """You are the CodeExecutorAgent in PLACEHOLDER mode.

You do NOT produce code. You produce:
- an implementation plan (3-7 concrete steps)
- the list of files likely to change
- the list of tests likely to run or need updating
- an explanation of why this task is complex
- a short human-readable summary

Return STRICT JSON:
{
  "summary": "short overview",
  "plan_steps": ["..."],
  "relevant_files": ["path/to/file"],
  "likely_tests": ["path/to/test_file"],
  "complexity_reasons": ["..."],
  "recommended_owner": "external_coding_agent | human_reviewer"
}
"""


class _ComplexPlan(BaseModel):
    summary: str
    plan_steps: list[str] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    likely_tests: list[str] = Field(default_factory=list)
    complexity_reasons: list[str] = Field(default_factory=list)
    recommended_owner: str = "external_coding_agent"


class PlaceholderCodeExecutorProvider(CodeExecutorProvider):
    name = "placeholder"

    def __init__(self, llm: OpenAIClient | None = None) -> None:
        self._llm = llm or get_llm_client()

    def execute(self, payload: CodeExecutorInput) -> CodeExecutorOutput:
        plan = self._generate_plan(payload)
        details_md = self._format_plan_markdown(plan)
        return CodeExecutorOutput(
            status="delegated",
            summary=plan.summary,
            details=details_md,
            pr_url=None,
            extra={
                "plan": plan.model_dump(),
                "provider": self.name,
                "note": (
                    "This task was routed to the complex_code lane. Today's "
                    "placeholder provider only produces a plan. Wire a real "
                    "CodeExecutorProvider (Cursor / Claude Code / Devin) to "
                    "open real PRs."
                ),
            },
        )

    def _generate_plan(self, payload: CodeExecutorInput) -> _ComplexPlan:
        chunks_str = "\n\n".join(
            f"[{c.id[:8]}] {c.file_path or c.source_type}\n{c.chunk_text[:800]}"
            for c in payload.retrieved_chunks[:6]
        ) or "(no context)"
        user_prompt = (
            f"User request:\n{payload.user_request}\n\n"
            f"Acceptance criteria:\n"
            + ("\n".join(f"- {a}" for a in payload.acceptance_criteria) or "(none)")
            + f"\n\nContext:\n{chunks_str}"
        )
        if self._llm.configured:
            try:
                data = self._llm.generate_json(
                    system_prompt=_COMPLEX_PLAN_PROMPT, user_prompt=user_prompt
                )
                return _ComplexPlan.model_validate(data)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ComplexCode placeholder LLM failed: %s", exc)
        return _fallback_complex_plan(payload)

    @staticmethod
    def _format_plan_markdown(plan: _ComplexPlan) -> str:
        lines = [
            "## Complex code task — routed to external agent",
            "",
            f"**Summary:** {plan.summary}",
            "",
            "**Plan:**",
        ]
        lines.extend(f"- {s}" for s in plan.plan_steps or ["(no steps)"])
        lines += ["", "**Relevant files:**"]
        lines.extend(f"- `{f}`" for f in plan.relevant_files or ["(none identified)"])
        lines += ["", "**Likely tests to run:**"]
        lines.extend(f"- `{t}`" for t in plan.likely_tests or ["(none identified)"])
        lines += ["", "**Why this is complex:**"]
        lines.extend(f"- {r}" for r in plan.complexity_reasons or ["(no reasons given)"])
        lines += [
            "",
            f"**Recommended owner:** `{plan.recommended_owner}`",
            "",
            "_No PR was opened. When a real code-executor provider is wired, "
            "this plan becomes the brief handed to it._",
        ]
        return "\n".join(lines)


def _fallback_complex_plan(payload: CodeExecutorInput) -> _ComplexPlan:
    return _ComplexPlan(
        summary=f"Complex work required for: {payload.user_request[:120]}",
        plan_steps=[
            "Identify the modules touched by this task.",
            "Read the relevant tests to understand current contracts.",
            "Draft the change in a branch and run the test suite.",
            "Iterate until tests pass, then open a PR.",
        ],
        relevant_files=[
            (c.file_path or "") for c in payload.retrieved_chunks if c.file_path
        ][:5],
        likely_tests=[],
        complexity_reasons=[
            "Touches application code that needs compile + test verification.",
            "One-shot API writes cannot validate correctness.",
        ],
        recommended_owner="external_coding_agent",
    )


# -----------------------------------------------------------------------------
# Lane
# -----------------------------------------------------------------------------


class ComplexCodeLane(BaseLane):
    name = "complex_code"

    def __init__(self, provider: CodeExecutorProvider | None = None) -> None:
        self._provider = provider or PlaceholderCodeExecutorProvider()

    def run(self, ctx: LaneContext) -> LaneResult:
        result = self._empty_result(self.name)
        result.citations = self._citations_from(ctx.retrieved_chunks)

        payload = CodeExecutorInput(
            project_id=ctx.request.project.id,
            repo_id=ctx.request.repo_id,
            jira_ticket_id=ctx.request.jira_ticket_id,
            user_request=ctx.request.user_request,
            acceptance_criteria=ctx.request.acceptance_criteria,
            retrieved_chunks=ctx.retrieved_chunks,
        )
        output = self._provider.execute(payload)

        result.status = "completed" if output.status in ("completed", "delegated") else "blocked"
        result.summary = output.summary
        result.details = output.details
        result.pr_url = output.pr_url
        result.extra = {"provider": self._provider.name, **(output.extra or {})}
        if output.status == "delegated":
            result.blocked_reason = "requires_external_coding_agent"
        ctx.add_step(
            result,
            "complex_code.delegated",
            f"provider={self._provider.name} status={output.status}",
            ok=True,
        )
        return result
