"""HTTP client for the learning service.

Queries learned preferences, skill recommendations, and pattern insights so
the agent-runtime can adapt behavior based on past signals.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

LEARNING_URL = os.getenv("LEARNING_URL", "http://learning:8004")
LEARNING_TIMEOUT = float(os.getenv("LEARNING_TIMEOUT", "2.0"))
LEARNING_ENABLED = os.getenv("LEARNING_ENABLED", "true").lower() in ("1", "true", "yes")


class LearningClient:
    """Thin HTTP wrapper around the learning service.

    All calls fail open: if the learning service is unreachable, methods
    return neutral/empty values so the agent-runtime keeps working.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._base_url = (base_url or LEARNING_URL).rstrip("/")
        self._timeout = timeout if timeout is not None else LEARNING_TIMEOUT
        self._enabled = enabled if enabled is not None else LEARNING_ENABLED

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def get_user_action_preference(
        self, user_id: str, action_type: str
    ) -> dict[str, Any]:
        """Fetch learned preference for a (user, action_type).

        Returns a dict with keys: suggestion, approval_rate, decision_count,
        confidence. On error returns {"suggestion": "insufficient_data"}.
        """
        if not self._enabled:
            return {"suggestion": "insufficient_data", "confidence": 0.0}

        url = f"{self._base_url}/preferences/users/{user_id}/actions/{action_type}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    return r.json()
                logger.debug("learning preferences %s → %d", url, r.status_code)
        except Exception as exc:
            logger.debug("learning unreachable: %s", exc)

        return {"suggestion": "insufficient_data", "confidence": 0.0}

    async def get_global_action_preference(self, action_type: str) -> dict[str, Any]:
        """Fetch global (org-wide) preference for an action type."""
        if not self._enabled:
            return {"suggestion": "insufficient_data", "confidence": 0.0}

        url = f"{self._base_url}/preferences/global/actions/{action_type}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    return r.json()
        except Exception as exc:
            logger.debug("learning unreachable: %s", exc)

        return {"suggestion": "insufficient_data", "confidence": 0.0}

    async def get_effective_preference(
        self, user_id: str | None, action_type: str
    ) -> dict[str, Any]:
        """Get the best available preference, preferring user > global.

        Returns the first source that has enough data; falls back to global,
        then to insufficient_data.
        """
        if user_id:
            user_pref = await self.get_user_action_preference(user_id, action_type)
            if user_pref.get("suggestion") != "insufficient_data":
                user_pref["source"] = "user"
                return user_pref

        global_pref = await self.get_global_action_preference(action_type)
        global_pref["source"] = "global"
        return global_pref

    async def health(self) -> bool:
        """Check whether the learning service is reachable."""
        if not self._enabled:
            return False
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.get(f"{self._base_url}/health")
                return r.status_code == 200
        except Exception:
            return False
