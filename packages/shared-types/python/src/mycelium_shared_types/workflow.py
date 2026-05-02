"""WorkflowState — current state of a multi-step workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    name: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    correlation_id: str
    parent_correlation_id: Optional[str] = None
    steps_completed: list[str] = Field(default_factory=list)
    next_step: Optional[str] = None
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
