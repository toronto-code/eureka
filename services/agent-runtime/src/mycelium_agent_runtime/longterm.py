"""Long-term memory: persistent agent recall via ``agent_memories`` + pgvector.

Two operations the worker calls:

- :func:`read_relevant_memories` at the start of a task, to inject context.
- :func:`write_memory` after a task succeeds, optionally + when the skill
  returned a ``remember_this`` payload.

Retrieval scope is controlled by ``LONGTERM_MEMORY_SCOPE``:

- ``agent_user`` (default): rows where agent_id matches AND user_id matches,
  falling back to user-only rows if we don't get enough hits.
- ``agent_only``: agent_id only.
- ``user_only``: user_id only.
- ``global``: any row (still subject to security filtering by callers).
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from mycelium_db import get_session
from mycelium_embeddings import get_default_provider

logger = logging.getLogger(__name__)


def _top_k() -> int:
    return int(os.getenv("LONGTERM_MEMORY_TOP_K", "5"))


def _scope() -> str:
    return os.getenv("LONGTERM_MEMORY_SCOPE", "agent_user").lower()


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def _summary_for(task: dict[str, Any], result: dict[str, Any]) -> str:
    """Deterministic template summary of a successful task.

    Replace with an LLM call once we have a budget for it. The template
    is intentionally information-dense so the embedding has something to
    chew on even with the hash provider.
    """
    skill = task.get("agent_type", "skill")
    actor = task.get("agent_id", "agent")
    prompt = (task.get("input_data", {}) or {}).get("prompt", "")
    out = result.get("summary") or result.get("briefing") or result.get("label") or ""
    out = str(out)[:240]
    return f"{actor} ran {skill}: input={prompt[:160]} → {out}".strip()


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


async def write_memory(
    *,
    agent_id: str | None,
    user_id: str | None,
    task_id: str | None,
    correlation_id: str,
    content: str,
    memory_type: str = "skill_outcome",
    importance: float = 0.5,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Insert one row into ``agent_memories``.

    Returns the row id, or ``None`` if we skipped (empty content, no agent_id).
    """
    if not agent_id:
        logger.debug("write_memory skipped: no agent_id")
        return None
    if not content or not content.strip():
        return None

    provider = get_default_provider()
    vec = await provider.embed(content)
    row_id = f"mem-{uuid.uuid4().hex}"

    sql = text(
        """
        INSERT INTO agent_memories
            (id, agent_id, user_id, task_id, correlation_id, memory_type,
             content, importance, metadata, embedding, created_at)
        VALUES
            (:id, :agent_id, :user_id, :task_id, :correlation_id, :memory_type,
             :content, :importance, CAST(:metadata AS jsonb),
             (:vec)::vector, :created_at)
        """
    )
    import json

    async with get_session() as session:
        await session.execute(
            sql,
            {
                "id": row_id,
                "agent_id": agent_id,
                "user_id": user_id,
                "task_id": task_id,
                "correlation_id": correlation_id,
                "memory_type": memory_type,
                "content": content,
                "importance": importance,
                "metadata": json.dumps(metadata or {}),
                "vec": _vec_literal(vec),
                "created_at": datetime.now(timezone.utc),
            },
        )
    return row_id


async def write_task_memories(
    *,
    task: dict[str, Any],
    result: dict[str, Any],
) -> list[str]:
    """Convenience: always-write summary + optional ``remember_this`` entry.

    Reads the skill output for a ``remember_this`` field; if present (string
    or list of strings) each item is stored as a ``fact`` memory in addition
    to the always-on ``skill_outcome`` summary.
    """
    written: list[str] = []
    agent_id = task.get("agent_id")
    user_id = (task.get("input_data", {}) or {}).get("user_id") or task.get("user_id")
    task_id = task.get("task_id")
    correlation_id = task["correlation_id"]

    # 1) Always-on skill outcome summary.
    summary_id = await write_memory(
        agent_id=agent_id,
        user_id=user_id,
        task_id=task_id,
        correlation_id=correlation_id,
        content=_summary_for(task, result),
        memory_type="skill_outcome",
        importance=0.4,
        metadata={"skill": task.get("agent_type")},
    )
    if summary_id:
        written.append(summary_id)

    # 2) Explicit "remember this" facts from the skill.
    remember = result.get("remember_this") if isinstance(result, dict) else None
    if isinstance(remember, str):
        remember = [remember]
    if isinstance(remember, list):
        for fact in remember:
            if not isinstance(fact, str):
                continue
            mid = await write_memory(
                agent_id=agent_id,
                user_id=user_id,
                task_id=task_id,
                correlation_id=correlation_id,
                content=fact,
                memory_type="fact",
                importance=0.7,
                metadata={"skill": task.get("agent_type"), "explicit": True},
            )
            if mid:
                written.append(mid)
    return written


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


async def read_relevant_memories(
    *,
    query: str,
    agent_id: str | None,
    user_id: str | None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Vector search over ``agent_memories``. Updates ``last_accessed_at``."""
    if not query or not query.strip():
        return []
    if not agent_id and _scope() not in ("user_only", "global"):
        return []

    limit = limit or _top_k()
    provider = get_default_provider()
    vec = await provider.embed(query)
    vec_lit = _vec_literal(vec)

    where, params = _build_scope_clause(agent_id=agent_id, user_id=user_id)
    params.update({"vec": vec_lit, "limit": limit})

    sql = text(
        f"""
        SELECT id, agent_id, user_id, memory_type, content, importance,
               metadata, created_at,
               1 - (embedding <=> (:vec)::vector) AS similarity
        FROM agent_memories
        {where}
        ORDER BY embedding <=> (:vec)::vector
        LIMIT :limit
        """
    )

    async with get_session() as session:
        result = await session.execute(sql, params)
        rows = result.mappings().all()
        if rows:
            await session.execute(
                text(
                    "UPDATE agent_memories SET last_accessed_at = NOW() "
                    "WHERE id = ANY(:ids)"
                ),
                {"ids": [r["id"] for r in rows]},
            )

    return [
        {
            "id": r["id"],
            "agent_id": r["agent_id"],
            "user_id": r["user_id"],
            "memory_type": r["memory_type"],
            "content": r["content"],
            "importance": float(r["importance"]),
            "metadata": r["metadata"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "similarity": float(r["similarity"]),
        }
        for r in rows
    ]


def _build_scope_clause(
    *, agent_id: str | None, user_id: str | None
) -> tuple[str, dict[str, Any]]:
    scope = _scope()
    params: dict[str, Any] = {}
    if scope == "agent_only":
        params["agent_id"] = agent_id
        return "WHERE agent_id = :agent_id", params
    if scope == "user_only":
        params["user_id"] = user_id
        return "WHERE user_id = :user_id", params
    if scope == "global":
        return "", params
    # default: agent_user — agent matches AND user matches if user provided,
    # otherwise just agent.
    if user_id:
        params["agent_id"] = agent_id
        params["user_id"] = user_id
        return "WHERE agent_id = :agent_id AND user_id = :user_id", params
    params["agent_id"] = agent_id
    return "WHERE agent_id = :agent_id", params
