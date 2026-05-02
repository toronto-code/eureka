"""OL Pydantic schemas — typed inputs and outputs for every LLM interaction.

Every OL boundary uses these schemas so downstream code never operates on
free-form dicts. The lane dispatcher, retrieval planner, and persistence
layer all rely on these shapes.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


# -----------------------------------------------------------------------------
# OL input
# -----------------------------------------------------------------------------


class ProjectSummary(_Base):
    """Cheap summary passed to OL during classification.

    IMPORTANT: Keep this small. OL must not see the whole project here — we
    only want the absolute minimum needed to decide the route.
    """

    id: str
    slug: str
    name: str
    description: str | None = None
    primary_language: str | None = None
    jira_project_key: str | None = None
    recent_events_summary: list[str] = Field(default_factory=list)


class OLRequest(_Base):
    """Everything OL sees for a single run."""

    project: ProjectSummary
    user_request: str
    origin: Literal[
        "manual",
        "jira_webhook",
        "jira_polling",
        "github_webhook",
        "github_polling",
        "api",
    ] = "manual"
    origin_reference: str | None = None
    jira_ticket_id: str | None = None
    jira_ticket_key: str | None = None
    repo_id: str | None = None
    acceptance_criteria: list[str] = Field(default_factory=list)
    extra_hints: dict[str, Any] = Field(default_factory=dict)


# -----------------------------------------------------------------------------
# OL output
# -----------------------------------------------------------------------------


RouteLiteral = Literal[
    "inquiry",
    "simple_code",
    "complex_code",
    "planning",
    "blocked",
    "needs_human_review",
]

RiskLiteral = Literal["low", "medium", "high"]
PriorityLiteral = Literal["low", "medium", "high"]

WorkerNameLiteral = Literal[
    "RepoContextAgent",
    "RiskSafetyAgent",
    "InquiryAnswerAgent",
    "SimpleCodePlanAgent",
    "CodeExecutorAgent",
    "PRSummaryAgent",
    "JiraCommentAgent",
    "PlanningAgent",
]


class RetrievalPlan(_Base):
    queries: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    file_paths: list[str] = Field(default_factory=list)
    repo_ids: list[str] = Field(default_factory=list)
    jira_ticket_ids: list[str] = Field(default_factory=list)
    max_chunks: int = 10
    recency_bias: bool = True


class DirectiveInputRequirements(_Base):
    needs_retrieved_chunks: bool = True
    source_types: list[str] = Field(default_factory=list)
    file_paths: list[str] = Field(default_factory=list)
    repo_ids: list[str] = Field(default_factory=list)
    jira_ticket_ids: list[str] = Field(default_factory=list)


class WorkerDirective(_Base):
    worker: WorkerNameLiteral
    purpose: str
    input_requirements: DirectiveInputRequirements = Field(
        default_factory=DirectiveInputRequirements
    )
    expected_output_schema: str = "generic"
    priority: PriorityLiteral = "medium"


class OLClassification(_Base):
    """Full structured output from OL's classifier."""

    route: RouteLiteral
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str
    risk_level: RiskLiteral = "low"
    retrieval_plan: RetrievalPlan = Field(default_factory=RetrievalPlan)
    worker_directives: list[WorkerDirective] = Field(default_factory=list)

    # Useful for the UI even though OL doesn't emit it directly.
    used_shallow_retrieval: bool = False
    model: str | None = None


# -----------------------------------------------------------------------------
# Lane result envelope
# -----------------------------------------------------------------------------


LaneStatusLiteral = Literal["pending", "running", "completed", "blocked", "error"]


class LaneStep(_Base):
    at: str  # ISO timestamp
    label: str
    detail: str | None = None
    ok: bool = True


class LaneResult(_Base):
    lane: str
    status: LaneStatusLiteral
    summary: str
    details: str | None = None
    pr_url: str | None = None
    jira_comment_url: str | None = None
    blocked_reason: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    steps: list[LaneStep] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
