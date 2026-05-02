"""FastAPI app + two consumer workers (agents.results, workflows.approvals)."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from mycelium_db import get_session
from mycelium_db.models import LearningSignalRow
from mycelium_learning.workers import run_results_observer, run_approvals_observer
from mycelium_shared_types.health import HealthCheck, ok

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("mycelium-learning")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.getenv("DEV_MODE", "true").lower() == "true":
        logger.warning("Running in DEV_MODE — auth disabled")
    tasks = [
        asyncio.create_task(run_results_observer(), name="learning-results"),
        asyncio.create_task(run_approvals_observer(), name="learning-approvals"),
    ]
    try:
        yield
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="mycelium-learning", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthCheck)
async def health() -> HealthCheck:
    return ok("mycelium-learning")


@app.get("/signals")
async def signals():
    async with get_session() as session:
        rows = (
            await session.execute(
                select(LearningSignalRow).order_by(LearningSignalRow.created_at.desc()).limit(50)
            )
        ).scalars().all()
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
