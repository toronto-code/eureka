"""Jira integration.

- **Real mode**: `JIRA_BASE_URL` + `JIRA_EMAIL` + `JIRA_API_TOKEN` set.
- **Dry-run mode**: otherwise. Seeded fake tasks drive the local demo.

`post_comment` and `transition_issue` return a structured result in both
modes so the ExecutionService can record what would have happened.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any
from uuid import uuid4

import httpx

from app.config import get_settings
from app.integrations._fakes import fake_jira_tasks

logger = logging.getLogger(__name__)


class JiraClient:
    """Minimal Jira REST client + seeded-fallback behaviour."""

    def __init__(
        self,
        base_url: str | None,
        email: str | None,
        api_token: str | None,
        project_key: str | None,
        bot_user: str | None = None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.email = email
        self.api_token = api_token
        self.project_key = project_key
        self.bot_user = bot_user

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.email and self.api_token)

    # ---------------------------------------------------------------
    # Identity / assignment helpers
    # ---------------------------------------------------------------

    def is_assigned_to_bot(self, issue: dict[str, Any]) -> bool:
        """Return True if the issue's assignee matches the configured bot user."""
        if not self.bot_user:
            return False
        assignee = issue.get("assignee")
        assignee_email = issue.get("assignee_email")
        assignee_account_id = issue.get("assignee_account_id")
        candidates = {c for c in (assignee, assignee_email, assignee_account_id) if c}
        return self.bot_user.lower() in {str(c).lower() for c in candidates}

    # ---------------------------------------------------------------
    # Read APIs
    # ---------------------------------------------------------------

    def fetch_issues(
        self,
        *,
        status: str | None = None,
        assignee: str | None = None,
        extra_jql: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.configured:
            issues = fake_jira_tasks()
            if status:
                issues = [i for i in issues if i.get("status") == status]
            if assignee:
                issues = [
                    i
                    for i in issues
                    if assignee.lower()
                    in {
                        str(i.get("assignee") or "").lower(),
                        str(i.get("assignee_email") or "").lower(),
                        str(i.get("assignee_account_id") or "").lower(),
                    }
                ]
            return issues
        try:
            jql_parts: list[str] = []
            if self.project_key:
                jql_parts.append(f"project = {self.project_key}")
            if status:
                jql_parts.append(f"status = '{status}'")
            if assignee:
                # Prefer accountId; fall back to email.
                if "@" in assignee:
                    jql_parts.append(f"assignee = '{assignee}'")
                else:
                    jql_parts.append(f"assignee = {assignee}")
            if extra_jql:
                jql_parts.append(f"({extra_jql})")
            jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"
            resp = self._get("/rest/api/3/search", params={"jql": jql, "maxResults": 50})
            return [self._normalise_issue(issue) for issue in resp.get("issues", [])]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Jira fetch_issues failed, falling back to fakes: %s", exc)
            return fake_jira_tasks()

    def fetch_issue(self, issue_key: str) -> dict[str, Any] | None:
        if not self.configured:
            for issue in fake_jira_tasks():
                if issue.get("key") == issue_key or issue.get("id") == issue_key:
                    return issue
            return None
        try:
            data = self._get(f"/rest/api/3/issue/{issue_key}")
            return self._normalise_issue(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Jira fetch_issue failed: %s", exc)
            return None

    # ---------------------------------------------------------------
    # Write APIs
    # ---------------------------------------------------------------

    def post_comment(self, issue_key: str, body: str) -> dict[str, Any]:
        """Post a comment to a Jira issue. Returns structured result."""
        if not self.configured:
            return {
                "issue_key": issue_key,
                "comment_id": f"dry-{uuid4().hex[:8]}",
                "body": body,
                "html_url": f"{self.base_url or 'https://jira.example'}/browse/{issue_key}",
                "dry_run": True,
            }
        try:
            resp = self._post(
                f"/rest/api/3/issue/{issue_key}/comment",
                json={
                    "body": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": body}],
                            }
                        ],
                    }
                },
            )
            return {
                "issue_key": issue_key,
                "comment_id": resp.get("id"),
                "body": body,
                "html_url": f"{self.base_url}/browse/{issue_key}",
                "dry_run": False,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Jira post_comment failed: %s", exc)
            return {
                "issue_key": issue_key,
                "error": str(exc),
                "dry_run": True,
            }

    def transition_issue(
        self, issue_key: str, *, transition_name: str
    ) -> dict[str, Any]:
        """Move a Jira issue to a new status (e.g. 'In Progress', 'In Review')."""
        if not self.configured:
            return {
                "issue_key": issue_key,
                "transition": transition_name,
                "dry_run": True,
            }
        try:
            # Resolve transition id from name.
            transitions_resp = self._get(f"/rest/api/3/issue/{issue_key}/transitions")
            transition_id: str | None = None
            for t in transitions_resp.get("transitions", []):
                if t.get("name", "").lower() == transition_name.lower():
                    transition_id = t.get("id")
                    break
            if transition_id is None:
                return {
                    "issue_key": issue_key,
                    "transition": transition_name,
                    "error": f"Transition '{transition_name}' not available.",
                    "dry_run": True,
                }
            self._post(
                f"/rest/api/3/issue/{issue_key}/transitions",
                json={"transition": {"id": transition_id}},
            )
            return {
                "issue_key": issue_key,
                "transition": transition_name,
                "transition_id": transition_id,
                "dry_run": False,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Jira transition_issue failed: %s", exc)
            return {
                "issue_key": issue_key,
                "transition": transition_name,
                "error": str(exc),
                "dry_run": True,
            }

    # ---------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------

    def _auth(self) -> tuple[str, str]:
        return (self.email or "", self.api_token or "")

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(self.base_url + path, params=params, auth=self._auth())
            resp.raise_for_status()
            return resp.json()

    def _post(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(self.base_url + path, json=json, auth=self._auth())
            resp.raise_for_status()
            return resp.json() if resp.content else {}

    @staticmethod
    def _normalise_issue(issue: dict[str, Any]) -> dict[str, Any]:
        fields = issue.get("fields", {}) or {}
        assignee_field = fields.get("assignee") or {}
        return {
            "id": issue.get("id"),
            "key": issue.get("key"),
            "title": fields.get("summary") or "",
            "description": _extract_atlassian_doc(fields.get("description")),
            "status": (fields.get("status") or {}).get("name"),
            "assignee": assignee_field.get("displayName"),
            "assignee_email": assignee_field.get("emailAddress"),
            "assignee_account_id": assignee_field.get("accountId"),
            "reporter": (fields.get("reporter") or {}).get("displayName"),
            "labels": fields.get("labels") or [],
            "priority": (fields.get("priority") or {}).get("name"),
            "comments": [
                {
                    "author": (c.get("author") or {}).get("displayName"),
                    "body": _extract_atlassian_doc(c.get("body")),
                }
                for c in (fields.get("comment") or {}).get("comments", []) or []
            ],
        }


def _extract_atlassian_doc(value: Any) -> str:
    """Best-effort plaintext extraction from Atlassian Document Format."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        out: list[str] = []
        for content in value.get("content") or []:
            for inner in content.get("content") or []:
                text = inner.get("text")
                if text:
                    out.append(text)
        return " ".join(out)
    return str(value)


@lru_cache(maxsize=1)
def get_jira_client() -> JiraClient:
    settings = get_settings()
    return JiraClient(
        base_url=settings.jira_base_url,
        email=settings.jira_email,
        api_token=settings.jira_api_token,
        project_key=settings.jira_project_key,
        bot_user=settings.mycelium_bot_jira_user,
    )
