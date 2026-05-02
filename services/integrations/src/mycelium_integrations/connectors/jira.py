"""Jira connector. Real impl uses Composio + Jira REST; stubbed in DEV_MODE."""

from __future__ import annotations

import logging
import os
import random

from mycelium_event_bus import EventBus
from mycelium_integrations.connectors._base import is_dev_mode, make_event, publish

logger = logging.getLogger(__name__)


async def sync_jira(bus: EventBus) -> int:
    if is_dev_mode() or not os.getenv("JIRA_API_TOKEN"):
        return await _sync_dev(bus)
    logger.info("jira real-mode sync not implemented; emitting empty result")
    return 0


async def _sync_dev(bus: EventBus) -> int:
    ticket_key = f"ENG-{random.randint(100, 200)}"
    actor = random.choice(["u_alice", "u_bob", "u_carol"])

    created = make_event(
        source="jira", type_="jira.ticket.created", actor_id=actor, actor_type="user",
        object_id=ticket_key, object_type="ticket", natural_id=ticket_key,
        metadata={"summary": "example ticket"},
    )
    transitioned = make_event(
        source="jira", type_="jira.ticket.transitioned", actor_id=actor, actor_type="user",
        object_id=ticket_key, object_type="ticket", natural_id=ticket_key,
        parent_correlation_id=created.correlation_id,
        metadata={"from": "todo", "to": "in_progress"},
    )

    for ev in (created, transitioned):
        await publish(bus, ev)
    return 2
