"""Filter + redaction primitives."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)


class SensitivityLevel(IntEnum):
    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3


@dataclass
class QueryContext:
    """Who is asking, with which clearance."""

    user_id: str
    role: str = "employee"
    clearance: SensitivityLevel = SensitivityLevel.INTERNAL
    via_agent: bool = False
    """True when an agent is querying on behalf of a user."""


@dataclass
class SecurityDecision:
    allowed: list[dict[str, Any]] = field(default_factory=list)
    redacted: list[dict[str, Any]] = field(default_factory=list)
    blocked: list[dict[str, Any]] = field(default_factory=list)


# Patterns. Real implementation should pull these from a shared policy store.
_REDACT_PATTERNS = [
    re.compile(r"(?i)(api[-_]?key|secret|token|password)\s*[:=]\s*\S+"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"\b[\w.-]+@[\w-]+\.[\w.-]+\b"),  # email — sometimes redacted
]


class SecurityFilter:
    """Filter result rows according to a Pebblo-style policy.

    DEV_MODE behavior: if ``SECURITY_ENFORCEMENT_ENABLED`` is unset or false,
    the filter is a permissive identity. It still emits redactions for obvious
    secrets so dashboards don't accidentally leak in screenshots.
    """

    def __init__(
        self,
        *,
        enforcement_enabled: bool,
        audit_callback: Callable[[SecurityDecision, QueryContext], None] | None = None,
    ) -> None:
        self.enforcement_enabled = enforcement_enabled
        self.audit_callback = audit_callback

    @classmethod
    def from_env(cls) -> "SecurityFilter":
        enabled = os.getenv("SECURITY_ENFORCEMENT_ENABLED", "false").lower() == "true"
        if not enabled:
            logger.warning(
                "SecurityFilter running in PERMISSIVE mode (DEV). "
                "Set SECURITY_ENFORCEMENT_ENABLED=true to enforce policy."
            )
        return cls(enforcement_enabled=enabled)

    # ------------------------------------------------------------------ filter

    def filter(
        self,
        rows: Iterable[dict[str, Any]],
        *,
        context: QueryContext,
    ) -> SecurityDecision:
        decision = SecurityDecision()

        for row in rows:
            level = SensitivityLevel(row.get("sensitivity_level", SensitivityLevel.PUBLIC))

            if self.enforcement_enabled and level > context.clearance:
                decision.blocked.append({"id": row.get("id"), "reason": "clearance"})
                continue

            redacted = self._redact_row(row)
            if redacted is not row:
                decision.redacted.append(redacted)
            else:
                decision.allowed.append(row)

        if self.audit_callback is not None:
            try:
                self.audit_callback(decision, context)
            except Exception:
                logger.exception("audit_callback failed")
        return decision

    # ------------------------------------------------------------------ redact

    def redact(self, text: str) -> str:
        out = text
        for pat in _REDACT_PATTERNS:
            out = pat.sub("[REDACTED]", out)
        return out

    def _redact_row(self, row: dict[str, Any]) -> dict[str, Any]:
        any_redacted = False
        new_row: dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, str):
                rv = self.redact(v)
                if rv != v:
                    any_redacted = True
                new_row[k] = rv
            else:
                new_row[k] = v
        return new_row if any_redacted else row
