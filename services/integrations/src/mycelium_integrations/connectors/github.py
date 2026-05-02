"""GitHub connector. Composio-backed in production; stubbed in DEV_MODE."""

from __future__ import annotations

import logging
import os
import random

from mycelium_event_bus import EventBus
from mycelium_integrations.connectors._base import is_dev_mode, make_event, publish

logger = logging.getLogger(__name__)


async def sync_github(bus: EventBus) -> int:
    if is_dev_mode() or not os.getenv("GITHUB_TOKEN"):
        return await _sync_dev(bus)
    # Real impl: use Composio + GitHub REST/GraphQL.
    logger.info("github real-mode sync not implemented; emitting empty result")
    return 0


async def _sync_dev(bus: EventBus) -> int:
    """Emit a few fake GitHub events with proper correlation_id chains."""
    pr_number = random.randint(40, 60)
    natural = f"pr-{pr_number}"
    actors = ["u_alice", "u_bob", "u_carol"]
    actor = random.choice(actors)

    opened = make_event(
        source="github", type_="github.pr.opened", actor_id=actor, actor_type="user",
        object_id=str(pr_number), object_type="pull_request", natural_id=natural,
        metadata={"title": f"feat: example change {pr_number}"},
    )
    reviewed = make_event(
        source="github", type_="github.pr.reviewed", actor_id="u_bob", actor_type="user",
        object_id=str(pr_number), object_type="pull_request", natural_id=natural,
        parent_correlation_id=opened.correlation_id,
        metadata={"state": "approved"},
    )
    merged = make_event(
        source="github", type_="github.pr.merged", actor_id=actor, actor_type="user",
        object_id=str(pr_number), object_type="pull_request", natural_id=natural,
        parent_correlation_id=opened.correlation_id,
    )

    for ev in (opened, reviewed, merged):
        await publish(bus, ev)
    return 3
