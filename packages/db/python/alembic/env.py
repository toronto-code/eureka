"""Alembic environment.

Reads ``POSTGRES_DSN`` from the environment and uses the ORM metadata declared
in :mod:`mycelium_db.models`.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from mycelium_db.models import Base
from mycelium_db.migration_dsn import coerce_dsn_for_alembic

config = context.config


if config.config_file_name is not None:
    fileConfig(config.config_file_name)

dsn = os.getenv("POSTGRES_DSN")
if dsn:
    config.set_main_option("sqlalchemy.url", coerce_dsn_for_alembic(dsn))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
