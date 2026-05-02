"""Process discovery using pm4py.

Reads from the Postgres ``events`` table — never from Redis. Redis is
transport, Postgres is the system of record.

We use the **Inductive Miner** (``pm4py.discover_petri_net_inductive``) over
an event log keyed by ``correlation_id`` (case id) and ``type`` (activity).
Inductive Miner is the safe default: it always produces a sound, block-
structured Petri net. For noisy real-world data we may switch to the
Heuristics Miner later — left as a TODO.

If pm4py is unavailable (e.g. minimal dev image), we fall back to the
hand-rolled grouping so the API surface still works end-to-end.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from mycelium_db import EventRow, get_session
from mycelium_event_bus import EventBus, Topic
from mycelium_event_bus.bus import EventBusConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# pm4py is optional. If imports fail we degrade gracefully.
# ---------------------------------------------------------------------------

try:
    import pandas as pd  # type: ignore[import-untyped]
    import pm4py  # type: ignore[import-untyped]

    _PM4PY_AVAILABLE = True
except Exception:  # pragma: no cover — only triggered in minimal dev image
    pd = None  # type: ignore[assignment]
    pm4py = None  # type: ignore[assignment]
    _PM4PY_AVAILABLE = False


def _bus() -> EventBus:
    return EventBus(EventBusConfig(redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0")))


def _window_days() -> int:
    return int(os.getenv("PROCESS_INTEL_WINDOW_DAYS", "30"))


def _row_cap() -> int:
    return int(os.getenv("PROCESS_INTEL_ROW_CAP", "10000"))


# ---------------------------------------------------------------------------
# Postgres → in-memory list[dict]
# ---------------------------------------------------------------------------


async def _load_event_window() -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=_window_days())
    async with get_session() as session:
        rows = (
            await session.execute(
                select(EventRow)
                .where(EventRow.timestamp >= cutoff)
                .order_by(EventRow.timestamp.asc())
                .limit(_row_cap())
            )
        ).scalars().all()
    return [
        {
            "correlation_id": r.correlation_id,
            "type": r.type,
            "timestamp": r.timestamp,
            "actor": (r.actor or {}).get("id"),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Fallback (no pm4py): cheap directly-follows graph + bottlenecks
# ---------------------------------------------------------------------------


def _fallback_discovery(events: list[dict[str, Any]]) -> dict[str, Any]:
    cases: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        cases.setdefault(e["correlation_id"], []).append(e)

    transitions: dict[tuple[str, str], int] = {}
    for trace in cases.values():
        trace.sort(key=lambda x: x["timestamp"])
        for a, b in zip(trace, trace[1:]):
            transitions[(a["type"], b["type"])] = transitions.get((a["type"], b["type"]), 0) + 1

    process_map = [{"from": a, "to": b, "count": c} for (a, b), c in transitions.items()]
    bottlenecks = sorted(process_map, key=lambda x: x["count"], reverse=True)[:5]
    return {
        "algorithm": "fallback-directly-follows",
        "process_maps": process_map,
        "bottlenecks": bottlenecks,
        "deviations": [],
        "case_count": len(cases),
    }


# ---------------------------------------------------------------------------
# Real pm4py path
# ---------------------------------------------------------------------------


def _to_event_log(events: list[dict[str, Any]]):  # type: ignore[no-untyped-def]
    """Build a pm4py-formatted DataFrame.

    pm4py expects ``case:concept:name``, ``concept:name``, and
    ``time:timestamp`` columns. ``format_dataframe`` handles renaming.
    """
    df = pd.DataFrame(events)
    if df.empty:
        return df
    df = pm4py.format_dataframe(
        df,
        case_id="correlation_id",
        activity_key="type",
        timestamp_key="timestamp",
    )
    return df


def _serialize_petri_net(net, im, fm) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Reduce a pm4py Petri net to a JSON-friendly nodes/edges shape.

    The frontend renders this with Cytoscape (same shape used elsewhere).
    """
    nodes: list[dict[str, Any]] = []
    for place in net.places:
        nodes.append(
            {
                "id": f"p::{place.name}",
                "label": "",
                "type": "place",
                "is_initial": place in im,
                "is_final": place in fm,
            }
        )
    for transition in net.transitions:
        nodes.append(
            {
                "id": f"t::{transition.name}",
                "label": transition.label or "",
                "type": "transition",
                "silent": transition.label is None,
            }
        )

    edges: list[dict[str, Any]] = []
    for arc in net.arcs:
        src = arc.source
        tgt = arc.target
        src_id = f"p::{src.name}" if src in net.places else f"t::{src.name}"
        tgt_id = f"p::{tgt.name}" if tgt in net.places else f"t::{tgt.name}"
        edges.append(
            {
                "id": f"{src_id}->{tgt_id}",
                "source_id": src_id,
                "target_id": tgt_id,
                "weight": getattr(arc, "weight", 1),
            }
        )
    return {"nodes": nodes, "edges": edges}


def _detect_bottlenecks(df) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    """Mean waiting time between consecutive activities, top 5."""
    if df.empty:
        return []
    df = df.sort_values(["case:concept:name", "time:timestamp"])
    df["next_activity"] = df.groupby("case:concept:name")["concept:name"].shift(-1)
    df["next_ts"] = df.groupby("case:concept:name")["time:timestamp"].shift(-1)
    df = df.dropna(subset=["next_activity", "next_ts"])
    if df.empty:
        return []
    df["wait_seconds"] = (df["next_ts"] - df["time:timestamp"]).dt.total_seconds()
    grouped = (
        df.groupby(["concept:name", "next_activity"])["wait_seconds"]
        .agg(["mean", "count"])
        .reset_index()
        .sort_values("mean", ascending=False)
        .head(5)
    )
    return [
        {
            "from": str(row["concept:name"]),
            "to": str(row["next_activity"]),
            "mean_wait_seconds": float(row["mean"]),
            "transitions": int(row["count"]),
        }
        for _, row in grouped.iterrows()
    ]


def _conformance_deviations(log, net, im, fm) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    """Token-based replay; surface up to 10 worst-fitting traces."""
    try:
        diagnostics = pm4py.conformance_diagnostics_token_based_replay(log, net, im, fm)
    except Exception as exc:
        logger.warning("conformance check failed: %s", exc)
        return []
    deviations: list[dict[str, Any]] = []
    for trace_diag in diagnostics:
        fit = trace_diag.get("trace_fitness", 1.0)
        if fit >= 0.999:
            continue
        deviations.append(
            {
                "fitness": float(fit),
                "missing": int(trace_diag.get("missing_tokens", 0)),
                "remaining": int(trace_diag.get("remaining_tokens", 0)),
            }
        )
    deviations.sort(key=lambda d: d["fitness"])
    return deviations[:10]


def _pm4py_discovery(events: list[dict[str, Any]]) -> dict[str, Any]:
    df = _to_event_log(events)
    if df.empty:
        return {
            "algorithm": "inductive",
            "petri_net": {"nodes": [], "edges": []},
            "bottlenecks": [],
            "deviations": [],
            "case_count": 0,
        }

    log = pm4py.convert_to_event_log(df)
    net, im, fm = pm4py.discover_petri_net_inductive(log)
    return {
        "algorithm": "inductive",
        "petri_net": _serialize_petri_net(net, im, fm),
        "bottlenecks": _detect_bottlenecks(df),
        "deviations": _conformance_deviations(log, net, im, fm),
        "case_count": int(df["case:concept:name"].nunique()),
        # SVG render: TODO (pm4py.save_vis_petri_net) — needs graphviz binary.
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def discover_once() -> dict[str, Any]:
    """Run discovery once and publish the summary on ``graph.updates``."""
    events = await _load_event_window()
    if _PM4PY_AVAILABLE:
        summary = _pm4py_discovery(events)
    else:
        logger.warning("pm4py unavailable — using fallback directly-follows discovery")
        summary = _fallback_discovery(events)

    summary["computed_at"] = datetime.now(timezone.utc).isoformat()
    summary["window_days"] = _window_days()
    summary["events_considered"] = len(events)

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
