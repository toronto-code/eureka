"""Tests for correlation_id derivation rules."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from mycelium_shared_types.correlation import derive_correlation_id


def test_natural_id_rule_uses_source_prefix() -> None:
    cid = derive_correlation_id(source="github", object_id="ignored", natural_id="pr-42")
    assert cid == "github:pr-42"


def test_hash_rule_shape_and_stability_with_fixed_time_and_uuid() -> None:
    fixed = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)

    class _FakeUUID:
        hex = "abcdef00112233445566778899aabbcc"

    with patch("mycelium_shared_types.correlation.uuid.uuid4", return_value=_FakeUUID()):
        cid = derive_correlation_id(
            source="api.chat",
            object_id="task-111",
            when=fixed,
            window_seconds=60,
        )

    assert cid.startswith("api.chat:")
    parts = cid.split(":")
    assert len(parts) == 3
    digest, suffix = parts[1], parts[2]
    assert len(digest) == 16
    assert len(suffix) == 8
    assert suffix == "abcdef00"

    with patch("mycelium_shared_types.correlation.uuid.uuid4", return_value=_FakeUUID()):
        cid2 = derive_correlation_id(
            source="api.chat",
            object_id="task-111",
            when=fixed,
            window_seconds=60,
        )
    assert cid == cid2

    later = datetime(2026, 5, 1, 12, 1, 30, tzinfo=timezone.utc)
    with patch("mycelium_shared_types.correlation.uuid.uuid4", return_value=_FakeUUID()):
        cid3 = derive_correlation_id(
            source="api.chat",
            object_id="task-111",
            when=later,
            window_seconds=60,
        )
    assert cid3 != cid


def test_window_size_can_change_digest() -> None:
    when = datetime(2026, 5, 1, 12, 0, 7, tzinfo=timezone.utc)

    class _FakeUUID:
        hex = "0" * 32

    with patch("mycelium_shared_types.correlation.uuid.uuid4", return_value=_FakeUUID()):
        c60 = derive_correlation_id(
            source="s", object_id="o", when=when, window_seconds=60
        )
        c300 = derive_correlation_id(
            source="s", object_id="o", when=when, window_seconds=300
        )
    assert c60 != c300
