"""Centralised configuration loaded from environment variables.

Secrets are NEVER hardcoded; everything comes from `.env` (see `.env.example`).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    Read from environment variables. A `.env` file at the repo root is loaded
    automatically when present.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- App ----
    app_name: str = "Mycelium API"
    environment: Literal["local", "staging", "production"] = "local"
    log_level: str = "INFO"
    dev_mode: bool = True

    # ---- Database ----
    postgres_dsn: str = Field(
        default="postgresql+psycopg://mycelium:mycelium@postgres:5432/mycelium",
        description="SQLAlchemy DSN. Falls back to local docker-compose default.",
    )

    # ---- OpenAI ----
    openai_api_key: str | None = None
    openai_default_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_temperature: float = 0.2

    # ---- Jira (optional, falls back to seeded fake tasks) ----
    jira_base_url: str | None = None
    jira_email: str | None = None
    jira_api_token: str | None = None
    jira_project_key: str | None = None

    # ---- GitHub (optional, falls back to seeded fake repo) ----
    github_token: str | None = None
    github_owner: str | None = None
    # Legacy / docker-compose.legacy env; used when github_owner is unset.
    github_org: str | None = None
    github_repo: str | None = None
    github_default_base_branch: str = "main"
    # Comma-separated list of glob-style allowed write paths. Empty = allow all
    # (still gated by the "never merge / never delete" rules enforced in code).
    github_allowed_write_paths: str = ""

    # ---- Mycelium bot identity / auto-execute ----
    # When a Jira task's assignee matches this value (display name OR email OR
    # accountId), the orchestrator treats the assignment itself as the human
    # approval and executes the plan end-to-end (branch -> file edits -> PR ->
    # Jira comment). Leave unset to disable autonomous execution.
    mycelium_bot_jira_user: str | None = None
    mycelium_bot_name: str = "Mycelium Bot"
    # Global kill-switch. Set to False to force "draft only" mode even when a
    # bot-assigned task is detected.
    mycelium_auto_execute: bool = True
    # Extra safety: refuse to run against a real GitHub repo unless this is set.
    # When False (default), execution writes to the seeded fake repo only.
    mycelium_allow_real_github: bool = False

    # ---- Jira watcher (polls Jira for newly-assigned tasks) ----
    jira_watcher_enabled: bool = False
    jira_watcher_interval_seconds: int = 60
    # Optional JQL fragment to narrow the watcher query. E.g.
    #   "status in ('To Do','In Progress') AND updated >= -7d"
    jira_watcher_extra_jql: str | None = None

    # ---- Webhook signing secrets (production path) ----
    github_webhook_secret: str | None = None
    # Jira Cloud webhooks aren't HMAC-signed by default. If you front the
    # webhook with a shared-secret header, put it here.
    jira_webhook_shared_secret: str | None = None

    # ---- Dev-mode polling sync (used when webhooks can't reach us) ----
    sync_polling_enabled: bool = False
    sync_polling_interval_seconds: int = 120

    # ---- Frontend / CORS ----
    frontend_origin: str = "http://localhost:3000"

    # ---- Demo / seed ----
    enable_demo_seed: bool = True

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def jira_configured(self) -> bool:
        return bool(self.jira_base_url and self.jira_email and self.jira_api_token)

    @property
    def effective_github_owner(self) -> str | None:
        return self.github_owner or self.github_org

    @property
    def github_configured(self) -> bool:
        return bool(self.github_token and self.effective_github_owner and self.github_repo)

    @property
    def bot_auto_execute_enabled(self) -> bool:
        """True iff Mycelium is allowed to autonomously execute bot-assigned tasks."""
        return bool(self.mycelium_auto_execute and self.mycelium_bot_jira_user)

    @property
    def allowed_write_paths(self) -> list[str]:
        raw = self.github_allowed_write_paths or ""
        return [p.strip() for p in raw.split(",") if p.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor. Always call this instead of constructing Settings()."""
    return Settings()
