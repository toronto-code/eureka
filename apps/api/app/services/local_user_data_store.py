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
