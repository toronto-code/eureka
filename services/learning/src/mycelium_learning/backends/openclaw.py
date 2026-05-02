"""OpenClaw rl/genverse backend - delegates RL to external services.

This is a stub implementation ready for when API keys are available.
Falls back to the local backend for actual updates when keys aren't set.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from mycelium_learning.backends.base import UpdateResult
from mycelium_learning.backends.local import LocalBackend
from mycelium_learning.config import (
    OPENCLAW_RL_API_KEY,
    OPENCLAW_RL_API_URL,
    GENVERSE_API_KEY,
    GENVERSE_API_URL,
)

if TYPE_CHECKING:
    from mycelium_learning.models.base import BaseModel, ModelKind
    from mycelium_learning.signals.types import Signal

logger = logging.getLogger(__name__)


class OpenClawRLBackend:
    """OpenClaw rl/genverse backend.

    When API keys are configured, ships signals to OpenClaw RL for processing
    and genverse for interaction modeling. When keys are missing, falls back
    to the LocalBackend so the service stays functional.
    """

    def __init__(
        self,
        openclaw_api_key: str | None = None,
        openclaw_api_url: str | None = None,
        genverse_api_key: str | None = None,
        genverse_api_url: str | None = None,
    ) -> None:
        self._openclaw_key = openclaw_api_key or OPENCLAW_RL_API_KEY
        self._openclaw_url = openclaw_api_url or OPENCLAW_RL_API_URL
        self._genverse_key = genverse_api_key or GENVERSE_API_KEY
        self._genverse_url = genverse_api_url or GENVERSE_API_URL
        self._http_client: httpx.AsyncClient | None = None
        self._fallback = LocalBackend()

        if not self._openclaw_key and not self._genverse_key:
            logger.warning(
                "No OpenClaw/Genverse API keys configured. "
                "Using LocalBackend as fallback."
            )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30)
        return self._http_client

    async def close(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
        await self._fallback.close()

    async def _send_to_openclaw(self, signals: list[Signal]) -> dict | None:
        """Ship signals to OpenClaw RL for RL processing.

        Production: POST to {openclaw_url}/signals with auth header.
        For now: stubbed.
        """
        if not self._openclaw_key:
            return None

        logger.info(
            "Would send %d signals to OpenClaw RL (stub - key present)",
            len(signals),
        )
        return {"stub": True, "signals_sent": len(signals)}

    async def _send_to_genverse(self, signals: list[Signal]) -> dict | None:
        """Ship signals to genverse for interaction modeling.

        Production: POST to {genverse_url}/interactions with auth header.
        For now: stubbed.
        """
        if not self._genverse_key:
            return None

        logger.info(
            "Would send %d signals to Genverse (stub - key present)",
            len(signals),
        )
        return {"stub": True, "signals_sent": len(signals)}

    async def update(
        self,
        signals: list[Signal],
        models: dict[ModelKind, BaseModel],
    ) -> UpdateResult:
        """Process signals via OpenClaw/Genverse (or local fallback)."""
        openclaw_result = await self._send_to_openclaw(signals)
        genverse_result = await self._send_to_genverse(signals)

        local_result = await self._fallback.update(signals, models)

        local_result.metadata.update({
            "openclaw_sent": openclaw_result is not None,
            "genverse_sent": genverse_result is not None,
            "openclaw_key_configured": bool(self._openclaw_key),
            "genverse_key_configured": bool(self._genverse_key),
        })

        return local_result
