"""Privacy guardrails. These are non-negotiable.

Every event built by the observer goes through ``redact_event`` before it
leaves the process. ``redact_event`` strips fields the observer must never
emit (file contents, command arguments, stdin/stdout, terminal contents).

This is enforced by code, not policy. There is no opt-out.
"""

from __future__ import annotations

# Fields that may NEVER appear in an observer event payload.
FORBIDDEN_FIELDS = frozenset(
    {
        "args",
        "argv",
        "command_args",
        "stdin",
        "stdout",
        "stderr",
        "file_contents",
        "diff",
        "patch",
        "env",
        "environment",
        "terminal",
        "session",
        "keystrokes",
    }
)


def redact_event(payload: dict) -> dict:
    """Drop forbidden fields from a payload, recursively.

    Returns a new dict; does not mutate the input.
    """

    def _scrub(obj):
        if isinstance(obj, dict):
            return {k: _scrub(v) for k, v in obj.items() if k not in FORBIDDEN_FIELDS}
        if isinstance(obj, list):
            return [_scrub(v) for v in obj]
        return obj

    return _scrub(payload)


def assert_no_contents(filenames: list[str]) -> None:
    """A small belt-and-braces check.

    The observer should be passing filenames as strings; if any caller
    accidentally hands us a path/content tuple, fail loud and early.
    """
    for f in filenames:
        if not isinstance(f, str):
            raise ValueError(
                "Observer privacy violation: filenames list must contain strings only "
                f"(got {type(f).__name__})"
            )
