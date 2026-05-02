"""Consumes events.processed and projects them into the temporal graph.

This is where Graphiti would live. For now we maintain a tiny mapping from
``MyceliumEvent`` to a graph upsert so the surface is visible.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from mycelium_event_bus import EventBus, Topic
from mycelium_event_bus.bus import EventBusConfig
from mycelium_knowledge.graph.store import upsert_edge, upsert_node

logger = logging.getLogger(__name__)


async def _project(event: dict[str, Any]) -> None:
    actor = event.get("actor", {})
    obj = event.get("object", {})
    if actor.get("id"):
        await upsert_node(
            {
                "id": actor["id"],
                "label": actor.get("display_name") or actor["id"],
                "type": "person" if actor.get("type") == "user" else actor.get("type", "concept"),
                "source": event.get("source"),
            }
        )
    if obj.get("id"):
        await upsert_node(
            {
                "id": f"{event.get('source', 'unknown')}:{obj['id']}",
                "label": obj.get("type", "object"),
                "type": obj.get("type", "concept"),
                "source": event.get("source"),
            }
        )
    if actor.get("id") and obj.get("id"):
        await upsert_edge(
            {
                "id": f"{event['id']}",
                "source_id": actor["id"],
                "target_id": f"{event.get('source', 'unknown')}:{obj['id']}",
                "type": event.get("type", "OBSERVED").upper(),
                "source": event.get("source"),
                "properties": {"correlation_id": event.get("correlation_id")},
            }
        )


async def run_graph_ingest_worker() -> None:
    bus = EventBus(EventBusConfig(redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0")))
    logger.info("graph ingest worker starting")

    async def handle(message_id: str, payload: dict[str, Any]) -> None:
        try:
            await _project(payload)
        except Exception:
            logger.exception("projection failed for event %s", payload.get("id"))
        finally:
            await bus.ack(Topic.EVENTS_PROCESSED, "knowledge-graph", message_id)

    await bus.consume(
        Topic.EVENTS_PROCESSED,
        group="knowledge-graph",
        consumer_name="knowledge-graph-1",
        handler=handle,
    )
