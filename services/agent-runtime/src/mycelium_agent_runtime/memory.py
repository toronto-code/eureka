"""Short-term memory: in-process per-correlation conversation buffer.

This is the ephemeral counterpart to the persistent ``agent_memories`` table.
A correlation_id usually maps to a single conversation or task chain, so we
keep the last N turns per correlation_id while it's active and drop it when
either:

- the correlation has been idle for ``MEMORY_TTL_SECONDS`` (default 3600), or
- we exceed ``MEMORY_LRU_CAP`` distinct correlation_ids (default 100).

The interface (``append`` / ``recent`` / ``clear``) is intentionally generic
so we can swap the in-process dict for a Redis-backed implementation later
without touching the worker.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        logger.warning("%s is not an int, falling back to %d", name, default)
        return default


MEMORY_BUFFER_SIZE = _env_int("MEMORY_BUFFER_SIZE", 20)
MEMORY_TTL_SECONDS = _env_int("MEMORY_TTL_SECONDS", 3600)
MEMORY_LRU_CAP = _env_int("MEMORY_LRU_CAP", 100)


@dataclass
class MemoryTurn:
    role: str  # "user" | "agent" | "system"
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


class ShortTermMemory(Protocol):
    """Minimal interface; concrete impls can live in-process or in Redis."""

    async def append(self, correlation_id: str, turn: MemoryTurn) -> None: ...
    async def recent(self, correlation_id: str, limit: int | None = None) -> list[MemoryTurn]: ...
    async def clear(self, correlation_id: str) -> None: ...


class InProcessShortTermMemory:
    """Default impl. OrderedDict gives us O(1) LRU semantics.

    Not safe across processes — that's what the persistent memory layer is for.
    For multi-replica deployments, wire ``RedisShortTermMemory`` (TODO) instead.
    """

    def __init__(
        self,
        *,
        size: int = MEMORY_BUFFER_SIZE,
        ttl: int = MEMORY_TTL_SECONDS,
        cap: int = MEMORY_LRU_CAP,
    ) -> None:
        self._size = size
        self._ttl = ttl
        self._cap = cap
        self._store: OrderedDict[str, list[MemoryTurn]] = OrderedDict()
        self._touched: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def append(self, correlation_id: str, turn: MemoryTurn) -> None:
        async with self._lock:
            self._evict_locked()
            buf = self._store.get(correlation_id)
            if buf is None:
                buf = []
                self._store[correlation_id] = buf
            buf.append(turn)
            if len(buf) > self._size:
                # Drop oldest turns past the size cap.
                del buf[: len(buf) - self._size]
            self._touched[correlation_id] = time.time()
            self._store.move_to_end(correlation_id)

    async def recent(
        self, correlation_id: str, limit: int | None = None
    ) -> list[MemoryTurn]:
        async with self._lock:
            self._evict_locked()
            buf = self._store.get(correlation_id, [])
            if not buf:
                return []
            self._store.move_to_end(correlation_id)
            self._touched[correlation_id] = time.time()
            if limit is None or limit >= len(buf):
                return list(buf)
            return list(buf[-limit:])

    async def clear(self, correlation_id: str) -> None:
        async with self._lock:
            self._store.pop(correlation_id, None)
            self._touched.pop(correlation_id, None)

    def _evict_locked(self) -> None:
        now = time.time()
        # TTL eviction.
        stale = [cid for cid, ts in self._touched.items() if now - ts > self._ttl]
        for cid in stale:
            self._store.pop(cid, None)
            self._touched.pop(cid, None)
        # LRU eviction.
        while len(self._store) > self._cap:
            cid, _ = self._store.popitem(last=False)
            self._touched.pop(cid, None)


def turns_to_context(turns: Iterable[MemoryTurn]) -> list[dict[str, Any]]:
    """Shape used when injecting memory into a skill's input dict."""
    return [
        {"role": t.role, "content": t.content, "metadata": t.metadata, "ts": t.ts}
        for t in turns
    ]


_default: InProcessShortTermMemory | None = None


def default_memory() -> InProcessShortTermMemory:
    global _default
    if _default is None:
        _default = InProcessShortTermMemory()
    return _default
