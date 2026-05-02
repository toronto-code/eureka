"""GET /health — uses the shared HealthCheck shape."""

from __future__ import annotations

from fastapi import APIRouter

from mycelium_shared_types import HealthCheck
from mycelium_shared_types.health import ok

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthCheck)
async def health() -> HealthCheck:
    return ok("mycelium-api")
