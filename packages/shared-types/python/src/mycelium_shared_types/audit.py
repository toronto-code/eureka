"""AuditEntry — immutable log of an agent action."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AuditEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    agent_id: str
    task_id: Optional[str] = None
    action: str
    actor_user_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str
    parent_correlation_id: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)
