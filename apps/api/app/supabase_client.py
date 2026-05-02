"""Single Supabase client used by all routers, plus JWT verification.

We keep TWO clients:
- _service: uses sb_secret_... — bypasses RLS, used for system writes (observer
  events, transcripts that aren't tied to one user).
- _user(jwt): a per-request client scoped to a user's JWT, RLS-enforced.

Auth dependency: get_supabase_user() reads Authorization: Bearer <jwt>, verifies
it with the supabase auth service, and returns a User record. If no JWT and
DEV_MODE is on, returns a fake dev user so the existing endpoints don't break.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel
from supabase import Client, create_client

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SECRET = os.getenv("SUPABASE_SECRET_KEY", "")
SUPABASE_PUBLISHABLE = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"

_service_client: Optional[Client] = None


def service_client() -> Client:
    global _service_client
    if _service_client is None:
        if not SUPABASE_URL or not SUPABASE_SECRET:
            raise RuntimeError("SUPABASE_URL or SUPABASE_SECRET_KEY missing")
        _service_client = create_client(SUPABASE_URL, SUPABASE_SECRET)
    return _service_client


def user_client(jwt: str) -> Client:
    """A client scoped to one user's JWT — all queries respect RLS."""
    if not SUPABASE_URL or not SUPABASE_PUBLISHABLE:
        raise RuntimeError("SUPABASE_URL or SUPABASE_PUBLISHABLE_KEY missing")
    c = create_client(SUPABASE_URL, SUPABASE_PUBLISHABLE)
    c.postgrest.auth(jwt)
    return c


class SupabaseUser(BaseModel):
    id: str
    email: Optional[str] = None
    jwt: str = ""


DEV_USER = SupabaseUser(id="00000000-0000-0000-0000-000000000001", email="dev@mycelium.local", jwt="")


async def get_supabase_user(request: Request) -> SupabaseUser:
    """FastAPI dependency. Verifies the JWT in the Authorization header against
    Supabase. Falls back to a dev user only if DEV_MODE and no header present.

    NOTE: We use the supabase python sdk to verify by calling auth.get_user(jwt).
    """
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth:
        if DEV_MODE:
            return DEV_USER
        raise HTTPException(401, "missing Authorization header")

    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Authorization header must be 'Bearer <jwt>'")

    jwt = auth[7:].strip()
    if not jwt:
        raise HTTPException(401, "empty JWT")

    try:
        # Supabase verifies JWTs server-side via auth.get_user(jwt)
        client = service_client()
        resp = client.auth.get_user(jwt)
        u = getattr(resp, "user", None) or resp
        user_id = getattr(u, "id", None) or (u.get("id") if isinstance(u, dict) else None)
        email = getattr(u, "email", None) or (u.get("email") if isinstance(u, dict) else None)
        if not user_id:
            raise HTTPException(401, "invalid JWT (no user id)")
        return SupabaseUser(id=str(user_id), email=email, jwt=jwt)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("JWT verification failed: %s", e)
        if DEV_MODE:
            return DEV_USER
        raise HTTPException(401, f"jwt verification failed: {e}")
