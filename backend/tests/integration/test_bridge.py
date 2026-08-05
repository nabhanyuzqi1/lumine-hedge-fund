# Copyright (c) 2026 Lumine. All rights reserved.
"""Level 2 integration tests for MT5 bridge Redis roundtrip."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from lumine.bridge.client import BridgeClient, BridgeTimeoutError
from lumine.bridge.types import BridgeCommand, BridgeResult, BridgeStatus
from lumine.shared.config import get_settings

if TYPE_CHECKING:
    import redis.asyncio as aioredis


@pytest.fixture
def bridge_client(redis_client: aioredis.Redis) -> BridgeClient:
    settings = get_settings()
    return BridgeClient(
        redis=redis_client,
        command_channel=settings.mt5_command_channel,
        result_channel=settings.mt5_result_channel,
        response_timeout_s=2.0,
    )


async def test_bridge_command_roundtrip(
    bridge_client: BridgeClient, redis_client: aioredis.Redis
) -> None:
    """Roundtrip from command LIST to matching result channel.

    A command pushed by the client is readable from the LIST; a matching
    result published on the channel is returned by send_and_wait.
    """
    cmd = BridgeCommand(command_id="cmd-int-1", action="BUY", symbol="XAUUSD", volume=0.1)

    async def publish_delayed_result() -> None:
        await asyncio.sleep(0.1)
        result = BridgeResult(
            command_id="cmd-int-1",
            status=BridgeStatus.FILLED,
            ticket=12345,
            fill_price=2500.0,
            fill_volume=0.1,
        )
        await redis_client.publish(get_settings().mt5_result_channel, result.model_dump_json())

    task = asyncio.create_task(publish_delayed_result())
    try:
        result = await bridge_client.send_and_wait(cmd)
    finally:
        await task

    assert result.status == BridgeStatus.FILLED
    assert result.ticket == 12345
    assert result.fill_price == 2500.0

    # Command landed in the LIST
    raw = await redis_client.brpop(get_settings().mt5_command_channel, timeout=0)
    assert raw is not None
    _, payload = raw
    queued = payload.decode() if isinstance(payload, bytes) else payload
    assert '"command_id": "cmd-int-1"' in queued


async def test_bridge_timeout_when_no_result(bridge_client: BridgeClient) -> None:
    cmd = BridgeCommand(command_id="cmd-int-2", action="SELL", symbol="XAUUSD", volume=0.1)
    with pytest.raises(BridgeTimeoutError):
        await bridge_client.send_and_wait(cmd)
