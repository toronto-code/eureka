"""Runs each connector every ``INTEGRATIONS_SYNC_INTERVAL`` seconds."""

from __future__ import annotations

import asyncio
import logging
import os

from mycelium_integrations.connectors import REGISTRY, run_connector

logger = logging.getLogger(__name__)


async def run_scheduler() -> None:
    interval = int(os.getenv("INTEGRATIONS_SYNC_INTERVAL", "300"))
    logger.info("scheduler starting; interval=%ds", interval)
    while True:
        for name in list(REGISTRY):
            try:
                await run_connector(name)
            except Exception:
                logger.exception("connector %s crashed", name)
        await asyncio.sleep(interval)
