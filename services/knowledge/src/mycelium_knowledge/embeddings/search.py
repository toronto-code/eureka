"""Cosine similarity search over ``document_embeddings``.

Used by the knowledge service ``/search`` endpoint and (eventually) by the
chat surface in ``apps/api`` for "find anything semantically close to X".

Read-only. Writes happen elsewhere (code-index chunker — TODO).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from mycelium_db import get_session
from mycelium_embeddings import get_default_provider


async def semantic_search(
    query: str,
    *,
    limit: int = 10,
    source_type: str | None = None,
) -> list[dict[str, Any]]:
    """Return top-``limit`` document chunks most similar to ``query``.

    ``1 - (embedding <=> $vec)`` is cosine similarity in pgvector.
    """
    if not query.strip():
        return []

    provider = get_default_provider()
    vec = await provider.embed(query)
    vec_lit = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"

    where_clause = ""
    params: dict[str, Any] = {"vec": vec_lit, "limit": limit}
    if source_type:
        where_clause = "WHERE source_type = :source_type"
        params["source_type"] = source_type

    sql = text(
        f"""
        SELECT id, source_type, source_id, chunk_index, content,
               metadata, 1 - (embedding <=> (:vec)::vector) AS similarity
        FROM document_embeddings
        {where_clause}
        ORDER BY embedding <=> (:vec)::vector
        LIMIT :limit
        """
    )

    async with get_session() as session:
        result = await session.execute(sql, params)
        rows = result.mappings().all()

    return [
        {
            "id": r["id"],
            "source_type": r["source_type"],
            "source_id": r["source_id"],
            "chunk_index": r["chunk_index"],
            "content": r["content"],
            "metadata": r["metadata"],
            "similarity": float(r["similarity"]),
        }
        for r in rows
    ]
