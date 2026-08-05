# Copyright (c) 2026 Lumine. All rights reserved.
"""Level 2 tests for PostgreSQL partition lifecycle management."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from lumine.data.partitions import ensure_partitions


async def test_ensure_partitions_creates_current_children(db_session: AsyncSession) -> None:
    """Runtime DDL creates one current child for each partitioned parent."""
    statements = await ensure_partitions(
        db_session,
        now=datetime(2026, 8, 3, 12, tzinfo=UTC),
        lookahead_periods=0,
    )

    result = await db_session.execute(
        text(
            "SELECT child.relname "
            "FROM pg_inherits "
            "JOIN pg_class AS child ON child.oid = inhrelid "
            "WHERE child.relname IN "
            "('ticks_20260803', 'bars_1m_202608', 'bars_5m_202608')"
        )
    )

    assert len(statements) == 3
    assert {row[0] for row in result} == {
        "ticks_20260803",
        "bars_1m_202608",
        "bars_5m_202608",
    }
