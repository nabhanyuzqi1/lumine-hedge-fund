# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for the RPC worker (B-04 dispatch)."""

from __future__ import annotations

import pytest

from lumine.api.sse.publisher import SSEEvent
from lumine.rpc.worker import _handle_cancel_order, _handle_halt_trading, _process
from lumine.shared.config import Settings


class _StubRedis:
    """Minimal async redis stand-in for worker handlers."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}

    async def hset(self, name: str, mapping: dict[str, str]) -> int:
        self.hashes.setdefault(name, {}).update(mapping)
        return 1


class _StubPublisher:
    def __init__(self) -> None:
        self.events: list[SSEEvent] = []

    async def publish(self, event: SSEEvent) -> None:
        self.events.append(event)


def _stub_redis(stub: _StubRedis):
    async def _get_redis() -> _StubRedis:
        return stub

    return _get_redis


def _settings() -> Settings:
    return Settings(hmac_secret_key="test", kill_switch_key="kill:switch")


@pytest.mark.asyncio
async def test_halt_trading_arms_kill_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _StubRedis()
    from lumine.rpc import worker as worker_module

    monkeypatch.setattr(worker_module, "get_redis", _stub_redis(stub), raising=False)
    result = await _handle_halt_trading({"reason": "manual"}, _settings())
    assert result["armed"] is True
    assert stub.hashes["kill:switch"]["armed"] == "1"
    assert stub.hashes["kill:switch"]["tier"] == "global"


@pytest.mark.asyncio
async def test_cancel_order_publishes_sse_event() -> None:
    publisher = _StubPublisher()
    result = await _handle_cancel_order({"order_id": "ord-1"}, publisher)
    assert result["status"] == "cancelled"
    assert publisher.events[0].event_type == "order_cancelled"
    assert publisher.events[0].channel == "orders"
    assert publisher.events[0].data["order_id"] == "ord-1"


@pytest.mark.asyncio
async def test_run_worker_decodes_bytes_fields() -> None:
    """redis-py returns bytes keys/values — the consumer must decode them."""
    from lumine.rpc.worker import _decode_fields

    decoded = _decode_fields({b"command_id": b"decoded-1", b"command": b"halt_trading", b"payload": b"{}"})
    assert decoded == {"command_id": "decoded-1", "command": "halt_trading", "payload": "{}"}


@pytest.mark.asyncio
async def test_get_result_decodes_bytes_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hgetall returns bytes keys — get_result must decode before reading."""

    class _StubRedis:
        async def get(self, key: str) -> None:
            return None  # no result yet → receipt fallback

        async def hgetall(self, key: str) -> dict[bytes, bytes]:
            return {b"command": b"halt_trading", b"status": b"queued", b"enqueued_at": b"2026-08-14T00:00:00Z"}

    async def _fake_get_redis() -> _StubRedis:
        return _StubRedis()

    from lumine.rpc import queue as queue_module

    monkeypatch.setattr(queue_module, "get_redis", _fake_get_redis, raising=False)
    result = await queue_module.get_result("cmd-1")
    assert result is not None
    assert result["status"] == "queued"
    assert result["command"] == "halt_trading"
    assert result["enqueued_at"] == "2026-08-14T00:00:00Z"


@pytest.mark.asyncio
async def test_process_is_idempotent_per_command_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redelivered messages with a stored result are skipped (at-least-once)."""
    calls: list[str] = []

    async def _fake_get_result(cid: str) -> dict | None:
        if cid == "done-1":
            return {"command_id": "done-1", "status": "completed", "result": {}, "error": None}
        return None

    async def _fake_set_result(*args: object, **kwargs: object) -> None:
        calls.append("set_result")

    from lumine.rpc import worker as worker_module

    monkeypatch.setattr(worker_module, "get_result", _fake_get_result, raising=False)
    monkeypatch.setattr(worker_module, "set_result", _fake_set_result, raising=False)

    await _process("done-1", "halt_trading", {}, _StubPublisher(), _settings())
    assert calls == []  # already completed → skipped

    # Unknown command id → failed result, no exception.
    await _process("new-1", "bogus_command", {}, _StubPublisher(), _settings())
    assert calls == ["set_result"]
