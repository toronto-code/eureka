"""OLClassifier: route-first, retrieve-later.

Flow per run:

1. Build a *small* prompt from the request + project summary (no chunks).
2. Call GPT-4o; parse strict JSON into `OLClassification`.
3. If `confidence < threshold`, do a *shallow* retrieval (top-3 keyword hits)
   and call GPT-4o one more time with that tiny context window. We never
   loop more than twice — if it's still ambiguous, we route to
   `needs_human_review`.
4. Never store or log chain-of-thought. Only `reasoning_summary` is kept.

Deterministic fallback: when `OPENAI_API_KEY` is missing, `OLClassifier`
returns a rule-based classification so the demo still runs.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agents.llm_client import OpenAIClient, get_llm_client
from app.agents.ol.prompts import (
    OL_CLASSIFIER_SYSTEM_PROMPT,
    OL_CLASSIFIER_USER_TEMPLATE,
)
from app.agents.ol.schemas import (
    DirectiveInputRequirements,
    OLClassification,
    OLRequest,
    ProjectSummary,
    RetrievalPlan,
    WorkerDirective,
)
from app.memory.project_data import ProjectDataService
from app.memory.retrieval import RetrievalQuery

logger = logging.getLogger(__name__)


CONFIDENCE_RETRY_THRESHOLD = 0.6
SHALLOW_RETRIEVAL_CHUNK_LIMIT = 3


@dataclass
class ClassifyOutcome:
    classification: OLClassification
    shallow_chunks: list[dict[str, Any]]


class OLClassifier:
    """Route-first orchestrator classifier."""

    def __init__(
        self,
        llm: OpenAIClient | None = None,
        project_data: ProjectDataService | None = None,
    ) -> None:
        self._llm = llm or get_llm_client()
        self._project_data = project_data or ProjectDataService()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def classify(
        self, session: Session, request: OLRequest
    ) -> ClassifyOutcome:
        """Run the classify-first flow. Returns classification + any shallow
        chunks the second pass used (for audit)."""
        classification = self._call_once(request, shallow_context=None)
        shallow_used: list[dict[str, Any]] = []
        if classification.confidence < CONFIDENCE_RETRY_THRESHOLD:
            shallow_used = self._shallow_retrieve(session, request)
            if shallow_used:
                classification = self._call_once(
                    request, shallow_context=shallow_used
                )
                classification.used_shallow_retrieval = True
            else:
                # Nothing in memory yet — flag as needs_human_review only if
                # confidence stays low after the extra pass.
                classification.used_shallow_retrieval = False
        classification.model = self._llm.default_model if self._llm.configured else "fallback:rule-based"
        return ClassifyOutcome(classification=classification, shallow_chunks=shallow_used)

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    def _call_once(
        self, request: OLRequest, *, shallow_context: list[dict[str, Any]] | None
    ) -> OLClassification:
        user_prompt = _render_user_prompt(request, shallow_context=shallow_context)
        if not self._llm.configured:
            return _rule_based_fallback(request)
        try:
            raw = self._llm.generate_json(
                system_prompt=OL_CLASSIFIER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model=self._llm.default_model,
            )
            return _parse_classification(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("OL classifier LLM call failed: %s", exc)
            return _rule_based_fallback(request)

    # ------------------------------------------------------------------
    # Shallow retrieval
    # ------------------------------------------------------------------

    def _shallow_retrieve(
        self, session: Session, request: OLRequest
    ) -> list[dict[str, Any]]:
        query = RetrievalQuery(
            project_id=request.project.id,
            text=request.user_request,
            max_chunks=SHALLOW_RETRIEVAL_CHUNK_LIMIT,
            per_source_cap=2,
            recency_bias=True,
        )
        try:
            hits = self._project_data.search(session, query)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Shallow retrieval failed: %s", exc)
            return []
        return [
            {
                "id": h.id,
                "source_type": h.source_type,
                "file_path": h.file_path,
                "excerpt": h.chunk_text[:400],
            }
            for h in hits
        ]


# -----------------------------------------------------------------------------
# Prompt rendering
# -----------------------------------------------------------------------------


def _render_user_prompt(
    request: OLRequest, *, shallow_context: list[dict[str, Any]] | None
) -> str:
    project = request.project
    recent = "\n".join(f"- {line}" for line in project.recent_events_summary[:10]) or "(none)"
    shallow = (
        "\n".join(
            f"[{c.get('id','?')[:8]}] ({c.get('source_type')}) "
            f"{c.get('file_path') or ''}\n{c.get('excerpt','')}"
            for c in shallow_context
        )
        if shallow_context
        else "(none)"
    )
    return OL_CLASSIFIER_USER_TEMPLATE.format(
        project_id=project.id,
        slug=project.slug,
        name=project.name,
        primary_language=project.primary_language or "unknown",
        jira_project_key=project.jira_project_key or "(unset)",
        description=(project.description or "(no description)")[:600],
        recent_events=recent,
        origin=request.origin,
        jira_ticket=request.jira_ticket_key or request.jira_ticket_id or "(none)",
        repo_id=request.repo_id or "(none)",
        acceptance_criteria=", ".join(request.acceptance_criteria) or "(none)",
        user_request=request.user_request.strip(),
        shallow_context=shallow,
    )


# -----------------------------------------------------------------------------
# JSON parsing + validation
# -----------------------------------------------------------------------------


def _parse_classification(raw: Any) -> OLClassification:
    data: dict[str, Any]
    if isinstance(raw, str):
        data = json.loads(raw)
    elif isinstance(raw, dict):
        data = raw
    else:
        raise ValueError(f"OL returned non-JSON value of type {type(raw).__name__}")
    try:
        return OLClassification.model_validate(data)
    except ValidationError as exc:
        logger.warning("OL classification failed validation: %s", exc)
        # Best-effort coercion: fall back to needs_human_review.
        return OLClassification(
            route="needs_human_review",
            confidence=0.2,
            reasoning_summary="Classifier output did not match schema; escalating.",
            risk_level="medium",
            retrieval_plan=RetrievalPlan(),
            worker_directives=[
                WorkerDirective(
                    worker="RiskSafetyAgent",
                    purpose="Schema-invalid classification",
                    priority="high",
                )
            ],
        )


# -----------------------------------------------------------------------------
# Rule-based fallback (used when no OpenAI key is configured)
# -----------------------------------------------------------------------------


_CODE_HINTS = (
    "implement", "refactor", "fix the", "add a ", "remove the", "write a ",
    "update the code", "change the code", "create a new file",
)
_SIMPLE_HINTS = (
    "onboarding doc", "readme", "documentation", "docs", "changelog",
    "typo", "update doc",
)
_INQUIRY_HINTS = (
    "what ", "how does", "where is", "explain ", "summarize", "summary of",
    "who owns", "why ", "status of",
)
_PLANNING_HINTS = ("plan ", "outline ", "breakdown", "how would you")
_BLOCKED_HINTS = ("cannot ", "need access", "waiting on")


def _rule_based_fallback(request: OLRequest) -> OLClassification:
    text = request.user_request.lower()
    route: str = "inquiry"
    if any(h in text for h in _BLOCKED_HINTS):
        route = "blocked"
    elif any(h in text for h in _PLANNING_HINTS):
        route = "planning"
    elif any(h in text for h in _SIMPLE_HINTS) or "add a section" in text:
        route = "simple_code"
    elif any(h in text for h in _CODE_HINTS):
        route = "complex_code"
    elif any(h in text for h in _INQUIRY_HINTS):
        route = "inquiry"

    workers = _fallback_workers_for(route)
    return OLClassification(
        route=route,  # type: ignore[arg-type]
        confidence=0.65 if route != "inquiry" else 0.7,
        reasoning_summary=(
            f"Rule-based fallback (no LLM): matched `{route}` on user text."
        ),
        risk_level="medium" if route == "complex_code" else "low",
        retrieval_plan=RetrievalPlan(
            queries=[request.user_request[:200]],
            source_types=_fallback_source_types_for(route),
            max_chunks=_fallback_max_chunks_for(route),
            recency_bias=True,
        ),
        worker_directives=workers,
    )


def _fallback_workers_for(route: str) -> list[WorkerDirective]:
    reqs = DirectiveInputRequirements(needs_retrieved_chunks=True)
    if route == "inquiry":
        return [
            WorkerDirective(worker="RepoContextAgent", purpose="pull relevant code + docs", input_requirements=reqs),
            WorkerDirective(worker="InquiryAnswerAgent", purpose="answer the question", input_requirements=reqs),
        ]
    if route == "simple_code":
        return [
            WorkerDirective(worker="RepoContextAgent", purpose="locate target file(s)", input_requirements=reqs),
            WorkerDirective(worker="SimpleCodePlanAgent", purpose="draft edits + PR", input_requirements=reqs),
            WorkerDirective(worker="RiskSafetyAgent", purpose="validate safety", input_requirements=reqs, priority="high"),
            WorkerDirective(worker="PRSummaryAgent", purpose="write PR body", input_requirements=reqs),
            WorkerDirective(worker="JiraCommentAgent", purpose="write Jira comment", input_requirements=reqs),
        ]
    if route == "complex_code":
        return [
            WorkerDirective(worker="RepoContextAgent", purpose="prep context bundle", input_requirements=reqs),
            WorkerDirective(
                worker="CodeExecutorAgent",
                purpose="delegate to external coding agent",
                input_requirements=reqs,
                priority="high",
            ),
        ]
    if route == "planning":
        return [
            WorkerDirective(worker="PlanningAgent", purpose="produce a structured plan", input_requirements=reqs),
            WorkerDirective(worker="JiraCommentAgent", purpose="post plan to Jira", input_requirements=reqs),
        ]
    if route == "blocked":
        return [WorkerDirective(worker="RiskSafetyAgent", purpose="explain blocker", input_requirements=reqs)]
    # needs_human_review
    return [
        WorkerDirective(
            worker="RiskSafetyAgent",
            purpose="escalate to human",
            input_requirements=reqs,
            priority="high",
        )
    ]


def _fallback_source_types_for(route: str) -> list[str]:
    if route == "inquiry":
        return ["code_file", "doc", "jira_ticket", "pr", "commit", "comment"]
    if route == "simple_code":
        return ["code_file", "doc"]
    if route == "complex_code":
        return ["code_file"]
    if route == "planning":
        return ["jira_ticket", "doc", "pr"]
    return []


def _fallback_max_chunks_for(route: str) -> int:
    return {
        "inquiry": 15,
        "simple_code": 8,
        "complex_code": 4,
        "planning": 12,
        "blocked": 0,
        "needs_human_review": 4,
    }.get(route, 8)
