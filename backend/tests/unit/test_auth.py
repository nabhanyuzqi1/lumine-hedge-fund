# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit + API tests for the internal session auth (replaces SSO stack).

Covers: PBKDF2 hashing, token sign/parse, login/logout/me/verify flows,
role gating on verify, and the Settings-bootstrap fallback when the DB
is unavailable (monkeypatched out of the session lookup).
"""

from __future__ import annotations

from typing import Annotated

import pytest
from fastapi.testclient import TestClient

from lumine.api.app import create_app
from lumine.api.middleware import rate_limit
from lumine.api.middleware.auth import AuthenticatedPrincipal, authenticate_request
from lumine.api.routers import auth as auth_module
from lumine.shared.config import Settings

_TEST_SECRET = "unit-test-hmac-secret"


class FakeRedis:
    """Minimal async Redis stand-in for the rate-limit dependency."""

    def __init__(self) -> None:
        self.data: dict[str, dict[str, str]] = {}
        self.zsets: dict[str, dict[str, float]] = {}

    async def hgetall(self, key: str) -> dict[str, str]:
        return self.data.get(key, {})

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

    async def zadd(self, name: str, mapping: dict[str, float]) -> int:
        self.zsets.setdefault(name, {}).update(mapping)
        return len(mapping)

    async def zremrangebyscore(self, name: str, min_score: float, max_score: float) -> int:
        store = self.zsets.setdefault(name, {})
        removed = [k for k, v in store.items() if min_score <= v <= max_score]
        for k in removed:
            del store[k]
        return len(removed)

    async def zcard(self, name: str) -> int:
        return len(self.zsets.get(name, {}))

    async def expire(self, name: str, seconds: int) -> int:
        return 1


def _async_redis(fake: FakeRedis):
    async def _get_redis() -> FakeRedis:
        return fake

    return _get_redis


@pytest.fixture
def settings() -> Settings:
    return Settings(hmac_secret_key=_TEST_SECRET)


@pytest.fixture
def client(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """App with DB lookups disabled → exercises the bootstrap fallback."""
    app = create_app(settings)

    fake = FakeRedis()
    monkeypatch.setattr(rate_limit, "get_redis", _async_redis(fake), raising=False)

    async def _no_db(*args: object, **kwargs: object) -> None:
        # Simulate "user not found / DB unavailable": fall back to bootstrap.
        return None

    monkeypatch.setattr(auth_module, "_db_user", _no_db)
    app.dependency_overrides[authenticate_request] = (
        lambda: AuthenticatedPrincipal(key_id="test", scopes=frozenset({"admin"}))
    )
    return TestClient(app)


# ── hashing ──────────────────────────────────────────────────────────────


def test_password_hash_roundtrip() -> None:
    salt = auth_module.new_salt()
    digest = auth_module.hash_password("hunter2", salt)
    assert len(digest) == 64  # sha256 hex
    assert auth_module.verify_password("hunter2", salt, digest)
    assert not auth_module.verify_password("hunter3", salt, digest)


def test_new_salt_is_unique() -> None:
    assert auth_module.new_salt() != auth_module.new_salt()


# ── tokens ───────────────────────────────────────────────────────────────


def test_token_roundtrip(settings: Settings) -> None:
    token = auth_module.issue_token(settings, "trader", "user")
    payload = auth_module.parse_token(token, settings)
    assert payload is not None
    assert payload["sub"] == "trader"
    assert payload["role"] == "user"
    assert payload["exp"] > 0


def test_token_rejects_tampering(settings: Settings) -> None:
    token = auth_module.issue_token(settings, "trader", "user")
    tampered = token[:-4] + ("abcd" if not token.endswith("abcd") else "wxyz")
    assert auth_module.parse_token(tampered, settings) is None


def test_token_rejects_wrong_secret(settings: Settings) -> None:
    token = auth_module.issue_token(settings, "trader", "user")
    other = Settings(hmac_secret_key="different-secret")
    assert auth_module.parse_token(token, other) is None


# ── login / logout / me / verify (bootstrap fallback path) ──────────────


def test_login_success_sets_cookie(client: TestClient) -> None:
    res = client.post(
        "/api/auth/login",
        json={"username": "trader", "password": "lumine2026"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["data"]["username"] == "trader"
    assert body["data"]["role"] == "user"
    assert "lumine_session" in res.headers.get("set-cookie", "")
    assert "HttpOnly" in res.headers["set-cookie"]


def test_login_invalid_credentials(client: TestClient) -> None:
    res = client.post(
        "/api/auth/login",
        json={"username": "trader", "password": "wrong-password"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "MISSING_AUTH"


def test_login_unknown_user(client: TestClient) -> None:
    res = client.post(
        "/api/auth/login",
        json={"username": "ghost", "password": "x"},
    )
    assert res.status_code == 401


def test_me_after_login(client: TestClient) -> None:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "lumine-admin"})
    assert login.status_code == 200
    res = client.get("/api/auth/me")
    assert res.status_code == 200
    assert res.json()["data"] == {"username": "admin", "role": "admin"}


def test_me_unauthenticated(client: TestClient) -> None:
    res = client.get("/api/auth/me")
    assert res.status_code == 401


def test_logout_clears_cookie(client: TestClient) -> None:
    client.post("/api/auth/login", json={"username": "trader", "password": "lumine2026"})
    res = client.post("/api/auth/logout")
    assert res.status_code == 200
    assert res.json()["data"] == {"ok": True}
    assert "lumine_session=" in res.headers["set-cookie"]  # empty value → cleared
    assert client.get("/api/auth/me").status_code == 401


def test_verify_ok_with_role_gate(client: TestClient) -> None:
    client.post("/api/auth/login", json={"username": "superadmin", "password": "Lumine@2026!"})
    res = client.get("/api/auth/verify", params={"role": "superadmin"})
    assert res.status_code == 200
    assert res.json()["data"]["role"] == "superadmin"


def test_verify_insufficient_role(client: TestClient) -> None:
    client.post("/api/auth/login", json={"username": "trader", "password": "lumine2026"})
    res = client.get("/api/auth/verify", params={"role": "admin"})
    assert res.status_code == 401


def test_verify_no_session(client: TestClient) -> None:
    res = client.get("/api/auth/verify")
    assert res.status_code == 401


def test_bootstrap_user_resolution(settings: Settings) -> None:
    user = auth_module._bootstrap_user("superadmin", settings)
    assert user is not None
    assert user["role"] == "superadmin"
    assert auth_module.verify_password("Lumine@2026!", user["password_salt"], user["password_hash"])
    assert auth_module._bootstrap_user("ghost", settings) is None


def test_role_gating_table() -> None:
    assert auth_module._role_ok("user", None)
    assert auth_module._role_ok("superadmin", "user")
    assert auth_module._role_ok("admin", "admin")
    assert not auth_module._role_ok("user", "admin")
    assert not auth_module._role_ok("guest", "user")


def test_envelope_shape_on_login(client: TestClient) -> None:
    res = client.post("/api/auth/login", json={"username": "trader", "password": "lumine2026"})
    body = res.json()
    assert set(body) == {"meta", "data"}
    assert body["meta"]["status"] == "ok"
