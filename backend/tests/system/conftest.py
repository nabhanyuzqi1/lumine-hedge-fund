# Copyright (c) 2026 Lumine. All rights reserved.
"""Level 4 system-test fixtures.

Reuses the Level 2/3 testcontainers stack (PostgreSQL + Redis with
migrations applied) from ``tests.integration.conftest`` so the full
decision cycle runs against real persistence. Only the LLM gateway (via
scripted FakeGateway) and the MT5 EA (via a fake bridge) are simulated —
everything else is real.

The fixtures are imported (not ``pytest_plugins``) so a full-suite run
does not double-register the integration conftest module.
"""

from __future__ import annotations

from tests.integration.conftest import (  # noqa: F401
    _applied_migrations,
    _cleanup_containers,
    db_session,
    integration_settings,
    redis_client,
)
