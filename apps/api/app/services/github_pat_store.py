"""Load/save GitHub PAT encrypted in ``integration_credentials``."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.crypto_credentials import decrypt_secret, encrypt_secret, fernet_from_settings
from app.models.credentials import IntegrationCredential

GITHUB_INTEGRATION = "github"


def hint_for_token(token: str) -> str:
    t = token.strip()
    if len(t) <= 4:
        return "****"
    return f"…{t[-4:]}"


def load_github_pat(session: Session, settings: Settings | None = None) -> str | None:
    settings = settings or get_settings()
    fernet = fernet_from_settings(settings)
    if not fernet:
        return None
    row = session.scalar(
        select(IntegrationCredential).where(
            IntegrationCredential.integration == GITHUB_INTEGRATION,
        )
    )
    if row is None or not row.secret_ciphertext:
        return None
    return decrypt_secret(fernet, row.secret_ciphertext)


def github_pat_row(session: Session) -> IntegrationCredential | None:
    return session.scalar(
        select(IntegrationCredential).where(
            IntegrationCredential.integration == GITHUB_INTEGRATION,
        )
    )


def save_github_pat(session: Session, token: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    fernet = fernet_from_settings(settings)
    if not fernet:
        raise RuntimeError("MYCELIUM_CREDENTIALS_KEY is not configured")
    cleaned = token.strip()
    if not cleaned:
        raise ValueError("empty token")
    blob = encrypt_secret(fernet, cleaned)
    hint = hint_for_token(cleaned)
    row = github_pat_row(session)
    if row is None:
        row = IntegrationCredential(
            integration=GITHUB_INTEGRATION,
            status="configured",
            secret_ciphertext=blob,
            secret_hint=hint,
        )
        session.add(row)
    else:
        row.secret_ciphertext = blob
        row.secret_hint = hint
        row.status = "configured"
    session.flush()
    return hint


def clear_github_pat(session: Session) -> bool:
    row = github_pat_row(session)
    if row is None:
        return False
    row.secret_ciphertext = None
    row.secret_hint = None
    row.status = "not_configured"
    session.flush()
    return True


def github_pat_saved(session: Session) -> bool:
    row = github_pat_row(session)
    return bool(row and row.secret_ciphertext)
