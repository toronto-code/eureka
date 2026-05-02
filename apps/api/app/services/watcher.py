"""Jira watcher: poll Jira for bot-assigned tasks and run the orchestrator.

- Can be triggered manually via `POST /agents/watch`.
- Can run as an asyncio background task when
  `JIRA_WATCHER_ENABLED=true` via `start_watcher_task`.
- Each Jira issue produces at most one orchestrator run per
  `updated_at` timestamp so the bot doesn't re-process the same ticket every
  tick. Tracking is done in memory (per-process).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.integrations.jira import get_jira_client
from app.models import AgentRun, Task
from app.schemas.project_data import JiraTaskData, ProjectData
from app.seed import build_demo_project_data
from app.services.orchestration import OrchestrationService

logger = logging.getLogger(__name__)


@dataclass
class WatcherRunResult:
    picked_up: int
    ran: int
    skipped: int
    details: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "picked_up": self.picked_up,
            "ran": self.ran,
            "skipped": self.skipped,
            "details": self.details,
        }


class JiraWatcher:
    """Polls Jira for bot-assigned issues and kicks off orchestration."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._seen_keys: set[str] = set()

    # -----------------------------------------------------------------
    # Public
    # -----------------------------------------------------------------

    def run_once(self, session: Session) -> WatcherRunResult:
        bot_user = self._settings.mycelium_bot_jira_user
        if not bot_user:
            return WatcherRunResult(
                picked_up=0,
                ran=0,
                skipped=0,
                details=[
                    {"info": "MYCELIUM_BOT_JIRA_USER is not set; watcher is a no-op."}
                ],
            )

        jira = get_jira_client()
        try:
            issues = jira.fetch_issues(
                assignee=bot_user,
                extra_jql=self._settings.jira_watcher_extra_jql,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Watcher: jira.fetch_issues failed: %s", exc)
            issues = []

        if not issues and not jira.configured:
            # Seed-mode: include the bot-assigned task from fixtures so the
            # demo can exercise the full flow without any real Jira.
            issues = [
                i
                for i in jira.fetch_issues(assignee=bot_user)
                if jira.is_assigned_to_bot(i)
            ]

        picked = 0
        ran = 0
        skipped = 0
        details: list[dict[str, Any]] = []

        for issue in issues:
            key = issue.get("key") or issue.get("id")
            if not key:
                continue
            if not jira.is_assigned_to_bot(issue):
                continue
            picked += 1
            if key in self._seen_keys or self.previously_processed(session, key):
                skipped += 1
                self._seen_keys.add(key)
                details.append({"task": key, "status": "already_processed"})
                continue

            task_row = self._upsert_task(session, issue)
            project_data = self._build_project_data_for_issue(issue)
            result = OrchestrationService().run(
                session, project_data, task_id=task_row.id
            )
            ran += 1
            self._seen_keys.add(key)
            details.append(
                {
                    "task": key,
                    "task_id": task_row.id,
                    "orchestrator_run_id": result["orchestrator_run_id"],
                    "auto_executed": result.get("auto_executed", False),
                    "pr_url": (result.get("execution") or {}).get("pr_url"),
                    "dry_run": (result.get("execution") or {}).get("dry_run", True),
                }
            )

        return WatcherRunResult(
            picked_up=picked, ran=ran, skipped=skipped, details=details
        )

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _upsert_task(session: Session, issue: dict[str, Any]) -> Task:
        key = issue.get("key") or issue.get("id")
        existing = session.execute(
            select(Task).where(Task.external_id == key)
        ).scalar_one_or_none()
        if existing is not None:
            # Update fields that might have changed.
            existing.title = issue.get("title") or existing.title
            existing.description = issue.get("description") or existing.description
            existing.status = issue.get("status") or existing.status
            existing.assignee = issue.get("assignee") or existing.assignee
            existing.labels = issue.get("labels") or existing.labels
            existing.priority = issue.get("priority") or existing.priority
            existing.raw_payload = issue
            session.flush()
            return existing
        task = Task(
            external_id=key,
            source="jira",
            project_key=issue.get("project_key"),
            title=issue.get("title") or "Untitled task",
            description=issue.get("description"),
            status=issue.get("status") or "To Do",
            assignee=issue.get("assignee"),
            reporter=issue.get("reporter"),
            labels=issue.get("labels") or [],
            priority=issue.get("priority"),
            raw_payload=issue,
        )
        session.add(task)
        session.flush()
        return task

    @staticmethod
    def _build_project_data_for_issue(issue: dict[str, Any]) -> ProjectData:
        project_data = build_demo_project_data()
        project_data.current_task = JiraTaskData(
            id=issue.get("id"),
            key=issue.get("key"),
            title=issue.get("title") or "",
            description=issue.get("description"),
            status=issue.get("status"),
            assignee=issue.get("assignee"),
            reporter=issue.get("reporter"),
            labels=issue.get("labels") or [],
            priority=issue.get("priority"),
            project_key=issue.get("project_key"),
        )
        project_data.user_goal = (
            f"Autonomously complete Jira task {issue.get('key')}: {issue.get('title')}"
        )
        return project_data

    def previously_processed(self, session: Session, key: str) -> bool:
        """Check DB for an existing orchestrator run for this task key."""
        task = session.execute(
            select(Task).where(Task.external_id == key)
        ).scalar_one_or_none()
        if task is None:
            return False
        run = session.execute(
            select(AgentRun)
            .where(AgentRun.task_id == task.id, AgentRun.agent_type == "orchestrator")
            .limit(1)
        ).scalar_one_or_none()
        return run is not None


# ---------------------------------------------------------------------------
# Background task glue
# ---------------------------------------------------------------------------


_watcher_task: asyncio.Task[None] | None = None


async def _watcher_loop(interval_seconds: int) -> None:
    watcher = JiraWatcher()
    while True:
        try:
            with SessionLocal() as session:
                result = watcher.run_once(session)
                session.commit()
                if result.ran:
                    logger.info(
                        "JiraWatcher: ran %d orchestration(s), skipped %d, picked up %d",
                        result.ran,
                        result.skipped,
                        result.picked_up,
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("JiraWatcher tick failed: %s", exc)
        await asyncio.sleep(interval_seconds)


def start_watcher_task() -> None:
    """Start the background watcher if enabled + not already running."""
    global _watcher_task
    settings = get_settings()
    if not settings.jira_watcher_enabled:
        return
    if _watcher_task and not _watcher_task.done():
        return
    loop = asyncio.get_event_loop()
    _watcher_task = loop.create_task(
        _watcher_loop(settings.jira_watcher_interval_seconds)
    )


def stop_watcher_task() -> None:
    global _watcher_task
    if _watcher_task and not _watcher_task.done():
        _watcher_task.cancel()
    _watcher_task = None
