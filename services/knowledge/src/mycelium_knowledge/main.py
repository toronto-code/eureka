"""FastAPI app + events.processed consumer for the knowledge service."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from mycelium_knowledge.code_index.routes import router as code_index_router
from mycelium_knowledge.graph.routes import router as graph_router
from mycelium_knowledge.onboarding.routes import router as onboarding_router
from mycelium_knowledge.graph.ingest_worker import run_graph_ingest_worker
from mycelium_shared_types.health import HealthCheck, ok

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("mycelium-knowledge")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.getenv("DEV_MODE", "true").lower() == "true":
        logger.warning("Running in DEV_MODE — auth disabled")
    task = asyncio.create_task(run_graph_ingest_worker(), name="graph-ingest")
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="mycelium-knowledge", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthCheck)
async def health() -> HealthCheck:
    return ok("mycelium-knowledge")


app.include_router(graph_router)
app.include_router(code_index_router, prefix="/code-index", tags=["code-index"])
app.include_router(onboarding_router, prefix="/onboarding", tags=["onboarding"])


@app.post("/seed")
async def seed():
    """Seed a small fake company graph. DEV-only."""
    from mycelium_knowledge.graph.store import seed_demo_graph

    return await seed_demo_graph()
