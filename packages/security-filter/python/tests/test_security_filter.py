"""SecurityFilter redaction + clearance behaviour."""

from __future__ import annotations

from mycelium_security_filter import QueryContext, SecurityFilter, SensitivityLevel


def test_redact_password_pattern() -> None:
    filt = SecurityFilter(enforcement_enabled=False)
    out = filt.redact("config password=hunter2 end")
    assert "REDACTED" in out
    assert "hunter2" not in out


def test_redact_openai_sk_pattern() -> None:
    filt = SecurityFilter(enforcement_enabled=False)
    token = "sk-" + ("a" * 20)
    out = filt.redact(f"Bearer {token}")
    assert "REDACTED" in out


def test_enforcement_blocks_high_sensitivity() -> None:
    filt = SecurityFilter(enforcement_enabled=True)
    rows = [
        {"id": "n1", "label": "x", "sensitivity_level": int(SensitivityLevel.RESTRICTED)},
    ]
    ctx = QueryContext(user_id="u1", clearance=SensitivityLevel.INTERNAL)
    decision = filt.filter(rows, context=ctx)
    assert decision.allowed == []
    assert len(decision.blocked) == 1


def test_permissive_moves_redacted_rows_to_redacted_list() -> None:
    filt = SecurityFilter(enforcement_enabled=False)
    rows = [{"id": "1", "note": "password: hunter2"}]
    decision = filt.filter(rows, context=QueryContext(user_id="u1"))
    assert len(decision.redacted) == 1
    assert "REDACTED" in decision.redacted[0]["note"]
