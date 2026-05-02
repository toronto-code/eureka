"""Tests for Alembic DSN coercion (no imports of ``mycelium_db.postgres`` / async drivers)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MOD_PATH = Path(__file__).resolve().parents[1] / "src" / "mycelium_db" / "migration_dsn.py"
_spec = importlib.util.spec_from_file_location("migration_dsn", _MOD_PATH)
assert _spec and _spec.loader
_migration_dsn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration_dsn)
_coerce = _migration_dsn.coerce_dsn_for_alembic


@pytest.mark.parametrize(
    "incoming,expected",
    [
        (
            "postgresql://u:p@localhost:5432/db",
            "postgresql+psycopg://u:p@localhost:5432/db",
        ),
        (
            "postgresql+asyncpg://u:p@localhost:5432/db",
            "postgresql+psycopg://u:p@localhost:5432/db",
        ),
        (
            "postgresql+psycopg://u:p@localhost:5432/db",
            "postgresql+psycopg://u:p@localhost:5432/db",
        ),
    ],
)
def test_coerce_dsn_for_alembic(incoming: str, expected: str) -> None:
    assert _coerce(incoming) == expected
