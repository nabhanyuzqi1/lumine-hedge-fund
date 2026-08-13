# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for the RPC worker (B-04 dispatch)."""

from __future__ import annotations

import pytest

from lumine.api.sse.publisher import SSEEvent
from lumine.rpc.queue import set_result
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
