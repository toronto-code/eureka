"""Process discovery.

Reads from the Postgres ``events`` table — never from Redis. Redis is
transport, Postgres is the system of record.

In production we use ``pm4py.discover_petri_net_inductive`` over an event log
keyed by ``correlation_id`` (the case ID). For now we provide a small stub
that groups by correlation_id and emits a process map shape.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from mycelium_db import EventRow, get_session
from mycelium_event_bus import EventBus, Topic
from mycelium_event_bus.bus import EventBusConfig

logger = logging.getLogger(__name__)


def _bus() -> EventBus:
    return EventBus(EventBusConfig(redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0")))


async def discover_once() -> dict:
    """Group recent events by correlation_id and emit a process map sketch."""
    async with get_session() as session:
        rows = (
            await session.execute(
                select(EventRow).order_by(EventRow.timestamp.desc()).limit(2000)
            )
        ).scalars().all()

    cases: dict[str, list[dict]] = {}
    for r in rows:
        cases.setdefault(r.correlation_id, []).append(
            {"type": r.type, "ts": r.timestamp.isoformat(), "actor": r.actor.get("id")}
        )

    transitions: dict[tuple[str, str], int] = {}
    for trace in cases.values():
        trace.sort(key=lambda e: e["ts"])
        for a, b in zip(trace, trace[1:]):
            transitions[(a["type"], b["type"])] = transitions.get((a["type"], b["type"]), 0) + 1

    process_map = [
        {"from": a, "to": b, "count": c} for (a, b), c in transitions.items()
    ]
    bottlenecks = sorted(process_map, key=lambda x: x["count"], reverse=True)[:5]

    summary = {
        "process_maps": process_map,
        "bottlenecks": bottlenecks,
        "deviations": [],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(cases),
    }

    bus = _bus()
    cid = f"process-intel:{uuid.uuid4().hex[:8]}"
    await bus.publish(
        Topic.GRAPH_UPDATES,
        {
            "id": str(uuid.uuid4()),
            "type": "process_intel.summary",
            "source": "process-intel",
            "actor": {"id": "process-intel", "type": "service"},
            "object": {"id": "process-summary", "type": "process_summary"},
            "timestamp": summary["computed_at"],
            "schema_version": "1.0",
            "metadata": summary,
            "correlation_id": cid,
            "parent_correlation_id": None,
        },
        correlation_id=cid,
    )
    return summary
