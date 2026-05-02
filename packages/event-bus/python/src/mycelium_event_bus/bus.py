"""Redis Streams-backed event bus.

This is intentionally small. It implements the four primitives every Mycelium
service needs:

  * ``publish(topic, event, *, correlation_id)``
  * ``consume(topic, group, consumer_name, handler)``
  * ``ack(topic, group, message_id)``
  * ``retry(topic, group, message_id)``

ORDERING GUARANTEE
------------------
Ordering is guaranteed *per correlation_id stream partition only*. Each topic
is split into N partitions (Redis streams) keyed by ``hash(correlation_id) % N``.
Consumers must never assume global ordering across partitions.

This is documented in ``docs/contracts.md``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

import redis.asyncio as aioredis

from mycelium_event_bus.topics import Topic

logger = logging.getLogger(__name__)

DEFAULT_PARTITIONS = 8
"""Number of stream partitions per topic. Small companies don't need more."""


Handler = Callable[[str, dict[str, Any]], Awaitable[None]]
"""Async handler called as ``await handler(message_id, payload)``."""


@dataclass
class EventBusConfig:
    redis_url: str
    partitions: int = DEFAULT_PARTITIONS
    consumer_group: str = "mycelium"


class EventBus:
    """Thin Redis Streams client. Async."""

    def __init__(self, config: EventBusConfig):
        self._config = config
        self._redis = aioredis.from_url(
            config.redis_url, decode_responses=True
        )

    # ------------------------------------------------------------------ utils

    def _partition_key(self, correlation_id: str) -> int:
        return hash(correlation_id) % self._config.partitions

    def _stream_name(self, topic: Topic | str, correlation_id: str) -> str:
        topic_value = topic.value if isinstance(topic, Topic) else topic
        return f"{topic_value}.p{self._partition_key(correlation_id)}"

    def _all_partition_streams(self, topic: Topic | str) -> list[str]:
        topic_value = topic.value if isinstance(topic, Topic) else topic
        return [f"{topic_value}.p{i}" for i in range(self._config.partitions)]

    # -------------------------------------------------------------- publish

    async def publish(
        self,
        topic: Topic | str,
        event: dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> str:
        """Publish ``event`` to ``topic``.

        ``correlation_id`` selects the partition. If it is omitted we fall back
        to ``event["correlation_id"]``. If neither is present we raise — every
        event in Mycelium must have a correlation_id (see contracts).
        """
        cid = correlation_id or event.get("correlation_id")
        if not cid:
            raise ValueError(
                "EventBus.publish requires correlation_id (mandatory on every event)"
            )

        stream = self._stream_name(topic, cid)
        message_id = await self._redis.xadd(
            stream,
            {"payload": json.dumps(event, default=str), "correlation_id": cid},
        )
        logger.debug("published %s to %s id=%s", event.get("type"), stream, message_id)
        return message_id

    # -------------------------------------------------------------- consume

    async def ensure_group(self, topic: Topic | str, group: str) -> None:
        """Create the consumer group on each partition if it doesn't exist."""
        for stream in self._all_partition_streams(topic):
            try:
                await self._redis.xgroup_create(
                    stream, group, id="0", mkstream=True
                )
            except Exception as exc:  # group already exists
                if "BUSYGROUP" not in str(exc):
                    raise

    async def consume(
        self,
        topic: Topic | str,
        group: str,
        consumer_name: str,
        handler: Handler,
        *,
        block_ms: int = 5000,
        count: int = 16,
    ) -> None:
        """Long-running consumer loop.

        Calls ``handler(message_id, payload)`` for each message. The handler
        must call ``await bus.ack(topic, group, message_id)`` on success or
        ``await bus.retry(topic, group, message_id)`` on transient failure.
        """
        await self.ensure_group(topic, group)
        streams = {s: ">" for s in self._all_partition_streams(topic)}

        while True:
            try:
                response = await self._redis.xreadgroup(
                    group,
                    consumer_name,
                    streams,
                    count=count,
                    block=block_ms,
                )
            except Exception:
                logger.exception("xreadgroup failed; backing off")
                continue

            if not response:
                continue

            for _stream, messages in response:
                for message_id, fields in messages:
                    try:
                        payload = json.loads(fields.get("payload", "{}"))
                    except json.JSONDecodeError:
                        logger.exception("invalid payload at %s; ack to drop", message_id)
                        await self.ack(topic, group, message_id)
                        continue
                    await handler(message_id, payload)

    # -------------------------------------------------------------- ack/retry

    async def ack(self, topic: Topic | str, group: str, message_id: str) -> None:
        """Acknowledge across all partitions; redis ignores misses."""
        for stream in self._all_partition_streams(topic):
            await self._redis.xack(stream, group, message_id)

    async def retry(
        self,
        topic: Topic | str,
        group: str,
        message_id: str,
        *,
        consumer_name: str = "retry",
        min_idle_ms: int = 0,
    ) -> None:
        """Reclaim ``message_id`` so it gets re-delivered.

        XCLAIM assigns the message to ``consumer_name``; when that consumer
        next calls XREADGROUP it'll see it as a pending entry. We don't ack
        here — the next handler attempt will.
        """
        for stream in self._all_partition_streams(topic):
            try:
                await self._redis.xclaim(
                    stream, group, consumer_name, min_idle_ms, [message_id]
                )
            except Exception:
                continue

    # -------------------------------------------------------------- close

    async def close(self) -> None:
        await self._redis.close()
