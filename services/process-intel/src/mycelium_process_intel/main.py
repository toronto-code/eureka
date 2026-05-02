"""FastAPI app + scheduled discovery loop."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import select

from mycelium_db import EventRow, get_session
from mycelium_process_intel.discovery import discover_once
from mycelium_shared_types.health import HealthCheck, ok

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("mycelium-process-intel")

_LATEST: dict = {
    "algorithm": None,
    "petri_net": {"nodes": [], "edges": []},
    "bottlenecks": [],
    "deviations": [],
    "case_count": 0,
}


async def _discovery_loop() -> None:
    interval = int(os.getenv("PROCESS_INTEL_INTERVAL", "600"))
    while True:
        try:
            result = await discover_once()
            _LATEST.update(result)
        except Exception:
            logger.exception("discovery failed")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.getenv("DEV_MODE", "true").lower() == "true":
        logger.warning("Running in DEV_MODE — auth disabled")
    task = asyncio.create_task(_discovery_loop(), name="process-intel-loop")
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="mycelium-process-intel", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthCheck)
async def health() -> HealthCheck:
    return ok("mycelium-process-intel")


@app.post("/discover")
async def discover_now():
    """Force a fresh discovery run and return the result."""
    result = await discover_once()
    _LATEST.update(result)
    return result


@app.get("/process-maps")
async def process_maps():
    """Return the most recent discovery result (cached)."""
    return _LATEST


@app.get("/deviations")
async def deviations():
    """Subset of /process-maps: just the conformance deviations.

    Useful for the dashboard's 'where are processes drifting?' panel.
    """
    return {
        "deviations": _LATEST.get("deviations", []),
        "computed_at": _LATEST.get("computed_at"),
    }


@app.get("/cases/{correlation_id}")
async def case_trace(correlation_id: str):
    """Reconstruct the full ordered trace for a single case."""
    async with get_session() as session:
        rows = (
            await session.execute(
                select(EventRow)
                .where(EventRow.correlation_id == correlation_id)
                .order_by(EventRow.timestamp.asc())
            )
        ).scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="no events for that correlation_id")
    return {
        "correlation_id": correlation_id,
        "trace": [
            {
                "id": r.id,
                "type": r.type,
                "source": r.source,
                "actor": r.actor,
                "object": r.object,
                "timestamp": r.timestamp.isoformat(),
            }
            for r in rows
        ],
    }
