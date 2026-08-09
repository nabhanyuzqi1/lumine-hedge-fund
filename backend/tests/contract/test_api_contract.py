# Copyright (c) 2026 Lumine. All rights reserved.
"""Contract tests for the public REST API envelope, auth, and router wiring."""

from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import hmac
import time
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
    monkeypatch.setattr(rpc_router, "get_redis", _async_redis(fake), raising=False)

    response = client.post("/api/v1/rpc/run-decision-cycle")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["command"] == "run_decision_cycle"
    assert data["status"] == "accepted"


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
    monkeypatch.setattr(rpc_router, "get_redis", _async_redis(fake), raising=False)
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
    monkeypatch.setattr(rpc_router, "get_redis", _async_redis(fake), raising=False)
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
    monkeypatch.setattr(rpc_router, "get_redis", _async_redis(fake), raising=False)
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
    monkeypatch.setattr(rpc_router, "get_redis", _async_redis(fake), raising=False)

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
    monkeypatch.setattr(rpc_router, "get_redis", _async_redis(fake), raising=False)

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
