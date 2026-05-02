"""Embedding providers.

Each provider implements :class:`EmbeddingProvider`. A small factory chooses
the active one from environment.

Why a hash provider exists at all: in DEV_MODE we need every codepath that
*depends* on embeddings (event embedder, agent memory write, semantic search)
to actually exercise the database column. Without the hash provider, we'd
either need an OpenAI key in CI or every call would have to be mocked. The
hash output is deterministic, fast, and the resulting cosine similarity is
meaningless — exactly what you want for tests and local demos.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import struct
from typing import Iterable, Protocol

logger = logging.getLogger(__name__)

# Must match EMBEDDING_DIM in mycelium_db and the migrations.
EMBEDDING_DIM = 1536


class EmbeddingProvider(Protocol):
    """Async batch-friendly interface."""

    name: str

    async def embed(self, text: str) -> list[float]: ...
    async def embed_many(self, texts: list[str]) -> list[list[float]]: ...


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


# ---------------------------------------------------------------------------
# Hash provider — deterministic, dependency-free, dev/test only
# ---------------------------------------------------------------------------


class HashEmbeddingProvider:
    """Deterministic hash-based projection into ``EMBEDDING_DIM`` floats.

    Uses repeated SHA-256 to fill a 1536-float vector with values in [-1, 1],
    then L2-normalises so cosine distance is well-defined. Two distinct
    strings will hash to nearly orthogonal vectors, and the same string will
    always produce the same vector. This is intentionally NOT useful for
    semantic search — it exists only to make the pipeline runnable offline.
    """

    name = "hash"

    async def embed(self, text: str) -> list[float]:
        return self._embed_sync(text)

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_sync(t) for t in texts]

    @staticmethod
    def _embed_sync(text: str) -> list[float]:
        # Each SHA-256 yields 32 bytes = 8 floats (4 bytes each → unpack as int32).
        # We need EMBEDDING_DIM floats, so iterate enough times.
        floats: list[float] = []
        counter = 0
        seed = text.encode("utf-8")
        while len(floats) < EMBEDDING_DIM:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "little")).digest()
            for i in range(0, len(digest), 4):
                if len(floats) >= EMBEDDING_DIM:
                    break
                (n,) = struct.unpack("<i", digest[i : i + 4])
                # Map int32 (-2^31 .. 2^31-1) to [-1, 1].
                floats.append(n / 2_147_483_648.0)
            counter += 1
        return _normalize(floats)


# ---------------------------------------------------------------------------
# OpenAI provider — text-embedding-3-small
# ---------------------------------------------------------------------------


class OpenAIEmbeddingProvider:
    """Uses ``text-embedding-3-small`` (1536 dim by default)."""

    name = "openai"

    def __init__(self, *, api_key: str | None = None, model: str = "text-embedding-3-small"):
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._model = model
        if not self._api_key:
            raise RuntimeError(
                "OpenAIEmbeddingProvider requires OPENAI_API_KEY. "
                "Set EMBEDDING_PROVIDER=hash to run without it."
            )

    async def embed(self, text: str) -> list[float]:
        results = await self.embed_many([text])
        return results[0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        # Lazy import — keeps the package usable without httpx if you only need hash.
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "input": texts},
            )
            r.raise_for_status()
            data = r.json()
        # Response is sorted by input index per OpenAI contract.
        return [item["embedding"] for item in data["data"]]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


_default: EmbeddingProvider | None = None


def get_default_provider() -> EmbeddingProvider:
    global _default
    if _default is not None:
        return _default

    name = os.getenv("EMBEDDING_PROVIDER", "hash").lower()
    if name == "openai":
        try:
            _default = OpenAIEmbeddingProvider()
            logger.info("embedding provider: openai (text-embedding-3-small)")
            return _default
        except RuntimeError as exc:
            logger.warning("OpenAI provider unavailable (%s); falling back to hash", exc)
    if name not in ("hash", "openai"):
        logger.warning("unknown EMBEDDING_PROVIDER=%s; using hash", name)
    _default = HashEmbeddingProvider()
    logger.info("embedding provider: hash (deterministic, dev only)")
    return _default


def reset_default_provider() -> None:
    """Test helper. Forces the next ``get_default_provider`` call to re-read env."""
    global _default
    _default = None


def chunk_text(text: str, *, max_chars: int = 1500) -> Iterable[str]:
    """Naive char-based chunker for the document embedder.

    Replace with a tokeniser-aware chunker once we standardise on a model.
    1500 chars ≈ 375 tokens — comfortably below all current model limits.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]
