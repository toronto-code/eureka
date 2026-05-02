"""Base model types and interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from mycelium_learning.signals.types import Signal


class ModelKind(str, Enum):
    """Kinds of learning models."""

    PERMISSIONS = "permissions"
    SKILLS = "skills"
    PATTERNS = "patterns"


@dataclass
class ModelState:
    """Serializable state of a model."""

    kind: ModelKind
    version: int = 1
    signal_count: int = 0
    data: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "version": self.version,
            "signal_count": self.signal_count,
            "data": self.data,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ModelState:
        return cls(
            kind=ModelKind(d["kind"]),
            version=d.get("version", 1),
            signal_count=d.get("signal_count", 0),
            data=d.get("data", {}),
            updated_at=datetime.fromisoformat(d["updated_at"])
            if "updated_at" in d
            else datetime.now(timezone.utc),
        )


class BaseModel(ABC):
    """Base class for learning models.

    A model consumes signals and exposes queries about derived preferences
    or recommendations.
    """

    kind: ModelKind

    def __init__(self, state: ModelState | None = None) -> None:
        self._state = state or ModelState(kind=self.kind)

    @property
    def state(self) -> ModelState:
        return self._state

    @property
    def signal_count(self) -> int:
        return self._state.signal_count

    def update(self, signals: list[Signal]) -> int:
        """Process signals and update model state.

        Returns number of signals actually incorporated (some may be filtered).
        """
        count = 0
        for signal in signals:
            if self._incorporate(signal):
                count += 1
        self._state.signal_count += count
        self._state.version += 1
        self._state.updated_at = datetime.now(timezone.utc)
        return count

    @abstractmethod
    def _incorporate(self, signal: Signal) -> bool:
        """Incorporate a single signal. Returns True if used, False if filtered."""
        ...

    @abstractmethod
    def summary(self) -> dict[str, Any]:
        """Return a human-readable summary of what the model has learned."""
        ...
