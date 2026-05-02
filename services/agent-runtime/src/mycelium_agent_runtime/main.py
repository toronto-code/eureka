"""FastAPI app + agent task worker."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from mycelium_agent_runtime.skills import registry
from mycelium_agent_runtime.worker import run_task_worker
from mycelium_shared_types.health import HealthCheck, ok

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("mycelium-agent-runtime")


def _announce_dev_mode() -> None:
    if os.getenv("DEV_MODE", "true").lower() == "true":
        logger.warning("Running in DEV_MODE — auth disabled")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _announce_dev_mode()
    task = asyncio.create_task(run_task_worker(), name="agent-runtime-worker")
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="mycelium-agent-runtime", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthCheck)
async def health() -> HealthCheck:
    return ok("mycelium-agent-runtime")


@app.get("/skills")
async def list_skills():
    return registry.describe()


@app.post("/agents/spawn")
async def spawn_agent(payload: dict):
    """Stub for Claworc-managed OpenClaw spawn.

    Real impl: ask Claworc to create an OpenClaw instance bound to ``owner_user_id``.
    """
    owner_user_id = payload.get("owner_user_id", "unknown")
    return {
        "agent_id": f"agent-{owner_user_id}",
        "owner_user_id": owner_user_id,
        "status": "spawned",
        "stub": True,
    }
