"""events.raw consumer.

For each event:
  1. Run classification (PII / secrets / credentials).
  2. If clean (or scrubbable), publish to events.processed.
  3. If classification fails, retry up to CLASSIFICATION_RETRY_LIMIT times.
  4. After the limit, publish to events.dlq with error_category, retry_count,
     original_event. Never silently drop.
"""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from mycelium_event_bus import DLQMessage, ErrorCategory, EventBus, Topic
from mycelium_event_bus.bus import EventBusConfig

logger = logging.getLogger(__name__)

DLQ_BUFFER: deque[dict] = deque(maxlen=200)
"""In-memory mirror of the most recent DLQ entries, exposed via /dlq."""


_RETRY_COUNTS: dict[str, int] = defaultdict(int)


_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)(api[-_]?key|secret|token|password)\s*[:=]\s*\S+"),
]


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        out = value
        for pat in _SECRET_PATTERNS:
            out = pat.sub("[REDACTED]", out)
        return out
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def _classify(event: dict[str, Any]) -> dict[str, Any]:
    """Return a (possibly scrubbed) copy of the event. Raises on hard failure."""
    if not event.get("correlation_id"):
        raise ValueError("missing correlation_id")
    return _scrub(event)


def _bus() -> EventBus:
    return EventBus(EventBusConfig(redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0")))


async def _publish_dlq(bus: EventBus, *, original: dict, retry_count: int,
                       error: Exception, category: ErrorCategory) -> None:
    msg = DLQMessage(
        error_category=category,
        retry_count=retry_count,
        original_event=original,
        error_message=str(error),
        failed_at=datetime.now(timezone.utc),
        failed_by="services/security/classification",
    )
    cid = original.get("correlation_id") or "dlq"
    await bus.publish(Topic.EVENTS_DLQ, msg.model_dump(mode="json"), correlation_id=cid)
    DLQ_BUFFER.appendleft(msg.model_dump(mode="json"))


async def run_classification_worker() -> None:
    bus = _bus()
    retry_limit = int(os.getenv("CLASSIFICATION_RETRY_LIMIT", "3"))
    logger.info("classification worker starting; retry_limit=%d", retry_limit)

    async def handle(message_id: str, payload: dict[str, Any]) -> None:
        event_id = payload.get("id", message_id)
        try:
            cleaned = _classify(payload)
        except Exception as exc:
            _RETRY_COUNTS[event_id] += 1
            attempts = _RETRY_COUNTS[event_id]
            if attempts < retry_limit:
                logger.warning(
                    "classification failed (attempt %d/%d) for %s: %s",
                    attempts, retry_limit, event_id, exc,
                )
                await bus.retry(Topic.EVENTS_RAW, "security-classifier", message_id)
                return

            category = (
                ErrorCategory.SCHEMA_INVALID
                if isinstance(exc, ValueError)
                else ErrorCategory.CLASSIFICATION_FAILED
            )
            await _publish_dlq(
                bus,
                original=payload,
                retry_count=attempts,
                error=exc,
                category=category,
            )
            _RETRY_COUNTS.pop(event_id, None)
            await bus.ack(Topic.EVENTS_RAW, "security-classifier", message_id)
            return

        await bus.publish(
            Topic.EVENTS_PROCESSED, cleaned, correlation_id=cleaned["correlation_id"]
        )
        _RETRY_COUNTS.pop(event_id, None)
        await bus.ack(Topic.EVENTS_RAW, "security-classifier", message_id)

    await bus.consume(
        Topic.EVENTS_RAW,
        group="security-classifier",
        consumer_name="security-classifier-1",
        handler=handle,
    )
