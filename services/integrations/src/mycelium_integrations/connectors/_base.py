"""Helpers shared by all connectors."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from mycelium_event_bus import EventBus, Topic
from mycelium_shared_types import MyceliumEvent, MyceliumEventActor, MyceliumEventObject
from mycelium_shared_types.correlation import derive_correlation_id


def is_dev_mode() -> bool:
    return os.getenv("DEV_MODE", "true").lower() == "true"


def make_event(
    *,
    source: str,
    type_: str,
    actor_id: str,
    actor_type: str,
    object_id: str,
    object_type: str,
    natural_id: str | None = None,
    metadata: dict | None = None,
    parent_correlation_id: str | None = None,
) -> MyceliumEvent:
    cid = derive_correlation_id(source=source, object_id=object_id, natural_id=natural_id)
    return MyceliumEvent(
        id=str(uuid.uuid4()),
        type=type_,
        source=source,
        actor=MyceliumEventActor(id=actor_id, type=actor_type),
        object=MyceliumEventObject(id=object_id, type=object_type),
        timestamp=datetime.now(timezone.utc),
        metadata=metadata or {},
        correlation_id=cid,
        parent_correlation_id=parent_correlation_id,
    )


async def publish(bus: EventBus, event: MyceliumEvent) -> None:
    await bus.publish(
        Topic.EVENTS_RAW,
        event.model_dump(mode="json"),
        correlation_id=event.correlation_id,
    )
