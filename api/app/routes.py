"""Dashboard-facing routes: auth, orders, positions, SSE stream."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import auth, bridge_stats, config, db, fail_reason, kill_switch, lot_sizing, market, market_status, risk_config, strategies, supervisor, totp
from . import symbol_sessions
from .auth import get_current_user, require_admin, require_csrf, require_2fa, require_2fa_control
from . import degradation_store
from .guardrail_ranges import (
    LLM_AUTO_LOT_RANGES,
    LLM_INTERVAL_RANGE_S,
    LLM_RISK_BOOL_KEYS,
    LLM_RISK_INT_KEYS,
    LLM_RISK_RANGES,
    TRIGGER_INT_KEYS,
    TRIGGER_RANGES,
    GuardrailRangeError,
    effective_interval_s,
    validate_auto_lot_updates,
    validate_interval_s,
    validate_llm_risk_updates,
    validate_trigger_updates,
)
from .regime_current import build_regime_snapshot
from .kill_switch import MODES, RECOVERY_CHECKLIST, SLIPPAGE_WARNING
from .portfolio_risk import (
    DEFAULT_PORTFOLIO_RISK,
    PORTFOLIO_LOCK_KEY,
    PortfolioFeed,
    collect_legs,
    collect_marks,
    gate_order,
    portfolio_config,
    portfolio_snapshot,
)
from .risk import RiskContext, SQL_EXCLUDE_QA_POSITION, risk_gate, symbol_spec
from .sse import broadcaster, sse_format
from .state_machine import fetchall, fetchone, transition
from .telegram_bot import notify_owner
from paper.backtest import canonical_tf, to_utc_candles
from paper.runner import db_timezone_offset_h
from strategies.broker_time import broker_utc_offset_hours

router = APIRouter()
logger = logging.getLogger(__name__)

# Kontrak 409 pasar tutup (dipakai UI OrderForm/Agent): bentuk body WAJIB
# {detail, code} di level atas supaya klien bisa membedakan penolakan pasar
# dari kegagalan validasi biasa (422).
MARKET_CLOSED_CODE = "market_closed"
MARKET_CLOSED_DETAIL = ("Market sedang tutup — order baru dinonaktifkan "
                        "hingga sesi buka")


# ---------------------------------------------------------------- auth

class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TwoFaCodeBody(BaseModel):
    code: str


async def _audit(conn, actor: str, role: str | None, action: str,
                 object: str | None = None, details: dict | None = None,
                 ip: str | None = None) -> None:
    """Append-only audit trail auth (PRD v2.2 §18)."""
    await conn.execute(
        """
        INSERT INTO audit_log (actor, actor_role, action, object, details, ip)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (actor, role, action, object, json.dumps(details or {}), ip),
    )


@router.post("/auth/login")
async def login(body: LoginBody, request: Request, response: Response):
    ip = request.client.host if request.client else "?"
    if auth.login_rate_limited(ip):
        raise HTTPException(status_code=429, detail="too many login attempts")
    auth.record_login_attempt(ip)
    # HTTPException di-raise SETELAH blok koneksi ditutup: pool psycopg
    # melakukan rollback bila exception keluar dari context manager, yang
    # sebelumnya menggulung-balik pencatatan login_failures + audit.
    locked_detail: str | None = None
    failed = False
    lock_alert: str | None = None
    user: dict | None = None
    token = csrf = ""
    async with db.pool().connection() as conn:
        # lockout dulu (sebelum verifikasi password) supaya akun terkunci
        # tidak bisa dipakai sebagai oracle password.
        failures = await auth.get_login_failures(conn, body.username)
        if auth.is_locked(failures):
            retry_after = max(1, int((failures["locked_until"].timestamp() - time.time()) / 60)) + 1
            locked_detail = f"account temporarily locked; retry in ~{retry_after} min"
        else:
            user = await fetchone(conn, "SELECT * FROM users WHERE username = %s", (body.username,))
            if user is None or not auth.verify_password(body.password, user["password_hash"]):
                failures = await auth.register_login_failure(conn, body.username)
                newly_locked = auth.is_locked(failures)
                await _audit(conn, body.username, None, "LOGIN_FAILED",
                             details={"locked": newly_locked}, ip=ip)
                failed = True
                # alert Telegram hanya untuk akun admin (anti-spam akun service)
                if newly_locked and user is not None and user.get("role") == "admin":
                    lock_alert = (
                        f"SECURITY: account '{body.username}' LOCKED after repeated "
                        f"failed logins ({failures['failed_count']} attempts). "
                        "Auto-expiry applies; verify this is you."
                    )
            else:
                # sukses: reset counter, rehash bcrypt legacy -> Argon2id
                await auth.clear_login_failures(conn, body.username)
                if auth.needs_rehash(user["password_hash"]):
                    await conn.execute(
                        "UPDATE users SET password_hash = %s WHERE id = %s",
                        (auth.hash_password(body.password), user["id"]),
                    )
                token, csrf = await auth.create_session(conn, user["id"])
                await _audit(conn, user["username"], user.get("role"), "LOGIN_SUCCESS", ip=ip)
    if locked_detail is not None:
        raise HTTPException(status_code=429, detail=locked_detail)
    if failed:
        if lock_alert:
            try:
                await notify_owner(lock_alert)
            except Exception:  # noqa: BLE001 - alert tidak boleh blok login
                pass
        raise HTTPException(status_code=401, detail="invalid credentials")
    auth.set_session_cookie(response, token, scheme=request.url.scheme)
    return {
        "username": user["username"],
        "csrf_token": csrf,
        "role": user.get("role"),
        "totp_enabled": bool(user.get("totp_enabled")),
        "env": config.FUND2_ENV,
    }


@router.post("/auth/logout")
async def logout(request: Request, response: Response, user: dict = Depends(require_csrf)):
    token = request.cookies.get(auth.SESSION_COOKIE, "")
    async with db.pool().connection() as conn:
        await conn.execute(
            "DELETE FROM sessions WHERE token_hash = %s",
            (auth._token_hash(token),),
        )
        await _audit(conn, user["username"], user.get("role"), "LOGOUT",
                     object=str(user.get("session_id")))
    auth.clear_session_cookie(response)
    return {"ok": True}


@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    two_fa_valid = False
    if user.get("totp_enabled") and user.get("2fa_passed_at") is not None:
        two_fa_valid = (time.time() - user["2fa_passed_at"].timestamp()) <= config.TWOFA_WINDOW_MIN * 60
    return {
        "username": user["username"],
        "csrf_token": user["csrf_token"],
        "role": user.get("role"),
        "totp_enabled": bool(user.get("totp_enabled")),
        "2fa_valid": two_fa_valid,
        "env": config.FUND2_ENV,
    }


# ------------------------------------------------- 2FA (step-up sensitif)
@router.post("/auth/2fa/setup")
async def twofa_setup(user: dict = Depends(require_csrf)):
    """Generate secret TOTP baru (belum aktif sampai /auth/2fa/enable)."""
    secret = totp.generate_secret()
    async with db.pool().connection() as conn:
        await conn.execute(
            "UPDATE users SET totp_secret = %s, totp_enabled = FALSE, "
            "totp_last_counter = -1 WHERE id = %s",
            (secret, user["user_id"]),
        )
        await _audit(conn, user["username"], user.get("role"), "2FA_SETUP")
    return {"secret": secret, "otpauth_uri": totp.provisioning_uri(secret, user["username"])}


@router.post("/auth/2fa/enable")
async def twofa_enable(body: TwoFaCodeBody, user: dict = Depends(require_csrf)):
    """Aktifkan 2FA dengan kode TOTP pertama dari authenticator app."""
    async with db.pool().connection() as conn:
        row = await fetchone(conn, "SELECT totp_secret FROM users WHERE id = %s", (user["user_id"],))
        secret = row["totp_secret"] if row else None
        if not secret:
            raise HTTPException(400, "call /auth/2fa/setup first")
        counter = totp.verify(secret, body.code)
        if counter is None:
            raise HTTPException(403, "invalid TOTP code")
        await conn.execute(
            "UPDATE users SET totp_enabled = TRUE, totp_last_counter = %s WHERE id = %s",
            (counter, user["user_id"]),
        )
        await _audit(conn, user["username"], user.get("role"), "2FA_ENABLED")
    return {"ok": True, "totp_enabled": True}


@router.post("/auth/2fa/disable")
async def twofa_disable(body: TwoFaCodeBody, user: dict = Depends(require_csrf)):
    """Nonaktifkan 2FA; butuh kode valid agar session thief tidak bisa matikan."""
    async with db.pool().connection() as conn:
        row = await fetchone(
            conn,
            "SELECT totp_secret, totp_enabled, totp_last_counter FROM users WHERE id = %s",
            (user["user_id"],),
        )
        if not row or not row["totp_enabled"]:
            raise HTTPException(400, "2FA not enabled")
        counter = totp.verify(row["totp_secret"], body.code,
                              last_counter=row["totp_last_counter"])
        if counter is None:
            raise HTTPException(403, "invalid TOTP code")
        await conn.execute(
            "UPDATE users SET totp_enabled = FALSE, totp_secret = NULL, "
            "totp_last_counter = -1 WHERE id = %s",
            (user["user_id"],),
        )
        await _audit(conn, user["username"], user.get("role"), "2FA_DISABLED")
    return {"ok": True, "totp_enabled": False}


@router.post("/auth/2fa/challenge")
async def twofa_challenge(body: TwoFaCodeBody, request: Request,
                          user: dict = Depends(require_csrf)):
    """Verifikasi kode TOTP -> assertion 2FA berlaku TWOFA_WINDOW_MIN menit."""
    retry_after = auth.action_rate_limited(
        f"2fa:{user['username']}", config.TWOFA_CHALLENGE_LIMIT, config.TWOFA_CHALLENGE_WINDOW_S)
    if retry_after:
        raise HTTPException(status_code=429,
                            detail=f"too many 2FA attempts; retry in {retry_after}s")
    ip = request.client.host if request.client else "?"
    not_enabled = invalid = False
    async with db.pool().connection() as conn:
        row = await fetchone(
            conn, "SELECT totp_secret, totp_enabled, totp_last_counter FROM users WHERE id = %s",
            (user["user_id"],),
        )
        if not row or not row["totp_enabled"]:
            not_enabled = True
        else:
            counter = totp.verify(row["totp_secret"], body.code,
                                  last_counter=row["totp_last_counter"])
            if counter is None:
                # audit ditulis dulu; raise-nya sesudah koneksi ditutup agar
                # tidak di-rollback pool (pola sama dengan login).
                await _audit(conn, user["username"], user.get("role"),
                             "2FA_CHALLENGE_FAILED", ip=ip)
                invalid = True
            else:
                await conn.execute(
                    "UPDATE sessions SET \"2fa_passed_at\" = now() WHERE id = %s",
                    (user["session_id"],),
                )
                await conn.execute(
                    "UPDATE users SET totp_last_counter = %s WHERE id = %s",
                    (counter, user["user_id"]),
                )
                await _audit(conn, user["username"], user.get("role"), "2FA_CHALLENGE_OK", ip=ip)
    if not_enabled:
        raise HTTPException(400, "2FA not enabled")
    if invalid:
        raise HTTPException(403, "invalid TOTP code")
    return {"ok": True, "window_minutes": config.TWOFA_WINDOW_MIN}


# ---------------------------------------------------------------- sessions
@router.get("/auth/sessions")
async def list_sessions(user: dict = Depends(get_current_user)):
    async with db.pool().connection() as conn:
        return await fetchall(
            conn,
            """
            SELECT id, created_at, expires_at, last_seen_at, "2fa_passed_at"
            FROM sessions WHERE user_id = %s ORDER BY last_seen_at DESC
            """,
            (user["user_id"],),
        )


@router.post("/auth/sessions/revoke-all")
async def revoke_all_sessions(request: Request, user: dict = Depends(require_csrf)):
    """Cabut SEMUA sesi user ini kecuali sesi saat ini (session hygiene)."""
    async with db.pool().connection() as conn:
        cur = await conn.execute(
            "DELETE FROM sessions WHERE user_id = %s AND id <> %s",
            (user["user_id"], user["session_id"]),
        )
        await _audit(conn, user["username"], user.get("role"), "SESSION_REVOKED",
                     details={"revoked": cur.rowcount})
    return {"ok": True, "revoked": cur.rowcount}


@router.get("/audit")
async def read_audit(limit: int = 50, user: dict = Depends(require_admin)):
    """Riwayat audit auth (admin only, terbaru dulu)."""
    async with db.pool().connection() as conn:
        return await fetchall(
            conn,
            "SELECT id, created_at, actor, actor_role, action, object, details, ip "
            "FROM audit_log ORDER BY id DESC LIMIT %s",
            (min(limit, 200),),
        )


# ---------------------------------------------------------------- orders

class OrderBody(BaseModel):
    symbol: str = Field(min_length=3, max_length=20)
    side: str
    volume: float
    sl: float
    tp: float
    strategy: str = "manual"
    # FUND2-LLM-B1 (t_9f36a70a): intent opsional 'layer' untuk menambah
    # posisi searah. Hanya dihormati untuk role agent / strategy llm;
    # role lain yang mengirim intent -> 422 (validasi di handler).
    intent: str | None = None


def _order_json(row: dict) -> dict:
    out = dict(row)
    for k in ("volume", "sl", "tp", "price_requested", "price_filled"):
        if out.get(k) is not None:
            out[k] = float(out[k])
    return out


async def _daily_pnl(conn) -> float:
    # t_4651d431: order QA (driver latensi, user role 'qa') bukan trafik live.
    # Posisi yang order-nya ditandai QA_REATTRIBUTED tidak dihitung daily_pnl
    # (insiden 25 Nov: 162 posisi QA closed -127.06 memicu drawdown halt palsu).
    # t_baeb3ce4: pengecualian diperluas ke semua order dari user role 'qa'
    # (username RECEIVED), mirror anomaly.SQL_EXCLUDE_QA -- lihat risk.py.
    row = await fetchone(
        conn,
        "SELECT COALESCE(SUM(profit), 0) AS pnl FROM positions p "
        "WHERE p.status = 'CLOSED' AND p.close_time::date = now()::date "
        + SQL_EXCLUDE_QA_POSITION,
    )
    return float(row["pnl"])


async def _orders_last_minute(conn) -> int:
    row = await fetchone(
        conn,
        "SELECT COUNT(*) AS n FROM orders WHERE created_at > now() - interval '60 seconds'",
    )
    return int(row["n"])


# RISK-D (t_a172bb7b): batas per-strategy (max posisi + rugi harian) dihitung
# dari order strategi itu saja. QA dikecualikan (pola sama dengan _daily_pnl:
# order driver QA bukan trafik live).
async def _strategy_open_positions(conn, strategy: str) -> int:
    row = await fetchone(
        conn,
        "SELECT COUNT(*) AS n FROM positions p "
        "JOIN orders o ON o.id = p.order_id "
        "WHERE p.status = 'OPEN' AND o.strategy = %s "
        + SQL_EXCLUDE_QA_POSITION,
        (strategy,),
    )
    return int(row["n"])


async def _strategy_daily_pnl(conn, strategy: str) -> float:
    row = await fetchone(
        conn,
        "SELECT COALESCE(SUM(p.profit), 0) AS pnl FROM positions p "
        "JOIN orders o ON o.id = p.order_id "
        "WHERE p.status = 'CLOSED' AND p.close_time::date = now()::date "
        "AND o.strategy = %s "
        + SQL_EXCLUDE_QA_POSITION,
        (strategy,),
    )
    return float(row["pnl"])


async def _open_exposure_usd(conn, settings: dict) -> float:
    """A4: notional terbuka AGREGAT lintas simbol (Σ lot × contract_size × harga).

    Harga mark = tick terbaru simbol (mid); fallback harga open posisi bila
    tick tidak ada. Simbol tanpa spec di-skip di sini karena gate menolaknya
    sendiri (fail-closed).
    """
    rows = await fetchall(
        conn,
        "SELECT symbol, volume, open_price FROM positions WHERE status = 'OPEN'",
    )
    total = 0.0
    for r in rows:
        spec = symbol_spec(r["symbol"], settings)
        if spec is None:
            continue
        tick = market.latest(r["symbol"])
        mark = (float(tick["bid"]) + float(tick["ask"])) / 2.0 if tick else float(r["open_price"])
        total += float(r["volume"]) * float(spec["contract_size"]) * mark
    return total


async def _equity_now(conn, settings: dict) -> float:
    """Equity = initial_balance + realized (semua closed) + floating (open).

    Sama dengan formula kill_switch.compute_metrics, versi ringan untuk gate.
    """
    row = await fetchone(
        conn,
        "SELECT "
        "(SELECT COALESCE(SUM(profit), 0) FROM positions WHERE status = 'CLOSED') + "
        "(SELECT COALESCE(SUM(profit), 0) FROM positions WHERE status = 'OPEN') AS pnl",
    )
    initial = float(settings.get("initial_balance", 10000.0))
    return initial + float(row["pnl"])


def _humanize_reason(value) -> str | None:
    """Satu elemen reasons -> string terbaca manusia, atau None bila kosong.

    AUDIT-B: payload event risk harus selalu `list[str]`; sebuah dict/objek
    bocor ke reasons akan dirender frontend jadi "[object Object]" lewat
    `String(r)`. Konvensi (keputusan desain CEO): string -> apa adanya;
    dict/objek -> `label: key=value; ...` (label dari field label/reason/
    message/code bila ada, bukan repr mentah); None/empty -> dibuang.
    """
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, dict):
        label = None
        for key in ("label", "reason", "message", "code"):
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                label = raw.strip()
                break
        parts = [
            f"{k}={v}" for k, v in value.items()
            if v is not None and v != "" and k not in ("label", "reason", "message", "code")
        ]
        body = "; ".join(parts)
        if label and body:
            return f"{label}: {body}"
        return label or body or None
    if isinstance(value, (list, tuple)):
        inner = [s for s in (_humanize_reason(v) for v in value) if s]
        return "; ".join(inner) or None
    text = str(value).strip()
    return text or None

def _humanize_reasons(reasons) -> list[str]:
    """Normalisasi list reasons apa pun -> list[str] terbaca manusia."""
    if not reasons:
        return []
    out: list[str] = []
    for item in reasons:
        if isinstance(item, (list, tuple)):
            # list di dalam list = satu reason multi-bagian, bukan banyak
            # reason: digabung jadi SATU string "a; b" (tidak di-flatten).
            inner = [s for s in (_humanize_reason(v) for v in item) if s]
            if inner:
                out.append("; ".join(inner))
            continue
        text = _humanize_reason(item)
        if text is not None:
            out.append(text)
    return out


@router.post("/orders")
async def create_order(body: OrderBody, request: Request, response: Response,
                       user: dict = Depends(require_csrf)):
    side = body.side.upper()
    if side not in ("BUY", "SELL"):
        raise HTTPException(422, "side must be BUY or SELL")
    if body.volume <= 0:
        raise HTTPException(422, "volume must be positive")
    if body.sl is None or body.tp is None:
        raise HTTPException(422, "SL and TP are mandatory")
    # FUND2-LLM-B1 (t_9f36a70a): intent hanya 'layer', hanya untuk role
    # agent / strategy llm; role lain yang mengirim intent -> 422.
    if body.intent is not None:
        if body.intent != "layer":
            raise HTTPException(422, "intent harus 'layer'")
        if user.get("role") != "agent" and body.strategy != "llm":
            raise HTTPException(
                422, "intent hanya dihormati untuk role agent / strategy llm")

    settings = await db.get_settings()
    if body.symbol not in (settings.get("allowed_symbols") or ["XAUUSD"]):
        raise HTTPException(422, f"symbol {body.symbol} not allowed")

    # MARKET-GATE (kartu candle pipeline): order BARU ditolak saat pasar tutup,
    # sebelum evaluasi lain (jangan bakar gate LLM/portfolio untuk order yang
    # pasti ditolak broker dengan retcode 10018). Hanya jalur order baru:
    # CLOSE/exit yang sudah ada tidak lewat endpoint ini, jadi tidak terblokir.
    # Status memakai fungsi yang sama dengan GET /market/status; penolakan
    # hanya dikirim bila jalur eksekusi ada (EA terhubung) — lihat
    # app.market_status.enforceable.
    market_state = await market_status.resolve(body.symbol)
    if (market_state["market_status"] == market_status.STATUS_CLOSED
            and market_status.enforceable()):
        detail = {
            "symbol": market_state["symbol"],
            "market_status": market_state["market_status"],
            "market_close_reason": market_state["market_close_reason"],
            "next_open_ts": market_state["next_open_ts"],
            "source": market_state["source"],
            "username": user["username"],
            "strategy": body.strategy,
        }
        logger.info("[orders] ditolak market_closed: %s", detail)
        broadcaster.publish({"type": "order_rejected", "code": MARKET_CLOSED_CODE,
                             **detail})
        return JSONResponse(
            status_code=409,
            content={"detail": MARKET_CLOSED_DETAIL, "code": MARKET_CLOSED_CODE},
        )

    # LLM (t_f2llm2): order milik agent LLM (role 'agent' ATAU strategy
    # 'llm') mendapat lapisan batas tambahan di atas gate umum. Import di
    # level fungsi: file ini sedang diedit paralel (RBAC), diff sengaja
    # minimal dan tidak menyentuh blok import modul.
    from .llm_risk import (breaker_alert_text, context_fields,
                           evaluate_llm_breaker, get_llm_agent_v2,
                           layer_gate_reason, llm_open_positions,
                           llm_order_stats, new_order_block_reason)

    is_llm = user.get("role") == "agent" or body.strategy == "llm"
    breaker_fired: list[dict] = []

    # FUND2-LLM-3 (t_d9e6b2a3): blackout kalender deterministik untuk order
    # BARU LLM saja (path ini memang hanya order baru; close/manual/backtest
    # tidak dievaluasi). Fetch kalender via cache 3600s di LUAR transaksi &
    # advisory-lock DB (network call), evaluasinya di dalam bersama gate lain.
    calendar_reject = None
    if is_llm:
        from .llm_risk import calendar_blackout_reason

        calendar_reject = await calendar_blackout_reason(
            settings, body.symbol, datetime.now(timezone.utc),
        )

    tick = market.latest(body.symbol)
    tick_age = (time.time() - tick["ts"]) if tick else None

    async with db.pool().connection() as conn:
        async with conn.transaction():
            # Serialisasi evaluasi risiko (PRD §7: race dua sinyal simultan
            # tidak boleh oversubscribe). Lock transaksi: dilepas otomatis
            # saat commit/rollback; request kedua membaca state hasil commit
            # request pertama.
            await conn.execute("SELECT pg_advisory_xact_lock(%s)", (PORTFOLIO_LOCK_KEY,))
            orders_last_min = await _orders_last_minute(conn)
            daily_pnl = await _daily_pnl(conn)
            open_exposure = await _open_exposure_usd(conn, settings)
            equity = await _equity_now(conn, settings)
            # RISK-D (t_a172bb7b): config risk efektif per strategi =
            # merge(global, override). Override divalidasi <= global (hard
            # ceiling) dan di-clamp saat dibaca, jadi pemakaian di bawah
            # tidak pernah melonggarkan gate global.
            order_strategy = (body.strategy or "manual").strip().lower()
            strat_risk = await risk_config.effective_for(
                conn, settings, order_strategy)
            automated = order_strategy not in ("", "manual")
            llm_fields: dict = {}
            if is_llm:
                llm_fields = context_fields(
                    settings,
                    await llm_order_stats(conn, settings),
                    kill_switch.ea_last_seen_age_s(),
                )
            order_dict = {
                "symbol": body.symbol,
                "side": side,
                "volume": body.volume,
                "sl": body.sl,
                "tp": body.tp,
                "strategy": body.strategy,
            }
            # RISK-A (t_8bf257a2): auto lot sizing deterministik untuk order
            # LLM (role 'agent' ATAU strategy 'llm') saat feature flag
            # 'llm_auto_lot.enabled' ON (DEFAULT OFF -- flag OFF = behavior
            # lama persis seperti sekarang: volume LLM dipakai apa adanya).
            # Lot dihitung dari jarak SL & %risk equity (0.5% default), bukan
            # tebakan LLM; gagal hitung (SL/tick/equity/spec tidak terbaca,
            # lot < min lot) = fail-closed -> order ditolak, BUKAN menebak.
            # Gate A5 di bawah tetap memvalidasi lot hasil hitung
            # (defense-in-depth). Entry = harga eksekusi (ask BUY, bid SELL),
            # konsisten dengan pengukuran jarak SL di A5.
            lot_reasons: list[str] = []
            lot_detail: dict | None = None
            auto_cfg = lot_sizing.auto_lot_config(settings)
            if is_llm and auto_cfg["enabled"]:
                entry = (tick["ask"] if side == "BUY" else tick["bid"]) if tick else None
                # Model biaya mirror portfolio gate: spread tick sekarang +
                # komisi round-turn per lot (slippage dibaca compute_lot
                # dari spec simbol) supaya lot 0.5% lolos worst-case gate.
                port_cfg = portfolio_config(settings)
                # RISK-A x RISK-D: risk_pct efektif = yang paling ketat antara
                # override per-strategy (<= global) dan override eksplisit
                # llm_auto_lot.risk_pct. Tidak ada jalur yang menaikkan risk.
                lot_risk_pct = min(float(strat_risk["values"]["risk_pct"]),
                                   float(auto_cfg["risk_pct"]))
                lot_res = lot_sizing.compute_lot(
                    symbol=body.symbol,
                    entry=entry,
                    sl=body.sl,
                    equity=equity,
                    risk_pct=lot_risk_pct,
                    spec=symbol_spec(body.symbol, settings),
                    spread_usd=(tick["ask"] - tick["bid"]) if tick else None,
                    commission_per_lot_usd=float(
                        port_cfg.get("commission_per_lot_usd", 0.0) or 0.0),
                )
                lot_detail = lot_res.detail
                lot_detail["risk_pct_source"] = strat_risk["sources"]["risk_pct"]
                lot_detail["strategy"] = order_strategy
                if lot_res.ok:
                    order_dict["volume"] = lot_res.lot
                else:
                    lot_reasons = list(lot_res.reasons)
            # Degradation (PRD §10.3): status strategi peng order. Order
            # manual/llm tanpa strategi terdaftar -> None (= NORMAL).
            deg_status = None
            if body.strategy and body.strategy not in ("manual", "llm"):
                deg_status = (await degradation_store.statuses(conn)).get(
                    body.strategy)
            # RISK-D: konteks gate per-strategy. Max posisi dihitung untuk
            # order strategi otomatis (manual bukan objek config strategi).
            # Batas rugi harian per-strategy hanya dikirim bila LEBIH KETAT
            # dari global: bila sama, gate drawdown global sudah menolak
            # dengan alasannya sendiri (tidak ada alasan duplikat).
            strat_open = 0
            strat_pnl = 0.0
            strat_loss_limit = None
            if automated:
                strat_open = await _strategy_open_positions(conn, order_strategy)
                limit = float(strat_risk["values"]["daily_loss_limit"])
                if limit < float(strat_risk["global"]["daily_loss_limit"]) - 1e-9:
                    strat_loss_limit = limit
                    strat_pnl = await _strategy_daily_pnl(conn, order_strategy)
            decision = risk_gate(
                order_dict,
                RiskContext(
                    settings=settings,
                    bid=tick["bid"] if tick else None,
                    ask=tick["ask"] if tick else None,
                    tick_age_s=tick_age,
                    daily_pnl=daily_pnl,
                    orders_last_minute=orders_last_min,
                    open_exposure_usd=open_exposure,
                    equity=equity,
                    degradation_status=deg_status,
                    strategy_id=order_strategy,
                    strategy_max_positions=(
                        int(strat_risk["values"]["max_positions"])
                        if automated else None),
                    strategy_open_positions=strat_open,
                    strategy_daily_loss_limit=strat_loss_limit,
                    strategy_daily_pnl=strat_pnl,
                    **llm_fields,
                ),
            )
            # Portfolio Risk Manager (PRD §7): lapisan agregat di atas gate
            # per-order — worst-case loss sampai SL semua posisi + pending/
            # SENT + kandidat, termasuk biaya+buffer, stress scenario, dan
            # batas portofolio. Gagal-aman: spec/tick value tak terverifikasi,
            # equity/margin hilang/stale, atau ada posisi tanpa SL -> tolak.
            portfolio = await gate_order(conn, order_dict, settings, equity)
            # Auto lot gagal dihitung = tolak order (fail-closed), alasan
            # digabung dengan gate lain; order tetap tercatat FAILED (audit).
            # AUDIT-B: reasons dipetakan ke list[str] terbaca manusia sebelum
            # masuk payload event / rejected_reasons; objek portfolio tidak
            # pernah masuk reasons (tetap terstruktur di payload.portfolio).
            all_reasons = _humanize_reasons(
                lot_reasons + list(decision.reasons) + portfolio.reasons)
            all_ok = decision.ok and portfolio.ok and not lot_reasons
            if calendar_reject:
                all_reasons = [_humanize_reason(calendar_reject)] + all_reasons
                all_ok = False
            # LLM v2 (FUND2-LLM-B1 D4): gate anti-spam order baru saat ada
            # posisi llm OPEN di simbol + gate layer (maks/rasio volume,
            # searah). Ini lapisan 2; lapisan 1 = pre-check di loop agent
            # sebelum POST /orders. Hanya untuk order LLM (role 'agent' ATAU
            # strategy 'llm') - order manual tidak terpengaruh.
            v2_reason = None
            if is_llm:
                v2_cfg = get_llm_agent_v2(settings)
                llm_positions = await llm_open_positions(conn, body.symbol)
                if body.intent == "layer":
                    v2_reason = layer_gate_reason(
                        llm_positions, v2_cfg, body.symbol, side,
                        float(order_dict["volume"]))
                else:
                    v2_reason = new_order_block_reason(
                        llm_positions, v2_cfg, body.symbol)
            if v2_reason:
                all_reasons = [_humanize_reason(v2_reason)] + all_reasons
                all_ok = False

            row = await fetchone(
                conn,
                """
                INSERT INTO orders (user_id, symbol, side, volume, sl, tp, strategy,
                                    price_requested, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'RECEIVED')
                RETURNING *
                """,
                (
                    user["user_id"], body.symbol, side, order_dict["volume"], body.sl, body.tp,
                    body.strategy, tick["ask"] if tick and side == "BUY" else (tick["bid"] if tick else None),
                ),
            )
            # creation event: from NULL -> RECEIVED (inserted directly, not via transition)
            await conn.execute(
                """
                INSERT INTO order_events (order_id, from_status, to_status, payload)
                VALUES (%s, NULL, 'RECEIVED', %s)
                """,
                (row["id"], json.dumps({"source": "api", "username": user["username"]})),
            )

            if decision.halt:
                # auto-halt drawdown (risk gate): mode WAJIB dari settings yang
                # sama dengan evaluator kill-switch (AUDIT-F2 #4) supaya satu
                # kondisi tidak punya dua mode (dulu hardcode GLOBAL_HALT).
                await kill_switch.activate(
                    await kill_switch.trigger_mode("daily_drawdown"),
                    reason="; ".join(decision.reasons),
                    source="auto:daily_drawdown_risk_gate",
                    actor="auto",
                )
                broadcaster.publish({"type": "halt", "reason": decision.reasons})

            event_payload = {
                "risk": "pass" if all_ok else "rejected",
                "reasons": all_reasons,
                "portfolio": asdict(portfolio.snapshot),
            }
            if body.intent is not None:
                # Audit intent layer (LLM v2): terlihat di event RECEIVED.
                event_payload["llm_intent"] = body.intent
            if lot_detail is not None:
                # Audit auto lot (RISK-A): bukti lot hasil hitung, bukan tebakan.
                event_payload["auto_lot"] = lot_detail
            if all_ok:
                await transition(conn, row["id"], "RISK_PASS", event_payload)
            else:
                # Constraint DB `orders_failed_requires_reason`: order FAILED
                # WAJIB membawa alasan. Tanpa ini penolakan gate berubah jadi
                # 500 (CheckViolation) dan alasan hilang dari tabel orders —
                # persis kelas bug "917 FAILED dengan fail_reason NULL".
                fail = fail_reason.from_reasons(
                    all_reasons, stage=fail_reason.STAGE_RISK_GATE)
                event_payload["fail"] = fail
                await transition(
                    conn, row["id"], "FAILED", event_payload,
                    set_fields={"fail_reason": fail_reason.render(fail),
                                "fail_detail": fail},
                    jsonb_fields=("fail_detail",),
                )
            final = await fetchone(conn, "SELECT * FROM orders WHERE id = %s", (row["id"],))

            if is_llm:
                # Breaker agent LLM dievaluasi setiap attempt (transaction
                # yang sama dgn order): 3 FAILED beruntun / drawdown harian
                # > 1.5% -> pause + alert (alert dikirim setelah commit).
                breaker_fired = await evaluate_llm_breaker(
                    conn=conn, settings=settings, notify=False,
                )

    if breaker_fired:
        await notify_owner(breaker_alert_text(breaker_fired))

    broadcaster.publish({"type": "order", "order_id": str(row["id"]), "status": final["status"]})
    payload = _order_json(final)
    if all_ok:
        response.status_code = 201
    else:
        response.status_code = 422
        payload["rejected_reasons"] = all_reasons
    return payload


@router.get("/orders")
async def list_orders(limit: int = 50, user: dict = Depends(get_current_user)):
    async with db.pool().connection() as conn:
        rows = await fetchall(
            conn,
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT %s",
            (min(limit, 200),),
        )
        # Event log per order (PRD P1b hari 9-10): buku besar event Riwayat.
        # Satu query untuk seluruh halaman, dikelompokkan per order_id.
        events: dict[str, list] = {}
        if rows:
            ev_rows = await fetchall(
                conn,
                """
                SELECT order_id, id, from_status, to_status, payload, created_at
                FROM order_events WHERE order_id = ANY(%s) ORDER BY id
                """,
                ([r["id"] for r in rows],),
            )
            for e in ev_rows:
                events.setdefault(e["order_id"], []).append(e)
    out = []
    for r in rows:
        order = _order_json(r)
        order["events"] = events.get(r["id"], [])
        out.append(order)
    return out


@router.get("/paper-orders")
async def list_paper_orders(limit: int = 100, strategy: str | None = None,
                            status: str | None = None,
                            user: dict = Depends(get_current_user)):
    """Buku besar PAPER (tabel paper_orders) — trade simulasi runner.

    Trade paper tidak pernah dikirim ke broker, jadi memang tidak muncul di
    GET /orders (ledger live). Tab "Paper" di Riwayat & Log membaca endpoint
    ini supaya P&L yang tampil di Strategy Lab bisa ditelusuri per trade.
    Read-only; filter opsional strategy/status.
    """
    clauses = ["mode = 'PAPER'"]
    args: list = []
    if strategy:
        clauses.append("strategy = %s")
        args.append(strategy)
    if status:
        clauses.append("status = %s")
        args.append(status.upper())
    args.append(min(max(limit, 1), 500))
    async with db.pool().connection() as conn:
        rows = await fetchall(
            conn,
            f"""
            SELECT id, strategy, symbol, side, volume, sl, tp, status,
                   entry_price, exit_price, profit, reason, risk_decision,
                   opened_at, closed_at, created_at, run_id
            FROM paper_orders WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC LIMIT %s
            """,
            tuple(args),
        )
    out = []
    for r in rows:
        row = dict(r)
        for k in ("volume", "sl", "tp", "entry_price", "exit_price", "profit"):
            if row.get(k) is not None:
                row[k] = float(row[k])
        out.append(row)
    return out


@router.get("/orders/{order_id}")
async def get_order(order_id: str, user: dict = Depends(get_current_user)):
    async with db.pool().connection() as conn:
        order = await fetchone(conn, "SELECT * FROM orders WHERE id = %s", (order_id,))
        if order is None:
            raise HTTPException(404, "order not found")
        events = await fetchall(
            conn,
            "SELECT id, from_status, to_status, payload, created_at "
            "FROM order_events WHERE order_id = %s ORDER BY id",
            (order_id,),
        )
    out = _order_json(order)
    out["events"] = events
    return out


# ---------------------------------------------------------------- strategies

class StrategyModeBody(BaseModel):
    mode: str


@router.get("/strategies")
async def list_strategies(user: dict = Depends(get_current_user)):
    """SATU sumber daftar strategi untuk Strategy Lab + Dashboard (AUDIT-C).

    Per strategi: mode (paper/live/off), lifecycle status supervisor,
    active/pause_reasons, P&L paper, winrate, equity_mini (<=30 titik), dan
    ringkasan shadow run terbaru. Panel paper/shadow Dashboard memfilter
    `mode` dari respons ini (bukan GET /shadow/runs) supaya daftarnya 1:1
    dengan Lab; /shadow/runs hanya untuk detail sinyal.
    """
    async with db.pool().connection() as conn:
        return await strategies.strategy_summaries(conn)


@router.post("/strategies/{strategy_id}/mode")
async def set_strategy_mode(strategy_id: str, body: StrategyModeBody,
                            user: dict = Depends(require_admin)):
    mode = (body.mode or "").strip().lower()
    if mode not in strategies.VALID_MODES:
        raise HTTPException(422, "mode harus salah satu dari paper | live | off")
    if mode == "live":
        # live approval (PRD §18): butuh step-up 2FA yang masih berlaku.
        auth.ensure_2fa(user)
    async with db.pool().connection() as conn:
        async with conn.transaction():
            summary = await strategies.set_mode(conn, strategy_id, mode)
            if summary is not None:
                await _audit(conn, user["username"], user.get("role"),
                             "APPROVAL" if mode == "live" else "CONFIG_CHANGED",
                             object=f"strategy:{strategy_id}", details={"mode": mode})
    if summary is None:
        raise HTTPException(404, "strategy not found")
    broadcaster.publish({"type": "strategy_mode", "strategy_id": strategy_id,
                         "mode": mode})
    return summary


# ------------------------------------------------- strategy isolation (PRD §5)

class StrategyLifecycleBody(BaseModel):
    to_status: str
    reason: str | None = None


@router.get("/strategies/supervisor")
async def supervisor_status(user: dict = Depends(get_current_user)):
    """Isolation supervisor: lifecycle + circuit breaker semua strategi (PRD v2.2 §5)."""
    async with db.pool().connection() as conn:
        return {"strategies": await supervisor.supervisor_states(conn)}


@router.get("/strategies/{strategy_id}/supervisor/events")
async def supervisor_events(strategy_id: str,
                            user: dict = Depends(get_current_user)):
    """Crash/fault/breaker/status terakhir untuk satu strategi (PRD 5.2)."""
    async with db.pool().connection() as conn:
        return {"strategy_id": strategy_id,
                "events": await supervisor.recent_events(conn, strategy_id)}


@router.post("/strategies/{strategy_id}/lifecycle")
async def transition_strategy_lifecycle(strategy_id: str,
                                        body: StrategyLifecycleBody,
                                        user: dict = Depends(require_admin)):
    """Transisi lifecycle strategi (PRD 5.3).

    Transisi yang menaikkan privilege trading (owner-only, PRD 5.3: 'hanya
    dapat dilakukan owner atau release workflow yang diotorisasi') menuntut
    step-up 2FA, selaras gerbang live di /strategies/{id}/mode.
    """
    target = (body.to_status or "").strip().upper()
    if target not in supervisor.LIFECYCLE_STATUSES:
        raise HTTPException(
            422, f"to_status harus salah satu dari {', '.join(supervisor.LIFECYCLE_STATUSES)}")
    async with db.pool().connection() as conn:
        state = await supervisor.get_strategy_state(conn, strategy_id)
        if state is None:
            raise HTTPException(404, "strategy not found")
        owner_gated = (state["status"], target) in supervisor.OWNER_ONLY_TRANSITIONS
        if owner_gated:
            auth.ensure_2fa(user)  # owner / release workflow (step-up 2FA)
        try:
            result = await supervisor.transition_strategy(
                conn, strategy_id, target,
                actor=user["username"], reason=body.reason or "",
                actor_role="owner" if owner_gated else "workflow")
            await _audit(conn, user["username"], user.get("role"),
                         "APPROVAL" if owner_gated else "CONFIG_CHANGED",
                         object=f"strategy:{strategy_id}",
                         details={"lifecycle": result["from"] + "->" + target,
                                  "reason": body.reason or ""})
        except supervisor.LifecycleError as exc:
            raise HTTPException(409, str(exc))
    broadcaster.publish({"type": "strategy_lifecycle", **result})
    return result


# ---------------------------------------------------------------- kill-switch

class KillSwitchBody(BaseModel):
    mode: str
    strategy: str | None = None
    confirm: bool = False
    reason: str | None = None


class ReleaseBody(BaseModel):
    checklist_ack: bool = False
    strategy: str | None = None
    # t_f2p5a1: harness QA (driver latensi) menandai event-nya dengan source
    # 'kanban:<card>' supaya alerts watcher melewatinya (anti-spam, lihat
    # alerts.py). Default tetap 'dashboard' untuk UI.
    source: str | None = None


class FlattenBody(BaseModel):
    confirm: bool = False
    # TOTP opsional: kalau dikirim, WAJIB valid (diverifikasi server-side,
    # anti-replay). Tutup celah QA UI-D6 [7_flatten_wrong_2FA]: sebelumnya
    # code salah di body diabaikan selama jendela 2FA sesi masih terbuka.
    code: str | None = None
    # t_fp5a1: source opsional untuk harness QA (anti-spam alert).
    source: str | None = None


class TriggersBody(BaseModel):
    # Konfirmasi ulang password (opsional di API demi kompatibilitas klien
    # lama, WAJIB dikirim UI admin): bila dikirim, password diverifikasi
    # server-side dan password salah -> 403 tanpa menyimpan apa pun.
    password: str | None = None
    # SATU-SATUNYA ambang drawdown harian yang memicu auto-halt: dibaca
    # gate order, breaker LLM, dan evaluator kill-switch (AUDIT-A2).
    daily_drawdown_pct: float | None = None
    total_drawdown_pct: float | None = None
    ea_offline_seconds: float | None = None
    # Ambang GLOBAL_HALT EA offline (terpisah dari ambang tandai offline A12).
    ea_offline_halt_seconds: float | None = None
    ea_offline_requires_positions: bool | None = None
    consecutive_failed_orders: int | None = None
    position_mismatch: bool | None = None
    check_interval_seconds: float | None = None
    modes: dict[str, str] | None = None


@router.get("/kill-switch")
async def kill_switch_status(user: dict = Depends(get_current_user)):
    state = await kill_switch.get_state()
    triggers = await kill_switch.get_triggers()
    paused = await kill_switch.get_paused_strategies()
    async with db.pool().connection() as conn:
        metrics = await kill_switch.compute_metrics(conn)
        events = await fetchall(
            conn,
            "SELECT action, mode, strategy, source, actor, reason, details, created_at "
            "FROM kill_switch_events ORDER BY id DESC LIMIT 20",
        )
    return {
        "state": state,
        "paused_strategies": paused,
        "triggers": triggers,
        "metrics": metrics,
        "bridge_requests": bridge_stats.snapshot(),
        "events": events,
        "recovery_checklist": RECOVERY_CHECKLIST,
        "slippage_warning": SLIPPAGE_WARNING,
    }


@router.post("/kill-switch")
async def kill_switch_activate(body: KillSwitchBody, user: dict = Depends(require_admin)):
    """Aktivasi kill-switch = emergency stop: sengaja TANPA 2FA (PRD §18
    mensyaratkan 2FA untuk flatten/release, bukan aktivasi) supaya
    proteksi posisi tidak pernah tertahan enrolment/challenge 2FA.
    Tetap wajib admin + CSRF."""
    if body.mode not in MODES:
        raise HTTPException(422, f"mode harus salah satu dari {MODES}")
    if body.mode == "PAUSE_STRATEGY" and not (body.strategy or "").strip():
        raise HTTPException(422, "PAUSE_STRATEGY membutuhkan nama strategi")
    if body.mode == "STOP_AND_FLATTEN" and not body.confirm:
        raise HTTPException(400, SLIPPAGE_WARNING)
    actor = user.get("username", "unknown")

    if body.mode == "PAUSE_STRATEGY":
        state = await kill_switch.pause_strategy(
            (body.strategy or "").strip(), source="dashboard", actor=actor, reason=body.reason,
        )
        return {"state": state, "paused_strategies": await kill_switch.get_paused_strategies()}

    state = await kill_switch.activate(
        body.mode, reason=body.reason, source="dashboard", actor=actor,
    )
    flat: list[dict] = []
    if body.mode == "STOP_AND_FLATTEN":
        flat = await kill_switch.flatten_positions(actor=actor, source="dashboard")
    return {"state": state, "flatten": {"requested": len(flat), "orders": flat}}


@router.post("/kill-switch/release")
async def kill_switch_release(body: ReleaseBody, user: dict = Depends(require_2fa)):
    """Release kill-switch: PRD §18 mewajibkan 2FA; HANYA owner/admin.

    Keputusan owner 25 Nov 2026 (kartu t_7c070c31): driver QA TIDAK boleh
    me-release kill-switch. Dulu role 'qa' diizinkan (t_4651d431) sehingga
    driver me-release halt tiap ~2 menit -> flapping 34x ACTIVATE / 33x
    RELEASE + spam alert Telegram. Kini: admin + 2FA, dan source dipaksa
    'dashboard' (source kanban:/auto: dari klien ditolak 403).
    """
    actor = user.get("username", "unknown")
    if body.source and body.source.strip() != "dashboard":
        raise HTTPException(
            403, "release hanya sah dari dashboard owner/admin ber-2FA (source ditolak)"
        )
    try:
        state = await kill_switch.release(
            checklist_ack=body.checklist_ack, strategy=body.strategy,
            source="dashboard", actor=actor,
        )
    except kill_switch.ReleaseForbidden as exc:
        raise HTTPException(403, str(exc))
    except PermissionError as exc:
        raise HTTPException(400, {
            "message": str(exc),
            "recovery_checklist": RECOVERY_CHECKLIST,
            "hint": "Penuhi checklist recovery lalu kirim checklist_ack=true",
        })
    return {"state": state, "paused_strategies": await kill_switch.get_paused_strategies()}


async def _verify_totp_request(user: dict, code: str | None, *, object: str) -> None:
    """Verifikasi TOTP per-request untuk aksi sensitif (PRD v2.2 §18).

    Kalau client mengirim `code`, kode itu WAJIB diverifikasi server-side
    (anti-replay via users.totp_last_counter); kode salah -> 403 dan aksi
    TIDAK dijalankan. Kalau tidak dikirim, assertion 2FA sesi berlaku
    (window TWOFA_WINDOW_MIN sejak /auth/2fa/challenge, di-enforce
    require_2fa di Depends).
    """
    if not code:
        return
    invalid = False
    async with db.pool().connection() as conn:
        row = await fetchone(
            conn,
            "SELECT totp_secret, totp_enabled, totp_last_counter FROM users WHERE id = %s",
            (user["user_id"],),
        )
        if row and row["totp_enabled"]:
            counter = totp.verify(row["totp_secret"], code,
                                  last_counter=row["totp_last_counter"])
        else:
            counter = None
        if counter is None:
            # audit ditulis di dalam koneksi (pola sama dengan /auth/2fa/challenge)
            await _audit(conn, user["username"], user.get("role"),
                         "2FA_VERIFY_FAILED", object=object)
            invalid = True
        else:
            await conn.execute(
                "UPDATE users SET totp_last_counter = %s WHERE id = %s",
                (counter, user["user_id"]),
            )
    if invalid:
        raise HTTPException(403, "invalid TOTP code")


@router.post("/kill-switch/flatten")
async def kill_switch_flatten(body: FlattenBody, user: dict = Depends(require_2fa_control)):
    """Flatten semua posisi: PRD §18 mewajibkan 2FA.

    t_4651d431: role 'qa' juga diizinkan (driver QA latensi login pakai
    user QA khusus, bukan admin, supaya order QA terpisah dari order live).
    `code` TOTP di body (jika dikirim) diverifikasi server-side di sini,
    bukan hanya di dialog UI: code salah -> 403 tanpa flatten."""
    if not body.confirm:
        raise HTTPException(400, SLIPPAGE_WARNING)
    await _verify_totp_request(user, body.code, object="kill-switch:flatten")
    actor = user.get("username", "unknown")
    flat = await kill_switch.flatten_positions(actor=actor, source=body.source or "dashboard")
    return {"flatten": {"requested": len(flat), "orders": flat}}


def _trigger_previous(current: dict, patch: dict) -> dict:
    """Nilai LAMA untuk tiap key yang diubah (audit harus from -> to)."""
    previous: dict = {}
    for key, value in patch.items():
        if key == "modes":
            current_modes = current.get("modes") or {}
            previous["modes"] = {t: current_modes.get(t) for t in value}
        else:
            previous[key] = current.get(key)
    return previous


async def _record_triggers_updated(conn, *, actor: str, updates: dict,
                                   previous: dict, source: str,
                                   channel: str) -> None:
    """Satu bentuk jejak audit `TRIGGERS_UPDATED` untuk kedua kanal tulis.

    kartu t_dc104883: `PUT /admin/risk-settings` dan `PUT /kill-switch/triggers`
    menulis objek yang sama, jadi event-nya wajib punya bentuk identik
    (`details` selalu `{updates, previous}`, mode/strategy selalu NULL).
    `source` + `channel` hanya menjelaskan kanal asal perubahan.
    """
    await kill_switch.record_event(
        conn, "TRIGGERS_UPDATED", None,
        source=source, actor=actor,
        reason=(f"auto-trigger diubah oleh {actor} via {channel}: "
                f"{', '.join(sorted(updates))}"),
        details={"updates": updates, "previous": previous},
    )


@router.put("/kill-switch/triggers", deprecated=True)
async def kill_switch_update_triggers(body: TriggersBody, request: Request,
                                      user: dict = Depends(require_2fa)):
    """DEPRECATED — jalur resmi auto-trigger adalah `PUT /admin/risk-settings`.

    Jalur tulis Ops lama untuk objek `kill_switch_triggers` (kartu t_dc104883).
    Dipertahankan untuk klien lama, tetapi kini tunduk pada aturan yang SAMA
    dengan kanal Guardrail:

    - validasi rentang lewat satu fungsi bersama
      (`app.guardrail_ranges.validate_trigger_updates`): nilai di luar rentang
      wajar ditolak 422 dengan pesan per field, tidak ada yang tersimpan;
    - `password` WAJIB (re-auth akun admin) di samping sesi 2FA; password
      salah menolak seluruh perubahan (403) + audit `RISK_SETTINGS_REJECTED`;
    - event `TRIGGERS_UPDATED` memakai bentuk identik dengan kanal admin;
    - setiap pemakaian dicatat sebagai warning di log aplikasi.

    Pengecualian password hanya untuk pemanggil SERVICE TOKEN, dan jalur itu
    sengaja tidak dibuka di sini: tidak ada EA/CLI di repo ini yang memanggil
    endpoint ini, dan memberi token bridge wewenang tulis guardrail akan
    memperluas wewenang mesin, bukan menutup celah. Klien sesi user tidak
    pernah boleh menulis guardrail tanpa verifikasi ulang password.
    """
    logger.warning(
        "DEPRECATED PUT /kill-switch/triggers dipakai oleh %s (client=%s); "
        "UI wajib menulis auto-trigger lewat PUT /admin/risk-settings",
        user.get("username", "unknown"), request.headers.get("x-fund2-client", "-"),
    )
    updates = body.model_dump(exclude_none=True)
    updates.pop("password", None)
    if not updates:
        raise HTTPException(400, "tidak ada nilai yang dikirim")
    if not body.password:
        raise HTTPException(
            422,
            "password wajib untuk mengubah auto-trigger lewat endpoint "
            "deprecated ini; UI wajib memakai PUT /admin/risk-settings",
        )
    async with db.pool().connection() as conn:
        row = await fetchone(conn, "SELECT password_hash FROM users WHERE id = %s",
                             (user["user_id"],))
    if not row or not auth.verify_password(body.password, row["password_hash"]):
        async with db.pool().connection() as conn:
            await _audit(conn, user.get("username", "unknown"), user.get("role"),
                         "RISK_SETTINGS_REJECTED", object="kill_switch_triggers",
                         details={"reason": "wrong password",
                                  "keys": sorted(updates)})
        raise HTTPException(403, "password salah")
    # Rentang angka + modes = SATU fungsi bersama `PUT /admin/risk-settings`
    # (app.guardrail_ranges). Tanpa ini endpoint ini bisa menyimpan DD 500%.
    try:
        updates = validate_trigger_updates(updates, allowed_modes=set(MODES))
    except GuardrailRangeError as exc:
        raise HTTPException(422, str(exc)) from exc
    current = await kill_switch.get_triggers()
    previous = _trigger_previous(current, updates)
    for key, value in updates.items():
        if key == "modes":
            current["modes"].update(value)
        else:
            current[key] = value
    actor = user.get("username", "unknown")
    await db.set_setting("kill_switch_triggers", current, actor=actor)
    async with db.pool().connection() as conn:
        await _record_triggers_updated(
            conn, actor=actor, updates=updates, previous=previous,
            source="dashboard:ops-legacy", channel="PUT /kill-switch/triggers",
        )
        await _audit(conn, user["username"], user.get("role"), "CONFIG_CHANGED",
                     object="kill_switch_triggers", details={"updates": updates})
    return {"triggers": current}


RISK_SETTING_RANGES: dict = {
    # Rentang kewajaran (bukan policy): mencegah salah ketik mematikan gate.
    "max_volume": (0.01, 100.0),
    "max_orders_per_min": (1, 600),
    # Field profil (USD). BUKAN pemicu blokir/halt: satu-satunya pemicu
    # auto-halt drawdown = kill_switch_triggers.daily_drawdown_pct (AUDIT-A2).
    # Tetap divalidasi agar nilai profil tidak salah ketik.
    "max_daily_drawdown": (1.0, 1e9),
    "max_spread": (0.0001, 1e6),
    "max_tick_age_s": (0.1, 3600.0),
}

# Key guardrail inti (PRD §14; nilai final KEPUTUSAN_OWNER.md §I) + key
# auto-trigger yang perubahannya juga harus terlihat operator di halaman admin.
RISK_SETTING_KEYS: tuple[str, ...] = tuple(RISK_SETTING_RANGES)
GUARDRAIL_AUDIT_KEYS: tuple[str, ...] = (
    *RISK_SETTING_KEYS, "kill_switch_triggers", "portfolio_risk",
    # Setelan agent LLM (kartu t_f412fd48): kanal tulisnya sama dengan
    # guardrail, jadi riwayat auditnya juga harus muncul di halaman admin.
    # `llm_agent_interval_s` = key kanonik interval siklus (AUDIT-E t_bb927ec7).
    "llm_risk", "llm_auto_lot", "llm_interval_s", "llm_agent_interval_s",
    # Jadwal analisa simbol (parallel/hybrid/weekend_only/custom): perubahan
    # jadwal = perubahan perilaku agent, jadi harus terekam di audit.
    "llm_symbol_policy",
)


def _ranges_payload(ranges: dict) -> dict:
    """Rentang {key: (lo, hi)} -> {key: {min, max}} untuk JSON."""
    return {k: {"min": lo, "max": hi} for k, (lo, hi) in ranges.items()}


@router.get("/admin/risk-settings")
async def read_risk_settings(user: dict = Depends(require_admin)):
    """Nilai guardrail inti yang AKTIF (read-only) untuk halaman admin UI.

    Sumber tunggal = tabel `settings` (bukan defaults kode): operator harus
    melihat angka yang benar-benar ditegakkan risk gate, beserta rentang
    kewajaran yang akan divalidasi `PUT /admin/risk-settings`, supaya form
    tidak perlu menebak batas. `defaults` hanya referensi; endpoint ini
    TIDAK pernah menulis apa pun.
    """
    settings = await db.get_settings()
    values = {
        k: settings.get(k, db.DEFAULT_SETTINGS.get(k)) for k in RISK_SETTING_KEYS
    }
    # Import lokal: llm_risk mengimpor modul risk/drawdown dan dipakai jalur
    # order; impor di dalam handler menghindari siklus impor saat startup.
    from .llm_risk import get_llm_agent_v2, get_llm_risk
    triggers = await kill_switch.get_triggers()
    auto_lot = lot_sizing.auto_lot_config(settings)
    specs = settings.get("symbol_specs") or {}
    vol_caps = {}
    for sym, spec in specs.items():
        if not isinstance(spec, dict):
            continue
        try:
            vol_caps[sym] = min(float(values.get("max_volume") or 0.0),
                                float(spec.get("vol_max_lot") or 0.0)) or None
        except (TypeError, ValueError):
            vol_caps[sym] = None
    return {
        "values": values,
        "defaults": {k: db.DEFAULT_SETTINGS.get(k) for k in RISK_SETTING_KEYS},
        "ranges": {
            k: {"min": lo, "max": hi} for k, (lo, hi) in RISK_SETTING_RANGES.items()
        },
        # Topi lot EFEKTIF per simbol = min(max_volume akun, vol_max_lot simbol).
        # Gate menegakkan keduanya (risk.py A3), jadi UI harus menampilkan angka
        # yang benar-benar berlaku, bukan hanya knob akun.
        "symbol_specs": {
            sym: {k: spec.get(k) for k in
                  ("vol_min_lot", "vol_max_lot", "lot_step")}
            for sym, spec in specs.items() if isinstance(spec, dict)
        },
        "effective_max_volume": vol_caps,
        "risk_per_trade_pct": settings.get("risk_per_trade_pct"),
        "portfolio_risk": settings.get("portfolio_risk"),
        # Auto-trigger: nilai efektif + rentang yang dipakai validasi server.
        # Dibaca dari kill_switch.get_triggers() (sumber yang sama dengan
        # monitor) supaya halaman admin tidak menampilkan angka basi.
        "triggers": {k: triggers.get(k) for k in TRIGGER_RANGES},
        "trigger_ranges": _ranges_payload(TRIGGER_RANGES),
        "trigger_modes": triggers.get("modes") or {},
        # Setelan agent LLM (kartu t_f412fd48). Satu objek `llm` supaya UI
        # tidak perlu tiga endpoint; semua key di sini bisa ditulis lewat
        # PUT /admin/risk-settings dengan password + 2FA.
        "llm": {
            "risk": {**get_llm_risk(settings), **get_llm_agent_v2(settings)},
            "risk_ranges": _ranges_payload(LLM_RISK_RANGES),
            "risk_bool_keys": sorted(LLM_RISK_BOOL_KEYS),
            "risk_int_keys": sorted(LLM_RISK_INT_KEYS),
            "auto_lot": auto_lot,
            "auto_lot_ranges": _ranges_payload(LLM_AUTO_LOT_RANGES),
            "interval_s": effective_interval_s(settings),
            "interval_range_s": {
                "min": LLM_INTERVAL_RANGE_S[0], "max": LLM_INTERVAL_RANGE_S[1],
            },
            # Jadwal analisa simbol: nilai aktif + pilihan mode + label hari,
            # supaya UI tidak perlu menduplikasi daftar mode/hari.
            "symbol_policy": symbol_sessions.normalize_policy(
                settings.get("llm_symbol_policy")),
            "symbol_policy_modes": [
                {"value": mode, "label": symbol_sessions.MODE_LABEL[mode]}
                for mode in symbol_sessions.MODES
            ],
            "symbol_policy_days": list(symbol_sessions.DAYS),
        },
        "owner_decision": "KEPUTUSAN_OWNER.md §I",
    }


@router.get("/admin/settings-audit")
async def read_settings_audit(limit: int = 20, user: dict = Depends(require_admin)):
    """Riwayat perubahan guardrail dari `settings_audit` (terbaru dulu).

    Trigger DB `settings_audit_trail` menulis satu baris per key setiap
    INSERT/UPDATE settings: `old_value` -> `new_value`, aktor `changed_by`,
    dan `source`. Halaman admin memakainya untuk bukti audit setelah simpan;
    endpoint ini read-only dan dibatasi 200 baris.
    """
    async with db.pool().connection() as conn:
        rows = await fetchall(
            conn,
            "SELECT id, key, old_value, new_value, changed_by, source, changed_at "
            "FROM settings_audit WHERE key = ANY(%s) ORDER BY id DESC LIMIT %s",
            (list(GUARDRAIL_AUDIT_KEYS), min(max(limit, 1), 200)),
        )
    return {"keys": list(GUARDRAIL_AUDIT_KEYS), "rows": rows}


class RiskSettingsBody(BaseModel):
    """Body ubah guardrail risiko inti (PRD §14, §18).

    `password` wajib: konfirmasi ulang password akun admin di samping sesi
    2FA aktif. Nilai final guardrail ada di `KEPUTUSAN_OWNER.md` §I.
    """

    password: str = Field(min_length=1, max_length=256)
    max_volume: float | None = None
    max_orders_per_min: int | None = None
    # Profil USD (info). Tidak memicu halt maupun blokir order; auto-halt
    # hanya dari kill_switch_triggers.daily_drawdown_pct (AUDIT-A2).
    max_daily_drawdown: float | None = None
    max_spread: float | None = None
    max_tick_age_s: float | None = None
    portfolio_risk: dict | None = None
    # Auto-trigger kill-switch (satu objek, merge parsial terhadap nilai
    # aktif). Jalur tulis lama `PUT /kill-switch/triggers` deprecated; seluruh
    # UI memakai field ini supaya password + 2FA + audit + rentang identik.
    kill_switch_triggers: dict | None = None
    # Setelan agent LLM (kartu t_f412fd48): batas order agent, auto-lot, dan
    # interval siklus (detik; floor 30 s). Semua merge parsial.
    llm_risk: dict | None = None
    llm_auto_lot: dict | None = None
    llm_interval_s: float | None = None
    # Jadwal analisa simbol (kartu jadwal): parallel | hybrid | weekend_only |
    # custom. Hanya menentukan siapa yang dipanggil LLM; gate order tetap
    # memutuskan sendiri apakah pasar bisa ditradingkan.
    llm_symbol_policy: dict | None = None


@router.put("/admin/risk-settings")
async def update_risk_settings(body: RiskSettingsBody, user: dict = Depends(require_2fa)):
    """Ubah guardrail risiko inti: password ulang + 2FA + audit (PRD §14, §18).

    Ini kanál resmi perubahan guardrail dari UI admin; `psql` langsung
    dilarang karena melewati audit aplikasi dan validasi policy. Audit
    ditulis dua lapis: `audit_log` (aksi CONFIG_CHANGED) dan trigger
    `settings_audit` yang mencatat nilai lama -> baru per key.
    """
    updates = body.model_dump(exclude_none=True)
    updates.pop("password", None)
    if not updates:
        raise HTTPException(400, "tidak ada nilai yang dikirim")

    async with db.pool().connection() as conn:
        row = await fetchone(conn, "SELECT password_hash FROM users WHERE id = %s",
                             (user["user_id"],))
    if not row or not auth.verify_password(body.password, row["password_hash"]):
        async with db.pool().connection() as conn:
            await _audit(conn, user.get("username", "unknown"), user.get("role"),
                         "RISK_SETTINGS_REJECTED", object="risk_settings",
                         details={"reason": "wrong password", "keys": sorted(updates)})
        raise HTTPException(403, "password salah")

    for key, (lo, hi) in RISK_SETTING_RANGES.items():
        if key in updates:
            val = float(updates[key])
            if not (lo <= val <= hi):
                raise HTTPException(422, f"{key} di luar rentang wajar ({lo}..{hi})")
            updates[key] = int(round(val)) if key == "max_orders_per_min" else val
    if "portfolio_risk" in updates:
        incoming = updates["portfolio_risk"]
        if not isinstance(incoming, dict):
            raise HTTPException(422, "portfolio_risk harus objek")
        # Baris DB boleh parsial (pola "merge parsial: key DB menang"); tanpa
        # lapisan default, key yang tidak disebut hilang dari DB dan gate
        # portfolio_risk jatuh ke nilai modul yang tak terlihat di audit.
        stored = (await db.get_settings()).get("portfolio_risk") or {}
        merged = {**DEFAULT_PORTFOLIO_RISK, **stored, **incoming}
        stress_in = incoming.get("stress")
        merged["stress"] = {
            **DEFAULT_PORTFOLIO_RISK.get("stress", {}),
            **(stored.get("stress") or {}),
            **(stress_in if isinstance(stress_in, dict) else {}),
        }
        updates["portfolio_risk"] = merged

    previous: dict = {}
    current_settings = await db.get_settings()

    # ── auto-trigger kill-switch: satu kanal tulis (kartu t_f412fd48) ──
    # Merge parsial di atas nilai AKTIF (bukan default kode), validasi lewat
    # fungsi yang sama dengan `PUT /kill-switch/triggers`, lalu tulis sebagai
    # satu key settings supaya trigger settings_audit mencatat old -> new.
    trigger_patch: dict = {}
    trigger_previous: dict = {}
    if "kill_switch_triggers" in updates:
        incoming = updates["kill_switch_triggers"]
        if not isinstance(incoming, dict):
            raise HTTPException(422, "kill_switch_triggers harus objek")
        # Satu validator untuk kedua kanal tulis (kartu t_dc104883): rentang
        # angka DAN mode sah diperiksa di sini, bukan diduplikasi.
        try:
            trigger_patch = validate_trigger_updates(
                incoming, allowed_modes=set(MODES))
        except GuardrailRangeError as exc:
            raise HTTPException(422, str(exc)) from exc
        current_triggers = await kill_switch.get_triggers()
        trigger_previous = _trigger_previous(current_triggers, trigger_patch)
        merged = {**current_triggers,
                  **{k: v for k, v in trigger_patch.items() if k != "modes"}}
        if "modes" in trigger_patch:
            merged["modes"] = {**(current_triggers.get("modes") or {}),
                               **trigger_patch["modes"]}
        updates["kill_switch_triggers"] = merged

    # ── setelan agent LLM: llm_risk / llm_auto_lot / interval siklus ──
    if "llm_risk" in updates:
        if not isinstance(updates["llm_risk"], dict):
            raise HTTPException(422, "llm_risk harus objek")
        try:
            patch = validate_llm_risk_updates(updates["llm_risk"])
        except GuardrailRangeError as exc:
            raise HTTPException(422, str(exc)) from exc
        stored = current_settings.get("llm_risk") or {}
        updates["llm_risk"] = {**stored, **patch}
        # Rate limit agent tidak boleh lebih longgar dari rate limit akun:
        # gate menegakkan yang core, jadi angka di atasnya tidak akan pernah
        # tercapai dan UI akan menampilkan batas yang menyesatkan.
        if "max_orders_per_min" in patch:
            core_raw = current_settings.get("max_orders_per_min",
                                            db.DEFAULT_SETTINGS.get("max_orders_per_min"))
            try:
                core_rate_f = float(core_raw) if core_raw is not None else None
            except (TypeError, ValueError):
                core_rate_f = None
            if core_rate_f is not None and float(patch["max_orders_per_min"]) > core_rate_f:
                raise HTTPException(
                    422,
                    f"llm_risk.max_orders_per_min ({patch['max_orders_per_min']}) "
                    f"melebihi batas akun max_orders_per_min ({core_rate_f:g}); "
                    "turunkan batas akun dulu atau pakai angka <= batas akun")
    if "llm_auto_lot" in updates:
        if not isinstance(updates["llm_auto_lot"], dict):
            raise HTTPException(422, "llm_auto_lot harus objek")
        try:
            patch = validate_auto_lot_updates(updates["llm_auto_lot"])
        except GuardrailRangeError as exc:
            raise HTTPException(422, str(exc)) from exc
        # Override di atas risk_per_trade_pct tidak pernah menaikkan risiko
        # (order path memakai min), jadi simpan nilai itu = kontrol palsu.
        if patch.get("risk_pct") is not None:
            try:
                global_pct = float(current_settings.get(
                    "risk_per_trade_pct",
                    db.DEFAULT_SETTINGS.get("risk_per_trade_pct", 0.5)))
            except (TypeError, ValueError):
                global_pct = 0.5
            if float(patch["risk_pct"]) > global_pct + 1e-9:
                raise HTTPException(
                    422,
                    f"llm_auto_lot.risk_pct ({patch['risk_pct']}) melebihi "
                    f"risk_per_trade_pct global ({global_pct:g}); override "
                    "hanya boleh menurunkan risiko")
        stored = current_settings.get("llm_auto_lot") or {}
        updates["llm_auto_lot"] = {**stored, **patch}
    if "llm_interval_s" in updates:
        try:
            updates["llm_interval_s"] = validate_interval_s(updates["llm_interval_s"])
        except GuardrailRangeError as exc:
            raise HTTPException(422, str(exc)) from exc
        # Cermin ke key kanonik: `effective_interval_s` membaca
        # `llm_agent_interval_s` LEBIH DULU (AUDIT-E t_bb927ec7). Tanpa
        # cermin ini, menulis lewat panel lama akan tampak sukses tetapi
        # tidak berpengaruh apa pun karena kalah oleh nilai kanonik.
        updates["llm_agent_interval_s"] = updates["llm_interval_s"]

    # ── jadwal analisa simbol: satu objek, merge parsial + validasi ──
    if "llm_symbol_policy" in updates:
        incoming = updates["llm_symbol_policy"]
        if not isinstance(incoming, dict):
            raise HTTPException(422, "llm_symbol_policy harus objek {mode, custom}")
        mode = str(incoming.get("mode") or "").strip().lower()
        if mode not in symbol_sessions.MODES:
            raise HTTPException(
                422,
                f"mode jadwal tidak dikenal: {mode or '(kosong)'}; "
                f"pilihan: {', '.join(symbol_sessions.MODES)}")
        stored = current_settings.get("llm_symbol_policy") or {}
        merged = symbol_sessions.normalize_policy({
            **stored, **incoming,
            "custom": {**(stored.get("custom") or {}),
                       **(incoming.get("custom") or {})},
        })
        allowed_syms = {str(s).upper() for s in (
            current_settings.get("allowed_symbols")
            or db.DEFAULT_SETTINGS.get("allowed_symbols") or [])}
        extra = sorted(set(merged["custom"]) - allowed_syms)
        if extra:
            # Menjadwalkan simbol yang tidak ada di allowed_symbols = kontrol
            # palsu: loop tidak akan pernah memanggilnya. Tolak, jangan diam.
            raise HTTPException(
                422,
                f"simbol tidak ada di allowed_symbols: {', '.join(extra)} "
                f"(allowed: {', '.join(sorted(allowed_syms)) or '-'})")
        empty = [sym for sym, days in merged["custom"].items() if not days]
        if merged["mode"] == symbol_sessions.MODE_CUSTOM and empty:
            raise HTTPException(
                422,
                f"mode custom butuh minimal satu hari per simbol: {', '.join(empty)}")
        updates["llm_symbol_policy"] = merged

    for key in updates:
        previous[key] = current_settings.get(key)
    actor = user.get("username", "unknown")
    for key, value in updates.items():
        # actor diteruskan supaya settings_audit.changed_by = username admin,
        # bukan role koneksi DB (audit harus bisa dibaca operator).
        await db.set_setting(key, value, actor=actor)
    async with db.pool().connection() as conn:
        if trigger_patch:
            # Event kill-switch tetap ditulis: riwayat di Ops dan alarm
            # berbasis kill_switch_events tidak boleh kehilangan jejak
            # perubahan ambang hanya karena jalur tulisnya pindah halaman.
            # Bentuk event IDENTIK dengan jalur legacy (kartu t_dc104883).
            await _record_triggers_updated(
                conn, actor=actor, updates=trigger_patch,
                previous=trigger_previous,
                source="dashboard:guardrail",
                channel="PUT /admin/risk-settings",
            )
        await _audit(conn, actor, user.get("role"), "CONFIG_CHANGED",
                     object="risk_settings",
                     details={"updates": updates, "previous": previous})
    return {"updated": sorted(updates), "values": updates}


# ---------------------------------------------------------------- positions

@router.get("/positions")
async def list_positions(user: dict = Depends(get_current_user)):
    async with db.pool().connection() as conn:
        rows = await fetchall(
            conn,
            "SELECT * FROM positions ORDER BY (status = 'OPEN') DESC, updated_at DESC",
        )
    for r in rows:
        for k in ("volume", "open_price", "close_price", "profit"):
            if r.get(k) is not None:
                r[k] = float(r[k])
    return rows


@router.get("/risk/portfolio")
async def risk_portfolio(user: dict = Depends(get_current_user)):
    """Snapshot Portfolio Risk Manager (PRD v2.2 §7) untuk UI/monitoring.

    Agregat worst-case loss seluruh posisi + order pending/SENT sampai SL
    (termasuk biaya + buffer), stress scenario (gap, spread melebar, beberapa
    SL bersamaan), dan posisi terhadap semua batas portofolio. Read-only:
    tidak pernah menutup posisi (PRD §7.3).
    """
    settings = await db.get_settings()
    async with db.pool().connection() as conn:
        legs = await collect_legs(conn, settings)
        row = await fetchone(
            conn,
            "SELECT "
            "(SELECT COALESCE(SUM(profit), 0) FROM positions WHERE status = 'CLOSED') + "
            "(SELECT COALESCE(SUM(profit), 0) FROM positions WHERE status = 'OPEN') AS pnl",
        )
    equity = float(settings.get("initial_balance", 10000.0)) + float(row["pnl"])
    marks = collect_marks([l.symbol for l in legs])
    feed = PortfolioFeed(
        equity=equity,
        equity_age_s=0.0,
        margin_used=None,
        margin_age_s=None,
        margin_source="computed",
    )
    snap = portfolio_snapshot(legs, feed, marks, settings)
    out = asdict(snap)
    out["breaches"] = _portfolio_breaches(snap, settings)
    return out


def _portfolio_breaches(snap, settings: dict) -> list[str]:
    """Daftar limit portofolio yang sedang dilewati (tanpa order kandidat)."""
    from .portfolio_risk import portfolio_config

    cfg = portfolio_config(settings)
    breaches: list[str] = []
    equity = snap.equity
    if equity and equity > 0:
        if snap.open_risk_usd > equity * float(cfg["max_open_risk_pct"]) / 100.0 + 1e-9:
            breaches.append("max_open_risk_pct")
        if snap.stress_risk_usd > equity * float(cfg["stress_max_risk_pct"]) / 100.0 + 1e-9:
            breaches.append("stress_max_risk_pct")
        if snap.margin_used_usd > equity * float(cfg["max_margin_utilization_pct"]) / 100.0 + 1e-9:
            breaches.append("max_margin_utilization_pct")
        cap_sym = equity * float(cfg["max_symbol_risk_pct"]) / 100.0
        if any(ps["risk_usd"] > cap_sym + 1e-9 for ps in snap.per_symbol.values()):
            breaches.append("max_symbol_risk_pct")
    cap_exposure = settings.get("exposure_max_usd")
    if cap_exposure is not None and snap.gross_exposure_usd > float(cap_exposure) + 1e-9:
        breaches.append("exposure_max_usd")
    if snap.total_volume_lot > float(cfg["max_total_volume_lot"]) + 1e-9:
        breaches.append("max_total_volume_lot")
    if snap.unbounded_sl > 0:
        breaches.append("unbounded_sl")
    return breaches


# ---------------------------------------------------------------- SSE

@router.get("/stream")
async def stream(request: Request, user: dict = Depends(get_current_user)):
    async def event_gen():
        q = broadcaster.subscribe()
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield sse_format(event)
        finally:
            broadcaster.unsubscribe(q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/health")
async def health():
    async with db.pool().connection() as conn:
        await conn.execute("SELECT 1")
    return {"ok": True, "subscribers": broadcaster.subscriber_count, "env": config.FUND2_ENV}


@router.get("/version")
async def version(user: dict = Depends(get_current_user)):
    """Versi kode yang berjalan vs kode di disk (deteksi proses basi).

    Login wajib: commit hash tidak boleh terbaca publik lewat /health.
    """
    from .version_info import info as version_info
    return version_info()



# ---------------------------------------------------------------- regime (PRD §6/§21, UI-D0)

REGIME_TIMEFRAME = "M5"          # kanonik DB/PRD (sama dgn paper runner)
REGIME_TF_SECONDS = 300
REGIME_CANDLE_LIMIT = 300        # sama dgn paper.runner.CANDLE_LIMIT
REGIME_LIQUIDITY_FRESH_S = 60    # sama dgn paper.runner.LIQUIDITY_FRESH_S


async def _regime_candles(conn, symbol: str, now: datetime) -> list[dict]:
    """Candle M5 closed terakhir, ascending, format regime.classify.

    Definisi sama dengan paper.runner.load_candles: bar yang masih forming
    (close > now) dibuang. Candle fund2 disimpan sebagai instan UTC
    sejati (timestamptz; stored_to_utc identitas untuk candle fund2,
    lihat strategies/broker_time.py).
    """
    rows = await fetchall(
        conn,
        """
        SELECT ts, open, high, low, close FROM candles
        WHERE symbol = %s AND timeframe = %s
        ORDER BY ts DESC LIMIT %s
        """,
        (symbol, REGIME_TIMEFRAME, REGIME_CANDLE_LIMIT),
    )
    out: list[dict] = []
    for row in reversed(rows):
        ts_utc = row["ts"]
        if ts_utc.tzinfo is None:
            ts_utc = ts_utc.replace(tzinfo=timezone.utc)
        else:
            ts_utc = ts_utc.astimezone(timezone.utc)
        if ts_utc + timedelta(seconds=REGIME_TF_SECONDS) > now:
            continue  # bar masih forming
        out.append({
            "ts": ts_utc.isoformat(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": 0,
        })
    return out


async def _regime_liquidity(conn, symbol: str, now: datetime) -> dict | None:
    """Likuiditas terkini utk classifier (read-only).

    Sumber: tick bridge in-memory (EA live, app.market), fallback sampel
    liquidity_samples terakhir. None = tidak ada data spread -> classifier
    mengeluarkan UNKNOWN (kondisi aman, PRD §6.2) -> endpoint stale.
    """
    tick = market.latest(symbol)
    if tick and tick.get("spread") is not None:
        src_ts = datetime.fromtimestamp(tick["ts"], tz=timezone.utc)
        spread = float(tick["spread"])
    else:
        row = await fetchone(
            conn,
            "SELECT window_start, spread_avg FROM liquidity_samples "
            "WHERE symbol = %s ORDER BY window_start DESC LIMIT 1",
            (symbol,),
        )
        if row is None:
            return None
        src_ts = row["window_start"]
        if src_ts.tzinfo is None:
            src_ts = src_ts.replace(tzinfo=timezone.utc)
        spread = float(row["spread_avg"])
    # median spread 15 menit (fitur confidence, bukan rule) - sumber sama
    # dengan feed.spread_median_15m runner, dihitung dari sampel 5 detik.
    med = await fetchone(
        conn,
        """
        SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY spread_avg) AS median15
        FROM liquidity_samples
        WHERE symbol = %s AND window_start >= %s
        """,
        (symbol, now - timedelta(minutes=15)),
    )
    median15 = med["median15"] if med else None
    return {
        "ts": src_ts.isoformat(),
        "spread": spread,
        "spread_median_15m": float(median15) if median15 is not None else None,
        "fresh": (now - src_ts).total_seconds() <= REGIME_LIQUIDITY_FRESH_S,
    }


@router.get("/regime/current")
async def get_regime_current(symbol: str = "XAUUSD",
                             user: dict = Depends(get_current_user)):
    """Regime live untuk dashboard (PRD v2.2 §6/§21, UI-D0). READ-ONLY.

    Klasifikasi memakai app.regime.classify - classifier yang sama dengan
    paper runner/backtest (PRD §6.5) - atas candle M5 closed terakhir dari
    DB. Data tidak layak (candle kurang/stale, likuiditas tidak fresh,
    classifier error) -> label null + stale=true dengan HTTP 200: UI
    menampilkan badge "REGIME STALE", bukan error merah.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(422, "symbol wajib diisi")
    now = datetime.now(timezone.utc)
    async with db.pool().connection() as conn:
        candles = await _regime_candles(conn, sym, now)
        liquidity = await _regime_liquidity(conn, sym, now)
    return build_regime_snapshot(symbol=sym, now=now, candles=candles,
                                 liquidity=liquidity)


# ---------------------------------------------------------------- market status

@router.get("/market/status")
async def get_market_status(symbol: str, user: dict = Depends(get_current_user)):
    """Status pasar satu simbol (kontrak UI: badge buka/tutup + alasan).

    Sumber berlapis: laporan EA (POST /bridge/heartbeat) > tabel
    ``market_sessions`` > bukti feed. Logika lengkap ada di
    app.market_status; endpoint ini hanya validasi + bentuk kontrak:

        {symbol, market_status, market_close_reason, trade_mode,
         last_tick_ts, last_tick_age_s, next_open_ts, ea_seen_s, source}

    READ-ONLY: tidak menulis DB (persist status EA terjadi di heartbeat).
    SSE type='market' dipublikasikan oleh market_status saat status berubah.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(422, "symbol wajib diisi")
    return await market_status.resolve(sym)


# ---------------------------------------------------------------- candles (UI-D5)

# Whitelist chart candlestick (BACKEND-C1). H1/H4/D1 sudah ada di DB dan
# dipakai test lain lewat alias '1h'/'4h'/'1d' (lihat paper.backtest.CANONICAL_TF).
CANDLE_SYMBOLS = ("XAUUSD", "BTCUSD")
CANDLE_TFS = ("M1", "M5", "M15", "H1", "H4", "D1")
# Alias durasi yang belum dikenal canonical_tf (hanya 1h/4h/1d). Tambahan
# minimal khusus /candles: dipetakan ke alias canonical, lalu canonical_tf.
CANDLE_TF_ALIAS = {"60m": "1h", "240m": "4h", "1440m": "1d"}
CANDLES_DEFAULT_LIMIT = 500
CANDLES_MAX_LIMIT = 2000
# Panjang bucket per timeframe untuk mendeteksi bar legacy yang periodenya
# sudah dicakup sumber baru ('ea'/'rollup'/'live').
CANDLE_BUCKET_SQL = {"M1": "1 minute", "M5": "5 minutes", "M15": "15 minutes",
                     "H1": "1 hour", "H4": "4 hours", "D1": "1 day", "W1": "7 days"}


@router.get("/candles")
async def list_candles(symbol: str,
                       tf: str = "M5",
                       limit: int = CANDLES_DEFAULT_LIMIT,
                       include_legacy: int = 0,
                       before: str | None = None,
                       user: dict = Depends(get_current_user)):
    """Candle OHLCV untuk chart dashboard (UI-D5). READ-ONLY: hanya SELECT.

    Konvensi penyimpanan sama dengan paper/research (lihat
    app.research_candles.load_candles): ts adalah jam broker yang di-render
    di timezone sesi DB, jadi konversi ke UTC WAJIB lewat helper teruji
    db_timezone_offset_h + to_utc_candles - bukan konversi manual (riwayat
    TS_BACKWARD/UTC+2 pernah menyesatkan regime & backtest).

    CUTOVER SUMBER (kartu candle pipeline): per (symbol, timeframe) seri hanya
    berisi bar dari sumber baru ('ea'/'rollup'). Bar lama ('legacy': volume
    2-5, 32% bar datar) yang ts-nya LEBIH TUA dari bar baru pertama
    disembunyikan, supaya histogram tidak mencampur dua generasi data. Bila
    belum ada bar sumber baru sama sekali, cutover = NULL dan seluruh bar
    legacy tetap tampil (chart tidak boleh kosong hanya karena migrasi
    berjalan lebih dulu daripada penulis baru). `include_legacy=1` = riset:
    tampilkan semua sumber apa adanya. Shape response tidak berubah.
    """
    sym = (symbol or "").strip().upper()
    if sym not in CANDLE_SYMBOLS:
        raise HTTPException(
            400, f"symbol tidak didukung; salah satu dari {', '.join(CANDLE_SYMBOLS)}")
    tf_clean = (tf or "").strip()
    tf_alias = CANDLE_TF_ALIAS.get(tf_clean.lower(), tf_clean)
    timeframe = canonical_tf(tf_alias)
    if timeframe not in CANDLE_TFS:
        timeframe = canonical_tf(tf_alias.lower())  # alias '5m'/'15M'/'1h'
    if timeframe not in CANDLE_TFS:
        raise HTTPException(
            400, f"tf tidak didukung; salah satu dari {', '.join(CANDLE_TFS)}")
    if limit < 1 or limit > CANDLES_MAX_LIMIT:
        raise HTTPException(400, f"limit harus 1..{CANDLES_MAX_LIMIT}")
    before_utc = None
    if before:
        try:
            before_utc = datetime.fromisoformat(before.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "before harus ISO-8601, mis. 2026-11-27T04:00:00+00:00")
        if before_utc.tzinfo is None:
            before_utc = before_utc.replace(tzinfo=timezone.utc)
        before_utc = before_utc.astimezone(timezone.utc)
    async with db.pool().connection() as conn:
        offset_h = await db_timezone_offset_h(conn)
        # JIT Postgres di host ini rusak (libLLVM-17.so.1 hilang): query
        # berbiaya menengah gagal dengan UndefinedFile. Matikan per transaksi.
        await conn.execute("SET LOCAL jit = off")
        sql = ("SELECT c.ts, c.open, c.high, c.low, c.close, c.volume FROM candles c "
               "WHERE c.symbol = %s AND c.timeframe = %s")
        params: list = [sym, timeframe]
        if not include_legacy:
            # Buang bar legacy yang periodenya sudah dicakup sumber baru. Grid
            # bar EA/rollup digeser 2 jam dari grid UTC (tengah malam broker),
            # jadi legacy H4 00:00 UTC dan EA 01:00 UTC adalah bucket yang sama.
            # Tanpa ini chart H4/D1 menggambar dua seri bersilang untuk satu
            # periode dan terlihat "melompat ke posisi awal candle".
            bucket = CANDLE_BUCKET_SQL[timeframe]
            sql += (" AND (c.source <> 'legacy' OR NOT EXISTS ("
                    "SELECT 1 FROM candles n WHERE n.symbol = c.symbol "
                    "AND n.timeframe = c.timeframe AND n.source <> 'legacy' "
                    "AND date_bin(%s::interval, n.ts + interval '2 hours', timestamp '2000-01-01') "
                    "  = date_bin(%s::interval, c.ts + interval '2 hours', timestamp '2000-01-01')))")
            params += [bucket, bucket]
        if before_utc is not None:
            # Cursor scrollback: batas atas eksklusif. before dikirim dalam UTC
            # (ts yang dilihat klien); kolom ts menyimpan jam broker yang
            # dirender di tz sesi DB, jadi invers stored_to_utc:
            # stored = utc - (db_tz - broker_offset).
            stored = before_utc - timedelta(
                hours=offset_h - broker_utc_offset_hours(before_utc))
            sql += " AND ts < %s"
            params.append(stored)
        sql += " ORDER BY ts DESC LIMIT %s"
        params.append(limit + 1)
        rows = await fetchall(conn, sql, tuple(params))
    # DESC -> reverse: oldest-first untuk rendering chart.
    has_more = len(rows) > limit
    rows = rows[:limit]
    candles = to_utc_candles(list(reversed(rows)), offset_h)
    return {
        "symbol": sym,
        "tf": timeframe,
        "count": len(candles),
        "has_more": has_more,
        "next_before": candles[0]["ts"].isoformat() if (has_more and candles) else None,
        "candles": [
            {
                "ts": c["ts"].isoformat(),
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": c["volume"],
            }
            for c in candles
        ],
    }
