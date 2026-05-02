"""Signal collector - consumes event bus topics, normalizes, and buffers/persists."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from mycelium_db import get_session
from mycelium_db.models import LearningSignalRow
from mycelium_event_bus import EventBus, Topic

from mycelium_learning.signals.buffer import SignalBuffer
from mycelium_learning.signals.types import Signal

logger = logging.getLogger(__name__)

# TTL for cached approval requests (7 days is plenty for most approvals)
APPROVAL_REQUEST_CACHE_TTL = 7 * 24 * 3600


class SignalCollector:
    """Consumes events from the bus, normalizes them into Signals.

    Each signal goes into:
    1. The in-memory buffer (triggers model updates)
    2. Postgres (learning_signals table) for durable record

    Approval join cache:
        Julian's API publishes approve/reject decisions without pending_actions
        (they only have workflow_id + decision). Agent-runtime publishes
        "requested" approvals with pending_actions. This class caches the
        requests and joins them with decisions so the permission model can
        learn per action_type.
    """

    def __init__(self, bus: EventBus, buffer: SignalBuffer) -> None:
        self._bus = bus
        self._buffer = buffer
        self._approval_requests: dict[str, tuple[dict[str, Any], float]] = {}

    async def _persist(self, signal: Signal) -> None:
        """Persist a signal to Postgres."""
        try:
            async with get_session() as session:
                session.add(
                    LearningSignalRow(
                        id=signal.id,
                        task_id=signal.task_id,
                        agent_id=signal.agent_id,
                        signal_type=signal.kind.value,
                        correlation_id=signal.correlation_id or "",
                        payload=signal.to_dict(),
                    )
                )
        except Exception:
            logger.exception("Failed to persist signal %s", signal.id)

    async def _ingest(self, signal: Signal) -> None:
        """Add a signal to the buffer and persist to Postgres."""
        await self._persist(signal)
        await self._buffer.add(signal)

    async def run_results_consumer(self) -> None:
        """Consume agents.results and generate TASK_RESULT signals."""
        logger.info("learning results consumer starting")

        async def handle(message_id: str, payload: dict[str, Any]) -> None:
            try:
                status = payload.get("status")
                if status in ("succeeded", "failed"):
                    signal = Signal.from_task_result(payload)
                    await self._ingest(signal)
            finally:
                await self._bus.ack(Topic.AGENTS_RESULTS, "learning-results", message_id)

        await self._bus.consume(
            Topic.AGENTS_RESULTS,
            group="learning-results",
            consumer_name="learning-results-1",
            handler=handle,
        )

    def _cache_approval_request(self, payload: dict[str, Any]) -> None:
        """Cache pending_actions from an approval request for later join."""
        workflow_id = payload.get("workflow_id") or payload.get("task_id")
        if not workflow_id:
            return

        pending = payload.get("pending_actions") or []
        agent_id = payload.get("agent_id")
        now = time.time()

        self._approval_requests[workflow_id] = (
            {"pending_actions": pending, "agent_id": agent_id},
            now + APPROVAL_REQUEST_CACHE_TTL,
        )

        # Cleanup expired entries opportunistically
        expired = [k for k, (_, exp) in self._approval_requests.items() if exp < now]
        for k in expired:
            self._approval_requests.pop(k, None)

    def _join_decision_with_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Enrich a decision payload with pending_actions from the cached request."""
        workflow_id = payload.get("workflow_id") or payload.get("task_id")
        if not workflow_id:
            return payload

        cached = self._approval_requests.get(workflow_id)
        if cached is None:
            return payload

        request_data, _expiry = cached
        return {
            **payload,
            "pending_actions": payload.get("pending_actions") or request_data.get("pending_actions") or [],
            "agent_id": payload.get("agent_id") or request_data.get("agent_id"),
        }

    async def run_approvals_consumer(self) -> None:
        """Consume workflows.approvals and generate APPROVAL_DECISION signals.

        - decision="requested": cache pending_actions (no signal yet)
        - decision="approve"/"reject": look up cached request, emit enriched signal
        """
        logger.info("learning approvals consumer starting")

        async def handle(message_id: str, payload: dict[str, Any]) -> None:
            try:
                decision = payload.get("decision")

                if decision == "requested":
                    self._cache_approval_request(payload)
                    return

                if decision in ("approve", "reject"):
                    enriched = self._join_decision_with_request(payload)
                    signal = Signal.from_approval_decision(enriched)
                    if signal is not None:
                        await self._ingest(signal)

                        workflow_id = payload.get("workflow_id") or payload.get("task_id")
                        if workflow_id:
                            self._approval_requests.pop(workflow_id, None)
            finally:
                await self._bus.ack(Topic.WORKFLOWS_APPROVALS, "learning-approvals", message_id)

        await self._bus.consume(
            Topic.WORKFLOWS_APPROVALS,
            group="learning-approvals",
            consumer_name="learning-approvals-1",
            handler=handle,
        )

    async def ingest_feedback(self, signal: Signal) -> None:
        """Ingest a signal from the feedback API (called from HTTP handler)."""
        await self._ingest(signal)
