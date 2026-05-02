"""Agent and AgentTask schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"
    ERROR = "error"


class Agent(BaseModel):
    """An agent instance bound to an employee."""

    model_config = ConfigDict(extra="forbid")

    id: str
    owner_user_id: str
    capabilities: list[str] = Field(default_factory=list)
    status: AgentStatus = AgentStatus.IDLE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentTaskStatus(str, Enum):
    """Lifecycle states. Transitions are strict — see ``transitions.py``.

    queued → running | pending_approval | cancelled
    pending_approval → running | failed | cancelled
    running → succeeded | failed | pending_approval
    failed → retried | cancelled
    retried → succeeded | cancelled
    """

    QUEUED = "queued"
    PENDING_APPROVAL = "pending_approval"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRIED = "retried"
    CANCELLED = "cancelled"


class AgentTask(BaseModel):
    """A unit of work dispatched to an agent."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    agent_id: str
    agent_type: str = Field(description="Class of agent: triage | onboard | code-review | ...")
    input_data: dict[str, Any] = Field(default_factory=dict)

    correlation_id: str = Field(description="Mandatory. Same rules as MyceliumEvent.")
    parent_correlation_id: Optional[str] = None

    status: AgentTaskStatus = AgentTaskStatus.QUEUED

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
