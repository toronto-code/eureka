"""PlanningLane: produce a structured plan + optionally post it to Jira."""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.agents.lanes.base import BaseLane, LaneContext
from app.agents.llm_client import OpenAIClient, get_llm_client
from app.agents.ol.prompts import PLANNING_SYSTEM_PROMPT
from app.agents.ol.schemas import LaneResult
from app.integrations.jira import JiraClient, get_jira_client

logger = logging.getLogger(__name__)


class _PlanStep(BaseModel):
    title: str
    detail: str | None = None
    files_touched: list[str] = Field(default_factory=list)
    risk: str = "low"


class _Plan(BaseModel):
    goal: str
    assumptions: list[str] = Field(default_factory=list)
    steps: list[_PlanStep] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    estimated_complexity: str = "medium"


class PlanningLane(BaseLane):
    name = "planning"

    def __init__(
        self,
        llm: OpenAIClient | None = None,
        jira: JiraClient | None = None,
    ) -> None:
        self._llm = llm or get_llm_client()
        self._jira = jira or get_jira_client()

    def run(self, ctx: LaneContext) -> LaneResult:
        result = self._empty_result(self.name)
        result.citations = self._citations_from(ctx.retrieved_chunks)

        plan = self._generate_plan(ctx)
        if plan is None:
            result.status = "error"
            result.summary = "Planning lane failed to produce a structured plan."
            ctx.add_step(result, "planning.failed", ok=False)
            return result

        markdown = _plan_to_markdown(plan)
        result.summary = plan.goal
        result.details = markdown
        result.extra = {"plan": plan.model_dump()}
        result.status = "completed"
        ctx.add_step(result, "planning.generated", f"{len(plan.steps)} steps")

        # Optionally post to Jira when we have a ticket anchor.
        if ctx.request.jira_ticket_key:
            try:
                jr = self._jira.post_comment(
                    ctx.request.jira_ticket_key,
                    f"🧭 Mycelium plan:\n\n{markdown}",
                )
                result.jira_comment_url = jr.get("html_url")
                ctx.add_step(
                    result,
                    "planning.posted_to_jira",
                    f"dry_run={jr.get('dry_run', True)}",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("PlanningLane Jira post failed: %s", exc)
                ctx.add_step(result, "planning.jira_post_failed", str(exc), ok=False)
        return result

    # ------------------------------------------------------------------
    # Plan generation
    # ------------------------------------------------------------------

    def _generate_plan(self, ctx: LaneContext) -> _Plan | None:
        chunks_str = "\n\n".join(
            f"[{c.id[:8]}] {c.file_path or c.source_type}\n{c.chunk_text[:800]}"
            for c in ctx.retrieved_chunks[:10]
        ) or "(no context)"
        user_prompt = (
            f"User request:\n{ctx.request.user_request.strip()}\n\n"
            f"Acceptance criteria:\n"
            + ("\n".join(f"- {a}" for a in ctx.request.acceptance_criteria) or "(none)")
            + f"\n\nContext:\n{chunks_str}"
        )
        if not self._llm.configured:
            return _fallback_plan(ctx)
        try:
            raw = self._llm.generate_json(
                system_prompt=PLANNING_SYSTEM_PROMPT, user_prompt=user_prompt
            )
            return _Plan.model_validate(raw)
        except ValidationError as exc:
            logger.warning("PlanningLane plan failed schema: %s", exc)
            return _fallback_plan(ctx)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PlanningLane LLM call failed: %s", exc)
            return _fallback_plan(ctx)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _plan_to_markdown(plan: _Plan) -> str:
    lines = [f"**Goal:** {plan.goal}", ""]
    if plan.assumptions:
        lines += ["**Assumptions:**"] + [f"- {a}" for a in plan.assumptions] + [""]
    lines += ["**Steps:**"]
    for i, step in enumerate(plan.steps, 1):
        bullet = f"{i}. **{step.title}**"
        if step.detail:
            bullet += f" — {step.detail}"
        bullet += f"  _(risk: {step.risk})_"
        lines.append(bullet)
        if step.files_touched:
            lines.append("   - Files: " + ", ".join(f"`{f}`" for f in step.files_touched))
    if plan.open_questions:
        lines += ["", "**Open questions:**"] + [f"- {q}" for q in plan.open_questions]
    lines += ["", f"**Estimated complexity:** {plan.estimated_complexity}"]
    return "\n".join(lines)


def _fallback_plan(ctx: LaneContext) -> _Plan:
    files = [
        c.file_path or ""
        for c in ctx.retrieved_chunks
        if c.file_path
    ][:5]
    return _Plan(
        goal=f"Deliver: {ctx.request.user_request[:140]}",
        assumptions=["No LLM available; producing a minimal fallback plan."],
        steps=[
            _PlanStep(
                title="Gather requirements",
                detail="Confirm acceptance criteria and ownership.",
                risk="low",
            ),
            _PlanStep(
                title="Identify affected files",
                detail="Map the request to concrete paths.",
                files_touched=files,
                risk="medium",
            ),
            _PlanStep(
                title="Execute change and open PR",
                detail="Either SimpleCodeLane (one-shot) or ComplexCodeLane (external agent).",
                risk="medium",
            ),
        ],
        open_questions=["Who should review this PR?"],
        estimated_complexity="medium",
    )
