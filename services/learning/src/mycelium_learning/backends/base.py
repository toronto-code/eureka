"""Learning backend protocol and types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from mycelium_learning.models.base import BaseModel, ModelKind
    from mycelium_learning.signals.types import Signal


@dataclass
class UpdateResult:
    """Result of a learning update pass."""

    signals_processed: int
    models_updated: list[str] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "signals_processed": self.signals_processed,
            "models_updated": self.models_updated,
            "error": self.error,
            "metadata": self.metadata,
        }


class LearningBackend(Protocol):
    """Protocol for learning backends.

    Backends handle the actual "learning" step - taking signals and updating
    model state. Local backends do simple frequency-based tracking. External
    backends (OpenClaw rl/genverse) can run more sophisticated RL.
    """

    async def update(
        self,
        signals: list[Signal],
        models: dict[ModelKind, BaseModel],
    ) -> UpdateResult:
        """Update models based on signals.

        Args:
            signals: The signals to process
            models: Current model state (keyed by ModelKind)

        Returns:
            UpdateResult summarizing what happened
        """
        ...

    async def close(self) -> None:
        """Close any open resources."""
        ...
