# Copyright (c) 2026 Lumine. All rights reserved.
"""HMAC-SHA256 API key authentication for the public REST API.

Stores dynamic API keys in Redis (hash per key id) and falls back to the
bootstrap key defined in Settings.hmac_secret_key. Scopes are checked against
the router decorator requirements.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from lumine.data.redis_client import get_redis
from lumine.shared.config import Settings, get_settings
from lumine.shared.errors import AuthError, ScopeError

_API_KEY_LEN = 32
_SIGNATURE_WINDOW_SECONDS = 300
_REPLAY_CACHE_MAX = 10_000

# In-memory replay cache keyed by (api_key, timestamp, body_hash), per
# docs/09-api/auth.md. Process-local; adequate for the single-worker
# deployment — multi-worker deployments should back this with Redis.
_replay_seen: dict[tuple[str, str, str], float] = {}

api_key_header = APIKeyHeader(name="X-Lumine-API-Key", auto_error=False)
timestamp_header = APIKeyHeader(name="X-Lumine-Timestamp", auto_error=False)
signature_header = APIKeyHeader(name="X-Lumine-Signature", auto_error=False)


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """Principal returned after successful HMAC verification."""

    key_id: str
    scopes: frozenset[str]

    def require(self, scope: str) -> None:
        """Raise if the principal lacks the required scope."""
        if scope not in self.scopes and "admin" not in self.scopes:
            msg = f"missing required scope: {scope}"
            raise ScopeError(msg)


async def _load_key(settings: Settings, key_id: str) -> tuple[str, frozenset[str]] | None:
    """Return (secret, scopes) for a key id, or None if not found/revoked."""
    if key_id == "bootstrap" and settings.hmac_secret_key:
        return settings.hmac_secret_key, frozenset({"admin"})

    r = await get_redis()
    raw = await r.hgetall(f"lumine:api_key:{key_id}")
    if not raw:
        return None

    decoded: dict[str, str] = {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in raw.items()
    }
    if decoded.get("revoked") == "1":
        return None

    secret = decoded.get("secret", "")
    scopes = frozenset(decoded.get("scopes", "").split(","))
    return secret, scopes


def _build_signature_payload(
    method: str,
    path: str,
    timestamp: str,
    body: bytes,
) -> bytes:
    """Construct the signed payload per docs/09-api/auth.md."""
    body_hash = hashlib.sha256(body).hexdigest()
    payload = f"{method}\n{path}\n{timestamp}\n{body_hash}"
    return payload.encode()


def _verify_signature(secret: str, payload: bytes, signature: str) -> bool:
    """Constant-time HMAC-SHA256 verification."""
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _prune_replay_cache(now: int) -> None:
    """Drop expired entries to keep the replay cache bounded."""
    for key, expiry in list(_replay_seen.items()):
        if expiry <= now:
            del _replay_seen[key]


def _check_replay(api_key: str, timestamp: str, body_hash: str, now: int) -> None:
    """Reject exact replays within the signature window (docs/09-api/auth.md).

    Records (api_key, timestamp, body_hash) after a valid signature is
    verified, so only authenticated requests enter the cache.
    """
    key = (api_key, timestamp, body_hash)
    if key in _replay_seen and _replay_seen[key] > now:
        msg = "request replay detected"
        raise AuthError(msg, code="REPLAY_DETECTED")
    _replay_seen[key] = now + _SIGNATURE_WINDOW_SECONDS
    if len(_replay_seen) > _REPLAY_CACHE_MAX:
        _prune_replay_cache(now)


async def authenticate_request(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    api_key: Annotated[str | None, Header(alias="X-Lumine-API-Key")] = None,
    timestamp: Annotated[str | None, Header(alias="X-Lumine-Timestamp")] = None,
    signature: Annotated[str | None, Header(alias="X-Lumine-Signature")] = None,
) -> AuthenticatedPrincipal:
    """FastAPI dependency verifying HMAC signature and timestamp freshness."""
    missing = [h for h, v in {
        "X-Lumine-API-Key": api_key,
        "X-Lumine-Timestamp": timestamp,
        "X-Lumine-Signature": signature,
    }.items() if not v]
    if missing:
        msg = f"missing auth headers: {', '.join(missing)}"
        raise AuthError(msg, code="MISSING_AUTH")

    if api_key is None or timestamp is None or signature is None:
        # Defensive: missing headers are caught above, but narrowing keeps mypy happy.
        missing_auth_message = "missing auth headers"
        raise AuthError(missing_auth_message, code="MISSING_AUTH")

    key_info = await _load_key(settings, api_key)
    if key_info is None:
        msg = "invalid or revoked API key"
        raise AuthError(msg, code="REVOKED_KEY")

    secret, scopes = key_info
    try:
        ts_int = int(timestamp)
    except ValueError as exc:
        msg = "invalid timestamp"
        raise AuthError(msg, code="INVALID_SIGNATURE") from exc

    now = int(time.time())
    if abs(now - ts_int) > _SIGNATURE_WINDOW_SECONDS:
        msg = "timestamp outside allowed window"
        raise AuthError(msg, code="EXPIRED_TIMESTAMP")

    body = await request.body()
    body_hash = hashlib.sha256(body).hexdigest()

    # docs/09-api/auth.md: request_path includes the query string.
    request_path = request.url.path
    if request.url.query:
        request_path = f"{request_path}?{request.url.query}"

    payload = _build_signature_payload(request.method, request_path, timestamp, body)
    if not _verify_signature(secret, payload, signature):
        msg = "HMAC signature mismatch"
        raise AuthError(msg, code="INVALID_SIGNATURE")

    # Reject exact replays within the valid window (docs/09-api/auth.md:68-75).
    _check_replay(api_key, timestamp, body_hash, now)

    return AuthenticatedPrincipal(key_id=api_key, scopes=scopes)


def require_scope(scope: str) -> Any:  # noqa: ANN401
    """Return a dependency that enforces a scope on the authenticated principal."""

    def _enforce(
        principal: Annotated[AuthenticatedPrincipal, Depends(authenticate_request)],
    ) -> AuthenticatedPrincipal:
        principal.require(scope)
        return principal

    return Depends(_enforce)


def auth_exception_handler(
    _request: Request,
    exc: AuthError | ScopeError,
) -> None:
    """Map auth exceptions to FastAPI HTTPException for exception handlers."""
    if isinstance(exc, ScopeError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
