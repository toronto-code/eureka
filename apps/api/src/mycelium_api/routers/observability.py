"""GET /observability — service health summary scraped from each /health.

Also exposes Prometheus metrics on /metrics.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from mycelium_api.config import (
    AGENT_RUNTIME_URL,
    INTEGRATIONS_URL,
    KNOWLEDGE_URL,
    LEARNING_URL,
    PROCESS_INTEL_URL,
    SECURITY_URL,
)

router = APIRouter(tags=["observability"])

_TARGETS = {
    "knowledge": KNOWLEDGE_URL,
    "agent-runtime": AGENT_RUNTIME_URL,
    "integrations": INTEGRATIONS_URL,
    "process-intel": PROCESS_INTEL_URL,
    "learning": LEARNING_URL,
    "security": SECURITY_URL,
}


async def _probe(name: str, url: str) -> dict:
    async with httpx.AsyncClient(timeout=2) as client:
        try:
            r = await client.get(f"{url}/health")
            r.raise_for_status()
            return {"service": name, "status": "ok", "details": r.json()}
        except Exception as exc:
            return {"service": name, "status": "error", "details": str(exc)}


@router.get("/observability")
async def observability_summary():
    results = await asyncio.gather(*[_probe(n, u) for n, u in _TARGETS.items()])
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": results,
    }


@router.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
