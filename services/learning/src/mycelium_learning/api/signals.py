"""Signal endpoints - list recent signals, submit user feedback."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from mycelium_db import get_session
from mycelium_db.models import LearningSignalRow

from mycelium_learning.signals.types import Signal

router = APIRouter(prefix="/signals", tags=["signals"])


class FeedbackRequest(BaseModel):
    """Explicit user feedback on a task or agent."""

    user_id: str
    task_id: str | None = None
    agent_id: str | None = None
    agent_type: str | None = None
    positive: bool
    notes: str | None = None


def get_collector():
    from mycelium_learning.main import collector
    if collector is None:
        raise HTTPException(status_code=503, detail="collector not initialized")
    return collector


def get_buffer():
    from mycelium_learning.main import buffer
    if buffer is None:
        raise HTTPException(status_code=503, detail="buffer not initialized")
    return buffer


@router.get("")
async def list_signals(
    limit: int = Query(50, ge=1, le=500),
    signal_type: str | None = Query(None),
) -> list[dict[str, Any]]:
    """List recent signals (from Postgres)."""
    async with get_session() as session:
        stmt = select(LearningSignalRow).order_by(LearningSignalRow.created_at.desc()).limit(limit)
        if signal_type:
            stmt = stmt.where(LearningSignalRow.signal_type == signal_type)
        rows = (await session.execute(stmt)).scalars().all()

    return [
        {
            "id": r.id,
            "task_id": r.task_id,
            "agent_id": r.agent_id,
            "signal_type": r.signal_type,
            "correlation_id": r.correlation_id,
            "payload": r.payload,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/feedback")
async def submit_feedback(req: FeedbackRequest) -> dict[str, Any]:
    """Submit explicit user feedback (thumbs up/down style)."""
    collector = get_collector()

    signal = Signal.from_user_feedback(
        user_id=req.user_id,
        task_id=req.task_id,
        agent_id=req.agent_id,
        positive=req.positive,
        notes=req.notes,
        agent_type=req.agent_type,
    )

    await collector.ingest_feedback(signal)

    return {
        "signal_id": signal.id,
        "status": "accepted",
        "kind": signal.kind.value,
        "outcome": signal.outcome.value,
    }


@router.get("/buffer")
async def buffer_stats() -> dict[str, Any]:
    """Get current buffer statistics."""
    buf = get_buffer()
    return buf.stats


@router.post("/flush")
async def flush_buffer() -> dict[str, Any]:
    """Manually trigger a buffer flush (for testing / debugging)."""
    buf = get_buffer()
    stats_before = dict(buf.stats)
    await buf.flush(reason="manual_api")
    return {
        "status": "flushed",
        "before": stats_before,
        "after": buf.stats,
    }
