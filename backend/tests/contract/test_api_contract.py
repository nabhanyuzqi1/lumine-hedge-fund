# Copyright (c) 2026 Lumine. All rights reserved.
"""Contract tests for the public REST API envelope, auth, and router wiring."""

from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import hmac
import json
import time
from collections import deque
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from lumine.api.app import create_app
from lumine.api.middleware import auth as auth_module
from lumine.api.middleware import idempotency, rate_limit
from lumine.api.middleware.auth import AuthenticatedPrincipal, authenticate_request
from lumine.api.routers import admin as admin_router
from lumine.api.routers import rpc as rpc_router
from lumine.api.routers import streams
from lumine.rpc import queue as rpc_queue
from lumine.shared.config import Settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

_TEST_HMAC_SECRET = "bootstrap-secret-for-tests"  # noqa: S105


class FakeRedis:
    """Minimal async Redis stand-in for admin/rpc contract tests."""

    def __init__(self) -> None:
        """Initialize an empty in-memory Redis store."""
        self.data: dict[str, dict[str, str]] = {}
        self.strings: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self._seq = 0

    async def hgetall(self, key: str) -> dict[str, str]:
        return self.data.get(key, {})

    async def hget(self, key: str, field: str) -> str | None:
        return self.data.get(key, {}).get(field)

    async def hset(
        self,
        name: str,
        key: str | None = None,
        value: object | None = None,
        mapping: dict[str, object] | None = None,
    ) -> int:
        if mapping is not None:
            self.data.setdefault(name, {}).update({k: str(v) for k, v in mapping.items()})
        if key is not None and value is not None:
            self.data.setdefault(name, {})[key] = str(value)
        return 1

    async def exists(self, key: str) -> int:
        return 1 if key in self.data else 0

    # ── stream + string ops (RPC queue B-04) ──────────────────────────────
    async def xadd(self, name: str, fields: dict[str, str]) -> str:
        self._seq += 1
        message_id = f"0-{self._seq}"
        self.streams.setdefault(name, []).append((message_id, fields))
        return message_id

    async def expire(self, name: str, seconds: int) -> int:
        return 1

    async def set(self, name: str, value: str, ex: int | None = None) -> str:
        self.strings[name] = value
        return "OK"

    async def get(self, key: str) -> str | None:
        return self.strings.get(key)

    async def set(self, name: str, value: object, ex: int | None = None) -> bool:  # noqa: ARG002 — TTL not enforced in fake
        self.strings[name] = str(value)
        return True

    async def delete(self, key: str) -> int:
        return int(self.strings.pop(key, None) is not None)

    async def zremrangebyscore(self, name: str, _min: float, _max: float) -> int:
        bucket = self.zsets.get(name, {})
        removed = [m for m, s in bucket.items() if _min <= s <= _max]
        for member in removed:
            del bucket[member]
        return len(removed)

    async def zcard(self, name: str) -> int:
        return len(self.zsets.get(name, {}))

    async def zadd(self, name: str, mapping: dict[str, float]) -> int:
        self.zsets.setdefault(name, {}).update(mapping)
        return len(mapping)

    async def expire(self, name: str, _seconds: int) -> bool:
        self.zsets.setdefault(name, {})
        return True

    async def scan_iter(self, match: str | None = None) -> AsyncIterator[bytes]:
        for key in list(self.data.keys()):
            if match is None or fnmatch.fnmatch(key, match):
                yield key.encode()


def _async_redis(fake: FakeRedis) -> Callable[[], Awaitable[FakeRedis]]:
    async def _get_redis() -> FakeRedis:
        return fake

    return _get_redis


async def _async_false(*_args: object, **_kwargs: object) -> bool:
    """Async stand-in returning False (kill switch not armed)."""
    return False


class _FakeStreamRequest:
    """Minimal Request stand-in for exercising streams._event_stream."""

    def __init__(self) -> None:
        """Attach client/state/headers used by the stream generator."""
        self.client = type("Client", (), {"host": "127.0.0.1"})()
        self.state = type(
            "State",
            (),
            {"principal": AuthenticatedPrincipal(key_id="unit", scopes=frozenset())},
        )()
        self.headers = {"Last-Event-ID": "0"}

    async def is_disconnected(self) -> bool:
        return False


def _run(awaitable: Awaitable[object]) -> str:
    """Drive a single coroutine step on a fresh event loop (sync test)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(awaitable)
    finally:
        loop.close()


@pytest.fixture
def settings() -> Settings:
    return Settings(hmac_secret_key=_TEST_HMAC_SECRET)


@pytest.fixture
def client(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    fake = FakeRedis()
    monkeypatch.setattr(rate_limit, "get_redis", _async_redis(fake), raising=False)
    app = create_app(settings)
    app.dependency_overrides[authenticate_request] = lambda: AuthenticatedPrincipal(
        key_id="test",
        scopes=frozenset({"admin"}),
    )
    return TestClient(app)


def _sign(method: str, path: str, timestamp: str, body: bytes, secret: str) -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    payload = f"{method}\n{path}\n{timestamp}\n{body_hash}".encode()
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def test_health_endpoint_returns_envelope(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["meta"]["status"] == "ok"
    assert payload["data"]["status"] == "ok"


def test_trace_id_echoed_and_consistent(client: TestClient) -> None:
    trace_id = "contract-trace-0001"
    response = client.get("/health", headers={"X-Request-ID": trace_id})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == trace_id
    assert response.json()["meta"]["request_id"] == trace_id


def test_trace_id_echoed_on_error_path(client: TestClient) -> None:
    trace_id = "contract-trace-0002"
    response = client.get("/api/v1/nonexistent", headers={"X-Request-ID": trace_id})
    assert response.status_code == 404
    assert response.headers["x-request-id"] == trace_id
    error = response.json()["error"]
    assert error["trace_id"] == trace_id


def test_hmac_missing_headers_is_401(settings: Settings) -> None:
    app = create_app(settings)
    unauthenticated_client = TestClient(app)

    response = unauthenticated_client.get("/api/v1/portfolio/summary")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MISSING_AUTH"


def test_hmac_invalid_signature_is_401(settings: Settings) -> None:
    app = create_app(settings)
    unauthenticated_client = TestClient(app)

    timestamp = str(int(time.time()))
    response = unauthenticated_client.get(
        "/api/v1/portfolio/summary",
        headers={
            "X-Lumine-API-Key": "bootstrap",
            "X-Lumine-Timestamp": timestamp,
            "X-Lumine-Signature": "invalid-signature",
        },
    )
    assert response.status_code == 401


def test_hmac_valid_bootstrap_key_succeeds(settings: Settings) -> None:
    app = create_app(settings)
    unauthenticated_client = TestClient(app)

    timestamp = str(int(time.time()))
    signature = _sign("GET", "/api/v1/portfolio/summary", timestamp, b"", _TEST_HMAC_SECRET)
    response = unauthenticated_client.get(
        "/api/v1/portfolio/summary",
        headers={
            "X-Lumine-API-Key": "bootstrap",
            "X-Lumine-Timestamp": timestamp,
            "X-Lumine-Signature": signature,
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["meta"]["status"] == "ok"
    assert payload["data"]["portfolio_id"] == "default"


def test_hmac_signature_covers_query_string(settings: Settings) -> None:
    """Request path in the signature includes the query string (auth.md)."""
    app = create_app(settings)
    unauthenticated_client = TestClient(app)

    # Offset: the replay cache keys on (api_key, timestamp, body_hash), so
    # each test needs a unique timestamp to avoid cross-test collisions.
    timestamp = str(int(time.time()) + 1)
    url = "/api/v1/portfolio/summary?limit=5"
    signature = _sign("GET", url, timestamp, b"", _TEST_HMAC_SECRET)
    response = unauthenticated_client.get(
        url,
        headers={
            "X-Lumine-API-Key": "bootstrap",
            "X-Lumine-Timestamp": timestamp,
            "X-Lumine-Signature": signature,
        },
    )
    assert response.status_code == 200

    # A signature computed over the bare path must not validate.
    path_only_signature = _sign(
        "GET", "/api/v1/portfolio/summary", timestamp, b"", _TEST_HMAC_SECRET
    )
    tampered = unauthenticated_client.get(
        url,
        headers={
            "X-Lumine-API-Key": "bootstrap",
            "X-Lumine-Timestamp": timestamp,
            "X-Lumine-Signature": path_only_signature,
        },
    )
    assert tampered.status_code == 401
    assert tampered.json()["error"]["code"] == "INVALID_SIGNATURE"


def test_hmac_replay_is_rejected(settings: Settings) -> None:
    """An identical signed request within the window is rejected (auth.md)."""
    app = create_app(settings)
    unauthenticated_client = TestClient(app)

    timestamp = str(int(time.time()) + 2)
    url = "/api/v1/portfolio/summary?replay-probe=1"
    headers = {
        "X-Lumine-API-Key": "bootstrap",
        "X-Lumine-Timestamp": timestamp,
        "X-Lumine-Signature": _sign("GET", url, timestamp, b"", _TEST_HMAC_SECRET),
    }

    first = unauthenticated_client.get(url, headers=headers)
    assert first.status_code == 200

    replay = unauthenticated_client.get(url, headers=headers)
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "REPLAY_DETECTED"


def test_404_uses_error_contract(client: TestClient) -> None:
    response = client.get("/no-such-route")
    assert response.status_code == 404

    payload = response.json()
    assert payload["meta"]["status"] == "error"
    assert payload["error"]["code"] == "NOT_FOUND"


def test_portfolio_endpoint_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/portfolio/summary")
    assert response.status_code == 200
    assert "meta" in response.json()
    assert response.json()["data"]["nav"] == "100000.00"


def test_orders_endpoint_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/orders")
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["symbol"] == "XAUUSD"


def test_market_endpoint_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/market/bars")
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["symbol"] == "XAUUSD"


def test_workflows_endpoint_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/workflows")
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["workflow_name"] == "decision_cycle"


def test_lineage_endpoint_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/lineage")
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["decision_type"] == "order_proposal"


def test_journal_endpoint_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/journal")
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["agent_name"] == "performance_reviewer"


def test_rpc_endpoint_envelope(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(rpc_router, "_kill_switch_armed", _async_false, raising=False)
    from lumine.rpc import queue as rpc_queue

    monkeypatch.setattr(rpc_queue, "get_redis", _async_redis(fake), raising=False)

    response = client.post("/api/v1/rpc/run-decision-cycle")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["command"] == "run_decision_cycle"
    assert data["status"] == "accepted"
    assert data["command_id"] != "00000000-0000-0000-0000-000000000000"
    # The command was actually enqueued to the stream (B-04 dispatch).
    assert len(fake.streams["rpc:commands"]) == 1
    assert fake.streams["rpc:commands"][0][1]["command"] == "run_decision_cycle"


def test_rpc_halt_trading_enqueues(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRedis()
    from lumine.rpc import queue as rpc_queue

    monkeypatch.setattr(rpc_queue, "get_redis", _async_redis(fake), raising=False)

    response = client.post("/api/v1/rpc/halt-trading")
    assert response.status_code == 200
    assert response.json()["data"]["command"] == "halt_trading"
    assert fake.streams["rpc:commands"][0][1]["command"] == "halt_trading"


def test_rpc_command_status_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    command_id = "11111111-2222-3333-4444-555555555555"
    from lumine.rpc import queue as rpc_queue

    async def _fake_result(cid: str) -> dict | None:
        if cid != command_id:
            return None
        return {
            "command_id": cid,
            "command": "halt_trading",
            "status": "completed",
            "result": {"armed": True, "tier": "global"},
            "error": None,
            "processed_at": "2026-08-14T00:00:00+00:00",
        }

    monkeypatch.setattr(rpc_router, "get_result", _fake_result, raising=False)

    response = client.get(f"/api/v1/rpc/commands/{command_id}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "completed"
    assert data["result"] == {"armed": True, "tier": "global"}

    response = client.get("/api/v1/rpc/commands/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    assert response.status_code == 404


def test_b06_portfolio_and_orders_endpoints(client: TestClient) -> None:
    """B-06 additions: equity curve, cancel-all, history, bulk, signals/symbol."""

    # Equity curve (paginated)
    response = client.get("/api/v1/portfolio/default/equity?limit=5")
    assert response.status_code == 200
    equity = response.json()["data"]
    assert equity["total"] == 240
    assert len(equity["items"]) == 5
    assert set(equity["items"][0]) == {"ts", "nav", "equity", "drawdown"}

    # Cancel-all
    response = client.delete("/api/v1/portfolio/default/orders")
    assert response.status_code == 200
    assert response.json()["data"] == {"cancelled": 3, "portfolio_id": "default"}

    # Order history
    order_id = "11111111-2222-3333-4444-555555555555"
    response = client.get(f"/api/v1/orders/{order_id}/history")
    assert response.status_code == 200
    history = response.json()["data"]
    assert history["total"] == 2
    assert history["items"][0]["new_state"] == "pending"

    # Bulk status
    response = client.post(
        "/api/v1/orders/bulk-status",
        json={"order_ids": [order_id, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"]},
    )
    assert response.status_code == 200
    bulk = response.json()["data"]
    assert bulk["total"] == 2
    assert bulk["statuses"][order_id] == "filled"

    # Signals per symbol
    response = client.get("/api/v1/market/signals/XAUUSD")
    assert response.status_code == 200
    signals = response.json()["data"]
    assert signals["total"] == 3
    assert all(item["symbol"] == "XAUUSD" for item in signals["items"])

    # Portfolio CRUD (single-portfolio v1)
    response = client.get("/api/v1/portfolio")
    assert response.status_code == 200
    assert response.json()["data"]["portfolio_id"] == "default"
    response = client.post("/api/v1/portfolio", json={"name": "book-a", "currency": "USD"})
    assert response.status_code == 201
    response = client.delete("/api/v1/portfolio/default")
    assert response.status_code == 409


def test_metrics_endpoint_exposes_prometheus_text(client: TestClient) -> None:
    """B-02: /metrics serves Prometheus text format (not enveloped)."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "lumine_process_uptime_seconds" in response.text


def test_sse_stream_is_not_enveloped(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _single_event(
        request: object, channel: str, interval_s: float = 2.0
    ) -> AsyncIterator[str]:
        yield 'data: {"channel": "portfolio"}\n\n'

    monkeypatch.setattr(streams, "_event_stream", _single_event)

    response = client.get("/api/v1/streams/analyst-outputs")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "data:" in response.text


def test_admin_kill_switch_lifecycle(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(admin_router, "get_redis", _async_redis(fake), raising=False)

    get_response = client.get("/api/v1/admin/kill-switch")
    assert get_response.status_code == 200
    assert get_response.json()["data"]["armed"] is False

    post_response = client.post(
        "/api/v1/admin/kill-switch",
        json={"reason": "market halt", "armed": True},
    )
    assert post_response.status_code == 200
    data = post_response.json()["data"]
    assert data["armed"] is True
    assert data["reason"] == "market halt"


def test_idempotency_replay_returns_original_envelope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same key + same body → 200 with meta.idempotent_replay (error-contract.md:182)."""
    fake = FakeRedis()
    monkeypatch.setattr(rpc_router, "_kill_switch_armed", _async_false, raising=False)
    monkeypatch.setattr(rpc_queue, "get_redis", _async_redis(fake), raising=False)
    monkeypatch.setattr(idempotency, "get_redis", _async_redis(fake), raising=False)

    headers = {"X-Idempotency-Key": "order-create-1"}
    first = client.post("/api/v1/rpc/run-decision-cycle", headers=headers)
    assert first.status_code == 200
    assert first.json()["meta"].get("idempotent_replay") is None

    replay = client.post("/api/v1/rpc/run-decision-cycle", headers=headers)
    assert replay.status_code == 200
    payload = replay.json()
    assert payload["meta"]["idempotent_replay"] is True
    assert payload["data"] == first.json()["data"]


def test_idempotency_conflict_on_different_body(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same key + different body → 409 CONFLICT (error-contract.md:183)."""
    fake = FakeRedis()
    monkeypatch.setattr(rpc_router, "_kill_switch_armed", _async_false, raising=False)
    monkeypatch.setattr(rpc_queue, "get_redis", _async_redis(fake), raising=False)
    monkeypatch.setattr(idempotency, "get_redis", _async_redis(fake), raising=False)

    headers = {"X-Idempotency-Key": "order-create-2"}
    first = client.post("/api/v1/rpc/run-decision-cycle", headers=headers)
    assert first.status_code == 200

    conflict = client.post(
        "/api/v1/rpc/run-decision-cycle",
        headers=headers,
        json={"symbol": "XAUUSD"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "CONFLICT"


def test_idempotency_key_is_per_api_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same key under a different API key is not a replay (error-contract.md)."""
    fake = FakeRedis()
    monkeypatch.setattr(rpc_router, "_kill_switch_armed", _async_false, raising=False)
    monkeypatch.setattr(rpc_queue, "get_redis", _async_redis(fake), raising=False)
    monkeypatch.setattr(idempotency, "get_redis", _async_redis(fake), raising=False)

    first = client.post(
        "/api/v1/rpc/run-decision-cycle",
        headers={"X-Idempotency-Key": "shared-key", "X-Lumine-API-Key": "key-a"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/rpc/run-decision-cycle",
        headers={"X-Idempotency-Key": "shared-key", "X-Lumine-API-Key": "key-b"},
    )
    assert second.status_code == 200
    assert second.json()["meta"].get("idempotent_replay") is None


def test_admin_create_and_revoke_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(admin_router, "get_redis", _async_redis(fake), raising=False)

    create_response = client.post(
        "/api/v1/admin/keys",
        json={
            "key_id": "test-key-1",
            "name": "contract test key",
            "scopes": ["read:portfolio"],
            "revoked": False,
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()["data"]
    assert created["secret"]
    assert created["scopes"] == ["read:portfolio"]

    list_response = client.get("/api/v1/admin/keys")
    assert list_response.status_code == 200
    keys = list_response.json()["data"]
    assert any(k["key_id"] == "test-key-1" for k in keys)

    revoke_response = client.delete("/api/v1/admin/keys/test-key-1")
    assert revoke_response.status_code == 200
    assert revoke_response.json()["data"]["revoked"] is True


def test_rate_limit_429_with_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    """Write endpoints honor the per-key limit: 429 RATE_LIMITED + Retry-After."""
    fake = FakeRedis()
    monkeypatch.setattr(rate_limit, "get_redis", _async_redis(fake), raising=False)
    monkeypatch.setattr(rpc_router, "_kill_switch_armed", _async_false, raising=False)
    monkeypatch.setattr(rpc_queue, "get_redis", _async_redis(fake), raising=False)

    limited_app = create_app(
        Settings(hmac_secret_key=_TEST_HMAC_SECRET, api_rate_limit_per_minute=2)
    )
    limited_app.dependency_overrides[authenticate_request] = lambda: AuthenticatedPrincipal(
        key_id="limited-key",
        scopes=frozenset({"admin"}),
    )
    limited_client = TestClient(limited_app)

    for _ in range(2):
        response = limited_client.post("/api/v1/rpc/run-decision-cycle")
        assert response.status_code == 200

    exceeded = limited_client.post("/api/v1/rpc/run-decision-cycle")
    assert exceeded.status_code == 429
    assert exceeded.json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in exceeded.headers


def test_rate_limit_disabled_when_limit_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """api_rate_limit_per_minute <= 0 disables enforcement (rate_limit.py:32)."""
    fake = FakeRedis()
    monkeypatch.setattr(rate_limit, "get_redis", _async_redis(fake), raising=False)
    monkeypatch.setattr(rpc_router, "_kill_switch_armed", _async_false, raising=False)
    monkeypatch.setattr(rpc_queue, "get_redis", _async_redis(fake), raising=False)

    unlimited_app = create_app(
        Settings(hmac_secret_key=_TEST_HMAC_SECRET, api_rate_limit_per_minute=0)
    )
    unlimited_app.dependency_overrides[authenticate_request] = lambda: AuthenticatedPrincipal(
        key_id="unlimited-key",
        scopes=frozenset({"admin"}),
    )
    unlimited_client = TestClient(unlimited_app)

    for _ in range(3):
        response = unlimited_client.post("/api/v1/rpc/run-decision-cycle")
        assert response.status_code == 200


def test_expired_timestamp_is_401(settings: Settings) -> None:
    """A signature with a timestamp outside the 5-minute window is rejected."""
    app = create_app(settings)
    unauthenticated_client = TestClient(app)

    timestamp = str(int(time.time()) - 400)
    signature = _sign("GET", "/api/v1/portfolio/summary", timestamp, b"", _TEST_HMAC_SECRET)
    response = unauthenticated_client.get(
        "/api/v1/portfolio/summary",
        headers={
            "X-Lumine-API-Key": "bootstrap",
            "X-Lumine-Timestamp": timestamp,
            "X-Lumine-Signature": signature,
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "EXPIRED_TIMESTAMP"


def test_revoked_key_is_401(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """A dynamic key marked revoked in Redis is rejected (auth.md)."""
    fake = FakeRedis()
    fake.data["lumine:api_key:dyn-key"] = {
        "secret": "dyn-secret",
        "scopes": "read:portfolio",
        "revoked": "1",
    }
    monkeypatch.setattr(auth_module, "get_redis", _async_redis(fake), raising=False)

    app = create_app(settings)
    unauthenticated_client = TestClient(app)

    timestamp = str(int(time.time()))
    signature = _sign("GET", "/api/v1/portfolio/summary", timestamp, b"", "dyn-secret")
    response = unauthenticated_client.get(
        "/api/v1/portfolio/summary",
        headers={
            "X-Lumine-API-Key": "dyn-key",
            "X-Lumine-Timestamp": timestamp,
            "X-Lumine-Signature": signature,
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "REVOKED_KEY"


def test_insufficient_scope_is_403(settings: Settings) -> None:
    """A key lacking the required scope is rejected with 403 (error-contract.md:53)."""
    app = create_app(settings)
    app.dependency_overrides[authenticate_request] = lambda: AuthenticatedPrincipal(
        key_id="readonly-key",
        scopes=frozenset({"read:portfolio"}),
    )
    limited_client = TestClient(app)

    response = limited_client.get("/api/v1/market/bars")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_SCOPE"


def test_validation_failure_is_400(client: TestClient) -> None:
    """Malformed write payloads map to 400 VALIDATION_FAILED (error-contract.md:47)."""
    response = client.post("/api/v1/orders", json={})
    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_FAILED"
    assert "errors" in payload["error"]["details"]


def test_pagination_limit_parameter(client: TestClient) -> None:
    """List endpoints honor the limit query parameter (rest-api.md pagination)."""
    response = client.get("/api/v1/orders?limit=1")
    assert response.status_code == 200
    assert len(response.json()["data"]["items"]) == 1


def test_sse_stream_open_and_heartbeat_frames() -> None:
    """Live SSE frames: stream_open first, then a heartbeat comment line."""
    request = _FakeStreamRequest()
    stream = streams._event_stream(  # noqa: SLF001 — test drives the private generator directly
        request, "unit-test-channel", 0.05
    )

    first = stream.__anext__()
    opened = _run(first)
    assert "event: stream_open" in opened
    assert '"request_id": "stream-' in opened

    second = stream.__anext__()
    heartbeat = _run(second)
    assert heartbeat == ": heartbeat\n\n"

    _run(stream.aclose())


def test_sse_frame_timestamp_has_utc_z_suffix() -> None:
    """SSE envelope timestamps carry ISO 8601 ms + Z (sse-api.md Freshness)."""
    frame = streams._emit(  # noqa: SLF001 — test drives the private emitter directly
        "unit-test-z", "s1", "market_data", {"symbol": "XAUUSD"}
    )
    assert frame.startswith("id: 1\n")
    payload = json.loads(frame.split("data: ", 1)[1].strip())
    stamp = payload["meta"]["timestamp"]
    assert stamp.endswith("Z")
    assert stamp.count(".") == 1  # exactly milliseconds precision
    # Round-trips as an aware UTC instant — clients may compute staleness.
    aware_ts = datetime.fromisoformat(stamp)
    assert aware_ts.tzinfo is not None
    assert aware_ts.utcoffset() == timedelta(0)


def test_sse_replay_resumes_with_gap_detected() -> None:
    """Reconnect with Last-Event-ID older than the ring buffer → resumed + gap."""
    channel = "unit-test-replay"
    req = _FakeStreamRequest()
    # The client last saw event 3, but the 1000-event / 5-min buffer has
    # already rolled over to event 7 — simulasi disconnect yang lama.
    buffers = streams._buffers  # noqa: SLF001 — direct state setup for the test
    the_channel = buffers.setdefault(channel, deque(maxlen=streams._BUFFER_MAX_EVENTS))  # noqa: SLF001
    the_channel.clear()
    the_channel.append(
        streams._BufferedEvent(  # noqa: SLF001
            event_id=7,
            ts=time.time(),
            frame='id: 7\nevent: test_event\ndata: {"n": 7}\n\n',
        )
    )
    streams._next_ids[channel] = 7  # noqa: SLF001
    req.headers = {"Last-Event-ID": "3"}
    stream = streams._event_stream(  # noqa: SLF001 — test drives the private generator directly
        req, channel, 0.1
    )

    opened = _run(stream.__anext__())
    assert "event: stream_open" in opened

    resumed = _run(stream.__anext__())
    assert "event: stream_resumed" in resumed
    assert '"gap_detected": true' in resumed
    assert '"from_event_id": 3' in resumed

    replay = _run(stream.__anext__())
    assert "event: test_event" in replay
    assert '"n": 7' in replay

    _run(stream.aclose())


# ── Orders: PATCH modify (ModifyOrderDialog contract) ────────────────────


def test_orders_patch_modify_updates_price(client: TestClient) -> None:
    order_id = "12345678-1234-5678-1234-567812345678"
    response = client.patch(
        f"/api/v1/orders/{order_id}",
        json={"price": "2450.00"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["order_id"] == order_id
    assert data["price"] == "2450.00"
    assert data["volume"] == "1.50"
    assert data["status"] == "pending"


def test_orders_patch_modify_updates_volume(client: TestClient) -> None:
    order_id = "12345678-1234-5678-1234-567812345679"
    response = client.patch(
        f"/api/v1/orders/{order_id}",
        json={"volume": "2.00"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["volume"] == "2.00"


def test_orders_patch_rejects_empty_body(client: TestClient) -> None:
    """PATCH with neither price nor volume → 400 VALIDATION_FAILED."""
    response = client.patch("/api/v1/orders/12345678-1234-5678-1234-567812345678", json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


# ── Market cluster (marketClient.ts contract) ────────────────────────────


def test_market_quote_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/market/quote/XAUUSD")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["symbol"] == "XAUUSD"
    assert float(data["bid"]) < float(data["ask"])
    assert float(data["last"]) > 0


def test_market_quotes_batch_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/market/quotes?symbols=XAUUSD&symbols=EURUSD")
    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {"XAUUSD", "EURUSD"}


def test_market_ohlcv_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/market/ohlcv/XAUUSD?timeframe=1h&limit=5")
    assert response.status_code == 200
    bars = response.json()["data"]
    assert len(bars) == 5
    assert bars[0]["symbol"] == "XAUUSD"
    assert bars[0]["timeframe"] == "1h"
    stamps = [b["timestamp"] for b in bars]
    assert stamps == sorted(stamps)


def test_market_ohlcv_rejects_bad_timeframe(client: TestClient) -> None:
    response = client.get("/api/v1/market/ohlcv/XAUUSD?timeframe=2h")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_market_symbol_and_symbols_endpoints(client: TestClient) -> None:
    symbol = client.get("/api/v1/market/symbol/XAUUSD")
    assert symbol.status_code == 200
    data = symbol.json()["data"]
    assert data["symbol"] == "XAUUSD"
    assert data["tick_size"] == "0.01"
    assert data["is_active"] is True

    symbols = client.get("/api/v1/market/symbols")
    assert symbols.status_code == 200
    assert len(symbols.json()["data"]) >= 2

    missing = client.get("/api/v1/market/symbol/UNKNOWN")
    assert missing.status_code == 404


def test_market_volatility_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/market/volatility/XAUUSD?window=14")
    assert response.status_code == 200
    volatility = response.json()["data"]["volatility"]
    assert 0.0 < volatility < 1.0


def test_market_correlation_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/market/correlation?symbols=XAUUSD&symbols=EURUSD")
    assert response.status_code == 200
    matrix = response.json()["data"]
    assert matrix["XAUUSD"]["XAUUSD"] == 1.0
    assert matrix["EURUSD"]["XAUUSD"] == matrix["XAUUSD"]["EURUSD"]


def test_market_spread_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/market/spread/XAUUSD?period=60")
    assert response.status_code == 200
    data = response.json()["data"]
    assert float(data["min_spread"]) <= float(data["avg_spread"]) <= float(data["max_spread"])


def test_market_session_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/market/session/XAUUSD")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["current_session"] in {"asian", "european", "american", "off"}
    assert data["time_until_next"] >= 0
    assert isinstance(data["is_trading_open"], bool)


def test_market_features_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/market/features/XAUUSD")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["symbol"] == "XAUUSD"
    assert "rsi_14" in data["features"]
    assert "ema_20" in data["features"]


# ── Portfolio simulate (simulateTrade contract) ──────────────────────────


def test_portfolio_simulate_endpoint(client: TestClient) -> None:
    response = client.post(
        "/api/v1/portfolio/default/simulate",
        json={"symbol": "XAUUSD", "side": "buy", "volume": "0.40", "price": "2420.00"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "projected_nav" in data
    assert "margin_required" in data
    assert "pnl_change" in data
    assert float(data["margin_required"]) > 0


# ── Kill switch tier round-trip ──────────────────────────────────────────


def test_admin_kill_switch_tier_roundtrip(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(admin_router, "get_redis", _async_redis(fake), raising=False)

    post_response = client.post(
        "/api/v1/admin/kill-switch",
        json={"reason": "news shock", "armed": True, "tier": "book"},
    )
    assert post_response.status_code == 200
    data = post_response.json()["data"]
    assert data["armed"] is True
    assert data["tier"] == "book"

    get_response = client.get("/api/v1/admin/kill-switch")
    assert get_response.status_code == 200
    persisted = get_response.json()["data"]
    assert persisted["tier"] == "book"
    assert persisted["reason"] == "news shock"
