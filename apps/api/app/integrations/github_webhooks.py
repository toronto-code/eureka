"""GithubWebhookHandler: verify signature + normalize + hand off to ingestion."""
from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.ingestion.event_ingestion import EventIngestionService
from app.integrations.github_normalizer import GithubEventNormalizer

logger = logging.getLogger(__name__)


@dataclass
class WebhookAck:
    accepted: bool
    events_ingested: int
    skipped: list[str]
    verified: bool
    reason: str | None = None


class GithubWebhookHandler:
    """Entry point for `POST /api/webhooks/github`."""

    def __init__(
        self,
        normalizer: GithubEventNormalizer | None = None,
        ingestion: EventIngestionService | None = None,
    ) -> None:
        self.normalizer = normalizer or GithubEventNormalizer()
        self.ingestion = ingestion or EventIngestionService()

    # ------------------------------------------------------------------
    # Signature
    # ------------------------------------------------------------------

    def verify_signature(
        self, *, body: bytes, signature_header: str | None
    ) -> bool:
        """Verify `X-Hub-Signature-256`. If no secret is configured, accept
        (dev-mode). In production, set `GITHUB_WEBHOOK_SECRET`."""
        secret = get_settings().github_webhook_secret
        if not secret:
            return True  # dev-mode
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        expected = hmac.new(
            secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        provided = signature_header.split("=", 1)[1]
        return hmac.compare_digest(expected, provided)

    # ------------------------------------------------------------------
    # Main handler
    # ------------------------------------------------------------------

    def handle(
        self,
        session: Session,
        *,
        github_event: str,
        payload: dict[str, Any],
        delivery_id: str | None,
        signature_header: str | None = None,
        raw_body: bytes | None = None,
    ) -> WebhookAck:
        verified = True
        if raw_body is not None:
            verified = self.verify_signature(
                body=raw_body, signature_header=signature_header
            )
            if not verified:
                return WebhookAck(
                    accepted=False,
                    events_ingested=0,
                    skipped=[],
                    verified=False,
                    reason="invalid_signature",
                )

        if github_event not in self.normalizer.SUPPORTED:
            return WebhookAck(
                accepted=True,
                events_ingested=0,
                skipped=[github_event],
                verified=verified,
                reason=f"unsupported_event:{github_event}",
            )

        events = self.normalizer.normalize(
            github_event=github_event,
            payload=payload,
            delivery_id=delivery_id,
            origin="webhook",
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
            accepted=True,
            events_ingested=ingested,
            skipped=skipped,
            verified=verified,
        )
