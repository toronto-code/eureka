"""Centralised OpenAI client wrapper.

- Reads OPENAI_API_KEY from environment via app settings.
- Defaults to gpt-4o but accepts per-call model overrides.
- Provides `generate_json` and `generate_text` with light retries.
- Logs failures safely (without exposing secrets).
- When OPENAI_API_KEY is missing, falls back to a deterministic mock so the
  local demo still works end-to-end.
"""
from __future__ import annotations

import json
import logging
import os
import time
from functools import lru_cache
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


class LLMUnavailableError(RuntimeError):
    """Raised when the LLM is configured but call retries all fail."""


class OpenAIClient:
    """Thin wrapper around `openai>=1` with sensible defaults and retries."""

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "gpt-4o",
        embedding_model: str = "text-embedding-3-small",
        temperature: float = 0.2,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.embedding_model = embedding_model
        self.temperature = temperature
        self.max_retries = max_retries
        self._client: Any | None = None
        if api_key:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=api_key)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to initialise OpenAI client: %s", exc)
                self._client = None

    # ---- public API ----------------------------------------------------

    @property
    def configured(self) -> bool:
        return self._client is not None

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        fallback: str | None = None,
    ) -> str:
        """Return free-form text from the LLM."""
        if not self.configured:
            return fallback if fallback is not None else self._mock_text(system_prompt, user_prompt)
        return self._call_with_retries(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=None,
        )

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        schema_hint: dict[str, Any] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        fallback: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a JSON object from the LLM.

        `schema_hint` is appended to the system prompt as documentation. We rely
        on `response_format={"type": "json_object"}` to force valid JSON.
        """
        if not self.configured:
            return fallback if fallback is not None else {}

        full_system = system_prompt
        if schema_hint:
            schema_text = json.dumps(schema_hint, indent=2)
            full_system = (
                f"{system_prompt}\n\nReturn ONLY a JSON object matching this schema:\n{schema_text}"
            )

        text = self._call_with_retries(
            system_prompt=full_system,
            user_prompt=user_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("LLM returned non-JSON output: %s", exc)
            return fallback if fallback is not None else {}

    def generate_embedding(self, text: str) -> list[float]:
        """Return an embedding vector or `[]` when not configured."""
        if not self.configured or not text:
            return []
        try:
            resp = self._client.embeddings.create(model=self.embedding_model, input=text)
            return list(resp.data[0].embedding)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Embedding call failed: %s", exc)
            return []

    # ---- internals -----------------------------------------------------

    def _call_with_retries(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
        response_format: dict[str, str] | None,
    ) -> str:
        last_error: Exception | None = None
        chosen_model = model or self.default_model
        chosen_temp = self.temperature if temperature is None else temperature
        chosen_max = 900 if max_tokens is None else max_tokens
        for attempt in range(self.max_retries + 1):
            try:
                kwargs: dict[str, Any] = {
                    "model": chosen_model,
                    "temperature": chosen_temp,
                    "max_tokens": chosen_max,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                }
                if response_format:
                    kwargs["response_format"] = response_format
                resp = self._client.chat.completions.create(**kwargs)
                return resp.choices[0].message.content or ""
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                # Never log the API key. openai SDK exceptions are safe by default.
                logger.warning(
                    "OpenAI call failed (attempt %s/%s): %s",
                    attempt + 1,
                    self.max_retries + 1,
                    type(exc).__name__,
                )
                time.sleep(min(2**attempt, 4))
        raise LLMUnavailableError(str(last_error) if last_error else "OpenAI call failed")

    @staticmethod
    def _mock_text(system_prompt: str, user_prompt: str) -> str:
        return (
            "[mock LLM] OPENAI_API_KEY is not set. Returning placeholder text. "
            "Set OPENAI_API_KEY in .env to enable real GPT-4o responses."
        )


@lru_cache(maxsize=1)
def get_llm_client() -> OpenAIClient:
    """Process-wide cached client built from settings."""
    settings = get_settings()
    # Allow OPENAI_API_KEY to come either from settings or directly from env.
    api_key = settings.openai_api_key or os.environ.get("OPENAI_API_KEY")
    return OpenAIClient(
        api_key=api_key,
        default_model=settings.openai_default_model,
        embedding_model=settings.openai_embedding_model,
        temperature=settings.openai_temperature,
    )
