"""Action types for agent operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from mycelium_agent_runtime.permissions.rules import ActionType


class ActionStatus(str, Enum):
    """Status of an action."""

    PENDING = "pending"
    APPROVED = "approved"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    PENDING_APPROVAL = "pending_approval"
    DENIED = "denied"


@dataclass
class Action:
    """An action proposed by an agent skill.

    Actions go through the permission guard before execution.
    """

    type: ActionType
    payload: dict[str, Any]
    reasoning: str
    id: str = field(default_factory=lambda: str(uuid4()))
    status: ActionStatus = ActionStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "type": self.type.value,
            "payload": self.payload,
            "reasoning": self.reasoning,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def shell(cls, command: str, reasoning: str, **kwargs: Any) -> Action:
        """Create a shell command action."""
        return cls(
            type=ActionType.SHELL_COMMAND,
            payload={"command": command, **kwargs},
            reasoning=reasoning,
        )

    @classmethod
    def file_read(cls, path: str, reasoning: str) -> Action:
        """Create a file read action."""
        return cls(
            type=ActionType.FILE_READ,
            payload={"path": path},
            reasoning=reasoning,
        )

    @classmethod
    def file_write(cls, path: str, content: str, reasoning: str) -> Action:
        """Create a file write action."""
        return cls(
            type=ActionType.FILE_WRITE,
            payload={"path": path, "content": content},
            reasoning=reasoning,
        )

    @classmethod
    def file_delete(cls, path: str, reasoning: str) -> Action:
        """Create a file delete action."""
        return cls(
            type=ActionType.FILE_DELETE,
            payload={"path": path},
            reasoning=reasoning,
        )

    @classmethod
    def git_read(cls, command: str, reasoning: str) -> Action:
        """Create a git read action (status, log, diff, etc.)."""
        return cls(
            type=ActionType.GIT_READ,
            payload={"command": command},
            reasoning=reasoning,
        )

    @classmethod
    def git_write(cls, command: str, reasoning: str) -> Action:
        """Create a git write action (commit, push, etc.)."""
        return cls(
            type=ActionType.GIT_WRITE,
            payload={"command": command},
            reasoning=reasoning,
        )

    @classmethod
    def http_request(
        cls,
        method: str,
        url: str,
        reasoning: str,
        headers: dict[str, str] | None = None,
        body: Any = None,
    ) -> Action:
        """Create an HTTP request action."""
        return cls(
            type=ActionType.HTTP_REQUEST,
            payload={
                "method": method,
                "url": url,
                "headers": headers or {},
                "body": body,
            },
            reasoning=reasoning,
        )


@dataclass
class ActionResult:
    """Result of executing an action."""

    action_id: str
    success: bool
    output: str | None = None
    error: str | None = None
    duration_ms: int = 0
    exit_code: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "action_id": self.action_id,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "exit_code": self.exit_code,
            "metadata": self.metadata,
        }

    @classmethod
    def success(
        cls,
        action_id: str,
        output: str,
        duration_ms: int = 0,
        exit_code: int = 0,
        **metadata: Any,
    ) -> ActionResult:
        """Create a successful result."""
        return cls(
            action_id=action_id,
            success=True,
            output=output,
            duration_ms=duration_ms,
            exit_code=exit_code,
            metadata=metadata,
        )

    @classmethod
    def failure(
        cls,
        action_id: str,
        error: str,
        duration_ms: int = 0,
        exit_code: int = 1,
        **metadata: Any,
    ) -> ActionResult:
        """Create a failed result."""
        return cls(
            action_id=action_id,
            success=False,
            error=error,
            duration_ms=duration_ms,
            exit_code=exit_code,
            metadata=metadata,
        )

    @classmethod
    def blocked(cls, action_id: str, reason: str) -> ActionResult:
        """Create a blocked result."""
        return cls(
            action_id=action_id,
            success=False,
            error=f"Action blocked: {reason}",
            metadata={"blocked": True, "reason": reason},
        )

    @classmethod
    def pending_approval(cls, action_id: str, reason: str) -> ActionResult:
        """Create a pending approval result."""
        return cls(
            action_id=action_id,
            success=False,
            error=None,
            output=f"Action requires approval: {reason}",
            metadata={"pending_approval": True, "reason": reason},
        )
