"""Connector registry + dispatcher."""

from __future__ import annotations

import logging
import os
from typing import Awaitable, Callable

from mycelium_event_bus import EventBus
from mycelium_event_bus.bus import EventBusConfig
from mycelium_integrations.sync_state import record_sync

from mycelium_integrations.connectors.github import sync_github
from mycelium_integrations.connectors.slack import sync_slack
from mycelium_integrations.connectors.jira import sync_jira

logger = logging.getLogger(__name__)


REGISTRY: dict[str, Callable[[EventBus], Awaitable[int]]] = {
    "github": sync_github,
    "slack": sync_slack,
    "jira": sync_jira,
}


def _bus() -> EventBus:
    return EventBus(EventBusConfig(redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0")))


async def run_connector(name: str) -> dict:
    """Run a connector once and record its result in integration_syncs."""
    fn = REGISTRY[name]
    bus = _bus()
    try:
        count = await fn(bus)
        await record_sync(name, status="ok")
        return {"status": "ok", "events_emitted": count}
    except Exception as exc:
        logger.exception("connector %s failed", name)
        await record_sync(name, status="error", error_message=str(exc))
        return {"status": "error", "error": str(exc)}
