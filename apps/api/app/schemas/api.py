"""DTOs returned by the FastAPI routes.

These keep the wire format stable independent of internal ORM/agent shapes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class TaskOut(_Base):
    id: str
    external_id: str | None = None
    source: str = "jira"
    project_key: str | None = None
    title: str
    description: str | None = None
    status: str
    assignee: str | None = None
    reporter: str | None = None
    labels: list[str] = Field(default_factory=list)
    priority: str | None = None
    risk_level: str | None = None
    approval_status: str = "NOT_REQUIRED"
    created_at: datetime
    updated_at: datetime


class AgentRunOut(_Base):
    id: str
    orchestrator_run_id: str | None = None
    parent_agent_run_id: str | None = None
    spawned_by_agent_run_id: str | None = None
    task_id: str | None = None
    agent_type: str
    agent_name: str
    input_summary: str | None = None
    output_summary: str | None = None
    status: str
    model: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    structured_output_json: dict[str, Any] = Field(default_factory=dict)
    project_data_subset_json: dict[str, Any] = Field(default_factory=dict)
    full_prompt: str | None = None
    created_at: datetime


class AuditLogOut(_Base):
    id: str
    actor: str
    actor_type: str = "agent"
    task_id: str | None = None
    agent_run_id: str | None = None
    action_type: str
    risk_level: str
    approval_status: str
    input_summary: str | None = None
    output_summary: str | None = None
    sources_used: list[str] = Field(default_factory=list)
    created_at: datetime


class ApprovalOut(_Base):
    id: str
    task_id: str | None = None
    agent_run_id: str | None = None
    action_type: str
    risk_level: str
    status: str
    reason: str | None = None
    approver: str | None = None
    decided_at: datetime | None = None
    decision_notes: str | None = None
    created_at: datetime


class DocumentOut(_Base):
    id: str
    source_type: str
    source_id: str | None = None
    title: str
    project_key: str | None = None
    related_task_id: str | None = None
    chunk_count: int = 0
    created_at: datetime


class DocumentDetailOut(DocumentOut):
    content: str
    chunks: list["DocumentChunkOut"] = Field(default_factory=list)


class DocumentChunkOut(_Base):
    id: str
    chunk_index: int
    content: str
    token_count: int | None = None


DocumentDetailOut.model_rebuild()


class WorkerRunRequest(BaseModel):
    agent_type: str
    project_data: dict[str, Any] = Field(default_factory=dict)
    task: dict[str, Any] | None = None
    reason: str | None = None


class OrchestrateRequest(BaseModel):
    project_data: dict[str, Any] = Field(default_factory=dict)


class GraphNode(BaseModel):
    id: str
    type: Literal["orchestrator", "worker"]
    label: str
    status: str
    agent_type: str
    summary: str = ""


class GraphEdge(BaseModel):
    from_: str = Field(alias="from")
    to: str
    label: str = ""

    model_config = ConfigDict(populate_by_name=True)


class AgentGraphOut(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class IntegrationStatusOut(BaseModel):
    openai: bool
    jira: bool
    github: bool
    database: bool
    bot_jira_user: str | None = None
    auto_execute_enabled: bool = False
    github_real_mode: bool = False
    jira_watcher_enabled: bool = False


class ApprovalDecisionRequest(BaseModel):
    approver: str | None = None
    notes: str | None = None


class ExecutedActionOut(_Base):
    id: str
    task_id: str | None = None
    agent_run_id: str | None = None
    integration: str
    action_type: str
    status: str
    dry_run: bool
    summary: str
    target_url: str | None = None
    error_message: str | None = None
    created_at: datetime


class WatcherRunOut(BaseModel):
    picked_up: int
    ran: int
    skipped: int
    details: list[dict[str, Any]]


# -----------------------------------------------------------------------------
# OL (new orchestrator) DTOs
# -----------------------------------------------------------------------------


class ProjectOut(_Base):
    id: str
    slug: str
    name: str
    description: str | None = None
    primary_language: str | None = None
    jira_project_key: str | None = None
    created_at: datetime
    updated_at: datetime


class OrchestratorRunOut(_Base):
    id: str
    project_id: str
    origin: str
    origin_reference: str | None = None
    user_request: str
    route: str | None = None
    confidence: float | None = None
    reasoning_summary: str | None = None
    risk_level: str | None = None
    retrieval_plan: dict[str, Any] = Field(default_factory=dict)
    worker_directives: list[dict[str, Any]] = Field(default_factory=list)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    lane_used: str | None = None
    lane_status: str | None = None
    lane_result: dict[str, Any] = Field(default_factory=dict)
    pr_url: str | None = None
    jira_comment_url: str | None = None
    blocked_reason: str | None = None
    status: str
    errors: list[dict[str, Any]] = Field(default_factory=list)
    run_metadata: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RetrievedChunkOut(BaseModel):
    id: str
    source_type: str
    source_id: str | None = None
    repo_id: str | None = None
    jira_ticket_id: str | None = None
    file_path: str | None = None
    language: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    branch: str | None = None
    commit_sha: str | None = None
    chunk_text: str
    score: float
    semantic_score: float
    keyword_score: float
    recency_score: float
    chunk_metadata: dict[str, Any] = Field(default_factory=dict)


class OLRunDetailOut(BaseModel):
    run: OrchestratorRunOut
    retrieved_chunks: list[RetrievedChunkOut] = Field(default_factory=list)


class OLRunRequest(BaseModel):
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
    jira_ticket_key: str | None = None
    jira_ticket_id: str | None = None
    repo_id: str | None = None
    acceptance_criteria: list[str] = Field(default_factory=list)
    extra_hints: dict[str, Any] = Field(default_factory=dict)


class OLSearchRequest(BaseModel):
    text: str = ""
    source_types: list[str] = Field(default_factory=list)
    file_paths: list[str] = Field(default_factory=list)
    repo_ids: list[str] = Field(default_factory=list)
    jira_ticket_ids: list[str] = Field(default_factory=list)
    max_chunks: int = 10
    recency_bias: bool = True


class OLSearchResponse(BaseModel):
    project_id: str
    chunks: list[RetrievedChunkOut]
    backend: str


class WebhookAckOut(BaseModel):
    accepted: bool
    events_ingested: int
    skipped: list[str] = Field(default_factory=list)
    verified: bool
    reason: str | None = None


class SyncResultOut(BaseModel):
    source: str
    events_ingested: int
    repos_checked: int = 0
    skipped: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
