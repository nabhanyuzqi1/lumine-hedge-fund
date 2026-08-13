# Copyright (c) 2026 Lumine. All rights reserved.
"""Smoke test: verifies testcontainers PG + Redis come up and migrations apply.

Will be removed once real Level 2 tests exist; for now it proves the
integration test infrastructure works end-to-end.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

if TYPE_CHECKING:
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession

from lumine.shared.config import Settings


class TestInfraSmoke:
    """Verify the testcontainers fixtures work."""

    async def test_pg_container_running(self, db_session: AsyncSession) -> None:
        """PG container is up and a session can execute a query."""
        result = await db_session.execute(text("SELECT 1 AS one"))
        row = result.first()
        assert row is not None
        assert row.one == 1

    async def test_redis_container_running(self, redis_client: aioredis.Redis) -> None:
        """Redis container is up and responds to PING."""
        assert await redis_client.ping() is True

    async def test_migrations_applied(self, db_session: AsyncSession) -> None:
        """Alembic 0001-0003 tables exist, including DEFAULT partitions."""
        # Core tables
        result = await db_session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name IN ('lineage_records', 'ticks', 'bars_1m', 'bars_5m') "
                "ORDER BY table_name"
            )
        )
        tables = {row[0] for row in result}
        assert tables == {"lineage_records", "ticks", "bars_1m", "bars_5m"}

        # DEFAULT partitions created by migration 0003
        result = await db_session.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE tablename IN ('ticks_default', 'bars_1m_default', 'bars_5m_default') "
                "ORDER BY tablename"
            )
        )
        partitions = {row[0] for row in result}
        assert partitions == {"ticks_default", "bars_1m_default", "bars_5m_default"}

    @pytest.mark.skip(reason="infra smoke only — not needed after integration tests pass")
    async def test_settings_point_at_containers(self) -> None:
        """Overridden settings point at the container URLs."""
        settings = Settings(
            environment="test",
            debug=False,
            database_url="postgresql+asyncpg://lumine:lumine@localhost:5432/lumine_test",
            redis_url="redis://localhost:6379/0",
            llm_daily_budget_usd=0.0,
            kill_switch_enabled=False,
            hmac_secret_key="integration-test-secret",
        )
        assert "localhost" in settings.database_url
        assert "localhost" in settings.redis_url
