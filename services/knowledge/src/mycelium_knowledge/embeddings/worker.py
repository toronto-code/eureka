"""Background loop: fills ``events.embedding`` where it's NULL.

Polls Postgres every ``EMBEDDING_POLL_SECONDS`` (default 30) for up to
``EMBEDDING_BATCH_SIZE`` (default 50) un-embedded events, builds a short
text summary for each, batch-embeds them, and writes back in a single
``UPDATE … FROM (VALUES …)`` statement.

Two policy levers controlled by env:

- ``EMBEDDING_TYPE_DENYLIST``: comma-separated event-type prefixes to skip
  (default: ``health,heartbeat,integration_sync.``). These are high-volume,
  low-signal events that would dominate the index without adding meaning.
- ``EMBEDDING_PROVIDER``: ``hash`` or ``openai`` (see mycelium_embeddings).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from sqlalchemy import select, text

from mycelium_db import EventRow, get_session
from mycelium_embeddings import get_default_provider

logger = logging.getLogger(__name__)


def _poll_interval() -> int:
    return int(os.getenv("EMBEDDING_POLL_SECONDS", "30"))


def _batch_size() -> int:
    return int(os.getenv("EMBEDDING_BATCH_SIZE", "50"))


def _denylist() -> list[str]:
    raw = os.getenv("EMBEDDING_TYPE_DENYLIST", "health,heartbeat,integration_sync.")
    return [p.strip() for p in raw.split(",") if p.strip()]


def _summarize_event(row: EventRow) -> str:
    """Build the short text we actually embed.

    Keep it stable: changes to this format invalidate every existing vector.
    """
    actor = (row.actor or {}).get("id", "unknown")
    obj = row.object or {}
    obj_part = f"{obj.get('type', 'object')}:{obj.get('id', '?')}"
    md = row.metadata_ or {}
    md_summary = md.get("summary") or md.get("title") or md.get("message") or ""
    base = f"{row.type} by {actor} on {obj_part} via {row.source}"
    return f"{base} — {md_summary}".strip(" —")


async def _select_unembedded(session, limit: int, denylist: list[str]) -> list[EventRow]:
    stmt = select(EventRow).where(EventRow.embedding.is_(None)).limit(limit).order_by(
        EventRow.timestamp.desc()
    )
    rows = (await session.execute(stmt)).scalars().all()
    if not denylist:
        return list(rows)
    keep: list[EventRow] = []
    for r in rows:
        if any(r.type.startswith(prefix) for prefix in denylist):
            continue
        keep.append(r)
    return keep


async def _write_embeddings(
    session, ids: list[str], vectors: list[list[float]]
) -> None:
    """One round-trip per batch via UPDATE ... FROM (VALUES ...).

    pgvector accepts the literal ``[0.1,0.2,...]`` text form which we cast.
    """
    if not ids:
        return

    rows_sql = ",".join(
        f"(:id_{i}, (:vec_{i})::vector)" for i in range(len(ids))
    )
    sql = text(
        f"""
        UPDATE events AS e
        SET embedding = v.vec
        FROM (VALUES {rows_sql}) AS v(id, vec)
        WHERE e.id = v.id
        """
    )
    params: dict[str, Any] = {}
    for i, (eid, vec) in enumerate(zip(ids, vectors)):
        params[f"id_{i}"] = eid
        params[f"vec_{i}"] = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
    await session.execute(sql, params)


async def embed_once() -> int:
    """One pass. Returns number of events embedded."""
    provider = get_default_provider()
    batch = _batch_size()
    deny = _denylist()

    async with get_session() as session:
        rows = await _select_unembedded(session, batch, deny)
        if not rows:
            return 0
        texts = [_summarize_event(r) for r in rows]
        vectors = await provider.embed_many(texts)
        await _write_embeddings(session, [r.id for r in rows], vectors)

    logger.info("embedded %d events via %s", len(rows), provider.name)
    return len(rows)


async def run_event_embed_worker() -> None:
    """Forever loop. Cancellable; survives transient failures."""
    interval = _poll_interval()
    logger.info(
        "event embed worker starting (interval=%ds, batch=%d, deny=%s)",
        interval,
        _batch_size(),
        _denylist(),
    )
    while True:
        try:
            n = await embed_once()
            if n == 0:
                await asyncio.sleep(interval)
            else:
                # Drain quickly when there's a backlog.
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("embed_once failed; sleeping before retry")
            await asyncio.sleep(interval)
