"""BlockedLane + HumanReviewLane.

Both produce a structured escalation summary. They never touch GitHub/Jira.
`HumanReviewLane` is a slight variation for the `needs_human_review` route
so the UI can distinguish "blocked on input" from "escalated due to risk".
"""
from __future__ import annotations

from app.agents.lanes.base import BaseLane, LaneContext
from app.agents.ol.schemas import LaneResult


class BlockedLane(BaseLane):
    name = "blocked"

    def run(self, ctx: LaneContext) -> LaneResult:
        result = self._empty_result(self.name)
        result.summary = ctx.classification.reasoning_summary or "Task is blocked."
        missing = _detect_missing(ctx)
        bullets = [f"- {m}" for m in missing] if missing else ["- (no specific blockers identified)"]
        result.details = "\n".join(
            [
                f"**Why blocked:** {result.summary}",
                "",
                "**What's needed to proceed:**",
                *bullets,
            ]
        )
        result.blocked_reason = ",".join(missing) or "unknown_blocker"
        result.status = "blocked"
        ctx.add_step(result, "blocked.summarised", f"{len(missing)} missing items")
        return result


class HumanReviewLane(BaseLane):
    name = "needs_human_review"

    def run(self, ctx: LaneContext) -> LaneResult:
        result = self._empty_result(self.name)
        result.citations = self._citations_from(ctx.retrieved_chunks)
        result.summary = (
            ctx.classification.reasoning_summary
            or "Escalating to human review."
        )
        risk = ctx.classification.risk_level
        result.details = "\n".join(
            [
                "## Needs human review",
                "",
                f"**Reason:** {result.summary}",
                f"**Risk:** {risk}",
                "",
                "**Recommended next step:** have a reviewer triage the request. "
                "Mycelium will not take autonomous action here.",
            ]
        )
        result.blocked_reason = f"risk_{risk}"
        result.status = "blocked"
        ctx.add_step(result, "review.escalated", f"risk={risk}")
        return result


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


_MISSING_HINTS = (
    ("credentials", "set GITHUB_TOKEN or GITHUB_APP_ID in env"),
    ("access", "grant repo access to the bot"),
    ("secrets", "cannot proceed without access to the relevant secret"),
    ("unclear", "clarify the acceptance criteria"),
    ("ambiguous", "clarify the acceptance criteria"),
    ("not configured", "configure the missing integration in settings"),
)


def _detect_missing(ctx: LaneContext) -> list[str]:
    text = (
        ctx.classification.reasoning_summary + " " + ctx.request.user_request
    ).lower()
    out: list[str] = []
    for hint, guidance in _MISSING_HINTS:
        if hint in text:
            out.append(guidance)
    return out
