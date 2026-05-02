"""ProjectData and related Pydantic models.

These define the flexible shape of context the orchestrator works with.
Every field is optional so the orchestrator stays robust when data is missing.
Each model permits free-form `metadata` dicts so callers can attach extra fields
without changing the schema.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    """Base model: ignore unknown fields, allow arbitrary metadata."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class JiraTaskData(_Base):
    id: str | None = None
    key: str | None = None
    title: str | None = None
    description: str | None = None
    status: str | None = None
    assignee: str | None = None
    reporter: str | None = None
    labels: list[str] = Field(default_factory=list)
    comments: list[dict[str, Any]] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    priority: str | None = None
    project_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CodeFileData(_Base):
    path: str
    repo: str | None = None
    language: str | None = None
    content: str | None = None
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GitHubRepoData(_Base):
    owner: str | None = None
    name: str
    description: str | None = None
    primary_language: str | None = None
    files: list[CodeFileData] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocData(_Base):
    id: str | None = None
    title: str
    content: str | None = None
    source: str | None = None
    url: str | None = None
    project_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TranscriptData(_Base):
    id: str | None = None
    title: str | None = None
    content: str | None = None
    participants: list[str] = Field(default_factory=list)
    occurred_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PreviousAgentRunData(_Base):
    id: str | None = None
    agent_type: str | None = None
    summary: str | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    risk_level: str | None = None
    occurred_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalData(_Base):
    action_type: str
    status: str = "REQUIRED"
    approver: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditLogData(_Base):
    actor: str | None = None
    action_type: str | None = None
    risk_level: str | None = None
    summary: str | None = None
    occurred_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SystemConfigData(_Base):
    default_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"
    risk_policy_version: str = "v1"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectData(_Base):
    """The wide context object passed to the orchestrator.

    Any field may be missing. Worker agents only ever see focused subsets.
    """

    user_goal: str | None = None
    current_task: JiraTaskData | None = None
    jira_tasks: list[JiraTaskData] = Field(default_factory=list)
    github_repositories: list[GitHubRepoData] = Field(default_factory=list)
    code_files: list[CodeFileData] = Field(default_factory=list)
    docs: list[DocData] = Field(default_factory=list)
    transcripts: list[TranscriptData] = Field(default_factory=list)
    previous_agent_runs: list[PreviousAgentRunData] = Field(default_factory=list)
    audit_logs: list[AuditLogData] = Field(default_factory=list)
    approvals: list[ApprovalData] = Field(default_factory=list)
    available_tools: list[str] = Field(default_factory=list)
    system_config: SystemConfigData = Field(default_factory=SystemConfigData)
    constraints: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
