"""Alembic environment untuk Fund2.

Sumber URL: app.config.DATABASE_URL (env var DATABASE_URL menang atas api/.env).
Driver: psycopg 3 (postgresql+psycopg) -- sama dengan runtime aplikasi.
Migrasi ditulis sebagai SQL mentah (op.execute) agar 1:1 dengan DDL produksi.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Pastikan package `app` (di api/) bisa diimport saat alembic dijalankan dari
# direktori mana pun.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config as app_config  # noqa: E402

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)


def _database_url() -> str:
    url = app_config.DATABASE_URL
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    raise RuntimeError(f"DATABASE_URL tidak didukung: {url!r}")


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        {"sqlalchemy.url": _database_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
