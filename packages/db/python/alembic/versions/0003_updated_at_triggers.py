"""Add updated_at auto-update triggers.

SQLAlchemy's ``onupdate`` only fires when the ORM writes a row. A raw SQL
UPDATE (data migration, external tool, Alembic fixup) bypasses it and leaves
stale timestamps. This migration adds a Postgres trigger so updated_at is
always correct regardless of how the row is modified.

Applies to: agent_tasks, integration_syncs (the tables that change in-place).
events and audit_log are append-only, learning_signals is append-only.

Revision ID: 0003_updated_at_triggers
Revises: 0002_add_vectors
Create Date: 2026-05-01
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0003_updated_at_triggers"
down_revision: Union[str, None] = "0002_add_vectors"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FUNCTION = """
CREATE OR REPLACE FUNCTION _set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW() AT TIME ZONE 'UTC';
    RETURN NEW;
END;
$$;
"""


def _attach(table: str) -> str:
    return f"""
    CREATE TRIGGER trg_{table}_updated_at
    BEFORE UPDATE ON {table}
    FOR EACH ROW EXECUTE FUNCTION _set_updated_at();
    """


def _detach(table: str) -> str:
    return f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};"


def upgrade() -> None:
    op.execute(_FUNCTION)
    for t in ("agent_tasks", "integration_syncs"):
        op.execute(_attach(t))


def downgrade() -> None:
    for t in ("agent_tasks", "integration_syncs"):
        op.execute(_detach(t))
    op.execute("DROP FUNCTION IF EXISTS _set_updated_at();")
