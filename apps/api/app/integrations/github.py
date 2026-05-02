"""GitHub integration.

Two modes:
- **Real mode**: `GITHUB_TOKEN` + `GITHUB_OWNER` + `GITHUB_REPO` set (and
  `MYCELIUM_ALLOW_REAL_GITHUB=true`). Calls hit the real GitHub REST API.
- **Dry-run mode**: credentials missing or safety flag off. The client returns
  plausible fake responses so the demo and tests work end to end. Every call
  sets `"dry_run": True` in the returned dict so the ExecutionService can tell
  downstream whether a real side-effect happened.

Safety rules enforced in code (never overridable by config):
- Never merges a PR.
- Never force-pushes.
- Never deletes a file or branch.
- PRs always target a non-default branch on the head side.
- If a caller passes a path outside the configured allow-list, the write is
  refused and a `safety_blocked` result is returned.
"""
from __future__ import annotations

import base64
import fnmatch
import logging
from typing import Any

import httpx

from app.config import get_settings
from app.integrations._fakes import fake_repo

logger = logging.getLogger(__name__)


class GitHubClient:
    """GitHub REST client with dry-run fallback + safety rails."""

    def __init__(
        self,
        token: str | None,
        owner: str | None,
        repo: str | None,
        default_base_branch: str = "main",
        allowed_write_paths: list[str] | None = None,
        allow_real: bool = False,
    ) -> None:
        self.token = token
        self.owner = owner
        self.repo = repo
        self.default_base_branch = default_base_branch
        self.allowed_write_paths = allowed_write_paths or []
        self.allow_real = allow_real

    # ---------------------------------------------------------------
    # Mode helpers
    # ---------------------------------------------------------------

    @property
    def configured(self) -> bool:
        return bool(self.token and self.owner and self.repo)

    @property
    def real_mode(self) -> bool:
        """True iff we're allowed AND able to hit the real GitHub API."""
        return self.configured and self.allow_real

    def _repo_base(self) -> str:
        return f"/repos/{self.owner}/{self.repo}"

    def _is_path_allowed(self, path: str) -> bool:
        if not self.allowed_write_paths:
            return True
        return any(fnmatch.fnmatch(path, pattern) for pattern in self.allowed_write_paths)

    # ---------------------------------------------------------------
    # Read APIs
    # ---------------------------------------------------------------

    def fetch_repo_metadata(self) -> dict[str, Any]:
        if not self.real_mode:
            meta = {k: v for k, v in fake_repo().items() if k != "files"}
            meta["dry_run"] = True
            return meta
        try:
            data = self._get(self._repo_base())
            return {
                "owner": (data.get("owner") or {}).get("login"),
                "name": data.get("name"),
                "description": data.get("description"),
                "primary_language": data.get("language"),
                "default_branch": data.get("default_branch", self.default_base_branch),
                "html_url": data.get("html_url"),
                "dry_run": False,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("GitHub repo metadata failed: %s", exc)
            meta = {k: v for k, v in fake_repo().items() if k != "files"}
            meta["dry_run"] = True
            return meta

    def fetch_files(self, paths: list[str] | None = None) -> list[dict[str, Any]]:
        if not self.real_mode:
            files = fake_repo()["files"]
            if paths:
                files = [f for f in files if f["path"] in paths]
            return files
        if not paths:
            return []
        out: list[dict[str, Any]] = []
        for path in paths:
            try:
                data = self._get(f"{self._repo_base()}/contents/{path}")
                content = ""
                if data.get("encoding") == "base64" and data.get("content"):
                    content = base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
                out.append(
                    {
                        "path": path,
                        "language": _language_for(path),
                        "content": content,
                        "summary": "",
                        "metadata": {"sha": data.get("sha")},
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("GitHub fetch_file failed for %s: %s", path, exc)
        return out

    def get_file_sha(self, path: str, branch: str) -> str | None:
        """Return the existing blob SHA for `path` on `branch`, or None if absent."""
        if not self.real_mode:
            return None
        try:
            data = self._get(f"{self._repo_base()}/contents/{path}", params={"ref": branch})
            if isinstance(data, dict):
                return data.get("sha")
            return None
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("GitHub get_file_sha failed for %s: %s", path, exc)
            return None

    def get_authenticated_user(self) -> dict[str, Any]:
        """Return `{login, html_url, dry_run}` for whoever the token belongs to."""
        if not self.real_mode:
            return {
                "login": "mycelium-bot[dry-run]",
                "html_url": "https://github.com/mycelium-bot",
                "dry_run": True,
            }
        try:
            data = self._get("/user")
            return {
                "login": data.get("login"),
                "html_url": data.get("html_url"),
                "dry_run": False,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("GitHub get_authenticated_user failed: %s", exc)
            return {"login": "unknown", "html_url": None, "dry_run": True}

    # ---------------------------------------------------------------
    # Write APIs (autonomous execution path)
    # ---------------------------------------------------------------

    def create_branch(
        self, branch_name: str, base_branch: str | None = None
    ) -> dict[str, Any]:
        base = base_branch or self.default_base_branch
        if not self.real_mode:
            return {
                "ref": f"refs/heads/{branch_name}",
                "branch": branch_name,
                "base_branch": base,
                "html_url": self._fake_branch_url(branch_name),
                "dry_run": True,
            }
        try:
            ref_data = self._get(f"{self._repo_base()}/git/ref/heads/{base}")
            base_sha = (ref_data.get("object") or {}).get("sha")
            if not base_sha:
                raise RuntimeError(f"Could not resolve base branch sha for {base}")
            data = self._post(
                f"{self._repo_base()}/git/refs",
                json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
            )
            return {
                "ref": data.get("ref"),
                "branch": branch_name,
                "base_branch": base,
                "html_url": f"https://github.com/{self.owner}/{self.repo}/tree/{branch_name}",
                "dry_run": False,
            }
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 422:
                # Branch already exists; treat as idempotent success.
                return {
                    "ref": f"refs/heads/{branch_name}",
                    "branch": branch_name,
                    "base_branch": base,
                    "html_url": f"https://github.com/{self.owner}/{self.repo}/tree/{branch_name}",
                    "dry_run": False,
                    "already_existed": True,
                }
            raise

    def create_or_update_file(
        self,
        *,
        path: str,
        content: str,
        branch: str,
        commit_message: str,
    ) -> dict[str, Any]:
        if not self._is_path_allowed(path):
            return {
                "path": path,
                "branch": branch,
                "safety_blocked": True,
                "reason": (
                    f"Path '{path}' is outside the configured allow-list "
                    f"({self.allowed_write_paths})."
                ),
                "dry_run": True,
            }
        if not self.real_mode:
            return {
                "path": path,
                "branch": branch,
                "commit_message": commit_message,
                "content_preview": content[:200],
                "html_url": self._fake_file_url(path, branch),
                "dry_run": True,
            }
        try:
            existing_sha = self.get_file_sha(path, branch)
            body: dict[str, Any] = {
                "message": commit_message,
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "branch": branch,
            }
            if existing_sha:
                body["sha"] = existing_sha
            data = self._put(f"{self._repo_base()}/contents/{path}", json=body)
            return {
                "path": path,
                "branch": branch,
                "commit_message": commit_message,
                "commit_sha": (data.get("commit") or {}).get("sha"),
                "html_url": (data.get("content") or {}).get("html_url"),
                "updated": bool(existing_sha),
                "dry_run": False,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("GitHub create_or_update_file failed for %s: %s", path, exc)
            return {
                "path": path,
                "branch": branch,
                "error": str(exc),
                "dry_run": True,
            }

    def open_pull_request(
        self,
        *,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str | None = None,
        draft: bool = False,
    ) -> dict[str, Any]:
        base = base_branch or self.default_base_branch
        if head_branch == base:
            return {
                "safety_blocked": True,
                "reason": "Refusing to open a PR whose head equals the base branch.",
                "dry_run": True,
            }
        if not self.real_mode:
            return {
                "number": 0,
                "title": title,
                "body": body,
                "head": head_branch,
                "base": base,
                "html_url": self._fake_pr_url(head_branch),
                "dry_run": True,
            }
        try:
            data = self._post(
                f"{self._repo_base()}/pulls",
                json={
                    "title": title,
                    "body": body,
                    "head": head_branch,
                    "base": base,
                    "draft": draft,
                },
            )
            return {
                "number": data.get("number"),
                "title": data.get("title"),
                "body": data.get("body"),
                "head": head_branch,
                "base": base,
                "html_url": data.get("html_url"),
                "dry_run": False,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("GitHub open_pull_request failed: %s", exc)
            return {
                "head": head_branch,
                "base": base,
                "error": str(exc),
                "dry_run": True,
            }

    # ---------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        with httpx.Client(timeout=15.0, base_url="https://api.github.com") as client:
            resp = client.get(path, params=params, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def _post(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=20.0, base_url="https://api.github.com") as client:
            resp = client.post(path, json=json, headers=self._headers())
            resp.raise_for_status()
            return resp.json() if resp.content else {}

    def _put(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=20.0, base_url="https://api.github.com") as client:
            resp = client.put(path, json=json, headers=self._headers())
            resp.raise_for_status()
            return resp.json() if resp.content else {}

    # ---- dry-run URL fakes (used for demo) ----

    def _fake_branch_url(self, branch: str) -> str:
        owner = self.owner or "mycelium-demo"
        repo = self.repo or "payments-service"
        return f"https://github.com/{owner}/{repo}/tree/{branch}"

    def _fake_file_url(self, path: str, branch: str) -> str:
        owner = self.owner or "mycelium-demo"
        repo = self.repo or "payments-service"
        return f"https://github.com/{owner}/{repo}/blob/{branch}/{path}"

    def _fake_pr_url(self, branch: str) -> str:
        owner = self.owner or "mycelium-demo"
        repo = self.repo or "payments-service"
        return f"https://github.com/{owner}/{repo}/pull/new/{branch}"


def _language_for(path: str) -> str:
    if path.endswith(".py"):
        return "python"
    if path.endswith((".ts", ".tsx")):
        return "typescript"
    if path.endswith(".md"):
        return "markdown"
    if path.endswith(".sql"):
        return "sql"
    return "text"


def get_github_client() -> GitHubClient:
    from app.integrations.github_token import resolve_github_token

    settings = get_settings()
    return GitHubClient(
        token=resolve_github_token(),
        owner=settings.effective_github_owner,
        repo=settings.github_repo,
        default_base_branch=settings.github_default_base_branch,
        allowed_write_paths=settings.allowed_write_paths,
        allow_real=settings.mycelium_allow_real_github,
    )
