"""FastAPI app + classification consumer."""

from __future__ import annotations

import asyncio
import logging
import os
from collections import deque
from contextlib import asynccontextmanager

from fastapi import FastAPI

from mycelium_security.classification.worker import DLQ_BUFFER, run_classification_worker
from mycelium_shared_types.health import HealthCheck, ok

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("mycelium-security")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.getenv("DEV_MODE", "true").lower() == "true":
        logger.warning("Running in DEV_MODE — auth disabled")
    task = asyncio.create_task(run_classification_worker(), name="security-classifier")
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="mycelium-security", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthCheck)
async def health() -> HealthCheck:
    return ok("mycelium-security")


@app.get("/dlq")
async def dlq():
    return list(DLQ_BUFFER)
