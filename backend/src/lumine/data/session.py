# Copyright (c) 2026 Lumine. All rights reserved.
"""Async SQLAlchemy session factory.

Provides engine creation, sessionmaker, and lifecycle helpers for the
async PostgreSQL connection. Uses the singleton Settings from shared/config.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from lumine.shared.config import get_settings

_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _create_engine() -> None:
    global _engine, _sessionmaker
    settings = get_settings()
    _engine = create_async_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_pool_overflow,
        echo=settings.database_echo,
        future=True,
    )
    _sessionmaker = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the singleton async sessionmaker. Lazy-creates the engine."""
    global _sessionmaker
    if _sessionmaker is None:
        _create_engine()
    return _sessionmaker  # type: ignore[return-value]


async def get_db_session() -> AsyncSession:
    """Get a single-use async session for direct operations."""
    sm = get_sessionmaker()
    session = sm()
    await session.__aenter__()
    return session


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession for dependency injection / context managers."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Close the engine and release all connections. Called on shutdown."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
