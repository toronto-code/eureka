"""JiraWebhookHandler: verify shared-secret (optional) + normalize + ingest."""
from __future__ import annotations

import hmac
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.ingestion.event_ingestion import EventIngestionService
from app.integrations.github_webhooks import WebhookAck
from app.integrations.jira_normalizer import JiraEventNormalizer

logger = logging.getLogger(__name__)


class JiraWebhookHandler:
    """Entry point for `POST /api/webhooks/jira`."""

    def __init__(
        self,
        normalizer: JiraEventNormalizer | None = None,
        ingestion: EventIngestionService | None = None,
    ) -> None:
        self.normalizer = normalizer or JiraEventNormalizer()
        self.ingestion = ingestion or EventIngestionService()

    def verify_secret(self, *, provided: str | None) -> bool:
        """Compare a shared-secret header if one is configured."""
        expected = get_settings().jira_webhook_shared_secret
        if not expected:
            return True  # dev-mode
        if not provided:
            return False
        return hmac.compare_digest(expected, provided)

    def handle(
        self,
        session: Session,
        *,
        payload: dict[str, Any],
        shared_secret_header: str | None = None,
        delivery_id: str | None = None,
    ) -> WebhookAck:
        if not self.verify_secret(provided=shared_secret_header):
            return WebhookAck(
                accepted=False,
                events_ingested=0,
                skipped=[],
                verified=False,
                reason="invalid_shared_secret",
            )

        events = self.normalizer.normalize(
            payload=payload, delivery_id=delivery_id, origin="webhook"
        )
        ingested = 0
        skipped: list[str] = []
        for event in events:
            result = self.ingestion.ingest(session, event)
            if result.skipped_reason:
                skipped.append(result.skipped_reason)
            else:
                ingested += 1
        return WebhookAck(
            accepted=True, events_ingested=ingested, skipped=skipped, verified=True
        )
