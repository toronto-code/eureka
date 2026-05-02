"""Local learning backend - frequency-based model updates in-process."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING

from mycelium_learning.config import (
    RECENT_SIGNAL_WEIGHT,
    RECENT_SIGNAL_WINDOW_HOURS,
)
from mycelium_learning.backends.base import UpdateResult

if TYPE_CHECKING:
    from mycelium_learning.models.base import BaseModel, ModelKind
    from mycelium_learning.signals.types import Signal

logger = logging.getLogger(__name__)


class LocalBackend:
    """Local learning - applies signals to models with recency weighting.

    Not true RL, but establishes the signal → model update pipeline. When
    OpenClaw rl/genverse is available, swap this out.
    """

    def __init__(
        self,
        recent_weight: float = RECENT_SIGNAL_WEIGHT,
        recent_window_hours: int = RECENT_SIGNAL_WINDOW_HOURS,
    ) -> None:
        self._recent_weight = recent_weight
        self._recent_window = timedelta(hours=recent_window_hours)

    def _apply_recency_weight(self, signal: Signal) -> Signal:
        """Boost weight of recent signals."""
        now = datetime.now(timezone.utc)
        age = now - signal.created_at
        if age < self._recent_window:
            decay = 1.0 - (age.total_seconds() / self._recent_window.total_seconds())
            signal.weight = signal.weight * (1.0 + decay * (self._recent_weight - 1.0))
        return signal

    async def update(
        self,
        signals: list[Signal],
        models: dict[ModelKind, BaseModel],
    ) -> UpdateResult:
        """Apply signals to all models."""
        weighted = [self._apply_recency_weight(s) for s in signals]

        updated: list[str] = []
        total_processed = 0

        for kind, model in models.items():
            try:
                count = model.update(weighted)
                if count > 0:
                    updated.append(kind.value)
                    total_processed += count
                logger.info(
                    "Model %s: incorporated %d/%d signals (total seen: %d)",
                    kind.value,
                    count,
                    len(weighted),
                    model.signal_count,
                )
            except Exception as e:
                logger.exception("Model %s update failed", kind.value)
                return UpdateResult(
                    signals_processed=total_processed,
                    models_updated=updated,
                    error=f"{kind.value}: {e}",
                )

        return UpdateResult(
            signals_processed=total_processed,
            models_updated=updated,
            metadata={
                "signals_in": len(signals),
                "signals_applied_with_weighting": len(weighted),
            },
        )

    async def close(self) -> None:
        pass
