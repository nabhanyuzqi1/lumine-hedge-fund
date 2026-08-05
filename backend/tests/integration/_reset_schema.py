# Copyright (c) 2026 Lumine. All rights reserved.
"""Test helper: drop and recreate the public schema on the DATABASE_URL DB.

Used by the integration conftest to guarantee a clean slate before applying
Alembic migrations. PostgresContainer may reuse a persisted volume, and
migration 0001's `CREATE TYPE` is not idempotent.

Run: uv run python tests/integration/_reset_schema.py
Reads DATABASE_URL from the environment.
"""

from __future__ import annotations

import asyncio
import os
import sys

import asyncpg


async def reset_schema() -> None:
    db_url = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "")
    if not db_url:
        sys.exit("DATABASE_URL not set")
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        await conn.execute("CREATE SCHEMA public")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(reset_schema())
