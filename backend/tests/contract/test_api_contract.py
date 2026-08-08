# Copyright (c) 2026 Lumine. All rights reserved.
"""Contract tests for the public REST API envelope, auth, and router wiring."""

from __future__ import annotations

import fnmatch
import hashlib
import hmac
import time
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from lumine.api.app import create_app
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

    async def scan_iter(self, match: str | None = None) -> AsyncIterator[bytes]:
        for key in list(self.data.keys()):
            if match is None or fnmatch.fnmatch(key, match):
                yield key.encode()


def _async_redis(fake: FakeRedis) -> Callable[[], Awaitable[FakeRedis]]:
    async def _get_redis() -> FakeRedis:
        return fake

    return _get_redis


@pytest.fixture
def settings() -> Settings:
    return Settings(hmac_secret_key=_TEST_HMAC_SECRET)


@pytest.fixture
def client(settings: Settings) -> TestClient:
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


def test_hmac_missing_headers_is_401(settings: Settings) -> None:
    app = create_app(settings)
    unauthenticated_client = TestClient(app)

    response = unauthenticated_client.get("/portfolio/summary")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MISSING_AUTH"


def test_hmac_invalid_signature_is_401(settings: Settings) -> None:
    app = create_app(settings)
    unauthenticated_client = TestClient(app)

    timestamp = str(int(time.time()))
    response = unauthenticated_client.get(
        "/portfolio/summary",
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
    signature = _sign("GET", "/portfolio/summary", timestamp, b"", _TEST_HMAC_SECRET)
    response = unauthenticated_client.get(
        "/portfolio/summary",
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
    url = "/portfolio/summary?limit=5"
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
    path_only_signature = _sign("GET", "/portfolio/summary", timestamp, b"", _TEST_HMAC_SECRET)
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
    url = "/portfolio/summary?replay-probe=1"
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
    response = client.get("/portfolio/summary")
    assert response.status_code == 200
    assert "meta" in response.json()
    assert response.json()["data"]["nav"] == "100000.00"


def test_orders_endpoint_envelope(client: TestClient) -> None:
    response = client.get("/orders")
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["symbol"] == "XAUUSD"


def test_market_endpoint_envelope(client: TestClient) -> None:
    response = client.get("/market/bars")
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["symbol"] == "XAUUSD"


def test_workflows_endpoint_envelope(client: TestClient) -> None:
    response = client.get("/workflows")
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["workflow_name"] == "decision_cycle"


def test_lineage_endpoint_envelope(client: TestClient) -> None:
    response = client.get("/lineage")
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["decision_type"] == "order_proposal"


def test_journal_endpoint_envelope(client: TestClient) -> None:
    response = client.get("/journal")
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["agent_name"] == "performance_reviewer"


def test_rpc_endpoint_envelope(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(rpc_router, "get_redis", _async_redis(fake), raising=False)

    response = client.post("/rpc/run-decision-cycle")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["command"] == "run_decision_cycle"
    assert data["status"] == "accepted"


def test_sse_stream_is_not_enveloped(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _single_event(
        request: object, channel: str, interval_s: float = 2.0
    ) -> AsyncIterator[str]:
        yield 'data: {"channel": "portfolio"}\n\n'

    monkeypatch.setattr(streams, "_event_stream", _single_event)

    response = client.get("/streams/portfolio")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "data:" in response.text


def test_admin_kill_switch_lifecycle(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(admin_router, "get_redis", _async_redis(fake), raising=False)

    get_response = client.get("/admin/kill-switch")
    assert get_response.status_code == 200
    assert get_response.json()["data"]["armed"] is False

    post_response = client.post(
        "/admin/kill-switch",
        json={"reason": "market halt", "armed": True},
    )
    assert post_response.status_code == 200
    data = post_response.json()["data"]
    assert data["armed"] is True
    assert data["reason"] == "market halt"


def test_admin_create_and_revoke_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(admin_router, "get_redis", _async_redis(fake), raising=False)

    create_response = client.post(
        "/admin/keys",
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

    list_response = client.get("/admin/keys")
    assert list_response.status_code == 200
    keys = list_response.json()["data"]
    assert any(k["key_id"] == "test-key-1" for k in keys)

    revoke_response = client.delete("/admin/keys/test-key-1")
    assert revoke_response.status_code == 200
    assert revoke_response.json()["data"]["revoked"] is True
