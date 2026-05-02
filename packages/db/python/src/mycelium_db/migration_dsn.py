"""DSN rewriting for synchronous Alembic engines (psycopg v3 vs asyncpg URLs)."""


def coerce_dsn_for_alembic(dsn: str) -> str:
    """Alembic uses synchronous SQLAlchemy engines; coerce app-style DSNs to psycopg (v3)."""
    if dsn.startswith("postgresql+asyncpg://"):
        return dsn.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+psycopg://", 1)
    return dsn
