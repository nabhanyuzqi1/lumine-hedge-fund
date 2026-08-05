# Copyright (c) 2026 Lumine. All rights reserved.
"""Shared test fixtures and configuration for all test levels."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest

from lumine.shared.config import Settings


@pytest.fixture
def settings() -> Settings:
    """Return test settings with safe defaults."""
    return Settings(
        environment="test",
        debug=True,
        database_url="postgresql+asyncpg://lumine:lumine@localhost:5432/lumine_test",
        redis_url="redis://localhost:6379/0",
        llm_daily_budget_usd=0.0,
        kill_switch_enabled=False,
        hmac_secret_key="test-secret-key",
    )


@pytest.fixture
def mock_llm_gateway() -> AsyncMock:
    """Return a mock LLM gateway that returns fixture responses."""
    gateway = AsyncMock()
    gateway.generate.return_value = {"content": "mock response", "usage": {"total_tokens": 100}}
    return gateway


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Return a mock Redis client."""
    client = AsyncMock()
    client.publish.return_value = 1
    client.get.return_value = None
    return client


@pytest.fixture
def db_session() -> AsyncIterator[AsyncMock]:
    """Return an async SQLAlchemy session for testing."""
    return AsyncMock()
