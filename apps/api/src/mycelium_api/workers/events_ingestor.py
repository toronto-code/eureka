"""Events ingestion worker.

Consumes ``events.processed`` and writes every event to the Postgres
``events`` table. The API ingestion worker is the SOLE writer of that table —
no other service touches it.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert

from mycelium_api.event_bus_client import get_event_bus
from mycelium_db import EventRow, get_session
from mycelium_event_bus import Topic

logger = logging.getLogger(__name__)


async def _handle(message_id: str, payload: dict[str, Any]) -> None:
    if not payload.get("correlation_id"):
        logger.warning("dropping event with no correlation_id: %s", payload.get("id"))
        bus = get_event_bus()
        await bus.ack(Topic.EVENTS_PROCESSED, "api-ingestor", message_id)
        return

    row = {
        "id": payload["id"],
        "type": payload["type"],
        "source": payload["source"],
        "actor": payload.get("actor", {}),
        "object": payload.get("object", {}),
        "timestamp": payload.get("timestamp"),
        "schema_version": payload.get("schema_version", "1.0"),
        "metadata": payload.get("metadata", {}),
        "correlation_id": payload["correlation_id"],
        "parent_correlation_id": payload.get("parent_correlation_id"),
    }

    async with get_session() as session:
        stmt = pg_insert(EventRow).values(**row).on_conflict_do_nothing(index_elements=[EventRow.id])
        await session.execute(stmt)

    bus = get_event_bus()
    await bus.ack(Topic.EVENTS_PROCESSED, "api-ingestor", message_id)


async def run_events_ingestor() -> None:
    bus = get_event_bus()
    logger.info("events ingestor starting")
    await bus.consume(
        Topic.EVENTS_PROCESSED,
        group="api-ingestor",
        consumer_name="api-ingestor-1",
        handler=_handle,
    )
