"""FastAPI app + agent task worker."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from mycelium_agent_runtime.approvals import run_approvals_consumer
from mycelium_agent_runtime.skills import registry
from mycelium_agent_runtime.worker import run_task_worker, _create_backend, _create_executor
from mycelium_shared_types.health import HealthCheck, ok

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("mycelium-agent-runtime")

_backend = None
_executor = None


def _announce_dev_mode() -> None:
    if os.getenv("DEV_MODE", "true").lower() == "true":
        logger.warning("Running in DEV_MODE — auth disabled")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _backend, _executor

    _announce_dev_mode()

    _backend = _create_backend()
    _executor = _create_executor(_backend)

    logger.info("Initialized execution backend: %s", type(_backend).__name__)

    worker_task = asyncio.create_task(
        run_task_worker(backend=_backend, executor=_executor),
        name="agent-runtime-worker",
    )
    approvals_task = asyncio.create_task(
        run_approvals_consumer(),
        name="agent-runtime-approvals",
    )

    try:
        yield
    finally:
        worker_task.cancel()
        approvals_task.cancel()
        await asyncio.gather(worker_task, approvals_task, return_exceptions=True)

        if hasattr(_backend, "close"):
            await _backend.close()


app = FastAPI(title="mycelium-agent-runtime", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthCheck)
async def health() -> HealthCheck:
    return ok("mycelium-agent-runtime")


@app.get("/skills")
async def list_skills() -> list[dict[str, str]]:
    """List all registered skills."""
    return registry.describe()


@app.get("/permissions")
async def list_permissions() -> dict[str, Any]:
    """List all permission rules."""
    if _executor is None:
        return {"error": "Executor not initialized"}

    rules = _executor.guard.rules
    return {
        "rules": [
            {
                "name": r.name,
                "action_type": r.action_type.value,
                "level": r.level.value,
                "description": r.description,
                "priority": r.priority,
            }
            for r in rules
        ],
        "count": len(rules),
    }


@app.post("/agents/spawn")
async def spawn_agent(payload: dict) -> dict[str, Any]:
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


@app.post("/actions/check")
async def check_action(payload: dict) -> dict[str, Any]:
    """Check if an action would be allowed by the permission system.

    Useful for debugging and understanding permission rules.
    """
    if _executor is None:
        return {"error": "Executor not initialized"}

    from mycelium_agent_runtime.actions.types import Action
    from mycelium_agent_runtime.permissions.rules import ActionType

    try:
        action_type = ActionType(payload.get("type", "shell_command"))
    except ValueError:
        return {"error": f"Invalid action type: {payload.get('type')}"}

    action = Action(
        type=action_type,
        payload=payload.get("payload", {}),
        reasoning=payload.get("reasoning", "permission check"),
    )

    decision = _executor.guard.check(action)
    return {
        "allowed": decision.is_allowed,
        "needs_approval": decision.needs_approval,
        "blocked": decision.is_blocked,
        "level": decision.level.value,
        "reason": decision.reason,
        "matched_rule": decision.matched_rule.name if decision.matched_rule else None,
    }
