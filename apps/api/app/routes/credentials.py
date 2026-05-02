"""Encrypted credential storage (GitHub PAT) — UI-backed, never returned in full."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto_credentials import fernet_from_settings
from app.db import get_db
from app.services.github_pat_store import (
    clear_github_pat,
    github_pat_row,
    github_pat_saved,
    save_github_pat,
)

router = APIRouter(tags=["credentials"])


class GitHubPatIn(BaseModel):
    token: str = Field(min_length=1)


class GitHubPatStatusOut(BaseModel):
    saved: bool
    secret_hint: str | None = None


class GitHubPatSavedOut(BaseModel):
    status: str = "stored"
    secret_hint: str


def _verify_setup_token(
    x_mycelium_setup_token: Annotated[str | None, Header(alias="X-Mycelium-Setup-Token")] = None,
) -> None:
    settings = get_settings()
    expected = (settings.mycelium_setup_token or "").strip()
    if not expected:
        return
    if not x_mycelium_setup_token or x_mycelium_setup_token.strip() != expected:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid X-Mycelium-Setup-Token header.",
        )


@router.get("/settings/credentials/github-pat", response_model=GitHubPatStatusOut)
def github_pat_status(
    session: Session = Depends(get_db),
) -> GitHubPatStatusOut:
    settings = get_settings()
    if not fernet_from_settings(settings):
        return GitHubPatStatusOut(saved=False, secret_hint=None)
    row_saved = github_pat_saved(session)
    row = github_pat_row(session)
    hint = row.secret_hint if row else None
    return GitHubPatStatusOut(saved=row_saved, secret_hint=hint if row_saved else None)


@router.post("/settings/credentials/github-pat", response_model=GitHubPatSavedOut)
def github_pat_save(
    body: GitHubPatIn,
    session: Session = Depends(get_db),
    _: None = Depends(_verify_setup_token),
) -> GitHubPatSavedOut:
    settings = get_settings()
    if not fernet_from_settings(settings):
        raise HTTPException(
            status_code=503,
            detail="Set MYCELIUM_CREDENTIALS_KEY in the API environment to enable encrypted PAT storage.",
        )
    try:
        hint = save_github_pat(session, body.token, settings=settings)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return GitHubPatSavedOut(secret_hint=hint)


@router.delete("/settings/credentials/github-pat")
def github_pat_delete(
    session: Session = Depends(get_db),
    _: None = Depends(_verify_setup_token),
) -> dict[str, str]:
    clear_github_pat(session)
    session.commit()
    return {"status": "cleared"}
