"""Shared embedding library.

Anything that needs to turn text into a 1536-dim vector imports from here.
The provider is selected at runtime via ``EMBEDDING_PROVIDER``:

- ``hash`` (default for DEV_MODE): a deterministic hash-based projection.
  Zero-dependency, free, useless for real semantic search but perfect for
  end-to-end tests and local development without API keys.
- ``openai``: ``text-embedding-3-small``. Requires ``OPENAI_API_KEY``.

All providers MUST return vectors of length :data:`EMBEDDING_DIM` (= 1536) so
the migrations and indexes don't need to change.
"""

from mycelium_embeddings.providers import (
    EMBEDDING_DIM,
    EmbeddingProvider,
    HashEmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_default_provider,
)

__all__ = [
    "EMBEDDING_DIM",
    "EmbeddingProvider",
    "HashEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "get_default_provider",
]
