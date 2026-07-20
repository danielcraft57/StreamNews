"""Alembic env : lit DATABASE_URL, supporte SQLite + Postgres."""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# analyzer/ sur sys.path pour models.*
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.db_schema import metadata  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def _sync_url(url: str) -> str:
    if url.startswith("sqlite+aiosqlite:"):
        return "sqlite:" + url.split(":", 1)[1]
    if url.startswith("postgresql+asyncpg:"):
        return "postgresql+psycopg2:" + url.split(":", 1)[1]
    return url


def get_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return _sync_url(url)
    return config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
