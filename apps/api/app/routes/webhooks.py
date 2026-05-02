"""Webhook endpoints for GitHub and Jira.

Both routes share the same behaviour contract:
- Read the raw body for signature verification.
- Pass the parsed payload + headers to the appropriate handler.
- Commit the session; the handler already flushed each event row.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.integrations.github_webhooks import GithubWebhookHandler
from app.integrations.jira_webhooks import JiraWebhookHandler
from app.schemas.api import WebhookAckOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/github", response_model=WebhookAckOut)
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default="ping"),
    x_github_delivery: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> WebhookAckOut:
    raw = await request.body()
    try:
        payload: dict[str, Any] = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        payload = {}
    handler = GithubWebhookHandler()
    ack = handler.handle(
        db,
        github_event=x_github_event,
        payload=payload,
        delivery_id=x_github_delivery,
        signature_header=x_hub_signature_256,
        raw_body=raw,
    )
    if ack.accepted:
        db.commit()
    else:
        db.rollback()
    return WebhookAckOut(
        accepted=ack.accepted,
        events_ingested=ack.events_ingested,
        skipped=ack.skipped,
        verified=ack.verified,
        reason=ack.reason,
    )


@router.post("/jira", response_model=WebhookAckOut)
async def jira_webhook(
    request: Request,
    x_atlassian_webhook_identifier: str | None = Header(default=None),
    x_mycelium_shared_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> WebhookAckOut:
    raw = await request.body()
    try:
        payload: dict[str, Any] = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        payload = {}
    handler = JiraWebhookHandler()
    ack = handler.handle(
        db,
        payload=payload,
        shared_secret_header=x_mycelium_shared_secret,
        delivery_id=x_atlassian_webhook_identifier,
    )
    if ack.accepted:
        db.commit()
    else:
        db.rollback()
    return WebhookAckOut(
        accepted=ack.accepted,
        events_ingested=ack.events_ingested,
        skipped=ack.skipped,
        verified=ack.verified,
        reason=ack.reason,
    )
