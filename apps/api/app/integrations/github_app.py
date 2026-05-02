"""GitHubAuthProvider: pluggable auth for GitHub API calls.

The spec requires a clean GitHub App abstraction without actually building
the full installation flow. We do that here:

- `GitHubAuthProvider` is the interface. `.token_for(repo)` returns a
  token string to use in the `Authorization: Bearer ...` header.
- `PatAuthProvider` implements it with the repo-global PAT from `.env`
  (the existing behaviour).
- `GitHubAppAuthProvider` is a placeholder that matches the interface
  shape real GitHub App installation tokens will fit into later. Today it
  raises if called — the switch-over happens when an installation_id is
  present on the `Repository` row AND a `GITHUB_APP_ID` + private key are
  configured.

This keeps `GitHubClient` / `ExecutionService` decoupled from the auth
mechanism.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache

from app.config import get_settings


@dataclass
class RepoRef:
    """Opaque reference passed to the auth provider for per-repo token derivation."""

    owner: str
    name: str
    installation_id: str | None = None


class GitHubAuthProvider(ABC):
    """Abstract provider. Implementations return a short-lived access token."""

    @abstractmethod
    def token_for(self, repo: RepoRef) -> str: ...

    @property
    @abstractmethod
    def is_real(self) -> bool: ...

    @property
    @abstractmethod
    def mode(self) -> str: ...


class PatAuthProvider(GitHubAuthProvider):
    """Personal Access Token / fine-grained PAT provider.

    One token, used for every repo. Good enough for a single-tenant setup
    or a bot account. Swap in `GitHubAppAuthProvider` when you need
    per-install tokens with short TTLs.
    """

    def __init__(self, token: str | None) -> None:
        self._token = token

    def token_for(self, repo: RepoRef) -> str:
        if not self._token:
            raise RuntimeError(
                "GitHub token not configured. Set GITHUB_TOKEN in .env."
            )
        return self._token

    @property
    def is_real(self) -> bool:
        return bool(self._token)

    @property
    def mode(self) -> str:
        return "pat"


class GitHubAppAuthProvider(GitHubAuthProvider):
    """Placeholder for GitHub App installation tokens.

    When wired up:
    1. Sign a JWT with `GITHUB_APP_ID` + private key.
    2. Call `POST /app/installations/{installation_id}/access_tokens`.
    3. Cache the resulting token until its `expires_at`.

    Today this raises; callers should feature-flag it.
    """

    def __init__(
        self, *, app_id: str | None, private_key_pem: str | None
    ) -> None:
        self._app_id = app_id
        self._private_key_pem = private_key_pem

    def token_for(self, repo: RepoRef) -> str:  # pragma: no cover - placeholder
        raise NotImplementedError(
            "GitHub App auth is not wired yet. Use PatAuthProvider until "
            "an installation flow exists."
        )

    @property
    def is_real(self) -> bool:
        return bool(self._app_id and self._private_key_pem)

    @property
    def mode(self) -> str:
        return "github_app"


@lru_cache(maxsize=1)
def get_github_auth_provider() -> GitHubAuthProvider:
    """Pick the right provider based on current settings.

    Preference order:
    1. GitHubAppAuthProvider — if app id + private key are present.
    2. PatAuthProvider — the existing PAT-based path.
    """
    settings = get_settings()
    # Placeholder values — we intentionally don't introduce new config fields
    # until the App flow is actually wired.
    return PatAuthProvider(token=settings.github_token)
