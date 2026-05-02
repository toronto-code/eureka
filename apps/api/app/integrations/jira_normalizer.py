"""JiraEventNormalizer.

Handles Jira Cloud webhook payloads and polled REST responses. Outputs
the same `NormalizedEvent` shape as `GithubEventNormalizer` so downstream
ingestion code doesn't care where the event came from.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.integrations.github_normalizer import NormalizedEvent


class JiraEventNormalizer:
    """Stateless normaliser for Jira events."""

    SUPPORTED = {
        "jira:issue_created",
        "jira:issue_updated",
        "jira:issue_deleted",
        "comment_created",
        "comment_updated",
        "comment_deleted",
    }

    def normalize(
        self,
        *,
        payload: dict[str, Any],
        delivery_id: str | None = None,
        origin: str = "webhook",
    ) -> list[NormalizedEvent]:
        webhook_event = payload.get("webhookEvent") or payload.get("event")
        if webhook_event and webhook_event.startswith("jira:issue_"):
            return self._handle_issue(
                payload, delivery_id=delivery_id, origin=origin,
                webhook_event=webhook_event,
            )
        if webhook_event in {"comment_created", "comment_updated", "comment_deleted"}:
            return self._handle_comment(
                payload, delivery_id=delivery_id, origin=origin,
                webhook_event=webhook_event,
            )
        # Polled "issue" payloads from the REST search endpoint — treat as
        # synthetic "issue_updated" events.
        if "issue" not in payload and ("key" in payload or "id" in payload):
            return self._handle_polled_issue(payload, delivery_id=delivery_id, origin=origin)
        if "issue" in payload:
            return self._handle_issue(
                payload, delivery_id=delivery_id, origin=origin,
                webhook_event="jira:issue_updated",
            )
        return []

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_issue(
        self,
        payload: dict[str, Any],
        *,
        delivery_id: str | None,
        origin: str,
        webhook_event: str,
    ) -> list[NormalizedEvent]:
        issue = payload.get("issue") or {}
        fields = issue.get("fields") or {}
        assignee = fields.get("assignee") or {}
        reporter = fields.get("reporter") or {}
        action = webhook_event.split("_", 1)[-1] if "_" in webhook_event else "updated"
        occurred_at = _parse_iso(fields.get("updated") or fields.get("created"))
        actor_name = (payload.get("user") or {}).get("displayName")
        normalized = {
            "key": issue.get("key"),
            "external_id": issue.get("id"),
            "title": fields.get("summary") or "",
            "description": _atlassian_plaintext(fields.get("description")),
            "status": (fields.get("status") or {}).get("name"),
            "assignee": assignee.get("displayName"),
            "assignee_email": assignee.get("emailAddress"),
            "assignee_account_id": assignee.get("accountId"),
            "reporter": reporter.get("displayName"),
            "priority": (fields.get("priority") or {}).get("name"),
            "labels": fields.get("labels") or [],
            "project_key": (fields.get("project") or {}).get("key"),
            "comments": [
                {
                    "author": (c.get("author") or {}).get("displayName"),
                    "body": _atlassian_plaintext(c.get("body")),
                }
                for c in (fields.get("comment") or {}).get("comments", []) or []
            ],
            "last_jira_updated_at": fields.get("updated"),
            "changelog": payload.get("changelog"),
        }
        return [
            NormalizedEvent(
                source="jira",
                event_type=f"jira:issue_{action}",
                entity_type="issue",
                entity_id=issue.get("key"),
                actor=actor_name,
                occurred_at=occurred_at,
                origin=origin,
                delivery_id=delivery_id,
                raw_payload=payload,
                normalized_payload=normalized,
            )
        ]

    def _handle_comment(
        self,
        payload: dict[str, Any],
        *,
        delivery_id: str | None,
        origin: str,
        webhook_event: str,
    ) -> list[NormalizedEvent]:
        comment = payload.get("comment") or {}
        issue = payload.get("issue") or {}
        issue_key = issue.get("key") or comment.get("issueKey")
        occurred_at = _parse_iso(comment.get("updated") or comment.get("created"))
        return [
            NormalizedEvent(
                source="jira",
                event_type=webhook_event,
                entity_type="comment",
                entity_id=str(comment.get("id")) if comment.get("id") else None,
                actor=(comment.get("author") or {}).get("displayName"),
                occurred_at=occurred_at,
                origin=origin,
                delivery_id=delivery_id,
                raw_payload=payload,
                normalized_payload={
                    "comment_id": comment.get("id"),
                    "body": _atlassian_plaintext(comment.get("body")),
                    "issue_key": issue_key,
                    "html_url": (
                        f"{comment.get('self', '').split('/rest/')[0]}/browse/{issue_key}"
                        if issue_key and comment.get("self")
                        else None
                    ),
                },
            )
        ]

    def _handle_polled_issue(
        self, issue: dict[str, Any], *, delivery_id: str | None, origin: str
    ) -> list[NormalizedEvent]:
        """Convert a polled REST issue record into a synthetic update event."""
        fields = issue.get("fields") or {}
        wrapped = {"issue": issue, "user": {}}
        return self._handle_issue(
            wrapped,
            delivery_id=delivery_id,
            origin=origin,
            webhook_event="jira:issue_updated",
        )


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def _atlassian_plaintext(value: Any) -> str:
    """Flatten Atlassian Document Format (ADF) to plaintext."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts: list[str] = []
        for block in value.get("content") or []:
            for inner in block.get("content") or []:
                text = inner.get("text")
                if text:
                    parts.append(text)
        return " ".join(parts)
    return str(value)
