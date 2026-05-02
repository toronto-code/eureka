"""Redis-backed model store."""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as redis

from mycelium_learning.models.base import ModelKind, ModelState

logger = logging.getLogger(__name__)


class ModelStore:
    """Stores serialized model state in Redis.

    Keys:
        learning:model:{kind}:global      — global model for all users
        learning:model:{kind}:user:{uid}  — per-user model
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client: redis.Redis | None = None

    async def _get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def _key(kind: ModelKind, user_id: str | None) -> str:
        if user_id:
            return f"learning:model:{kind.value}:user:{user_id}"
        return f"learning:model:{kind.value}:global"

    async def load(
        self, kind: ModelKind, user_id: str | None = None
    ) -> ModelState | None:
        """Load a model state from Redis. Returns None if not found."""
        try:
            client = await self._get_client()
            key = self._key(kind, user_id)
            data = await client.get(key)
            if data is None:
                return None
            return ModelState.from_dict(json.loads(data))
        except Exception:
            logger.exception("Failed to load model %s/%s", kind.value, user_id)
            return None

    async def save(
        self,
        state: ModelState,
        user_id: str | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        """Save a model state to Redis."""
        try:
            client = await self._get_client()
            key = self._key(state.kind, user_id)
            data = json.dumps(state.to_dict())
            if ttl_seconds:
                await client.setex(key, ttl_seconds, data)
            else:
                await client.set(key, data)
        except Exception:
            logger.exception("Failed to save model %s/%s", state.kind.value, user_id)

    async def delete(
        self, kind: ModelKind, user_id: str | None = None
    ) -> None:
        try:
            client = await self._get_client()
            key = self._key(kind, user_id)
            await client.delete(key)
        except Exception:
            logger.exception("Failed to delete model %s/%s", kind.value, user_id)

    async def list_user_models(self, kind: ModelKind) -> list[str]:
        """List user IDs that have a model of the given kind."""
        try:
            client = await self._get_client()
            pattern = f"learning:model:{kind.value}:user:*"
            keys = []
            async for key in client.scan_iter(match=pattern):
                keys.append(key)
            prefix_len = len(f"learning:model:{kind.value}:user:")
            return [k[prefix_len:] for k in keys]
        except Exception:
            logger.exception("Failed to list user models for %s", kind.value)
            return []
