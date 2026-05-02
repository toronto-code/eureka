"""EmbeddingService.

Primary backend: OpenAI `text-embedding-3-small` (1536-dim).
Fallback backend: deterministic hash-based embeddings (1536-dim), used ONLY
when `OPENAI_API_KEY` is missing. The fallback is clearly marked as
non-production — it's for local demos and tests so the end-to-end flow can
still run.

The service:
- Batches requests (OpenAI accepts up to 2048 inputs per call).
- Truncates each input to a safe character budget (embeddings API limit is
  8192 tokens ≈ 32k chars for small model; we cap at 8k chars).
- Is idempotent when the client is missing (returns deterministic vectors).
"""
from __future__ import annotations

import hashlib
import logging
import math
from functools import lru_cache
from typing import Iterable

from app.agents.llm_client import OpenAIClient, get_llm_client

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536
MAX_CHARS_PER_INPUT = 8000
OPENAI_BATCH_SIZE = 96  # conservative; 2048 is the absolute max


class EmbeddingService:
    """Turn text into 1536-dim vectors, with an explicit dev-only fallback."""

    def __init__(self, llm: OpenAIClient | None = None) -> None:
        self._llm = llm or get_llm_client()

    @property
    def is_real(self) -> bool:
        """True when embeddings come from OpenAI. False for the hash fallback."""
        return bool(self._llm and self._llm.configured)

    @property
    def backend_name(self) -> str:
        return "openai:text-embedding-3-small" if self.is_real else "deterministic-hash (dev only)"

    # ---- single ----------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        if not text:
            return []
        if self.is_real:
            vec = self._llm.generate_embedding(text[:MAX_CHARS_PER_INPUT])
            if vec:
                return vec
            # Fall through to hash fallback on API failure.
            logger.warning("OpenAI embedding returned empty; using hash fallback for this input.")
        return _hash_embedding(text[:MAX_CHARS_PER_INPUT])

    # ---- batched ---------------------------------------------------------

    def embed_many(self, texts: Iterable[str]) -> list[list[float]]:
        items = [t[:MAX_CHARS_PER_INPUT] if t else "" for t in texts]
        if not items:
            return []
        if not self.is_real:
            return [_hash_embedding(t) if t else [] for t in items]
        out: list[list[float]] = [[] for _ in items]
        # Embed non-empty inputs in batches.
        to_embed_idx = [i for i, t in enumerate(items) if t]
        for start in range(0, len(to_embed_idx), OPENAI_BATCH_SIZE):
            batch_idx = to_embed_idx[start : start + OPENAI_BATCH_SIZE]
            batch_texts = [items[i] for i in batch_idx]
            try:
                resp = self._llm._client.embeddings.create(  # type: ignore[union-attr]
                    model=self._llm.embedding_model, input=batch_texts
                )
                for idx, datum in zip(batch_idx, resp.data):
                    out[idx] = list(datum.embedding)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "OpenAI batch embedding failed (%s); using hash fallback for this batch.",
                    type(exc).__name__,
                )
                for idx in batch_idx:
                    out[idx] = _hash_embedding(items[idx])
        return out


# ---------------------------------------------------------------------------
# Deterministic hash-based embedding
# ---------------------------------------------------------------------------
#
# Non-production. Produces a stable unit-length vector from text. Good enough
# for the demo retrieval pipeline to exercise cosine similarity without calling
# an external service, but NOT a real semantic embedding. Two paraphrases will
# have very different hash vectors — lexical changes move the vector a lot.
#
# Why 1536 dims: matches text-embedding-3-small so the pgvector column type is
# identical whether real or fallback is used.


def _hash_embedding(text: str) -> list[float]:
    if not text:
        return []
    # Build a deterministic stream of bytes by hashing overlapping 3-grams of
    # tokens. This gives a little more signal than a single full-text hash.
    tokens = _tokenise(text)
    bucket = [0.0] * EMBEDDING_DIM
    if not tokens:
        tokens = [text]
    for ngram in _ngrams(tokens, 3) or [" ".join(tokens)]:
        digest = hashlib.blake2b(ngram.encode("utf-8"), digest_size=EMBEDDING_DIM // 8).digest()
        for i, byte in enumerate(digest):
            # Each byte contributes to 8 dims via its bits — keeps the vector
            # mostly-dense rather than sparse, which plays better with cosine.
            for bit in range(8):
                slot = (i * 8 + bit) % EMBEDDING_DIM
                bucket[slot] += 1.0 if (byte >> bit) & 1 else -1.0
    norm = math.sqrt(sum(x * x for x in bucket)) or 1.0
    return [x / norm for x in bucket]


def _tokenise(text: str) -> list[str]:
    return [t for t in _simple_split(text.lower()) if t]


def _simple_split(text: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    for ch in text:
        if ch.isalnum() or ch in "_":
            buf.append(ch)
        else:
            if buf:
                out.append("".join(buf))
                buf.clear()
    if buf:
        out.append("".join(buf))
    return out


def _ngrams(tokens: list[str], n: int) -> list[str]:
    if len(tokens) < n:
        return []
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()
