"""FastAPI app entry point.

Wires routers, starts the event-bus consumer workers (events.processed,
agents.results), and exposes Prometheus metrics on /metrics.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mycelium_api.config import announce_dev_mode
from mycelium_api.routers import (
    agent_chat,
    agents,
    chat,
    chat_intel,
    dashboard_web,
    docker_obs,
    graph,
    health,
    integrations,
    observability,
    workflows,
)
from mycelium_api.workers.events_ingestor import run_events_ingestor
from mycelium_api.workers.agent_results import run_agent_results_consumer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("mycelium-api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    announce_dev_mode("mycelium-api")
    logger.info("starting background workers")
    tasks = [
        asyncio.create_task(run_events_ingestor(), name="events-ingestor"),
        asyncio.create_task(run_agent_results_consumer(), name="agent-results"),
    ]
    try:
        yield
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="Mycelium API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # DEV. tighten before staging.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(graph.router)
app.include_router(agents.router)
app.include_router(integrations.router)
app.include_router(workflows.router)
app.include_router(observability.router)
app.include_router(chat_intel.router)
app.include_router(docker_obs.router)
app.include_router(agent_chat.router)
app.include_router(dashboard_web.router)
