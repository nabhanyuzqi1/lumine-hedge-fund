# Copyright (c) 2026 Lumine. All rights reserved.
"""Level 2 integration test fixtures.

Spins up ephemeral PostgreSQL + Redis containers via testcontainers,
applies Alembic migrations to the fresh DB via the real CLI, and yields
async sessions and Redis clients. Containers are session-scoped to stay
under the < 2 min budget; Redis is flushed per-test for isolation.

No mocks for PG/Redis — only MT5 bridge and LLM gateway are mocked
in higher-level tests. See docs/13-testing/test-levels.md Level 2.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from lumine.data.redis_client import close_redis, get_redis
from lumine.data.session import dispose_engine, get_sessionmaker
from lumine.shared.config import Settings, override_settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession
    from testcontainers.community.postgres import PostgresContainer
    from testcontainers.community.redis import RedisContainer

# ── Session-scoped container management ───────────────────────────────────────
# Containers persist for the whole session (started once) to respect the
# < 2 min integration test budget. testcontainers' sync API is used; the
# async session/redis fixtures bridge to async below.

_PG_CONTAINER: PostgresContainer | None = None
_REDIS_CONTAINER: RedisContainer | None = None
_DB_URL: str | None = None
_REDIS_URL: str | None = None
_LOCK = threading.Lock()
_MIGRATIONS_APPLIED = False


def _start_containers() -> tuple[str, str]:
    """Start PG + Redis containers once per session. Returns (db_url, redis_url)."""
    global _PG_CONTAINER, _REDIS_CONTAINER, _DB_URL, _REDIS_URL  # noqa: PLW0603
    with _LOCK:
        if _DB_URL is not None and _REDIS_URL is not None:
            return _DB_URL, _REDIS_URL

        # Local import keeps testcontainers out of unit-test collection time.
        from testcontainers.community.postgres import PostgresContainer
        from testcontainers.community.redis import RedisContainer

        pg = PostgresContainer("postgres:16-alpine")
        pg.start()
        # PostgresContainer URL uses +psycopg2; asyncpg needs +asyncpg.
        raw_pg_url = pg.get_connection_url()
        asyncpg_url = raw_pg_url.replace("+psycopg2", "+asyncpg")

        redis = RedisContainer("redis:7-alpine")
        redis.start()
        redis_host = redis.get_container_host_ip()
        redis_port = redis.get_exposed_port(6379)
        redis_url = f"redis://{redis_host}:{redis_port}/0"

        _PG_CONTAINER = pg
        _REDIS_CONTAINER = redis
        _DB_URL = asyncpg_url
        _REDIS_URL = redis_url
        return _DB_URL, _REDIS_URL


def _apply_migrations(db_url: str) -> None:
    """Run `alembic upgrade head` against the container DB via subprocess.

    Drops and recreates the public schema first to guarantee a clean
    slate — PostgresContainer may reuse a persisted volume across runs,
    and migration 0001's non-idempotent `CREATE TYPE` would otherwise
    fail on a dirty schema.
    """
    global _MIGRATIONS_APPLIED  # noqa: PLW0603
    if _MIGRATIONS_APPLIED:
        return
    backend_dir = Path(__file__).resolve().parents[2]
    env = {**os.environ, "DATABASE_URL": db_url}

    # 1. Reset the schema to a clean state.
    reset_script = backend_dir / "tests" / "integration" / "_reset_schema.py"
    reset = subprocess.run(  # noqa: S603 — trusted local interpreter
        [sys.executable, str(reset_script)],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if reset.returncode != 0:
        msg = f"schema reset failed:\nSTDOUT:\n{reset.stdout}\nSTDERR:\n{reset.stderr}"
        raise RuntimeError(msg)

    # 2. Apply migrations via the real CLI (same path as `make migrate`).
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        msg = f"alembic upgrade head failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        raise RuntimeError(msg)
    _MIGRATIONS_APPLIED = True


def _stop_containers() -> None:
    """Stop containers at session end."""
    global _PG_CONTAINER, _REDIS_CONTAINER, _DB_URL, _REDIS_URL, _MIGRATIONS_APPLIED  # noqa: PLW0603
    if _REDIS_CONTAINER is not None:
        _REDIS_CONTAINER.stop()
        _REDIS_CONTAINER = None
    if _PG_CONTAINER is not None:
        _PG_CONTAINER.stop()
        _PG_CONTAINER = None
    _DB_URL = None
    _REDIS_URL = None
    _MIGRATIONS_APPLIED = False


@pytest.fixture(scope="session")
def integration_settings() -> Settings:
    """Return settings pointed at the testcontainers PG + Redis."""
    db_url, redis_url = _start_containers()
    settings = Settings(
        environment="test",
        debug=False,
        database_url=db_url,
        redis_url=redis_url,
        llm_daily_budget_usd=0.0,
        kill_switch_enabled=False,
        hmac_secret_key="integration-test-secret",
    )
    override_settings(settings)
    # Also export as env var so any subprocess (already-applied migrations)
    # and the alembic env.py see the container URL.
    os.environ["DATABASE_URL"] = db_url
    os.environ["REDIS_URL"] = redis_url
    return settings


@pytest.fixture(scope="session")
def _applied_migrations(integration_settings: Settings) -> None:
    """Apply Alembic migrations to the fresh container DB once per session."""
    _apply_migrations(integration_settings.database_url)


@pytest_asyncio.fixture
async def db_session(_applied_migrations: None) -> AsyncIterator[AsyncSession]:
    """Yield an async session on the migrated container DB.

    The session is rolled back after each test so tests are isolated
    without re-running migrations. Writes within a transaction are
    visible to that same transaction, so tests can read their own writes.
    """
    # dispose any engine cached from a prior settings override so the
    # sessionmaker binds to the current (container) settings.
    await dispose_engine()
    sm = get_sessionmaker()
    session = sm()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
    await dispose_engine()


@pytest_asyncio.fixture
async def redis_client(_applied_migrations: None) -> AsyncIterator[aioredis.Redis]:
    """Yield a flushed async Redis client on the container."""
    await close_redis()
    client = await get_redis()
    await client.flushdb()
    yield client
    await client.flushdb()
    await close_redis()


@pytest.fixture(scope="session", autouse=True)
def _cleanup_containers() -> Iterator[None]:
    """Stop containers after the integration session ends."""
    yield
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(dispose_engine())
        loop.run_until_complete(close_redis())
    finally:
        loop.close()
        _stop_containers()
