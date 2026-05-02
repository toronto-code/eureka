"""Pebblo-pattern enforcement.

The library is intentionally minimal: a single ``SecurityFilter`` class with
``filter()`` and ``redact()`` methods, plus a ``QueryContext`` describing the
caller. Both apps/api and services/knowledge import this — never roll your own.
"""

from mycelium_security_filter.filter import (
    QueryContext,
    SecurityDecision,
    SecurityFilter,
    SensitivityLevel,
)

__all__ = [
    "QueryContext",
    "SecurityDecision",
    "SecurityFilter",
    "SensitivityLevel",
]
