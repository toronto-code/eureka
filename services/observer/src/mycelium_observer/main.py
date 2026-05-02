"""Observer main loop.

Watches a set of local directories. On debounced filesystem activity inside a
``.git`` directory we emit an ``observer.git.update`` event. We never read
file contents — we only collect filenames via ``git diff --name-only``.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

import httpx
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from mycelium_observer.privacy import assert_no_contents, redact_event
from mycelium_shared_types import MyceliumEvent, MyceliumEventActor, MyceliumEventObject
from mycelium_shared_types.correlation import derive_correlation_id

logger = logging.getLogger("mycelium-observer")


def _watch_dirs() -> list[Path]:
    raw = os.getenv("OBSERVER_WATCH_DIRS", "").strip()
    if raw:
        return [Path(p).expanduser() for p in raw.split(",") if p.strip()]
    fallback = Path.home() / "dev"
    if fallback.exists():
        return [fallback]
    return []


class GitWatcher(FileSystemEventHandler):
    """Coalesces git filesystem activity into one event per repo every N seconds."""

    def __init__(self, *, debounce_seconds: float = 2.0) -> None:
        self._debounce = debounce_seconds
        self._pending: dict[Path, float] = {}
        self._lock = Lock()

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if ".git" not in path.parts:
            return
        repo = self._repo_for(path)
        if repo is None:
            return
        with self._lock:
            self._pending[repo] = time.time() + self._debounce

    def drain(self) -> list[Path]:
        now = time.time()
        out: list[Path] = []
        with self._lock:
            for repo, due in list(self._pending.items()):
                if due <= now:
                    out.append(repo)
                    self._pending.pop(repo, None)
        return out

    @staticmethod
    def _repo_for(path: Path) -> Path | None:
        for parent in path.parents:
            if (parent / ".git").exists():
                return parent
        return None


def _changed_filenames(repo: Path) -> list[str]:
    """``git diff --name-only`` — filenames only, never contents."""
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), "diff", "--name-only"],
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode("utf-8", errors="replace")
    except Exception:
        return []
    files = [line.strip() for line in out.splitlines() if line.strip()]
    assert_no_contents(files)
    return files[:200]  # cap, just in case


def _build_event(repo: Path, user_id: str) -> dict:
    object_id = str(repo)
    correlation_id = derive_correlation_id(source="observer", object_id=object_id)
    ev = MyceliumEvent(
        id=str(uuid.uuid4()),
        type="observer.git.update",
        source="observer",
        actor=MyceliumEventActor(id=user_id, type="user"),
        object=MyceliumEventObject(id=object_id, type="repo"),
        timestamp=datetime.now(timezone.utc),
        metadata={"repo_path": str(repo), "changed_files": _changed_filenames(repo)},
        correlation_id=correlation_id,
    )
    return redact_event(ev.model_dump(mode="json"))


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if os.getenv("DEV_MODE", "true").lower() == "true":
        logger.warning("Running in DEV_MODE — auth disabled")

    api_url = os.getenv("OBSERVER_API_URL", "http://localhost:8000")
    user_id = os.getenv("OBSERVER_USER_ID", "dev-user-1")
    watch_dirs = _watch_dirs()

    if not watch_dirs:
        logger.warning(
            "no OBSERVER_WATCH_DIRS configured and ~/dev not present; nothing to watch."
        )
        return

    handler = GitWatcher()
    obs = Observer()
    for d in watch_dirs:
        logger.info("watching %s", d)
        obs.schedule(handler, str(d), recursive=True)

    obs.start()
    logger.info("observer started; posting to %s", api_url)
    try:
        with httpx.Client(timeout=5) as client:
            while True:
                time.sleep(1)
                for repo in handler.drain():
                    payload = _build_event(repo, user_id)
                    try:
                        r = client.post(f"{api_url}/integrations/ingest", json=payload)
                        r.raise_for_status()
                        logger.info("posted observer.git.update repo=%s", repo)
                    except Exception as exc:
                        logger.warning("post failed: %s", exc)
    except KeyboardInterrupt:
        logger.info("stopping")
    finally:
        obs.stop()
        obs.join()


if __name__ == "__main__":
    run()
