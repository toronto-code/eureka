"""Async SQLAlchemy engine + session factory."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _async_dsn() -> str:
    dsn = os.getenv("POSTGRES_DSN", "postgresql://mycelium:mycelium@postgres:5432/mycelium")
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    return dsn


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_postgres_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(_async_dsn(), pool_pre_ping=True, future=True)
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_postgres_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Async context manager yielding a session. Commits on success, rolls back on error."""
    session = _get_session_factory()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


class PostgresClient:
    """Convenience wrapper. Most callers should use ``get_session`` directly."""

    def __init__(self) -> None:
        self.engine = get_postgres_engine()

    def session(self):
        return get_session()
