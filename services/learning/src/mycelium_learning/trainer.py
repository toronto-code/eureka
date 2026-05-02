"""Trainer - orchestrates the signal → model update loop.

Receives flushed signal batches from the buffer, runs them through the
learning backend to update all three models, and persists updated model
state to Redis.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mycelium_learning.config import MODEL_CACHE_TTL_SECONDS
from mycelium_learning.models import (
    ModelKind,
    ModelStore,
    PermissionModel,
    SkillModel,
    PatternModel,
)

if TYPE_CHECKING:
    from mycelium_learning.backends.base import LearningBackend
    from mycelium_learning.models.base import BaseModel
    from mycelium_learning.signals.types import Signal

logger = logging.getLogger(__name__)


class Trainer:
    """Orchestrates model updates.

    Maintains the in-memory model instances, loads prior state from the store
    on startup, and writes updated state back after each flush.
    """

    def __init__(
        self,
        backend: LearningBackend,
        store: ModelStore,
        user_scoped: bool = True,
    ) -> None:
        self._backend = backend
        self._store = store
        self._user_scoped = user_scoped
        self._global_models: dict[ModelKind, BaseModel] = {}
        self._user_models: dict[str, dict[ModelKind, BaseModel]] = {}
        self._total_batches = 0
        self._last_update = None

    def _new_model(self, kind: ModelKind) -> BaseModel:
        if kind == ModelKind.PERMISSIONS:
            return PermissionModel()
        if kind == ModelKind.SKILLS:
            return SkillModel()
        if kind == ModelKind.PATTERNS:
            return PatternModel()
        raise ValueError(f"Unknown model kind: {kind}")

    async def load_all(self) -> None:
        """Load all global models from the store into memory."""
        for kind in ModelKind:
            state = await self._store.load(kind, user_id=None)
            model = self._new_model(kind)
            if state is not None:
                model._state = state
                logger.info(
                    "Loaded model %s (version=%d, signals=%d)",
                    kind.value,
                    state.version,
                    state.signal_count,
                )
            else:
                logger.info("Initialized fresh model: %s", kind.value)
            self._global_models[kind] = model

    async def _ensure_user_models(self, user_id: str) -> dict[ModelKind, BaseModel]:
        if user_id in self._user_models:
            return self._user_models[user_id]

        user_models: dict[ModelKind, BaseModel] = {}
        for kind in ModelKind:
            state = await self._store.load(kind, user_id=user_id)
            model = self._new_model(kind)
            if state is not None:
                model._state = state
            user_models[kind] = model

        self._user_models[user_id] = user_models
        return user_models

    async def on_flush(self, signals: list[Signal]) -> None:
        """Callback invoked by SignalBuffer when the batch is flushed."""
        if not signals:
            return

        self._total_batches += 1

        logger.info("Training on %d signals", len(signals))

        global_result = await self._backend.update(signals, self._global_models)
        logger.info("Global update: %s", global_result.to_dict())

        for kind, model in self._global_models.items():
            await self._store.save(
                model.state,
                user_id=None,
                ttl_seconds=MODEL_CACHE_TTL_SECONDS,
            )

        if self._user_scoped:
            by_user: dict[str, list[Signal]] = {}
            for signal in signals:
                if signal.user_id:
                    by_user.setdefault(signal.user_id, []).append(signal)

            for user_id, user_signals in by_user.items():
                user_models = await self._ensure_user_models(user_id)
                await self._backend.update(user_signals, user_models)

                for kind, model in user_models.items():
                    await self._store.save(
                        model.state,
                        user_id=user_id,
                        ttl_seconds=MODEL_CACHE_TTL_SECONDS,
                    )

        from datetime import datetime, timezone
        self._last_update = datetime.now(timezone.utc)

    def get_global_model(self, kind: ModelKind) -> BaseModel:
        return self._global_models[kind]

    async def get_user_model(self, user_id: str, kind: ModelKind) -> BaseModel:
        models = await self._ensure_user_models(user_id)
        return models[kind]

    @property
    def stats(self) -> dict:
        return {
            "total_batches_processed": self._total_batches,
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "users_tracked": len(self._user_models),
            "global_models": {
                kind.value: {
                    "signal_count": model.signal_count,
                    "version": model.state.version,
                }
                for kind, model in self._global_models.items()
            },
        }
