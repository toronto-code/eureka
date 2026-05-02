"""Execution result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ExecutionStatus(str, Enum):
    """Status of an execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass
class ExecutionResult:
    """Result of a task execution."""

    execution_id: str
    status: ExecutionStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    duration_ms: int = 0
    actions_executed: int = 0
    actions_blocked: int = 0
    actions_pending_approval: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "execution_id": self.execution_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "actions_executed": self.actions_executed,
            "actions_blocked": self.actions_blocked,
            "actions_pending_approval": self.actions_pending_approval,
        }

    @classmethod
    def success(
        cls,
        execution_id: str,
        result: dict[str, Any],
        duration_ms: int = 0,
        actions_executed: int = 0,
    ) -> ExecutionResult:
        """Create a successful result."""
        now = datetime.now(timezone.utc)
        return cls(
            execution_id=execution_id,
            status=ExecutionStatus.SUCCEEDED,
            result=result,
            completed_at=now,
            duration_ms=duration_ms,
            actions_executed=actions_executed,
        )

    @classmethod
    def failure(
        cls,
        execution_id: str,
        error: str,
        duration_ms: int = 0,
    ) -> ExecutionResult:
        """Create a failed result."""
        now = datetime.now(timezone.utc)
        return cls(
            execution_id=execution_id,
            status=ExecutionStatus.FAILED,
            error=error,
            completed_at=now,
            duration_ms=duration_ms,
        )
