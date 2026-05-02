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
