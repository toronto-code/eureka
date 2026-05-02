"""Unified LLM client for the agent runtime.

Calls Claude (Anthropic) or GPT-4o (OpenAI) over raw HTTP using ``httpx``
(already a dependency). No new SDKs required.

Resolution order:
    1. ``ANTHROPIC_API_KEY`` set → Claude
    2. ``OPENAI_API_KEY`` set → GPT-4o
    3. Nothing set → deterministic stub response (so the local demo still
       works end-to-end without any API key configured)

All errors fail open: on network/5xx/parse errors the client returns a
stub response rather than raising, so a flaky LLM never takes down the
agent runtime.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_API_URL = os.getenv(
    "ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages"
)
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
CLAUDE_MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "1024"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_API_URL = os.getenv(
    "OPENAI_API_URL", "https://api.openai.com/v1/chat/completions"
)
OPENAI_MODEL = os.getenv("OPENAI_DEFAULT_MODEL", "gpt-4o")

LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30.0"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))


@dataclass
class LLMResponse:
    """Normalised LLM response shape."""

    text: str
    model: str
    provider: str  # "anthropic" | "openai" | "stub"
    stub: bool = False
    usage: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


# Backwards-compatible alias so existing ``from ...llm import ClaudeResponse``
# keeps working even though the client is multi-provider.
ClaudeResponse = LLMResponse


class LLMClient:
    """Multi-provider LLM client.

    ``provider`` can be explicitly forced to ``"anthropic"``, ``"openai"``,
    or ``"stub"``. When ``None`` (default) the client auto-selects based on
    which API key is configured.
    """

    def __init__(
        self,
        provider: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._timeout = timeout if timeout is not None else LLM_TIMEOUT

        if provider == "anthropic" or (provider is None and ANTHROPIC_API_KEY):
            self.provider = "anthropic"
            self.model = CLAUDE_MODEL
        elif provider == "openai" or (provider is None and OPENAI_API_KEY):
            self.provider = "openai"
            self.model = OPENAI_MODEL
        else:
            self.provider = "stub"
            self.model = "stub"

    @property
    def enabled(self) -> bool:
        """True when a real LLM is wired (not stub mode)."""
        return self.provider != "stub"

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Send a single-turn prompt and return the response text."""
        if self.provider == "anthropic":
            return await self._anthropic(prompt, system, max_tokens, temperature)
        if self.provider == "openai":
            return await self._openai(prompt, system, max_tokens, temperature)
        return self._stub(prompt)

    async def complete_json(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> tuple[dict[str, Any] | None, LLMResponse]:
        """Ask for a JSON object; parse it if possible.

        Returns ``(parsed_dict_or_None, raw_response)``. When the LLM is a
        stub or parsing fails, ``parsed_dict_or_None`` is None and the
        caller should fall back to heuristics.
        """
        system_json = (
            (system or "")
            + "\n\nRespond with valid JSON only. No prose, no code fences."
        ).strip()
        resp = await self.complete(
            prompt=prompt,
            system=system_json,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        parsed = _safe_parse_json(resp.text) if not resp.stub else None
        return parsed, resp

    # ---- providers ------------------------------------------------------

    async def _anthropic(
        self,
        prompt: str,
        system: str | None,
        max_tokens: int | None,
        temperature: float | None,
    ) -> LLMResponse:
        if not ANTHROPIC_API_KEY:
            return self._stub(prompt)

        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or CLAUDE_MAX_TOKENS,
            "temperature": (
                temperature if temperature is not None else LLM_TEMPERATURE
            ),
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(ANTHROPIC_API_URL, headers=headers, json=body)
            if r.status_code != 200:
                logger.warning(
                    "anthropic non-200: %s %s", r.status_code, r.text[:200]
                )
                return self._stub(prompt, error=f"anthropic {r.status_code}")
            data = r.json()
            text = "".join(
                block.get("text", "")
                for block in data.get("content", [])
                if block.get("type") == "text"
            )
            return LLMResponse(
                text=text,
                model=data.get("model", self.model),
                provider="anthropic",
                usage=data.get("usage", {}) or {},
            )
        except Exception as exc:
            logger.warning("anthropic request failed: %s", exc)
            return self._stub(prompt, error=str(exc))

    async def _openai(
        self,
        prompt: str,
        system: str | None,
        max_tokens: int | None,
        temperature: float | None,
    ) -> LLMResponse:
        if not OPENAI_API_KEY:
            return self._stub(prompt)

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "content-type": "application/json",
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": (
                temperature if temperature is not None else LLM_TEMPERATURE
            ),
        }
        if max_tokens:
            body["max_tokens"] = max_tokens

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(OPENAI_API_URL, headers=headers, json=body)
            if r.status_code != 200:
                logger.warning(
                    "openai non-200: %s %s", r.status_code, r.text[:200]
                )
                return self._stub(prompt, error=f"openai {r.status_code}")
            data = r.json()
            choices = data.get("choices") or []
            text = ""
            if choices:
                text = (choices[0].get("message") or {}).get("content", "")
            return LLMResponse(
                text=text,
                model=data.get("model", self.model),
                provider="openai",
                usage=data.get("usage", {}) or {},
            )
        except Exception as exc:
            logger.warning("openai request failed: %s", exc)
            return self._stub(prompt, error=str(exc))

    def _stub(self, prompt: str, error: str | None = None) -> LLMResponse:
        """Deterministic fallback when no LLM is configured or a call fails."""
        snippet = prompt[:200] + "..." if len(prompt) > 200 else prompt
        return LLMResponse(
            text=f"(stub) Response to: {snippet}",
            model="stub",
            provider="stub",
            stub=True,
            error=error,
        )


def _safe_parse_json(text: str) -> dict[str, Any] | None:
    """Best-effort JSON extraction from an LLM response.

    Tolerates code fences and leading/trailing prose by grabbing the first
    ``{...}`` balanced block.
    """
    if not text:
        return None
    stripped = text.strip()
    # Strip markdown fences if present.
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
    stripped = re.sub(r"\s*```$", "", stripped)
    try:
        obj = json.loads(stripped)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


# Backwards-compat alias — the package previously imported ``ClaudeClient``.
ClaudeClient = LLMClient
