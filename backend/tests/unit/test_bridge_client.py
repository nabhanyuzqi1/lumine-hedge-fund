# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for MT5 bridge client request/response orchestration.

These tests use a fake Redis client so they run without a real server.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Protocol

import pytest

from lumine.bridge.client import BridgeClient, BridgeTimeoutError
from lumine.bridge.types import BridgeCommand, BridgeResult, BridgeStatus


class _PubSub(Protocol):
    async def subscribe(self, channel: str) -> None: ...
    async def unsubscribe(self, channel: str | None) -> None: ...
    async def aclose(self) -> None: ...
    async def get_message(
        self, *, ignore_subscribe_messages: bool = True, timeout: float | None = None
    ) -> dict[str, Any] | None: ...


class _Redis(Protocol):
    async def lpush(self, key: str, value: str) -> int: ...
    async def publish(self, channel: str, message: str) -> int: ...
    def pubsub(self) -> _PubSub: ...


class FakeRedis:
    """In-memory Redis double supporting the operations the bridge uses."""

    def __init__(self) -> None:
        """Initialize empty queues and subscriber list."""
        self.lists: dict[str, deque[str]] = {}
        self.subscribers: list[FakePubSub] = []

    async def lpush(self, key: str, value: str) -> int:
        self.lists.setdefault(key, deque()).appendleft(value)
        return len(self.lists[key])

    async def publish(self, key: str, value: str) -> int:
        for pubsub in self.subscribers:
            if pubsub.channel == key:
                pubsub.messages.append({"type": "message", "channel": key, "data": value.encode()})
                pubsub._event.set()
        return len(self.subscribers)

    def pubsub(self) -> FakePubSub:
        return FakePubSub(self)


class FakePubSub:
    def __init__(self, redis: FakeRedis) -> None:
        """Attach to a FakeRedis instance."""
        self.redis = redis
        self.channel: str | None = None
        self.messages: list[dict[str, Any]] = []
        self._event = asyncio.Event()

    async def subscribe(self, channel: str) -> None:
        self.channel = channel
        self.redis.subscribers.append(self)

    async def get_message(
        self,
        *,
        ignore_subscribe_messages: bool = True,
        timeout: float | None = None,
    ) -> dict[str, Any] | None:
        if not self.messages and timeout:
            try:
                await asyncio.wait_for(self._event.wait(), timeout=timeout)
            except TimeoutError:
                return None
            self._event.clear()
        if self.messages:
            return self.messages.pop(0)
        return None

    async def unsubscribe(self, channel: str | None = None) -> None:
        if self in self.redis.subscribers:
            self.redis.subscribers.remove(self)

    async def close(self) -> None:
        await self.unsubscribe(self.channel)

    async def aclose(self) -> None:
        await self.close()


@pytest.fixture
def fake_redis() -> _Redis:
    return FakeRedis()


@pytest.fixture
def client(fake_redis: _Redis) -> BridgeClient:
    return BridgeClient(
        redis=fake_redis,  # type: ignore[arg-type]
        command_channel="mt5:commands",
        result_channel="mt5:results",
        response_timeout_s=0.5,
    )


class TestBridgeClientSendCommand:
    async def test_send_command_pushes_to_list(
        self, client: BridgeClient, fake_redis: FakeRedis
    ) -> None:
        cmd = BridgeCommand(command_id="cmd-1", action="BUY", symbol="XAUUSD", volume=0.1)
        await client.send_command(cmd)
        assert len(fake_redis.lists["mt5:commands"]) == 1
        assert '"command_id": "cmd-1"' in fake_redis.lists["mt5:commands"][0]


class TestBridgeClientReceiveResult:
    async def test_receive_result_returns_matching_result(
        self, client: BridgeClient, fake_redis: FakeRedis
    ) -> None:
        receive_task = asyncio.create_task(client.receive_result("cmd-1"))
        await asyncio.sleep(0.01)
        result = BridgeResult(command_id="cmd-1", status=BridgeStatus.FILLED, ticket=123)
        await fake_redis.publish("mt5:results", result.model_dump_json())

        received = await receive_task
        assert received is not None
        assert received.ticket == 123

    async def test_receive_result_ignores_other_command_ids(
        self, client: BridgeClient, fake_redis: FakeRedis
    ) -> None:
        other = BridgeResult(command_id="cmd-2", status=BridgeStatus.FILLED, ticket=999)
        await fake_redis.publish("mt5:results", other.model_dump_json())

        with pytest.raises(BridgeTimeoutError):
            await client.receive_result("cmd-1")


class TestBridgeClientResilience:
    """Malformed/corrupt pub/sub messages must be skipped, not fatal (client.py:73-75)."""

    async def test_malformed_json_is_skipped_and_valid_result_received(
        self, client: BridgeClient, fake_redis: FakeRedis
    ) -> None:
        receive_task = asyncio.create_task(client.receive_result("cmd-1"))
        await asyncio.sleep(0.01)
        # Corrupt payload first — the client must skip it and keep waiting
        # (json.JSONDecodeError path, client.py:74).
        await fake_redis.publish("mt5:results", "this is not json")
        result = BridgeResult(command_id="cmd-1", status=BridgeStatus.FILLED, ticket=7)
        await fake_redis.publish("mt5:results", result.model_dump_json())

        received = await receive_task
        assert received is not None
        assert received.ticket == 7

    async def test_malformed_json_then_timeout_raises(
        self, client: BridgeClient, fake_redis: FakeRedis
    ) -> None:
        await fake_redis.publish("mt5:results", "not json at all")
        with pytest.raises(BridgeTimeoutError):
            await client.receive_result("cmd-1")

    async def test_cleanup_unsubscribes_and_closes_pubsub(
        self, client: BridgeClient, fake_redis: FakeRedis
    ) -> None:
        # The finally block (client.py:79-81) must release the subscription
        # and the connection on every exit path — success and timeout.
        with pytest.raises(BridgeTimeoutError):
            await client.receive_result("cmd-1")
        assert fake_redis.subscribers == []


class TestBridgeClientRoundTrip:
    async def test_roundtrip_returns_result(
        self, client: BridgeClient, fake_redis: FakeRedis
    ) -> None:
        async def delayed_result() -> None:
            await asyncio.sleep(0.05)
            result = BridgeResult(command_id="cmd-1", status=BridgeStatus.FILLED, ticket=123)
            await fake_redis.publish("mt5:results", result.model_dump_json())

        asyncio.create_task(delayed_result())  # noqa: RUF006
        cmd = BridgeCommand(command_id="cmd-1", action="BUY", symbol="XAUUSD", volume=0.1)
        result = await client.send_and_wait(cmd)
        assert result.status == BridgeStatus.FILLED
        assert result.ticket == 123

    async def test_roundtrip_timeout(self, client: BridgeClient) -> None:
        cmd = BridgeCommand(command_id="cmd-1", action="BUY", symbol="XAUUSD", volume=0.1)
        with pytest.raises(BridgeTimeoutError):
            await client.send_and_wait(cmd)

    async def test_roundtrip_idempotency_key_preserved(
        self, client: BridgeClient, fake_redis: FakeRedis
    ) -> None:
        cmd = BridgeCommand(
            command_id="cmd-1",
            action="BUY",
            symbol="XAUUSD",
            volume=0.1,
            idempotency_key="idem-1",
        )
        with pytest.raises(BridgeTimeoutError):
            await client.send_and_wait(cmd)
        queued = fake_redis.lists["mt5:commands"][0]
        assert '"idempotency_key": "idem-1"' in queued
