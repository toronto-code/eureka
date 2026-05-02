"""Session processor — compress a raw web-recorder session into a
markdown summary + structured metadata that downstream agents can actually
use as context.

Design goals:
    - Purely deterministic / heuristic. No LLM calls on the ingest path
      (keeps the feature free and instant; LLM-based distillation can be
      layered on later).
    - Produces a human-readable markdown document that chunks well for
      the existing vector / lexical search backends.
    - Extracts a small set of high-signal workflow patterns (task
      creation, ingestion, orchestration) so retrieval can surface them
      by name.
    - Drops repetitive / low-signal events (e.g. consecutive visibility
      toggles, duplicate clicks) so the summary stays short.

The shape of `raw_payload` matches `SessionIngestPayload` in
`apps/web/components/SessionRecorder.tsx`. Keep them in sync.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class Workflow:
    name: str
    description: str
    started_at: str
    ended_at: str
    step_count: int


@dataclass
class ProcessedSession:
    title: str
    description: str
    summary_markdown: str
    duration_seconds: int
    event_count: int
    pages_visited: list[str]
    workflows: list[Workflow] = field(default_factory=list)
    insights: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class SessionProcessor:
    """Turn a raw web-recorder payload into agent-friendly context."""

    def parse_payload(self, raw: str) -> dict[str, Any]:
        """Parse the JSON string stored on `raw_text` for web sessions.

        Raises ValueError with a caller-friendly message on failure.
        """
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"web session payload was not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("web session payload must be a JSON object")
        if "events" not in data or not isinstance(data["events"], list):
            raise ValueError("web session payload is missing an 'events' list")
        return data

    def process(self, payload: dict[str, Any]) -> ProcessedSession:
        events: list[dict[str, Any]] = payload.get("events", [])
        title = payload.get("title") or "Untitled web session"
        description = payload.get("description") or ""
        duration = int(payload.get("duration_seconds") or 0)
        pages = list(payload.get("pages_visited") or [])

        cleaned = _dedupe_events(events)
        workflows = _detect_workflows(cleaned)
        insights = _build_insights(cleaned, duration, pages)
        summary_md = _build_summary(
            title=title,
            description=description,
            duration_seconds=duration,
            pages=pages,
            events=cleaned,
            workflows=workflows,
            insights=insights,
        )
        return ProcessedSession(
            title=title,
            description=description,
            summary_markdown=summary_md,
            duration_seconds=duration,
            event_count=len(events),
            pages_visited=pages,
            workflows=workflows,
            insights=insights,
        )


# ---------------------------------------------------------------------------
# Compression + deduping
# ---------------------------------------------------------------------------


def _dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse consecutive identical events and drop low-signal ones.

    Rules:
      - Consecutive events with the same `type` + target.selector + target.text
        are merged, with a ``repeat_count`` field on the survivor.
      - Visibility events that don't change state are dropped.
      - Navigation events that don't change path are dropped.
    """
    out: list[dict[str, Any]] = []
    last_vis: bool | None = None
    last_path: str | None = None

    for ev in events:
        etype = ev.get("type")
        target = ev.get("target") or {}
        if etype == "web.visibility":
            hidden = bool((ev.get("metadata") or {}).get("hidden"))
            if hidden == last_vis:
                continue
            last_vis = hidden
        if etype == "web.navigation":
            new_path = target.get("selector") or ev.get("page_path")
            if new_path == last_path:
                continue
            last_path = new_path
        if out:
            prev = out[-1]
            if (
                prev.get("type") == etype
                and (prev.get("target") or {}).get("selector")
                == target.get("selector")
                and (prev.get("target") or {}).get("text")
                == target.get("text")
            ):
                prev["repeat_count"] = int(prev.get("repeat_count", 1)) + 1
                prev["timestamp"] = ev.get("timestamp", prev.get("timestamp"))
                continue
        out.append(dict(ev))
    return out


# ---------------------------------------------------------------------------
# Workflow detection (simple, intentional heuristics)
# ---------------------------------------------------------------------------


_WORKFLOW_RULES: list[dict[str, Any]] = [
    {
        "name": "Task creation",
        "path_prefixes": ("/tasks",),
        "requires_submit": True,
        "description": "Opened the tasks page and submitted a form (likely created a task).",
    },
    {
        "name": "Document ingestion",
        "path_prefixes": ("/ingestion",),
        "requires_submit": True,
        "description": "Visited the ingestion page and submitted a form (likely uploaded a doc or transcript).",
    },
    {
        "name": "Orchestrator run",
        "path_prefixes": ("/ol", "/orchestration"),
        "click_text_any": ("run", "orchestrate", "execute"),
        "description": "Ran the orchestrator or started an agent task.",
    },
    {
        "name": "Team web review",
        "path_prefixes": ("/team",),
        "description": "Explored the team graph / collaboration view.",
    },
    {
        "name": "Settings configuration",
        "path_prefixes": ("/settings",),
        "description": "Reviewed or changed integration/agent settings.",
    },
    {
        "name": "Observability review",
        "path_prefixes": ("/observability",),
        "description": "Reviewed observability dashboards or agent activity.",
    },
]


def _detect_workflows(events: list[dict[str, Any]]) -> list[Workflow]:
    found: list[Workflow] = []
    for rule in _WORKFLOW_RULES:
        matches = [
            ev for ev in events
            if _matches_path(ev, rule.get("path_prefixes", ()))
        ]
        if not matches:
            continue
        if rule.get("requires_submit") and not any(
            ev.get("type") == "web.form.submit" for ev in matches
        ):
            continue
        click_terms = rule.get("click_text_any")
        if click_terms and not any(
            _click_matches(ev, click_terms) for ev in matches
        ):
            continue
        found.append(
            Workflow(
                name=rule["name"],
                description=rule["description"],
                started_at=matches[0].get("timestamp", ""),
                ended_at=matches[-1].get("timestamp", ""),
                step_count=len(matches),
            )
        )
    return found


def _matches_path(ev: dict[str, Any], prefixes: tuple[str, ...]) -> bool:
    if not prefixes:
        return True
    path = ev.get("page_path") or ""
    return any(path.startswith(p) for p in prefixes)


def _click_matches(ev: dict[str, Any], terms: tuple[str, ...]) -> bool:
    if ev.get("type") != "web.click":
        return False
    text = ((ev.get("target") or {}).get("text") or "").lower()
    return any(t in text for t in terms)


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------


def _build_insights(
    events: list[dict[str, Any]],
    duration_seconds: int,
    pages: list[str],
) -> dict[str, Any]:
    page_counter: Counter[str] = Counter()
    type_counter: Counter[str] = Counter()
    click_texts: Counter[str] = Counter()

    for ev in events:
        path = ev.get("page_path") or ""
        if path:
            page_counter[path] += 1
        type_counter[ev.get("type") or "unknown"] += 1
        if ev.get("type") == "web.click":
            text = ((ev.get("target") or {}).get("text") or "").strip()
            if text:
                click_texts[text[:60]] += 1

    return {
        "duration_seconds": duration_seconds,
        "pages_visited": pages,
        "most_visited_pages": page_counter.most_common(5),
        "event_type_counts": dict(type_counter),
        "top_clicks": click_texts.most_common(8),
    }


# ---------------------------------------------------------------------------
# Markdown summary — what the agent will actually read
# ---------------------------------------------------------------------------


def _build_summary(
    *,
    title: str,
    description: str,
    duration_seconds: int,
    pages: list[str],
    events: list[dict[str, Any]],
    workflows: list[Workflow],
    insights: dict[str, Any],
) -> str:
    lines: list[str] = [f"# {title}", ""]

    if description:
        lines.append(description.strip())
        lines.append("")

    lines.append("## Session overview")
    lines.append(f"- Duration: {_fmt_duration(duration_seconds)}")
    lines.append(f"- Events captured: {len(events)}")
    lines.append(f"- Pages visited: {len(pages)}")
    if pages:
        lines.append("- Page list: " + ", ".join(f"`{p}`" for p in pages))
    lines.append("")

    if workflows:
        lines.append("## Detected workflows")
        for wf in workflows:
            lines.append(f"- **{wf.name}** — {wf.description} ({wf.step_count} steps)")
        lines.append("")

    top_clicks = insights.get("top_clicks") or []
    if top_clicks:
        lines.append("## Most clicked actions")
        for label, n in top_clicks:
            lines.append(f"- {label} ({n}×)")
        lines.append("")

    most_pages = insights.get("most_visited_pages") or []
    if most_pages:
        lines.append("## Most active pages")
        for path, n in most_pages:
            lines.append(f"- `{path}` ({n} events)")
        lines.append("")

    lines.append("## Timeline")
    current_path: str | None = None
    for ev in events:
        path = ev.get("page_path") or ""
        if path != current_path:
            lines.append("")
            lines.append(f"### `{path}`")
            current_path = path
        lines.append(f"- {_render_event(ev)}")

    lines.append("")
    return "\n".join(lines)


def _render_event(ev: dict[str, Any]) -> str:
    ts = _fmt_time(ev.get("timestamp"))
    etype = ev.get("type", "unknown")
    target = ev.get("target") or {}
    repeat = int(ev.get("repeat_count") or 1)
    suffix = f" ×{repeat}" if repeat > 1 else ""

    if etype == "web.navigation":
        return f"{ts} — navigated to `{target.get('selector') or ev.get('page_path')}`{suffix}"
    if etype == "web.click":
        label = target.get("text") or target.get("selector") or target.get("tag") or "element"
        return f"{ts} — clicked **{label}**{suffix}"
    if etype == "web.form.submit":
        fc = (ev.get("metadata") or {}).get("field_count", 0)
        return f"{ts} — submitted form ({fc} fields){suffix}"
    if etype == "web.input.change":
        label = target.get("name") or target.get("tag") or "field"
        return f"{ts} — changed field `{label}`{suffix}"
    if etype == "web.visibility":
        hidden = (ev.get("metadata") or {}).get("hidden")
        return f"{ts} — tab {'hidden' if hidden else 'visible'}{suffix}"
    return f"{ts} — {etype}{suffix}"


def _fmt_time(ts: Any) -> str:
    if not ts:
        return "--:--:--"
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.strftime("%H:%M:%S")
    except Exception:  # noqa: BLE001
        return str(ts)[:8]


def _fmt_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    rem = seconds % 60
    return f"{minutes}m {rem:02d}s"
