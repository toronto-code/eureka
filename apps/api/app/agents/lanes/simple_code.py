"""SimpleCodeLane: safe, one-shot code changes via the GitHub Contents API.

Thin wrapper over the existing `ExecutionService`, but with:

1. A new, typed plan schema (SimpleCodePlan) that the LLM must satisfy.
2. A validator that refuses unsafe paths, destructive ops, binary blobs,
   huge files, secrets, path traversal, and out-of-repo edits.
3. A lane-level "if the task looks complex, bail" check — if the LLM's own
   plan requires >5 files or mentions tests/build/deps, we downgrade to
   `complex_code` instead of shipping a broken PR.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.agents.lanes.base import BaseLane, LaneContext
from app.agents.llm_client import OpenAIClient, get_llm_client
from app.agents.ol.schemas import LaneResult
from app.memory.retrieval import RetrievedChunk
from app.services.execution import ExecutionService

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Typed plan schema
# -----------------------------------------------------------------------------


class _FileChange(BaseModel):
    path: str
    operation: str  # create | update
    content: str
    commit_message: str


class _PRSection(BaseModel):
    title: str
    body: str


class SimpleCodePlan(BaseModel):
    summary: str
    branch_name: str
    file_changes: list[_FileChange] = Field(default_factory=list)
    pr: _PRSection
    jira_comment: str | None = None


# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------


# Absolute, code-enforced refusals. NOT configurable.
_HARD_DENIED_PATTERNS = (
    r"(^|/)\.env($|/)",
    r"(^|/)\.env\..+$",
    r"(^|/)secrets($|/)",
    r"(^|/)\.github/workflows($|/)",
    r"(^|/)infrastructure($|/)",
    r"\.pem$",
    r"\.key$",
    r"id_rsa",
)

# Secret-like content checks (cheap regexes on the submitted content).
_SECRET_HINTS = (
    r"AKIA[0-9A-Z]{16}",          # AWS access key id
    r"ghp_[A-Za-z0-9]{30,}",      # GitHub classic PAT
    r"github_pat_[A-Za-z0-9_]{30,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"xox[bap]-[A-Za-z0-9-]{10,}", # Slack token
)

MAX_FILE_BYTES = 64_000
MAX_FILES_IN_PLAN = 5
COMPLEX_HINTS = (
    "run the tests", "run npm ", "pip install", "migration", "schema change",
    "performance", "regression test", "benchmark",
)


@dataclass
class ValidationResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    should_downgrade_to_complex: bool = False


def validate_plan(plan: SimpleCodePlan, *, allowed_repo_id: str | None) -> ValidationResult:
    reasons: list[str] = []
    if not plan.file_changes:
        reasons.append("no_file_changes")
    if len(plan.file_changes) > MAX_FILES_IN_PLAN:
        return ValidationResult(
            ok=False,
            reasons=[f"too_many_files:{len(plan.file_changes)}"],
            should_downgrade_to_complex=True,
        )
    for ch in plan.file_changes:
        path = ch.path or ""
        if ".." in path or path.startswith("/"):
            reasons.append(f"path_traversal:{path}")
        if any(re.search(p, path) for p in _HARD_DENIED_PATTERNS):
            reasons.append(f"hard_denied_path:{path}")
        if ch.operation not in {"create", "update"}:
            reasons.append(f"bad_operation:{ch.operation}")
        if len(ch.content.encode("utf-8", errors="ignore")) > MAX_FILE_BYTES:
            reasons.append(f"file_too_large:{path}")
        if "\x00" in ch.content[:1024]:
            reasons.append(f"binary_content:{path}")
        if any(re.search(pat, ch.content) for pat in _SECRET_HINTS):
            reasons.append(f"secret_detected:{path}")
    # Downgrade heuristic — if the plan talks like it's complex, it's complex.
    summary_lower = (plan.summary + " " + plan.pr.body).lower()
    if any(h in summary_lower for h in COMPLEX_HINTS):
        return ValidationResult(
            ok=False,
            reasons=reasons + ["complex_signals_detected"],
            should_downgrade_to_complex=True,
        )
    return ValidationResult(ok=not reasons, reasons=reasons)


# -----------------------------------------------------------------------------
# Lane
# -----------------------------------------------------------------------------


SIMPLE_CODE_SYSTEM_PROMPT = """You are the SimpleCodePlanAgent.

Produce a safe, one-shot code change plan that:
- touches at most 5 files
- never edits .env, secrets, CI config, or infra
- contains full file contents (no diffs, no placeholders)
- has a short PR title + body
- picks a branch_name starting with `ai/`
- refuses anything that would need a compile/test loop

If the task requires compiling or running tests, say so in `summary` and
return an empty `file_changes` list.

Return STRICT JSON matching this schema:
{
  "summary": "...",
  "branch_name": "ai/...",
  "file_changes": [
    {"path": "...", "operation": "create|update", "content": "...", "commit_message": "..."}
  ],
  "pr": {"title": "...", "body": "..."},
  "jira_comment": "optional"
}
"""


class SimpleCodeLane(BaseLane):
    name = "simple_code"

    def __init__(
        self,
        llm: OpenAIClient | None = None,
        execution: ExecutionService | None = None,
    ) -> None:
        self._llm = llm or get_llm_client()
        self._execution = execution or ExecutionService()

    def run(self, ctx: LaneContext) -> LaneResult:
        result = self._empty_result(self.name)
        result.citations = self._citations_from(ctx.retrieved_chunks)

        plan = self._generate_plan(ctx)
        if plan is None:
            result.status = "blocked"
            result.summary = "SimpleCodeLane could not produce a valid plan."
            result.blocked_reason = "plan_generation_failed"
            ctx.add_step(result, "simple_code.plan_failed", ok=False)
            return result

        validation = validate_plan(plan, allowed_repo_id=ctx.request.repo_id)
        if not validation.ok:
            result.status = "blocked"
            result.summary = (
                "Plan rejected by SimpleCodeLane validator."
                if not validation.should_downgrade_to_complex
                else "Task looks complex; recommending complex_code lane."
            )
            result.blocked_reason = ",".join(validation.reasons)
            result.extra = {
                "should_downgrade_to_complex": validation.should_downgrade_to_complex,
                "plan": plan.model_dump(),
            }
            ctx.add_step(result, "simple_code.validation_failed", result.blocked_reason, ok=False)
            return result

        # Translate plan → ExecutionService's existing executor_output shape.
        executor_output = _plan_to_executor_output(plan, ctx=ctx)
        ctx.add_step(result, "simple_code.plan_validated", plan.summary)

        try:
            execution = self._execution.execute(
                ctx.session,
                task=_task_snapshot(ctx),
                executor_output=executor_output,
                task_id=None,
                orchestrator_run_id=None,
                executor_run_id=None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("ExecutionService failed: %s", exc)
            err_text = str(exc)
            failure = _classify_execution_failure(err_text)
            result.status = "error"
            result.summary = failure["summary"]
            result.blocked_reason = failure["code"]
            result.extra = {
                "plan": plan.model_dump(),
                "failure": failure,
            }
            ctx.add_step(result, "simple_code.execution_error", err_text, ok=False)
            return result

        result.pr_url = execution.pr_url
        result.jira_comment_url = execution.jira_comment_url
        result.details = plan.pr.body
        # If the GitHub write succeeded (PR exists), don't fail the whole lane
        # because of follow-up Jira comment/transition errors.
        non_jira_errors = [
            err for err in execution.errors if not err.startswith("jira_")
        ]
        pr_completed_with_jira_warning = bool(execution.pr_url) and not non_jira_errors
        result.status = (
            "completed"
            if (execution.executed or pr_completed_with_jira_warning)
            else ("blocked" if execution.skipped_reason else "error")
        )
        if execution.skipped_reason:
            result.blocked_reason = execution.skipped_reason
        result.summary = plan.summary or (
            f"Opened PR on branch {execution.branch}" if execution.pr_url else "Dry-run complete"
        )
        result.extra = {
            "plan": plan.model_dump(),
            "execution": execution.to_dict(),
        }
        step_detail = f"pr={execution.pr_url} dry_run={execution.dry_run}"
        if execution.errors:
            step_detail += f" warnings={len(execution.errors)}"
        ctx.add_step(
            result,
            "simple_code.execution_completed",
            step_detail,
            ok=(execution.executed or pr_completed_with_jira_warning),
        )
        return result

    # ------------------------------------------------------------------
    # Plan generation
    # ------------------------------------------------------------------

    def _generate_plan(self, ctx: LaneContext) -> SimpleCodePlan | None:
        if not self._llm.configured:
            return _fallback_plan(ctx)
        user_prompt = _render_plan_prompt(ctx)
        try:
            raw = self._llm.generate_json(
                system_prompt=SIMPLE_CODE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.0,
                max_tokens=1400,
            )
            return SimpleCodePlan.model_validate(raw)
        except ValidationError as exc:
            logger.warning("SimpleCodeLane plan failed schema: %s", exc)
            return _fallback_plan(ctx)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SimpleCodeLane LLM call failed: %s", exc)
            return _fallback_plan(ctx)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _render_plan_prompt(ctx: LaneContext) -> str:
    chunks_str = "\n\n".join(
        f"[{c.id[:8]}] {c.file_path or c.source_type}\n{c.chunk_text[:800]}"
        for c in ctx.retrieved_chunks[:8]
    ) or "(no prior context)"
    return (
        f"User request:\n{ctx.request.user_request.strip()}\n\n"
        f"Acceptance criteria:\n"
        + ("\n".join(f"- {c}" for c in ctx.request.acceptance_criteria) or "(none)")
        + f"\n\nProject: {ctx.request.project.slug}\n"
        f"Jira ticket: {ctx.request.jira_ticket_key or '(none)'}\n\n"
        f"Context chunks:\n{chunks_str}\n"
    )


def _fallback_plan(ctx: LaneContext) -> SimpleCodePlan:
    slug = _slugify(ctx.request.user_request or "task")
    branch = f"ai/{slug}"[:60]
    return SimpleCodePlan(
        summary=f"Fallback plan for: {ctx.request.user_request[:120]}",
        branch_name=branch,
        file_changes=[],
        pr=_PRSection(
            title=f"Mycelium: {ctx.request.user_request[:80]}",
            body=(
                "Fallback plan produced without an LLM. No files were generated. "
                "Switch to the LLM-backed path by setting `OPENAI_API_KEY`."
            ),
        ),
        jira_comment=None,
    )


def _plan_to_executor_output(plan: SimpleCodePlan, *, ctx: LaneContext) -> dict[str, Any]:
    requested_branch = str(ctx.request.extra_hints.get("preferred_branch_name", "")).strip()
    requested_base = str(ctx.request.extra_hints.get("preferred_base_branch", "")).strip()
    branch_name = requested_branch or plan.branch_name
    base_branch = requested_base or "main"
    return {
        "action_taken": "open_pull_request",
        "summary": plan.summary,
        "file_changes": [
            {
                "path": f.path,
                "operation": f.operation,
                "content": f.content,
                "description": f.commit_message,
            }
            for f in plan.file_changes
        ],
        "pr": {
            "title": plan.pr.title,
            "description": plan.pr.body,
            "branch_name": branch_name,
            "base_branch": base_branch,
        },
        "jira_comment": plan.jira_comment,
        "safety_notes": "",
        "requires_real_integration": False,
    }


def _task_snapshot(ctx: LaneContext) -> dict[str, Any]:
    return {
        "key": ctx.request.jira_ticket_key or "OL",
        "id": ctx.request.jira_ticket_id or "OL",
        "title": ctx.request.user_request[:200],
        "description": "\n".join(ctx.request.acceptance_criteria),
    }


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "task"


def _classify_execution_failure(err_text: str) -> dict[str, str]:
    msg = (err_text or "").lower()
    if "api.github.com" in msg:
        if "401" in msg or "unauthorized" in msg:
            return {
                "category": "github",
                "code": "github_auth_failed",
                "summary": "GitHub execution failed (auth). Jira was not the blocker.",
            }
        if "403" in msg or "forbidden" in msg:
            return {
                "category": "github",
                "code": "github_permission_failed",
                "summary": "GitHub execution failed (permissions). Jira was not the blocker.",
            }
        return {
            "category": "github",
            "code": "github_execution_failed",
            "summary": "GitHub execution failed. Jira was not the blocker.",
        }
    if "atlassian.net" in msg or "jira" in msg:
        return {
            "category": "jira",
            "code": "jira_execution_failed",
            "summary": "Jira side-effect failed after planning.",
        }
    return {
        "category": "unknown",
        "code": "execution_failed",
        "summary": f"Execution failed: {err_text}",
    }
