"""FastAPI app wiring: collector, buffer, trainer, backend, HTTP API."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from mycelium_event_bus import EventBus
from mycelium_event_bus.bus import EventBusConfig
from mycelium_shared_types.health import HealthCheck, ok

from mycelium_learning.api import preferences_router, recommendations_router, signals_router
from mycelium_learning.backends import LearningBackend, LocalBackend, OpenClawRLBackend
from mycelium_learning.config import (
    DEV_MODE,
    LEARNING_BACKEND,
    REDIS_URL,
    SIGNAL_BATCH_INTERVAL_SECONDS,
    SIGNAL_BATCH_SIZE,
)
from mycelium_learning.models import ModelStore
from mycelium_learning.signals import SignalBuffer, SignalCollector
from mycelium_learning.trainer import Trainer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("mycelium-learning")

buffer: SignalBuffer | None = None
collector: SignalCollector | None = None
trainer: Trainer | None = None
store: ModelStore | None = None
backend: LearningBackend | None = None


def _create_backend() -> LearningBackend:
    if LEARNING_BACKEND == "openclaw":
        logger.info("Using OpenClaw RL + Genverse learning backend")
        return OpenClawRLBackend()
    logger.info("Using local learning backend")
    return LocalBackend()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global buffer, collector, trainer, store, backend

    if DEV_MODE:
        logger.warning("Running in DEV_MODE — auth disabled")

    logger.info(
        "Initializing learning service (batch_size=%d, interval=%ds, backend=%s)",
        SIGNAL_BATCH_SIZE,
        SIGNAL_BATCH_INTERVAL_SECONDS,
        LEARNING_BACKEND,
    )

    store = ModelStore(redis_url=REDIS_URL)
    backend = _create_backend()

    trainer = Trainer(backend=backend, store=store)
    await trainer.load_all()

    buffer = SignalBuffer(
        batch_size=SIGNAL_BATCH_SIZE,
        interval_seconds=SIGNAL_BATCH_INTERVAL_SECONDS,
        on_flush=trainer.on_flush,
    )
    buffer.start_ticker()

    bus = EventBus(EventBusConfig(redis_url=REDIS_URL))
    collector = SignalCollector(bus=bus, buffer=buffer)

    tasks = [
        asyncio.create_task(
            collector.run_results_consumer(),
            name="learning-results",
        ),
        asyncio.create_task(
            collector.run_approvals_consumer(),
            name="learning-approvals",
        ),
    ]

    logger.info("Learning service ready")

    try:
        yield
    finally:
        logger.info("Shutting down learning service")
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        if buffer is not None:
            await buffer.flush(reason="shutdown")
            await buffer.stop_ticker()

        if backend is not None:
            await backend.close()

        if store is not None:
            await store.close()


app = FastAPI(
    title="mycelium-learning",
    version="0.2.0",
    description="Evolution + Learning service - collects signals, trains models, serves recommendations.",
    lifespan=lifespan,
)

app.include_router(preferences_router)
app.include_router(recommendations_router)
app.include_router(signals_router)


@app.get("/health", response_model=HealthCheck)
async def health() -> HealthCheck:
    return ok("mycelium-learning")


@app.get("/stats")
async def stats() -> dict[str, Any]:
    """Overall service stats - buffer, trainer, models."""
    return {
        "buffer": buffer.stats if buffer else None,
        "trainer": trainer.stats if trainer else None,
        "backend": type(backend).__name__ if backend else None,
    }
