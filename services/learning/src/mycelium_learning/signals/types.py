"""Signal data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class SignalKind(str, Enum):
    """What kind of signal this is."""

    TASK_RESULT = "task_result"
    APPROVAL_DECISION = "approval_decision"
    USER_FEEDBACK = "user_feedback"
    ACTION_OUTCOME = "action_outcome"
    INTERACTION = "interaction"


class Outcome(str, Enum):
    """The outcome that drives the learning signal."""

    SUCCESS = "success"
    FAILURE = "failure"
    APPROVED = "approved"
    REJECTED = "rejected"
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


@dataclass
class Signal:
    """A normalized learning signal.

    All sources (task results, approvals, feedback) get normalized into this
    shape so the models can consume them uniformly.
    """

    kind: SignalKind
    outcome: Outcome
    id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    agent_type: str | None = None
    action_type: str | None = None
    action_pattern: str | None = None
    correlation_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "outcome": self.outcome.value,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "agent_type": self.agent_type,
            "action_type": self.action_type,
            "action_pattern": self.action_pattern,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
            "weight": self.weight,
            "created_at": self.created_at.isoformat(),
        }

    @property
    def is_positive(self) -> bool:
        return self.outcome in (Outcome.SUCCESS, Outcome.APPROVED, Outcome.POSITIVE)

    @property
    def is_negative(self) -> bool:
        return self.outcome in (Outcome.FAILURE, Outcome.REJECTED, Outcome.NEGATIVE)

    @classmethod
    def from_task_result(cls, payload: dict[str, Any]) -> Signal:
        """Create a signal from an agents.results message."""
        status = payload.get("status", "")
        outcome = Outcome.SUCCESS if status == "succeeded" else (
            Outcome.FAILURE if status == "failed" else Outcome.NEUTRAL
        )
        input_data = payload.get("input_data") or {}
        return cls(
            kind=SignalKind.TASK_RESULT,
            outcome=outcome,
            user_id=input_data.get("user_id"),
            agent_id=payload.get("agent_id"),
            task_id=payload.get("task_id"),
            agent_type=payload.get("agent_type"),
            correlation_id=payload.get("correlation_id", ""),
            metadata={
                "status": status,
                "error": payload.get("error"),
                "has_result": bool(payload.get("result")),
            },
        )

    @classmethod
    def from_approval_decision(cls, payload: dict[str, Any]) -> Signal | None:
        """Create a signal from a workflows.approvals decision.

        Returns None for 'requested' decisions (not a learning signal).
        """
        decision = payload.get("decision", "")
        if decision not in ("approve", "reject"):
            return None

        outcome = Outcome.APPROVED if decision == "approve" else Outcome.REJECTED

        pending = payload.get("pending_actions") or []
        action_types = [a.get("type") for a in pending if a.get("type")]
        primary_action_type = action_types[0] if action_types else None

        return cls(
            kind=SignalKind.APPROVAL_DECISION,
            outcome=outcome,
            user_id=payload.get("actor_user_id"),
            agent_id=payload.get("agent_id"),
            task_id=payload.get("task_id") or payload.get("workflow_id"),
            action_type=primary_action_type,
            correlation_id=payload.get("correlation_id", ""),
            metadata={
                "decision": decision,
                "notes": payload.get("notes"),
                "pending_actions": pending,
                "all_action_types": action_types,
            },
        )

    @classmethod
    def from_user_feedback(
        cls,
        user_id: str,
        task_id: str | None,
        agent_id: str | None,
        positive: bool,
        notes: str | None = None,
        agent_type: str | None = None,
    ) -> Signal:
        """Create a signal from explicit user feedback (thumbs up/down)."""
        return cls(
            kind=SignalKind.USER_FEEDBACK,
            outcome=Outcome.POSITIVE if positive else Outcome.NEGATIVE,
            user_id=user_id,
            agent_id=agent_id,
            task_id=task_id,
            agent_type=agent_type,
            metadata={"notes": notes} if notes else {},
        )
