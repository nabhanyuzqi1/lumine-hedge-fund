# Copyright (c) 2026 Lumine. All rights reserved.
"""First-party session auth — replaces the Authelia/Keycloak SSO stack.

Design (ADR: internal-session-auth):
- Users live in the ``users`` table (PostgreSQL); bootstrap users are
  seeded idempotently at startup from Settings (superadmin/admin/trader).
  When the database is unreachable the router falls back to the
  Settings-derived bootstrap credentials so the platform never locks out.
- Passwords are stored as PBKDF2-HMAC-SHA256 (hash + per-user salt).
- Sessions are stateless HMAC-SHA256 signed tokens (``lumine_session``
  HttpOnly cookie). No session table, no server-side state.
- ``GET /api/auth/verify?role=<role>`` is the Caddy ``forward_auth``
  target: returns 200 when a valid session satisfies the role gate and
  401 otherwise, so /superadmin, /novnc, /dozzle are protected at the
  reverse-proxy layer (defense in depth on top of SPA route guards).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from lumine.data.models import User
from lumine.data.session import get_sessionmaker
from lumine.shared.config import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_COOKIE = "lumine_session"
_PBKDF2_ITERATIONS = 200_000
_ROLE_LEVELS = {"user": 1, "admin": 2, "superadmin": 3}

# Bootstrap role table: username → (role, password setting field).
_BOOTSTRAP: tuple[tuple[str, str, str], ...] = (
    ("superadmin", "superadmin", "superadmin_password"),
    ("admin", "admin", "admin_password"),
    ("trader", "user", "trader_password"),
)


class LoginRequest(BaseModel):
    """Login payload (JSON body, no HMAC — first-party session flow)."""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


# ── Password hashing (stdlib only, no new deps) ───────────────────────


def hash_password(password: str, salt: str) -> str:
    """PBKDF2-HMAC-SHA256 hex digest with a fixed iteration count."""
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        _PBKDF2_ITERATIONS,
    )
    return digest.hex()


def new_salt() -> str:
    """Cryptographically random 16-byte salt (hex)."""
    return secrets.token_hex(16)


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """Constant-time comparison against the stored PBKDF2 hash."""
    actual = hash_password(password, salt)
    return hmac.compare_digest(actual, expected_hash)


# ── Session token (HMAC-SHA256 signed, stateless) ─────────────────────


def _token_body(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def issue_token(settings: Settings, username: str, role: str) -> str:
    """Sign a session token: ``base64url(json).hex(hmac_sha256)``."""
    payload = {
        "sub": username,
        "role": role,
        "exp": int(time.time()) + settings.session_ttl_seconds,
    }
    body = _token_body(payload)
    signature = hmac.new(
        settings.hmac_secret_key.encode("utf-8"),
        body.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"{body}.{signature}"


def parse_token(token: str, settings: Settings) -> dict[str, Any] | None:
    """Validate signature + expiry; return the payload or None."""
    if not token or "." not in token:
        return None
    body, signature = token.rsplit(".", 1)
    expected = hmac.new(
        settings.hmac_secret_key.encode("utf-8"),
        body.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body.encode("ascii")))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("exp", 0) < time.time():
        return None
    return payload


def _session_from_request(request: Request, settings: Settings) -> dict[str, Any] | None:
    token = request.cookies.get(SESSION_COOKIE)
    return parse_token(token, settings) if token else None


def _role_ok(payload_role: str, required: str | None) -> bool:
    if required is None:
        return True
    return _ROLE_LEVELS.get(payload_role, 0) >= _ROLE_LEVELS.get(required, 99)


# ── User store: PostgreSQL with Settings-bootstrap fallback ───────────


def _bootstrap_user(username: str, settings: Settings) -> dict[str, str] | None:
    """Resolve a bootstrap credential without touching the database."""
    for name, role, setting_field in _BOOTSTRAP:
        if name == username:
            password = getattr(settings, setting_field)
            # Deterministic per-deploy salt: stable within a deployment so
            # repeated logins compare against the same hash, but unique per
            # (deployment, user) and never stored as plaintext.
            salt = hashlib.sha256(f"{settings.hmac_secret_key}:{name}".encode()).hexdigest()[:32]
            return {
                "username": name,
                "role": role,
                "password_hash": hash_password(password, salt),
                "password_salt": salt,
            }
    return None


async def _db_user(username: str) -> dict[str, str] | None:
    """Look up a user in PostgreSQL. Returns None on any DB failure."""
    try:
        async with get_sessionmaker()() as session:
            row = await session.execute(select(User).where(User.username == username))
            user = row.scalar_one_or_none()
            if user is not None and user.is_active:
                return {
                    "username": user.username,
                    "role": user.role,
                    "password_hash": user.password_hash,
                    "password_salt": user.password_salt,
                }
    except Exception:
        logger.warning("auth: DB lookup failed for %r — falling back to bootstrap", username)
    return None


async def _find_user(username: str, settings: Settings) -> dict[str, str] | None:
    db_user = await _db_user(username)
    if db_user is not None:
        return db_user
    return _bootstrap_user(username, settings)


async def seed_bootstrap_users(settings: Settings) -> int:
    """Idempotent upsert of bootstrap users. Returns rows created (0 when
    the database is unavailable or all users already exist).
    """
    try:
        async with get_sessionmaker()() as session:
            created = 0
            for name, role, setting_field in _BOOTSTRAP:
                row = await session.execute(select(User).where(User.username == name))
                existing = row.scalar_one_or_none()
                if existing is None:
                    salt = new_salt()
                    password = getattr(settings, setting_field)
                    session.add(
                        User(
                            username=name,
                            role=role,
                            password_hash=hash_password(password, salt),
                            password_salt=salt,
                            is_active=True,
                        )
                    )
                    created += 1
            await session.commit()
            return created
    except Exception:
        logger.warning("auth: bootstrap seed skipped (DB unavailable)", exc_info=True)
        return 0


# ── Endpoints ──────────────────────────────────────────────────────────


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Authenticate and set the ``lumine_session`` HttpOnly cookie."""
    username = body.username.strip().lower()
    user = await _find_user(username, settings)
    if user is None or not verify_password(
        body.password, user["password_salt"], user["password_hash"]
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    token = issue_token(settings, user["username"], user["role"])
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        samesite="lax",
        path="/",
        secure=settings.session_cookie_secure,  # True di production (HTTPS via CF)
    )
    return {"username": user["username"], "role": user["role"]}


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    """Clear the session cookie."""
    response.set_cookie(
        key=SESSION_COOKIE,
        value="",
        max_age=0,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return {"ok": True}


@router.get("/me")
async def me(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Return the current session principal (SPA bootstraps from here).

    Sliding renewal (17 Aug 2026): setiap panggilan /me yang valid
    memperpanjang session TTL (rolling expiry) — selama user aktif memakai
    aplikasi, session tidak pernah kedaluwarsa → "sekali login, tidak
    pernah 401" (kecuali logout eksplisit). Hanya renew jika sisa waktu
    < 50% TTL (hindari re-set cookie tiap request).
    """
    payload = _session_from_request(request, settings)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
        )
    remaining = payload.get("exp", 0) - time.time()
    if remaining < settings.session_ttl_seconds / 2:
        token = issue_token(settings, payload["sub"], payload["role"])
        response.set_cookie(
            key=SESSION_COOKIE,
            value=token,
            max_age=settings.session_ttl_seconds,
            httponly=True,
            samesite="lax",
            path="/",
            secure=settings.session_cookie_secure,
        )
    return {"username": payload["sub"], "role": payload["role"]}


@router.get("/verify")
async def verify(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    role: str | None = None,
) -> dict[str, Any]:
    """Caddy ``forward_auth`` target + SPA guard endpoint.

    Returns 200 when a valid session exists and satisfies the optional
    ``?role=`` gate (user < admin < superadmin); 401 otherwise.
    """
    payload = _session_from_request(request, settings)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
        )
    if not _role_ok(payload["role"], role):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="insufficient role",
        )
    return {"ok": True, "username": payload["sub"], "role": payload["role"]}


# Re-export for the envelope/lifespan wiring tests.
__all__ = [
    "hash_password",
    "issue_token",
    "parse_token",
    "router",
    "seed_bootstrap_users",
    "verify_password",
]
