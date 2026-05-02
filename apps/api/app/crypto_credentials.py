"""Symmetric encryption for credentials stored in Postgres (Fernet)."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings


def fernet_from_settings(settings: Settings) -> Fernet | None:
    raw = settings.mycelium_credentials_key
    if not raw or not raw.strip():
        return None
    try:
        return Fernet(raw.strip().encode("ascii"))
    except Exception:  # noqa: BLE001 — bad key format
        return None


def encrypt_secret(fernet: Fernet, plaintext: str) -> bytes:
    return fernet.encrypt(plaintext.encode("utf-8"))


def decrypt_secret(fernet: Fernet, ciphertext: bytes) -> str | None:
    try:
        return fernet.decrypt(ciphertext).decode("utf-8")
    except InvalidToken:
        return None
