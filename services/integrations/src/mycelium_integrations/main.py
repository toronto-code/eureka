"""FastAPI app + scheduler that runs each connector on an interval."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from mycelium_integrations.connectors import REGISTRY, run_connector
from mycelium_integrations.scheduler import run_scheduler
from mycelium_shared_types.health import HealthCheck, ok

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("mycelium-integrations")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.getenv("DEV_MODE", "true").lower() == "true":
        logger.warning("Running in DEV_MODE — auth disabled")
    task = asyncio.create_task(run_scheduler(), name="integrations-scheduler")
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="mycelium-integrations", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthCheck)
async def health() -> HealthCheck:
    return ok("mycelium-integrations")


@app.get("/connectors")
async def list_connectors():
    return [{"name": k, "enabled": True} for k in REGISTRY]


@app.post("/connectors/{name}/sync")
async def sync_now(name: str):
    if name not in REGISTRY:
        raise HTTPException(404, f"unknown connector: {name}")
    result = await run_connector(name)
    return {"connector": name, **result}
