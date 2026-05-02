"""Local user-data persistence outside Docker volumes.

Stores lightweight OL run snapshots under an OS-specific app-data directory:
- macOS:   ~/Library/Application Support/Mycelium
- Windows: %APPDATA%\\Mycelium
- Linux:   ~/.local/share/Mycelium
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _app_support_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        appdata = os.getenv("APPDATA")
        base = Path(appdata) if appdata else (Path.home() / "AppData" / "Roaming")
    else:
        base = Path.home() / ".local" / "share"
    return base / "Mycelium"


def _runs_dir() -> Path:
    path = _app_support_dir() / "orchestrator-runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _chat_dir() -> Path:
    path = _app_support_dir() / "orchestrator-chat"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_orchestrator_run_snapshot(
    run_data: dict[str, Any],
    *,
    project_slug: str | None = None,
) -> None:
    run_id = str(run_data.get("id") or "").strip()
    if not run_id:
        return
    payload = dict(run_data)
    if project_slug:
        payload["project_slug"] = project_slug
    out = _runs_dir() / f"{run_id}.json"
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp.replace(out)


def get_orchestrator_run_snapshot(run_id: str) -> dict[str, Any] | None:
    path = _runs_dir() / f"{run_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_orchestrator_run_snapshots(
    *,
    project_id: str,
    project_slug: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in _runs_dir().glob("*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        row_project_id = str(row.get("project_id") or "")
        row_project_slug = str(row.get("project_slug") or "")
        if row_project_id == project_id or (project_slug and row_project_slug == project_slug):
            out.append(row)
    out.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return out[:limit]


def _chat_key(project_id: str, project_slug: str | None = None) -> str:
    if (project_slug or "").strip():
        return f"slug-{project_slug.strip().lower()}"
    return f"id-{project_id.strip().lower()}"


def _chat_file(project_id: str, project_slug: str | None = None) -> Path:
    return _chat_dir() / f"{_chat_key(project_id, project_slug)}.json"


def load_orchestrator_chat_history(
    project_id: str,
    *,
    project_slug: str | None = None,
) -> list[dict[str, Any]]:
    candidates = [
        _chat_file(project_id, project_slug),
        _chat_file(project_id, None),
    ]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def append_orchestrator_chat_message(
    project_id: str,
    message: dict[str, Any],
    *,
    project_slug: str | None = None,
    max_items: int = 300,
) -> None:
    if not isinstance(message, dict):
        return
    row = {
        "role": str(message.get("role") or ""),
        "text": str(message.get("text") or ""),
        "ts": int(message.get("ts") or 0),
        "status": message.get("status"),
        "runId": message.get("runId"),
        "route": message.get("route"),
        "risk": message.get("risk"),
        "laneStatus": message.get("laneStatus"),
        "reasoning": message.get("reasoning"),
        "prUrl": message.get("prUrl"),
        "jiraCommentUrl": message.get("jiraCommentUrl"),
        "blockedReason": message.get("blockedReason"),
        "error": message.get("error"),
    }
    path = _chat_file(project_id, project_slug)
    items = load_orchestrator_chat_history(project_id, project_slug=project_slug)
    items.append(row)
    items = items[-max_items:]
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp.replace(path)


def get_orchestrator_chat_history_file_info(
    project_id: str,
    *,
    project_slug: str | None = None,
) -> dict[str, Any]:
    path = _chat_file(project_id, project_slug)
    data = load_orchestrator_chat_history(project_id, project_slug=project_slug)
    return {
        "path": str(path),
        "exists": path.exists(),
        "messages_count": len(data),
        "messages": data,
    }
