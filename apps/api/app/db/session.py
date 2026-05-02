"""SQLAlchemy engine + session factory.

Uses synchronous psycopg3. Switch to async later by introducing a parallel
async engine; the current MVP path is small and deterministic so sync is fine.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()


def _build_engine() -> Engine:
    """Build a SQLAlchemy engine. Tolerant when Postgres isn't reachable yet."""
    dsn = _settings.postgres_dsn
    # Prefer psycopg3 driver explicitly when caller supplied bare 'postgresql://'.
    if dsn.startswith("postgresql://"):
        dsn = dsn.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(dsn, pool_pre_ping=True, future=True)


engine: Engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@event.listens_for(engine, "connect")
def _ensure_pgvector(dbapi_conn, _connection_record) -> None:  # type: ignore[no-untyped-def]
    """Best-effort pgvector enablement on each new connection."""
    try:
        with dbapi_conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        dbapi_conn.commit()
    except Exception as exc:  # noqa: BLE001 - extension may be missing in non-pgvector images
        logger.debug("pgvector extension not enabled: %s", exc)


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a managed Session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
