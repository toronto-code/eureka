"""Slack connector. Real impl uses Composio + Slack Bolt; stubbed in DEV_MODE."""

from __future__ import annotations

import logging
import os
import random

from mycelium_event_bus import EventBus
from mycelium_integrations.connectors._base import is_dev_mode, make_event, publish

logger = logging.getLogger(__name__)


async def sync_slack(bus: EventBus) -> int:
    if is_dev_mode() or not os.getenv("SLACK_BOT_TOKEN"):
        return await _sync_dev(bus)
    logger.info("slack real-mode sync not implemented; emitting empty result")
    return 0


async def _sync_dev(bus: EventBus) -> int:
    thread_id = f"T1.{random.randint(1, 9999)}"
    actor = random.choice(["u_alice", "u_bob", "u_carol"])

    posted = make_event(
        source="slack", type_="slack.message.posted", actor_id=actor, actor_type="user",
        object_id=f"msg-{random.randint(1, 9999)}", object_type="message",
        natural_id=f"thread-{thread_id}",
        metadata={"channel": "#engineering"},
    )
    edited = make_event(
        source="slack", type_="slack.message.edited", actor_id=actor, actor_type="user",
        object_id=posted.object.id, object_type="message",
        natural_id=f"thread-{thread_id}",
        parent_correlation_id=posted.correlation_id,
        metadata={"channel": "#engineering"},
    )

    for ev in (posted, edited):
        await publish(bus, ev)
    return 2
