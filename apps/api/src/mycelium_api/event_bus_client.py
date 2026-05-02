"""Lazy singleton EventBus."""

from __future__ import annotations

from functools import lru_cache

from mycelium_api.config import REDIS_URL
from mycelium_event_bus import EventBus
from mycelium_event_bus.bus import EventBusConfig


@lru_cache
def get_event_bus() -> EventBus:
    return EventBus(EventBusConfig(redis_url=REDIS_URL))
