# Copyright (c) 2026 Lumine. All rights reserved.
"""Standalone MT5 bridge worker for containerized deployments.

Connects to Redis, subscribes to `mt5:results`, and stays alive. Without a
real MT5 terminal the bridge runs in demo mode — fills are published by the
API layer (MarketService / SSE) and the bridge merely provides the Redis
transport contract (`mt5:commands` queue + `mt5:results` channel).

Run: python -m scripts.run_bridge   (or as the compose `mt5-bridge` service)
"""

from __future__ import annotations

import asyncio

from lumine.shared.config import get_settings
from lumine.trading.mt5_bridge import MT5Bridge


async def main() -> None:
    """Start the bridge and keep the event loop alive."""
    settings = get_settings()
    bridge = await MT5Bridge.from_url(settings.redis_url)
    await bridge.start()
    print(f"mt5-bridge live: redis={settings.redis_url} (demo mode: no EA attached)")  # noqa: T201
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await bridge.stop()


if __name__ == "__main__":
    asyncio.run(main())
