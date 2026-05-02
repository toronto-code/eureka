"""FastAPI app + scheduled discovery loop."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from mycelium_process_intel.discovery import discover_once
from mycelium_shared_types.health import HealthCheck, ok

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("mycelium-process-intel")

_LATEST: dict = {"process_maps": [], "bottlenecks": [], "deviations": []}


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
    return await discover_once()


@app.get("/process-maps")
async def process_maps():
    return _LATEST
