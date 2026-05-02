"""ExecutionService: turn an ExecutorAgent plan into real GitHub + Jira writes.

Called by the orchestrator when a Jira task is assigned to the Mycelium bot
(assignment == approval). Every side-effect is recorded as an `ExecutedAction`
row AND an `AuditLog` row so operators can trace what happened.

Safety guarantees enforced in code (not config):
- Never merges PRs.
- Never deletes files or branches.
- Never writes to the default branch directly.
- Respects the configured allow-list of write paths (if any).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.github import GitHubClient, get_github_client
from app.integrations.jira import JiraClient, get_jira_client
from app.models import AuditLog, ExecutedAction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result shapes
# ---------------------------------------------------------------------------


@dataclass
class ExecutionResult:
    """Outcome of one end-to-end execution run."""

    executed: bool = False
    dry_run: bool = True
    branch: str | None = None
    base_branch: str | None = None
    pr_url: str | None = None
    pr_number: int | None = None
    jira_comment_url: str | None = None
    jira_transition: str | None = None
    file_changes: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "executed": self.executed,
            "dry_run": self.dry_run,
            "branch": self.branch,
            "base_branch": self.base_branch,
            "pr_url": self.pr_url,
            "pr_number": self.pr_number,
            "jira_comment_url": self.jira_comment_url,
            "jira_transition": self.jira_transition,
            "file_changes": self.file_changes,
            "errors": self.errors,
            "skipped_reason": self.skipped_reason,
        }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


# Paths that can never be written, regardless of config.
_HARD_BLOCKED_PATTERNS = (
    r"(^|/)\.env($|/)",
    r"(^|/)\.env\.",
    r"(^|/)secrets($|/)",
    r"(^|/)\.github/workflows($|/)",
    r"(^|/)infrastructure($|/)",
)


def _is_hard_blocked(path: str) -> bool:
    return any(re.search(p, path) for p in _HARD_BLOCKED_PATTERNS)


class ExecutionService:
    """Turns an executor plan into real GitHub/Jira side-effects."""

    def __init__(
        self,
        github: GitHubClient | None = None,
        jira: JiraClient | None = None,
    ) -> None:
        self.github = github or get_github_client()
        self.jira = jira or get_jira_client()
        self._settings = get_settings()

    # -----------------------------------------------------------------
    # Public entrypoint
    # -----------------------------------------------------------------

    def execute(
        self,
        session: Session,
        *,
        task: dict[str, Any],
        executor_output: dict[str, Any],
        task_id: str | None,
        orchestrator_run_id: str | None,
        executor_run_id: str | None,
    ) -> ExecutionResult:
        """Perform the plan. Writes ExecutedAction + AuditLog rows for each step."""
        result = ExecutionResult()

        pr_plan = executor_output.get("pr") or {}
        file_changes = executor_output.get("file_changes") or []

        if not file_changes:
            result.skipped_reason = (
                "ExecutorAgent returned no file_changes; nothing to commit."
            )
            self._write_audit(
                session,
                task_id=task_id,
                agent_run_id=orchestrator_run_id,
                action_type="execution_skipped",
                summary=result.skipped_reason,
            )
            return result

        base_branch = pr_plan.get("base_branch") or self._settings.github_default_base_branch
        branch_name = pr_plan.get("branch_name") or self._default_branch_name(task)

        # Safety: never write directly to the default branch.
        if branch_name == base_branch:
            branch_name = f"mycelium/{branch_name}"

        result.base_branch = base_branch
        result.branch = branch_name

        # -- 1. Create branch ------------------------------------------
        branch_res = self.github.create_branch(branch_name, base_branch=base_branch)
        self._record(
            session,
            task_id=task_id,
            agent_run_id=executor_run_id,
            integration="github",
            action_type="create_branch",
            summary=f"Created branch {branch_name} from {base_branch}",
            target_url=branch_res.get("html_url"),
            payload=branch_res,
            error=branch_res.get("error"),
        )
        if branch_res.get("error"):
            result.errors.append(f"create_branch: {branch_res['error']}")
            return result

        # -- 2. Commit each file change --------------------------------
        overall_dry_run = bool(branch_res.get("dry_run", True))
        committed_files: list[dict[str, Any]] = []
        for change in file_changes:
            path = change.get("path") or ""
            content = change.get("content") or ""
            operation = change.get("operation") or "create"
            description = change.get("description") or ""

            if _is_hard_blocked(path):
                committed_files.append(
                    {
                        "path": path,
                        "operation": operation,
                        "safety_blocked": True,
                        "reason": "Path is on the hard-blocked list.",
                    }
                )
                self._record(
                    session,
                    task_id=task_id,
                    agent_run_id=executor_run_id,
                    integration="github",
                    action_type="file_blocked",
                    summary=f"Refused to {operation} {path} (hard-blocked).",
                    target_url=None,
                    payload=change,
                    error="Path on hard-blocked list.",
                )
                continue

            commit_message = f"Mycelium: {description or operation + ' ' + path}"
            file_res = self.github.create_or_update_file(
                path=path,
                content=content,
                branch=branch_name,
                commit_message=commit_message,
            )
            committed_files.append(
                {
                    "path": path,
                    "operation": operation,
                    "description": description,
                    "commit_sha": file_res.get("commit_sha"),
                    "html_url": file_res.get("html_url"),
                    "dry_run": file_res.get("dry_run", True),
                    "safety_blocked": file_res.get("safety_blocked", False),
                }
            )
            overall_dry_run = overall_dry_run and bool(file_res.get("dry_run", True))
            self._record(
                session,
                task_id=task_id,
                agent_run_id=executor_run_id,
                integration="github",
                action_type="create_file" if operation == "create" else "update_file",
                summary=commit_message,
                target_url=file_res.get("html_url"),
                payload=file_res,
                error=file_res.get("error"),
            )
            if file_res.get("error"):
                result.errors.append(f"{path}: {file_res['error']}")
        result.file_changes = committed_files

        # -- 3. Open PR ------------------------------------------------
        pr_title = pr_plan.get("title") or f"Mycelium: {task.get('title') or 'change'}"
        pr_body = self._augment_pr_body(
            pr_plan.get("description") or "",
            task=task,
            orchestrator_run_id=orchestrator_run_id,
        )
        pr_res = self.github.open_pull_request(
            title=pr_title,
            body=pr_body,
            head_branch=branch_name,
            base_branch=base_branch,
        )
        result.pr_url = pr_res.get("html_url")
        result.pr_number = pr_res.get("number")
        overall_dry_run = overall_dry_run and bool(pr_res.get("dry_run", True))
        self._record(
            session,
            task_id=task_id,
            agent_run_id=executor_run_id,
            integration="github",
            action_type="open_pr",
            summary=f"Opened PR: {pr_title}",
            target_url=pr_res.get("html_url"),
            payload=pr_res,
            error=pr_res.get("error"),
        )
        if pr_res.get("error"):
            result.errors.append(f"open_pr: {pr_res['error']}")

        # -- 4. Post Jira comment -------------------------------------
        issue_key = task.get("key") or task.get("id")
        jira_comment_template = executor_output.get("jira_comment") or ""
        jira_comment_body = jira_comment_template.replace(
            "{PR_URL}", result.pr_url or "(PR URL unavailable)"
        )
        if issue_key and jira_comment_body:
            jira_res = self.jira.post_comment(issue_key, jira_comment_body)
            result.jira_comment_url = jira_res.get("html_url")
            overall_dry_run = overall_dry_run and bool(jira_res.get("dry_run", True))
            self._record(
                session,
                task_id=task_id,
                agent_run_id=executor_run_id,
                integration="jira",
                action_type="post_comment",
                summary=f"Posted Jira comment on {issue_key}",
                target_url=jira_res.get("html_url"),
                payload=jira_res,
                error=jira_res.get("error"),
            )
            if jira_res.get("error"):
                result.errors.append(f"jira_comment: {jira_res['error']}")

            # -- 5. Move ticket to In Review / In Progress ------------
            transition_target = "In Review"
            trans_res = self.jira.transition_issue(
                issue_key, transition_name=transition_target
            )
            if trans_res.get("error"):
                # Fall back to "In Progress".
                trans_res = self.jira.transition_issue(
                    issue_key, transition_name="In Progress"
                )
                transition_target = "In Progress"
            result.jira_transition = transition_target
            self._record(
                session,
                task_id=task_id,
                agent_run_id=executor_run_id,
                integration="jira",
                action_type="transition",
                summary=f"Moved {issue_key} to {transition_target}",
                target_url=None,
                payload=trans_res,
                error=trans_res.get("error"),
            )

        result.executed = not result.errors
        result.dry_run = overall_dry_run
        return result

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _default_branch_name(task: dict[str, Any]) -> str:
        key = task.get("key") or task.get("id") or "task"
        title = task.get("title") or "change"
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")[:40] or "change"
        return f"mycelium/{key}-{slug}"

    def _augment_pr_body(
        self,
        body: str,
        *,
        task: dict[str, Any],
        orchestrator_run_id: str | None,
    ) -> str:
        signature = (
            "\n\n---\n"
            "_Opened automatically by **Mycelium** — review carefully before merging._\n"
        )
        if orchestrator_run_id:
            signature += f"_Orchestrator run: `{orchestrator_run_id}`_\n"
        key = task.get("key") or task.get("id")
        if key and self.jira.base_url:
            signature += f"_Jira: {self.jira.base_url}/browse/{key}_\n"
        elif key:
            signature += f"_Jira: {key}_\n"
        return (body or "") + signature

    def _record(
        self,
        session: Session,
        *,
        task_id: str | None,
        agent_run_id: str | None,
        integration: str,
        action_type: str,
        summary: str,
        target_url: str | None,
        payload: dict[str, Any],
        error: str | None,
    ) -> None:
        status = "failed" if error else "succeeded"
        dry_run = bool(payload.get("dry_run", False))
        session.add(
            ExecutedAction(
                task_id=task_id,
                agent_run_id=agent_run_id,
                integration=integration,
                action_type=action_type,
                status=status,
                dry_run=dry_run,
                summary=summary,
                target_url=target_url,
                payload=_scrub(payload),
                error_message=error,
            )
        )
        self._write_audit(
            session,
            task_id=task_id,
            agent_run_id=agent_run_id,
            action_type=f"{integration}.{action_type}",
            summary=summary,
            error=error,
        )

    def _write_audit(
        self,
        session: Session,
        *,
        task_id: str | None,
        agent_run_id: str | None,
        action_type: str,
        summary: str,
        error: str | None = None,
    ) -> None:
        session.add(
            AuditLog(
                actor="ExecutionService",
                actor_type="agent",
                task_id=task_id,
                agent_run_id=agent_run_id,
                action_type=action_type,
                risk_level="HIGH_RISK_WRITE",
                approval_status="APPROVED",
                input_summary=summary,
                output_summary=error or "ok",
                sources_used=[],
                payload={},
            )
        )


def _scrub(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop obviously-large content fields before persisting to avoid bloat."""
    out: dict[str, Any] = {}
    for key, value in (payload or {}).items():
        if key in {"content", "content_preview"} and isinstance(value, str):
            out[key] = value[:500]
        elif key == "body" and isinstance(value, str):
            out[key] = value[:500]
        else:
            out[key] = value
    return out
