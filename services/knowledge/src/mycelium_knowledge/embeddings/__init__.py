"""Embedding pipeline for the knowledge service.

Two responsibilities:

- ``embed_worker``: background loop that fills ``events.embedding`` for any
  rows where it is NULL (skipping a configurable denylist of high-volume
  low-signal event types).
- ``search``: cosine similarity query over ``document_embeddings`` for the
  ``/search`` HTTP endpoint.

Heavy lifting (provider selection, vector math) lives in
``mycelium_embeddings``; this module owns the *policy* (which events to
embed, batch size, polling interval, denylist).
"""

from mycelium_knowledge.embeddings.worker import run_event_embed_worker
from mycelium_knowledge.embeddings.search import semantic_search

__all__ = ["run_event_embed_worker", "semantic_search"]
