"""Auth middleware. Stub JWT with DEV_MODE bypass."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Header, HTTPException, status
from jose import JWTError, jwt

from mycelium_api.config import (
    DEV_USER_EMAIL,
    DEV_USER_ID,
    JWT_ALGORITHM,
    JWT_SECRET,
    is_dev_mode,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    role: str = "employee"


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    """FastAPI dependency. Returns the calling user.

    DEV_MODE: short-circuits to a fixed dev user.
    Otherwise: validates a Bearer JWT (HS256 by default).
    """
    if is_dev_mode():
        return CurrentUser(id=DEV_USER_ID, email=DEV_USER_EMAIL, role="employee")

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return CurrentUser(
        id=claims.get("sub", "unknown"),
        email=claims.get("email", "unknown"),
        role=claims.get("role", "employee"),
    )
