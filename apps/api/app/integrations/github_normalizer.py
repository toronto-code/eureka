"""GithubEventNormalizer.

Turns raw GitHub webhook payloads (or polled REST responses) into the
common `NormalizedEvent` shape. The same shape is consumed downstream by
`EventIngestionService` whether the event originated from a webhook or a
dev-mode polling sync.

We only normalise the fields OL actually reads. Raw payloads are stored
alongside so operators can replay / debug.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class NormalizedEvent:
    source: str                        # "github"
    event_type: str                    # e.g. "push", "pull_request.opened"
    entity_type: str | None            # "commit" | "pull_request" | "issue" | "comment" | "review"
    entity_id: str | None              # sha | pr number | issue key | comment id
    actor: str | None
    occurred_at: datetime | None
    origin: str                        # "webhook" | "polling" | "manual"
    delivery_id: str | None
    raw_payload: dict[str, Any] = field(default_factory=dict)
    normalized_payload: dict[str, Any] = field(default_factory=dict)
    repo_full_name: str | None = None  # "owner/repo" for routing to Repository


class GithubEventNormalizer:
    """Stateless normaliser. One method per webhook X-GitHub-Event."""

    SUPPORTED = {
        "push",
        "pull_request",
        "pull_request_review",
        "pull_request_review_comment",
        "issues",
        "issue_comment",
        "create",
        "delete",
    }

    def normalize(
        self,
        *,
        github_event: str,
        payload: dict[str, Any],
        delivery_id: str | None = None,
        origin: str = "webhook",
    ) -> list[NormalizedEvent]:
        """Return a list because one webhook can expand into multiple events
        (e.g. a `push` carries N commits)."""
        handler = getattr(self, f"_handle_{github_event}", None)
        if handler is None:
            return [
                NormalizedEvent(
                    source="github",
                    event_type=github_event,
                    entity_type=None,
                    entity_id=None,
                    actor=_sender_login(payload),
                    occurred_at=None,
                    origin=origin,
                    delivery_id=delivery_id,
                    raw_payload=payload,
                    normalized_payload={},
                    repo_full_name=(payload.get("repository") or {}).get("full_name"),
                )
            ]
        return handler(payload, delivery_id=delivery_id, origin=origin)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_push(
        self, payload: dict[str, Any], *, delivery_id: str | None, origin: str
    ) -> list[NormalizedEvent]:
        repo_full = (payload.get("repository") or {}).get("full_name")
        ref = payload.get("ref") or ""
        branch = ref.split("/", 2)[-1] if ref.startswith("refs/heads/") else None
        events: list[NormalizedEvent] = []
        for commit in payload.get("commits") or []:
            sha = commit.get("id") or commit.get("sha")
            author = (commit.get("author") or {}).get("username") or (
                commit.get("author") or {}
            ).get("name")
            occurred_at = _parse_iso(commit.get("timestamp"))
            events.append(
                NormalizedEvent(
                    source="github",
                    event_type="push",
                    entity_type="commit",
                    entity_id=sha,
                    actor=author,
                    occurred_at=occurred_at,
                    origin=origin,
                    delivery_id=delivery_id,
                    repo_full_name=repo_full,
                    raw_payload=payload,
                    normalized_payload={
                        "sha": sha,
                        "message": commit.get("message"),
                        "author_name": (commit.get("author") or {}).get("name"),
                        "author_email": (commit.get("author") or {}).get("email"),
                        "branch": branch,
                        "html_url": commit.get("url"),
                    },
                )
            )
        return events or [
            NormalizedEvent(
                source="github",
                event_type="push",
                entity_type="branch",
                entity_id=branch,
                actor=_sender_login(payload),
                occurred_at=None,
                origin=origin,
                delivery_id=delivery_id,
                repo_full_name=repo_full,
                raw_payload=payload,
                normalized_payload={"branch": branch, "ref": ref},
            )
        ]

    def _handle_pull_request(
        self, payload: dict[str, Any], *, delivery_id: str | None, origin: str
    ) -> list[NormalizedEvent]:
        action = payload.get("action") or "unknown"
        pr = payload.get("pull_request") or {}
        return [
            NormalizedEvent(
                source="github",
                event_type=f"pull_request.{action}",
                entity_type="pull_request",
                entity_id=str(pr.get("number")) if pr.get("number") else None,
                actor=(pr.get("user") or {}).get("login") or _sender_login(payload),
                occurred_at=_parse_iso(pr.get("updated_at") or pr.get("created_at")),
                origin=origin,
                delivery_id=delivery_id,
                repo_full_name=(payload.get("repository") or {}).get("full_name"),
                raw_payload=payload,
                normalized_payload={
                    "number": pr.get("number"),
                    "title": pr.get("title"),
                    "body": pr.get("body"),
                    "state": pr.get("state"),
                    "author": (pr.get("user") or {}).get("login"),
                    "head_branch": (pr.get("head") or {}).get("ref"),
                    "base_branch": (pr.get("base") or {}).get("ref"),
                    "html_url": pr.get("html_url"),
                    "opened_at": pr.get("created_at"),
                    "merged_at": pr.get("merged_at"),
                    "closed_at": pr.get("closed_at"),
                },
            )
        ]

    def _handle_pull_request_review(
        self, payload: dict[str, Any], *, delivery_id: str | None, origin: str
    ) -> list[NormalizedEvent]:
        action = payload.get("action") or "submitted"
        review = payload.get("review") or {}
        pr = payload.get("pull_request") or {}
        return [
            NormalizedEvent(
                source="github",
                event_type=f"pull_request_review.{action}",
                entity_type="review",
                entity_id=str(review.get("id")) if review.get("id") else None,
                actor=(review.get("user") or {}).get("login"),
                occurred_at=_parse_iso(review.get("submitted_at")),
                origin=origin,
                delivery_id=delivery_id,
                repo_full_name=(payload.get("repository") or {}).get("full_name"),
                raw_payload=payload,
                normalized_payload={
                    "review_id": review.get("id"),
                    "pr_number": pr.get("number"),
                    "body": review.get("body"),
                    "state": review.get("state"),
                    "html_url": review.get("html_url"),
                },
            )
        ]

    def _handle_issues(
        self, payload: dict[str, Any], *, delivery_id: str | None, origin: str
    ) -> list[NormalizedEvent]:
        action = payload.get("action") or "unknown"
        issue = payload.get("issue") or {}
        return [
            NormalizedEvent(
                source="github",
                event_type=f"issues.{action}",
                entity_type="issue",
                entity_id=str(issue.get("number")) if issue.get("number") else None,
                actor=(issue.get("user") or {}).get("login") or _sender_login(payload),
                occurred_at=_parse_iso(issue.get("updated_at") or issue.get("created_at")),
                origin=origin,
                delivery_id=delivery_id,
                repo_full_name=(payload.get("repository") or {}).get("full_name"),
                raw_payload=payload,
                normalized_payload={
                    "number": issue.get("number"),
                    "title": issue.get("title"),
                    "body": issue.get("body"),
                    "state": issue.get("state"),
                    "html_url": issue.get("html_url"),
                },
            )
        ]

    def _handle_issue_comment(
        self, payload: dict[str, Any], *, delivery_id: str | None, origin: str
    ) -> list[NormalizedEvent]:
        action = payload.get("action") or "created"
        comment = payload.get("comment") or {}
        issue = payload.get("issue") or {}
        return [
            NormalizedEvent(
                source="github",
                event_type=f"issue_comment.{action}",
                entity_type="comment",
                entity_id=str(comment.get("id")) if comment.get("id") else None,
                actor=(comment.get("user") or {}).get("login"),
                occurred_at=_parse_iso(comment.get("updated_at") or comment.get("created_at")),
                origin=origin,
                delivery_id=delivery_id,
                repo_full_name=(payload.get("repository") or {}).get("full_name"),
                raw_payload=payload,
                normalized_payload={
                    "comment_id": comment.get("id"),
                    "body": comment.get("body"),
                    "issue_number": issue.get("number"),
                    "html_url": comment.get("html_url"),
                },
            )
        ]

    def _handle_create(
        self, payload: dict[str, Any], *, delivery_id: str | None, origin: str
    ) -> list[NormalizedEvent]:
        return [
            NormalizedEvent(
                source="github",
                event_type="create",
                entity_type=payload.get("ref_type"),
                entity_id=payload.get("ref"),
                actor=_sender_login(payload),
                occurred_at=None,
                origin=origin,
                delivery_id=delivery_id,
                repo_full_name=(payload.get("repository") or {}).get("full_name"),
                raw_payload=payload,
                normalized_payload={
                    "ref": payload.get("ref"),
                    "ref_type": payload.get("ref_type"),
                },
            )
        ]

    def _handle_delete(
        self, payload: dict[str, Any], *, delivery_id: str | None, origin: str
    ) -> list[NormalizedEvent]:
        return [
            NormalizedEvent(
                source="github",
                event_type="delete",
                entity_type=payload.get("ref_type"),
                entity_id=payload.get("ref"),
                actor=_sender_login(payload),
                occurred_at=None,
                origin=origin,
                delivery_id=delivery_id,
                repo_full_name=(payload.get("repository") or {}).get("full_name"),
                raw_payload=payload,
                normalized_payload={
                    "ref": payload.get("ref"),
                    "ref_type": payload.get("ref_type"),
                },
            )
        ]


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _sender_login(payload: dict[str, Any]) -> str | None:
    return (payload.get("sender") or {}).get("login")


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None
