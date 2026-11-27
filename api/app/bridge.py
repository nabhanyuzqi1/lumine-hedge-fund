"""EA bridge endpoints (auth: Bearer token from settings.bridge_token).

GET  /bridge/poll      long-poll; returns the next SENT command for the EA
POST /bridge/result    idempotent by command_id; SENT/STUCK -> FILLED/FAILED
POST /bridge/tick      tick batch -> in-memory price + SSE broadcast (+ candles upsert)
POST /bridge/positions full open-positions snapshot -> positions table sync
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac as hmac_mod
import json
import logging
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, model_validator
from uuid import UUID

from . import bridge_stats, config, db, fail_reason, ingest, kill_switch, market, market_status, risk, validate
from .config import BRIDGE_POLL_MAX_S
from .state_machine import (
    ALLOWED_TRANSITIONS,
    CLOSE_OWNER_TARGETS,
    TERMINAL_STATUSES,
    fetchall,
    fetchone,
    record_event,
    transition,
)
from .sse import broadcaster
from .telegram_bot import notify_owner

router = APIRouter(prefix="/bridge")

log = logging.getLogger("fund2.bridge")
_bearer = HTTPBearer(auto_error=False)

# ── HMAC auth (PRD 7; kontrak EA v5 — ea/HMAC_CONTRACT.md) ─────────────────
HMAC_TS_TOLERANCE_S = 5                          # toleransi jam ±5 detik
HMAC_NONCE_TTL_S = 2 * HMAC_TS_TOLERANCE_S + 1   # nonce dipakai sekali, TTL 11 dtk
_nonces: dict[str, float] = {}


def _check_hmac(request: Request, body: bytes) -> bool:
    """Verifikasi header X-Fund2-Timestamp / -Nonce / -Signature.

    string_to_sign = ts \\n nonce \\n METHOD \\n path-with-query \\n sha256_hex(body)
    Urutan verifikasi sesuai kontrak: header lengkap -> timestamp dalam
    toleransi -> nonce belum dipakai -> signature (constant-time compare).
    """
    secret = config.FUND2_HMAC_SECRET
    if not secret:
        return False
    ts = request.headers.get("x-fund2-timestamp", "")
    nonce = request.headers.get("x-fund2-nonce", "")
    sig = request.headers.get("x-fund2-signature", "")
    if not ts or not nonce or not sig:
        return False
    try:
        ts_val = int(ts)
    except ValueError:
        return False
    if abs(time.time() - ts_val) > HMAC_TS_TOLERANCE_S:
        return False
    if not (8 <= len(nonce) <= 64) or any(c not in "0123456789abcdef" for c in nonce.lower()):
        return False
    now = time.time()
    if len(_nonces) > 4096:  # purge lazy (kontrak)
        for n in [n for n, exp in _nonces.items() if exp <= now]:
            del _nonces[n]
    if _nonces.get(nonce, 0.0) > now:
        return False  # nonce replayed
    path_with_query = request.url.path
    if request.url.query:
        path_with_query += "?" + request.url.query
    body_hash = hashlib.sha256(body).hexdigest()
    sts = "\n".join([ts, nonce, request.method, path_with_query, body_hash]).encode("utf-8")
    expected = hmac_mod.new(secret.encode("utf-8"), sts, hashlib.sha256).hexdigest()
    if not hmac_mod.compare_digest(expected, sig.lower()):
        return False
    # Nonce dicatat HANYA setelah signature valid: request invalid tidak
    # membakar nonce (anti-DoS terhadap retry EA), replay tetap terblok
    # karena pemeriksaan + pencatatan atomik di event loop (tanpa await).
    _nonces[nonce] = now + HMAC_NONCE_TTL_S
    return True


async def require_bridge_token(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    # 1) Bearer (kontrak lama: harness latensi, test, simulator lawas)
    if creds is not None and creds.scheme.lower() == "bearer":
        settings = await db.get_settings()
        expected = str(settings.get("bridge_token", ""))
        if expected and secrets.compare_digest(creds.credentials, expected):
            return
    # 2) HMAC-SHA256 (kontrak EA v5, PRD 7)
    if _check_hmac(request, await request.body()):
        return
    raise HTTPException(401, "bridge token required")


class Candle(BaseModel):
    symbol: str
    timeframe: str
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0


class TickItem(BaseModel):
    """Satu tick dalam batch EA v5 ({ts(ms), bid, ask, spread})."""
    ts: str | int | None = None
    bid: float
    ask: float
    spread: float | None = None


class HeartbeatBody(BaseModel):
    """EA liveness (PRD 5.5): POST /bridge/heartbeat tiap 2 detik.

    Field status pasar (market_status, market_close_reason, trade_mode,
    symbol_time, tick_age_s) OPSIONAL dan aditif: EA versi lama tidak
    mengirimnya, dan heartbeat-nya tetap sah (tidak 422). Nilai asing
    (mis. trade_mode tak dikenal) diabaikan oleh market_status, bukan ditolak.
    """
    ts: int | None = None
    symbol: str | None = None
    bid: float | None = None
    ask: float | None = None
    spread: float | None = None
    ea: str | None = None
    schema_version: str | None = None   # PRD 4.4: versi schema EA
    market_status: str | None = None    # OPEN | CLOSED | UNKNOWN
    market_close_reason: str | None = None  # weekend|session|holiday|broker|no_data
    trade_mode: str | int | None = None     # FULL | CLOSEONLY | DISABLED (atau 0/1/2)
    symbol_time: str | int | float | None = None  # jam server simbol di EA
    tick_age_s: float | None = None         # umur tick terakhir menurut EA


class TickBody(BaseModel):
    symbol: str
    bid: float | None = None        # legacy single-tick (EA v0)
    ask: float | None = None
    ts: str | None = None
    ticks: list[TickItem] = []      # batch EA v5 (250 ms)
    # t_afd7fe4e: status trading-enabled simbol menurut EA (SYMBOL_TRADE_MODE
    # penuh). EA v5 belum mengirimnya -> None = belum dilaporkan, dan
    # pre-flight gate memakai kesegaran tick sebagai bukti. Field ini
    # opsional supaya EA versi lama tetap sah.
    trade_enabled: bool | None = None
    candles: list[Candle] = []
    schema_version: str | None = None   # PRD 4.4: versi schema EA


class ResultBody(BaseModel):
    command_id: str
    status: str
    ticket: int | None = None
    price: float | None = None
    profit: float | None = None
    reason: str | None = None


class PositionItem(BaseModel):
    ticket: int
    order_id: str | None = None
    symbol: str
    side: str
    volume: float
    open_price: float | None = None
    open_time: str | None = None
    close_price: float | None = None
    close_time: str | None = None
    sl: float | None = None
    tp: float | None = None
    profit: float = 0
    status: str = "OPEN"
    # Payload mentah posisi: tempat menyimpan order_id terpotong untuk recon.
    raw: dict = {}

    @model_validator(mode="before")
    @classmethod
    def _tolerate_truncated_order_id(cls, data):
        # Comment broker MT5 dipotong ~31 char -> order_id bisa UUID terpotong
        # (kelas bug commit 45858f6; dulu 500 InvalidTextRepresentation di
        # INSERT positions). Nilai non-UUID dibuang supaya snapshot tidak 500;
        # nilai mentah disimpan di raw + dilog untuk recon. Posisi tetap
        # ter-link via ticket (lihat fallback orphan lookup di bawah).
        if isinstance(data, dict) and isinstance(data.get("order_id"), str):
            try:
                UUID(data["order_id"])
            except ValueError:
                raw = data["raw"] if isinstance(data.get("raw"), dict) else {}
                raw["order_id_raw_dropped"] = data["order_id"]
                data["raw"] = raw
                data["order_id"] = None
                log.warning(
                    "positions: order_id bukan UUID dibuang (disimpan di raw): %r",
                    raw["order_id_raw_dropped"],
                )
        return data


class DealItem(BaseModel):
    """Satu deal dari snapshot EA (PRD 5.8: deal 24 jam terakhir).

    entry: IN (buka) | OUT (tutup) | INOUT (balik arah). Reconciler hanya
    memakai deal OUT sebagai bukti penutupan posisi.
    """

    ticket: int
    position_id: int
    order_ticket: int | None = None
    symbol: str = ""
    side: str = ""
    volume: float = 0
    price: float | None = None
    profit: float = 0
    time: str | None = None
    entry: str = "OUT"


class PositionsBody(BaseModel):
    positions: list[PositionItem]
    deals: list[DealItem] = []


def _emergency_sl_distance(symbol: str, open_price: float | None,
                           settings: dict) -> tuple[float, str]:
    """Jarak SL darurat posisi orphan, per-simbol (QA_MP5 finding 1).

    Prioritas sumber jarak:
    1. spec simbol (settings symbol_specs, A2) -> sl_max_usd. Jarak absolut
       satuan harga simbol tsb, sehingga hanya sah untuk simbol yang sama;
    2. fallback price-relative: EMERGENCY_SL_FALLBACK_PCT × harga open,
       dipakai bila simbol belum punya spec risk (jarak absolut global
       dilarang: 15.0 = 0.42% XAUUSD tapi 0.025% BTCUSD @ 61269);
    3. legacy EMERGENCY_SL_DISTANCE hanya bila harga open juga tidak
       diketahui (tidak ada dasar perhitungan apa pun).

    Return (distance, source); source untuk order_events.
    """
    spec = risk.symbol_spec(symbol, settings)
    if spec is not None:
        return float(spec["sl_max_usd"]), "spec_sl_max"
    price = float(open_price or 0.0)
    if price > 0:
        return price * config.EMERGENCY_SL_FALLBACK_PCT, "fallback_price_pct"
    return float(config.EMERGENCY_SL_DISTANCE), "legacy_abs"


def _close_profit_from_prices(
    symbol: str | None, side: str | None, volume: float | None,
    entry_price: float | None, close_price: float | None,
    settings: dict,
) -> float | None:
    """Profit close dari harga; rumus = DEAL_PROFIT broker (terverifikasi).

    (close - entry) * contract_size * volume * dir; dir BUY=+1 / SELL=-1;
    contract_size dari settings.symbol_specs simbol terkait (XAUUSD=100,
    BTCUSD=1, spec_verified). None bila ada komponen tak lengkap atau tak
    valid — pemanggil wajib menandai payload, bukan mengarang angka.
    Komisi TIDAK dihitung di sini (evaluator memotong terpisah).
    """
    try:
        entry = float(entry_price) if entry_price is not None else None
        close = float(close_price) if close_price is not None else None
        vol = float(volume) if volume is not None else None
    except (TypeError, ValueError):
        return None
    if not entry or not close or not vol or vol <= 0:
        return None
    if side not in ("BUY", "SELL"):
        return None
    spec = (settings.get("symbol_specs") or {}).get(symbol) or {}
    try:
        contract_size = float(spec.get("contract_size"))
    except (TypeError, ValueError):
        return None
    if not contract_size or contract_size <= 0:
        return None
    direction = 1.0 if side == "BUY" else -1.0
    return round((close - entry) * contract_size * vol * direction, 2)


def _resolve_close_profit(
    body_profit: float | None, owner: dict | None,
    close_price: float | None, settings: dict,
) -> tuple[float, bool]:
    """(profit, profit_estimated) untuk payload hasil CLOSE.

    EA BuildResultJson hardcode "profit":0.0 untuk semua hasil command
    (termasuk CLOSE) -> laporan 0 tak tepercaya. Profit non-nol diteruskan
    apa adanya; profit 0/falsy dihitung ulang dari harga (entry dari
    price_filled order induk, close dari harga result). Bila harga tak
    lengkap -> 0 + marker profit_estimated (jangan mengarang).
    """
    if body_profit:
        return float(body_profit), False
    if owner is not None:
        computed = _close_profit_from_prices(
            owner.get("symbol"), owner.get("side"), owner.get("volume"),
            owner.get("price_filled"), close_price, settings,
        )
        if computed is not None:
            return computed, True
    return 0.0, True


# Interval pemeriksaan ulang command baru di dalam long-poll /bridge/poll.
# EA memegang long-poll terus-menerus, jadi beban = (iterasi per siklus) x EA.
# Dua fase: panas 0.6 s pertama @0.05 s (command yang tiba tepat setelah EA
# mulai menunggu tetap diambil ~50 ms), lalu idle @0.20 s. Efek: transaksi DB
# dari long-poll turun ~70% (20 -> ~6 iter/s per EA) dengan tambahan latensi
# maksimum 200 ms hanya untuk command yang tiba >0.6 s setelah poll dimulai.
# Koneksi pool dilepas sebelum sleep (tidak menahan koneksi saat menunggu).
BRIDGE_POLL_HOT_S = 0.6
BRIDGE_POLL_INTERVAL_S = 0.05
BRIDGE_POLL_IDLE_S = 0.20

# Batas bawah timeout long-poll. EA lama memanggil ?timeout_s=0 sehingga
# setiap request langsung kembali dan berubah jadi busy-loop: ribuan
# request/menit, tiap request menulis mark_ea_seen + mengambil koneksi pool.
# Efek terukur: CPU host jenuh (load ~10/6 core) dan pool fund2-api habis
# (PoolTimeout) -> SEV-2 db_unavailable -> kill-switch STOP_NEW_ORDERS
# memblokir semua order (termasuk agent LLM). Batas bawah ini memaksa satu
# request menunggu, sehingga beban turun ke ~1 request per beberapa detik.
#
# Sebelumnya 5.0 s. Namun WebRequest MQL5 sinkron: selama long-poll menunggu,
# OnTimer EA ikut tertahan, jadi heartbeat (2 s) dan flush tick batch (250 ms)
# hanya terjadi tepat setelah poll kembali. Terukur di host ini: tick yang
# dipakai pre-flight selalu berumur 0..5.1 s (sawtooth), sehingga
# max_tick_age_s=3.0 gagal sporadis pada XAUUSD dan BTCUSD sekaligus
# (tick basi 5.3-8.9 s) padahal kedua feed hidup.
# 1.0 s cukup untuk mencegah busy-loop (1 request/detik per EA) sekaligus
# menjaga umur tick < ambang gate; latency pickup command maksimum ditentukan
# throttle EA sendiri (InpPollSec), bukan floor ini.
BRIDGE_POLL_MIN_S = 1.0


@router.get("/poll", dependencies=[Depends(require_bridge_token)])
async def poll(request: Request, timeout_s: float = 25.0):
    """Long-poll for the next SENT command. Marks it delivered on handover."""
    await kill_switch.mark_ea_seen()
    bridge_stats.inc("poll")
    timeout_s = min(max(timeout_s, BRIDGE_POLL_MIN_S), BRIDGE_POLL_MAX_S)
    loop = asyncio.get_event_loop()
    started = loop.time()
    while True:
        async with db.pool().connection() as conn:
            async with conn.transaction():
                cmd = await fetchone(
                    conn,
                    """
                    SELECT * FROM orders
                    WHERE status = 'SENT' AND delivered_at IS NULL
                    ORDER BY sent_at
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """,
                )
                if cmd is not None:
                    await conn.execute(
                        "UPDATE orders SET delivered_at = now() WHERE id = %s", (cmd["id"],)
                    )
                    out = {
                        "command_id": cmd["command_id"],
                        "order_id": str(cmd["id"]),
                        "symbol": cmd["symbol"],
                        "side": cmd["side"],
                        "volume": float(cmd["volume"]),
                        "sl": float(cmd["sl"]) if cmd["sl"] is not None else None,
                        "tp": float(cmd["tp"]) if cmd["tp"] is not None else None,
                    }
                    if cmd.get("action") == "CLOSE":
                        # Kontrak EA: ticket berupa string; keberadaan ticket = CLOSE.
                        out["action"] = "CLOSE"
                        out["ticket"] = str(cmd["ticket"])
                    return out
                # Antrian reconciler (PRD 5.8): MODIFY_SL darurat untuk posisi
                # orphan. command_id = bridge_commands.id; hasilnya dilaporkan
                # EA via /bridge/result (diselesaikan di bridge_commands, bukan
                # state machine orders).
                cmd2 = await fetchone(
                    conn,
                    """
                    SELECT * FROM bridge_commands
                    WHERE status = 'QUEUED'
                    ORDER BY created_at
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """,
                )
                if cmd2 is not None:
                    await conn.execute(
                        "UPDATE bridge_commands SET status = 'DELIVERED', "
                        "delivered_at = now() WHERE id = %s",
                        (cmd2["id"],),
                    )
                    payload = cmd2.get("payload") or {}
                    return {
                        "command_id": str(cmd2["id"]),
                        "order_id": str(cmd2["order_id"]) if cmd2["order_id"] else "",
                        "action": cmd2["action"],          # 'MODIFY_SL'
                        "symbol": "",
                        "side": "",
                        "volume": 0,
                        "ticket": str(payload.get("ticket", "")),
                        "sl": payload.get("sl"),
                        "tp": payload.get("tp"),
                    }
        elapsed = loop.time() - started
        if elapsed >= timeout_s:
            return None  # 204-style empty body
        await asyncio.sleep(
            BRIDGE_POLL_INTERVAL_S if elapsed < BRIDGE_POLL_HOT_S else BRIDGE_POLL_IDLE_S
        )


@router.post("/result", dependencies=[Depends(require_bridge_token)])
async def result(body: ResultBody):
    bridge_stats.inc("result")
    if body.status not in ("FILLED", "FAILED"):
        raise HTTPException(422, "status must be FILLED or FAILED")
    await kill_switch.mark_ea_seen()
    owner_transitions: list[dict] = []
    async with db.pool().connection() as conn:
        async with conn.transaction():
            order = await fetchone(
                conn, "SELECT * FROM orders WHERE command_id = %s FOR UPDATE", (body.command_id,)
            )
            if order is None:
                # Bukan order: mungkin hasil command reconciler (MODIFY_SL) dari
                # bridge_commands. FILLED -> DONE, FAILED -> FAILED; idempotent.
                cmd = await fetchone(
                    conn, "SELECT * FROM bridge_commands WHERE id = %s FOR UPDATE",
                    (body.command_id,),
                )
                if cmd is None:
                    raise HTTPException(404, "unknown command_id")
                if cmd["status"] in ("DONE", "FAILED"):
                    return {"ok": True, "duplicate": True, "status": cmd["status"]}
                final = "DONE" if body.status == "FILLED" else "FAILED"
                await conn.execute(
                    "UPDATE bridge_commands SET status = %s, fail_reason = %s, "
                    "resolved_at = now() WHERE id = %s",
                    (final, body.reason, cmd["id"]),
                )
                if cmd["order_id"]:
                    await conn.execute(
                        """
                        INSERT INTO order_events (order_id, from_status, to_status, payload)
                        SELECT id, status, status, %s FROM orders WHERE id = %s
                        """,
                        (json.dumps({"event": "command_result", "action": cmd["action"],
                                     "result": final, "ticket": body.ticket,
                                     "reason": body.reason}), cmd["order_id"]),
                    )
                broadcaster.publish(
                    {"type": "bridge_command", "command_id": str(cmd["id"]),
                     "action": cmd["action"], "status": final}
                )
                return {"ok": True, "duplicate": False, "status": final}
            if order["status"] in TERMINAL_STATUSES:
                # idempotent replay of an already-applied result
                return {"ok": True, "duplicate": True, "status": order["status"]}
            if order["status"] not in ("SENT", "STUCK"):
                raise HTTPException(409, f"order in status {order['status']} cannot receive results")
            is_close = order.get("action") == "CLOSE"
            owners: list[dict] = []
            settings: dict = {}
            profit_value: float | None = body.profit
            profit_estimated = False
            if is_close and body.status == "FILLED":
                # Race T4 (PRD 5.8): result CLOSE yang FILLED menutup posisi di
                # DB secara langsung. Bila ia menang melawan snapshot
                # reconciler, posisi tidak pernah terlihat "hilang" dan order
                # OPEN induk stuck di FILLED selamanya. Transisikan semua order
                # induk (link ticket atau positions.order_id) di sini juga,
                # dengan bukti penutupan (close order, harga, profit). Urutan
                # lock (order CLOSE -> order induk -> baris positions) konsisten
                # dengan snapshot reconciler (owner -> position) agar bebas
                # deadlock. Order induk dikunci sebelum result CLOSE ditulis;
                # urutan lock tidak berubah.
                owners = await fetchall(
                    conn,
                    """
                    SELECT * FROM orders
                    WHERE action = 'OPEN'
                      AND status = ANY(%s)
                      AND (ticket = %s
                           OR id = (SELECT order_id FROM positions WHERE ticket = %s))
                    FOR UPDATE
                    """,
                    (list(CLOSE_OWNER_TARGETS), order["ticket"], order["ticket"]),
                )
                settings = await db.get_settings()
                # EA BuildResultJson hardcode "profit":0.0 untuk semua hasil
                # command (termasuk CLOSE) -> laporan 0 tak tepercaya. Hitung
                # ulang dari harga sebelum transisi ditulis supaya payload
                # order CLOSE maupun order induk tidak mencatat 0.0 palsu.
                profit_value, profit_estimated = _resolve_close_profit(
                    body.profit, owners[0] if owners else None, body.price, settings)
            # t_afd7fe4e butir B: detail terstruktur disiapkan sebelum transisi
            # supaya payload event dan kolom orders memakai sumber yang sama.
            fail_detail = (fail_reason.from_text(
                body.reason, stage=fail_reason.STAGE_BRIDGE_RESULT,
                default_code="ea_failed")
                if body.status == "FAILED" else None)
            await transition(
                conn, order["id"], body.status,
                {
                    "source": "bridge",
                    "action": "CLOSE" if is_close else "OPEN",
                    "ticket": body.ticket,
                    "price": body.price,
                    "profit": profit_value,
                    **({"profit_estimated": True} if profit_estimated else {}),
                    "reason": body.reason,
                },
                set_fields={
                    # order CLOSE: kolom ticket = ticket posisi target, jangan ditimpa
                    **({} if is_close else {"ticket": body.ticket}),
                    "price_filled": body.price,
                    # t_afd7fe4e butir B: FAILED dari EA WAJIB beralasan
                    # terstruktur. Dulu `body.reason` mentah (sering None atau
                    # hanya retcode) -> tidak bisa diquery/dihitung.
                    **({} if body.status != "FAILED" else {
                        "fail_reason": fail_reason.render(fail_detail),
                        "fail_detail": fail_detail,
                    }),
                },
                jsonb_fields=("fail_detail",),
            )
            if is_close and body.status == "FILLED":
                for owner in owners:
                    target = CLOSE_OWNER_TARGETS.get(owner["status"])
                    if target is None or target not in ALLOWED_TRANSITIONS.get(
                            owner["status"], set()):
                        continue
                    owner_profit, owner_estimated = _resolve_close_profit(
                        body.profit, owner, body.price, settings)
                    await transition(
                        conn, owner["id"], target,
                        {
                            "source": "bridge_result",
                            "close_order_id": str(order["id"]),
                            "close_command_id": body.command_id,
                            "ticket": order["ticket"],
                            "close_price": body.price,
                            "profit": owner_profit,
                            **({"profit_estimated": True} if owner_estimated else {}),
                            "reason": body.reason,
                        },
                    )
                    owner_transitions.append(
                        {"order_id": str(owner["id"]), "status": target})
                await conn.execute(
                    """
                    UPDATE positions SET status = 'CLOSED', close_price = COALESCE(%s, close_price),
                                         close_time = now(), updated_at = now()
                    WHERE ticket = %s AND status = 'OPEN'
                    """,
                    (body.price, order["ticket"]),
                )
    broadcaster.publish(
        {"type": "order", "order_id": str(order["id"]), "status": body.status,
         "ticket": body.ticket, "price": body.price}
    )
    for item in owner_transitions:
        broadcaster.publish({"type": "order", **item, "ticket": body.ticket})
    return {"ok": True, "duplicate": False, "status": body.status}


@router.post("/heartbeat", dependencies=[Depends(require_bridge_token)])
async def heartbeat(body: HeartbeatBody):
    """EA liveness (PRD 5.5): dipanggil EA tiap 2 detik.

    Menandai EA terlihat (kill-switch OFFLINE monitor) dan menyimpan status
    pasar terakhir yang dilaporkan EA (field opsional market_status /
    market_close_reason / trade_mode / symbol_time / tick_age_s). Status
    disimpan in-memory (dipakai GET /market/status, gate order, dan pipeline
    ingest) + dipersist ringan ke settings, throttled; SSE type='market'
    dipublikasikan HANYA saat status simbol berubah.

    Semua langkah status bersifat best-effort: heartbeat adalah jalur
    liveness, jadi kegagalan audit/persist tidak boleh menggagalkannya.
    """
    bridge_stats.inc("heartbeat")
    await kill_switch.mark_ea_seen()
    try:
        change = market_status.record_report(
            body.symbol,
            market_status=body.market_status,
            market_close_reason=body.market_close_reason,
            trade_mode=body.trade_mode,
            symbol_time=body.symbol_time,
            tick_age_s=body.tick_age_s,
        )
        if change.get("changed") and change.get("status"):
            broadcaster.publish({"type": "market", **change["status"]})
        await market_status.persist_throttled()
    except Exception as exc:  # noqa: BLE001 - liveness EA tidak boleh gagal karena audit
        log.warning("heartbeat: simpan status pasar gagal (diabaikan): %r", exc)
    return {"ok": True, "ts": body.ts}


@router.post("/tick", dependencies=[Depends(require_bridge_token)])
async def tick(body: TickBody):
    """Ingest tick dari EA (PRD 5.1).

    Kontrak EA v5 (batch 250 ms): {symbol, ticks:[{ts,bid,ask,spread}], candles?}
    Kontrak legacy (EA v0 single):    {symbol, bid, ask, ts?, candles?}

    Tick -> ring buffer memori -> parquet 60 dtk (pipeline background);
    agregat spread per 5 dtk -> liquidity_samples; candle -> antrean upsert
    background. Endpoint ini TIDAK menyentuh DB (order path tidak pernah
    menunggu tulis tick; backpressure hanya membuang sampel likuiditas).
    """
    bridge_stats.inc("tick")
    if not validate.schema_version_supported(body.schema_version):
        # PRD 4.4: EA mengirim versi schema yang tidak didukung -> tolak.
        raise HTTPException(
            422, f"unsupported schema_version {body.schema_version!r}; "
            f"didukung: {sorted(validate.SUPPORTED_SCHEMA_VERSIONS)}")
    await kill_switch.mark_ea_seen()
    pipeline = ingest.get_pipeline()
    validator = validate.get_validator()
    n = 0
    rejected_n = 0
    flagged_n = 0
    if body.ticks:
        for item in body.ticks:
            issues = validator.check_tick(body.symbol, item.bid, item.ask, item.ts)
            if validate.rejected(issues):
                # PRD 4.4: data rusak ditolak, tidak masuk market store /
                # pipeline / SSE; dihitung + dilaporkan di respons.
                rejected_n += 1
                log.warning("[tick] ditolak: %s (symbol=%s bid=%r ask=%r ts=%r)",
                            [i.code for i in issues], body.symbol,
                            item.bid, item.ask, item.ts)
                continue
            flagged_n += len(validate.flagged(issues))
            t = market.update_tick(body.symbol, item.bid, item.ask, item.ts,
                                   trade_enabled=body.trade_enabled)
            if item.spread is not None:
                t["spread"] = item.spread
            pipeline.add_tick(body.symbol, item.bid, item.ask, item.spread, item.ts)
            broadcaster.publish({"type": "tick", **t})
            n += 1
    elif body.bid is not None and body.ask is not None:
        # legacy single-tick (EA v0)
        issues = validator.check_tick(body.symbol, body.bid, body.ask, body.ts)
        if validate.rejected(issues):
            rejected_n = 1
            log.warning("[tick] single ditolak: %s (symbol=%s)",
                        [i.code for i in issues], body.symbol)
        else:
            flagged_n += len(validate.flagged(issues))
            t = market.update_tick(body.symbol, body.bid, body.ask, body.ts,
                                   trade_enabled=body.trade_enabled)
            pipeline.add_tick(body.symbol, body.bid, body.ask, None, body.ts)
            broadcaster.publish({"type": "tick", **t})
            n = 1
    elif not body.candles:
        # bukan batch, bukan legacy, dan tanpa candle -> payload tidak valid
        raise HTTPException(422, "bid/ask required for single-tick contract")
    # else: candle-only (seed history / refresh M1) — sah, ticks=0
    if body.candles:
        rejected_n += pipeline.add_candles([c.model_dump() for c in body.candles])
    return {"ok": True, "ticks": n, "rejected": rejected_n, "flagged": flagged_n}


@router.post("/positions", dependencies=[Depends(require_bridge_token)])
async def positions(body: PositionsBody):
    """Snapshot sync + reconciler (PRD 5.8).

    EA mengirim snapshot (posisi terbuka + deal 24 jam terakhir) tiap 5 detik
    dan saat reconnect. Reconciler membandingkan snapshot dengan positions/orders:

    - posisi broker tanpa order DB  -> ORPHAN_ADOPTED (dicatat, SL darurat
      bila belum ada, notifikasi owner);
    - posisi DB tanpa broker        -> FILLED_THEN_CLOSED bila ada deal
      penutup (snapshot deals / order CLOSE FILLED), selain itu FAILED;
    - tetap tak terjelaskan         -> kill-switch + alert;
    - semua langkah tercatat di order_events.
    """
    bridge_stats.inc("positions")
    await kill_switch.mark_ea_seen()
    orphans: list[dict] = []
    unexplained: list[int] = []
    closed: list[dict] = []
    async with db.pool().connection() as conn:
        async with conn.transaction():
            # ── 1. Upsert posisi snapshot (order_id existing tidak dilepas) ──
            for p in body.positions:
                await conn.execute(
                    """
                    INSERT INTO positions (ticket, order_id, symbol, side, volume, open_price,
                                           open_time, close_price, close_time, sl, tp,
                                           profit, status, raw, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (ticket) DO UPDATE SET
                        order_id = COALESCE(EXCLUDED.order_id, positions.order_id),
                        symbol = EXCLUDED.symbol, side = EXCLUDED.side, volume = EXCLUDED.volume,
                        open_price = EXCLUDED.open_price, open_time = EXCLUDED.open_time,
                        close_price = EXCLUDED.close_price, close_time = EXCLUDED.close_time,
                        sl = EXCLUDED.sl, tp = EXCLUDED.tp,
                        profit = EXCLUDED.profit, status = EXCLUDED.status,
                        raw = positions.raw || EXCLUDED.raw, updated_at = now()
                    """,
                    (p.ticket, p.order_id, p.symbol, p.side.upper(), p.volume, p.open_price,
                     p.open_time, p.close_price, p.close_time, p.sl, p.tp, p.profit,
                     p.status.upper(), json.dumps(p.raw)),
                )

            # ── 2. Orphan: posisi broker tanpa order DB -> ORPHAN_ADOPTED ──
            settings = await db.get_settings()
            for p in body.positions:
                owner = None
                if p.order_id:
                    owner = await fetchone(
                        conn, "SELECT * FROM orders WHERE id = %s", (p.order_id,)
                    )
                if owner is None:
                    owner = await fetchone(
                        conn,
                        """
                        SELECT * FROM orders WHERE ticket = %s AND action = 'OPEN'
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        (p.ticket,),
                    )
                if owner is not None:
                    if p.order_id and owner["id"] != p.order_id:
                        await conn.execute(
                            "UPDATE positions SET order_id = %s, updated_at = now() "
                            "WHERE ticket = %s",
                            (owner["id"], p.ticket),
                        )
                    elif p.order_id is None:
                        # order_id terpotong dibuang validator -> pulihkan link
                        # dari fallback ticket, tanpa menimpa link yang sudah ada.
                        await conn.execute(
                            "UPDATE positions SET order_id = %s, updated_at = now() "
                            "WHERE ticket = %s AND order_id IS NULL",
                            (owner["id"], p.ticket),
                        )
                    continue
                # posisi broker tidak dikenal -> adopsi
                row = await fetchone(
                    conn,
                    """
                    INSERT INTO orders (user_id, symbol, side, volume, sl, tp, status, ticket,
                                        price_filled, strategy, action, sent_at, delivered_at)
                    VALUES (NULL, %s, %s, %s, %s, %s, 'ORPHAN_ADOPTED', %s, %s, 'reconciler',
                            'OPEN', now(), now())
                    RETURNING id, command_id
                    """,
                    (p.symbol, p.side.upper(), p.volume, p.sl, p.tp, p.ticket, p.open_price),
                )
                await conn.execute(
                    "UPDATE positions SET order_id = %s, updated_at = now() WHERE ticket = %s",
                    (row["id"], p.ticket),
                )
                await conn.execute(
                    """
                    INSERT INTO order_events (order_id, from_status, to_status, payload)
                    VALUES (%s, NULL, 'ORPHAN_ADOPTED', %s)
                    """,
                    (row["id"], json.dumps({
                        "source": "snapshot_reconciler", "ticket": p.ticket,
                        "symbol": p.symbol, "side": p.side.upper(), "volume": p.volume,
                        "open_price": p.open_price,
                        "reason": "posisi broker tanpa order DB (PRD 5.8)",
                    })),
                )
                entry: dict = {"order_id": str(row["id"]), "ticket": p.ticket,
                               "symbol": p.symbol, "side": p.side.upper(),
                               "volume": p.volume}
                # SL darurat bila posisi belum punya SL (PRD 5.8: "beri SL darurat
                # bila belum ada"). Jarak per-simbol dari spec risk (QA_MP5
                # finding 1); fallback persen harga bila simbol tanpa spec.
                if not p.sl:
                    dist, dist_source = _emergency_sl_distance(
                        p.symbol, p.open_price, settings)
                    sl_price = ((p.open_price or 0) - dist if p.side.upper() == "BUY"
                                else (p.open_price or 0) + dist)
                    sl_price = round(sl_price, 5)
                    await conn.execute(
                        "UPDATE positions SET sl = %s, updated_at = now() WHERE ticket = %s",
                        (sl_price, p.ticket),
                    )
                    await conn.execute(
                        """
                        INSERT INTO bridge_commands (order_id, action, payload)
                        VALUES (%s, 'MODIFY_SL', %s)
                        """,
                        (row["id"], json.dumps({
                            "ticket": p.ticket, "sl": sl_price, "tp": p.tp,
                            "reason": "orphan_emergency_sl",
                        })),
                    )
                    await record_event(
                        conn, row["id"], "emergency_sl_queued",
                        {"ticket": p.ticket, "sl": sl_price,
                         "distance": dist, "distance_source": dist_source},
                    )
                    entry["emergency_sl"] = sl_price
                orphans.append(entry)
            if orphans:
                await broadcaster_publish_orphans(orphans)

            # ── 3. Posisi DB OPEN yang hil dari snapshot broker ──
            tickets = [p.ticket for p in body.positions]
            if tickets:
                missing = await fetchall(
                    conn,
                    """
                    SELECT * FROM positions
                    WHERE status = 'OPEN' AND NOT (ticket = ANY(%s))
                    """,
                    (tickets,),
                )
            else:
                missing = await fetchall(
                    conn, "SELECT * FROM positions WHERE status = 'OPEN'"
                )
            for pos in missing:
                ticket = pos["ticket"]
                # bukti penutupan: deal OUT di snapshot (24 jam) atau order CLOSE FILLED
                deal = next(
                    (d for d in reversed(body.deals)
                     if d.position_id == ticket and d.entry in ("OUT", "INOUT")),
                    None,
                )
                close_order = await fetchone(
                    conn,
                    """
                    SELECT id FROM orders
                    WHERE action = 'CLOSE' AND status = 'FILLED' AND ticket = %s
                    """,
                    (ticket,),
                )
                owner = None
                if pos["order_id"]:
                    owner = await fetchone(
                        conn, "SELECT * FROM orders WHERE id = %s FOR UPDATE",
                        (pos["order_id"],),
                    )
                if owner is None:
                    owner = await fetchone(
                        conn,
                        "SELECT * FROM orders WHERE ticket = %s AND action = 'OPEN' "
                        "ORDER BY created_at DESC LIMIT 1 FOR UPDATE",
                        (ticket,),
                    )
                await conn.execute(
                    """
                    UPDATE positions SET status = 'CLOSED',
                        close_price = COALESCE(%s, close_price), close_time = now(),
                        profit = %s, updated_at = now()
                    WHERE ticket = %s AND status = 'OPEN'
                    """,
                    (deal.price if deal else None, deal.profit if deal else pos["profit"],
                     ticket),
                )
                closed.append({"ticket": ticket})
                if deal is not None or close_order is not None:
                    # penutupan bisa dijelaskan -> FILLED_THEN_CLOSED / ORPHAN_CLOSED
                    if owner is not None:
                        to_status = ("ORPHAN_CLOSED" if owner["status"] == "ORPHAN_ADOPTED"
                                     else "FILLED_THEN_CLOSED")
                        if to_status in ALLOWED_TRANSITIONS.get(owner["status"], set()):
                            await transition(
                                conn, owner["id"], to_status,
                                {"source": "snapshot_reconciler", "ticket": ticket,
                                 "deal_ticket": deal.ticket if deal else None,
                                 "close_price": deal.price if deal else None,
                                 "profit": deal.profit if deal else None,
                                 "close_order_filled": close_order is not None},
                            )
                        else:
                            await record_event(
                                conn, owner["id"], "reconciled_closed",
                                {"ticket": ticket, "note": f"status {owner['status']} tetap",
                                 "deal_ticket": deal.ticket if deal else None},
                            )
                        broadcaster.publish(
                            {"type": "order", "order_id": str(owner["id"]),
                             "status": to_status, "ticket": ticket}
                        )
                else:
                    # tak terjelaskan: order -> FAILED + kill-switch + alert
                    unexplained.append(ticket)
                    await conn.execute(
                        """
                        UPDATE positions SET raw = raw || %s, updated_at = now()
                        WHERE ticket = %s
                        """,
                        (json.dumps({"unexplained": True,
                                     "detected_at": datetime.now(timezone.utc).isoformat()}),
                         ticket),
                    )
                    if owner is not None and "FAILED" in ALLOWED_TRANSITIONS.get(
                            owner["status"], set()):
                        # t_afd7fe4e butir B: jalur FAILED ini dulu TANPA
                        # fail_reason sama sekali (salah satu sumber 192 NULL).
                        fail = fail_reason.detail(
                            "position_unexplained",
                            "posisi hilang dari snapshot broker tanpa deal penutup",
                            fail_reason.STAGE_BRIDGE_RECONCILE)
                        await transition(
                            conn, owner["id"], "FAILED",
                            {"source": "snapshot_reconciler", "ticket": ticket,
                             "reason": fail["message"], "fail": fail},
                            set_fields={"fail_reason": fail_reason.render(fail),
                                        "fail_detail": fail},
                            jsonb_fields=("fail_detail",),
                        )
                        broadcaster.publish(
                            {"type": "order", "order_id": str(owner["id"]),
                             "status": "FAILED", "ticket": ticket}
                        )
                    elif owner is not None:
                        await record_event(
                            conn, owner["id"], "reconciled_unexplained",
                            {"ticket": ticket,
                             "note": f"status {owner['status']} tidak bisa di-FAILED"},
                        )

    # ── 4. Notifikasi + kill-switch (setelah commit) ──
    if orphans:
        await notify_owner(
            "🔗 ORPHAN ADOPTED (PRD 5.8): " + "; ".join(
                f"{o['ticket']} {o['symbol']} {o['side']} {o['volume']} lot "
                f"-> order {o['order_id'][:8]}"
                + (f", SL darurat {o['emergency_sl']}" if o.get("emergency_sl") else "")
                for o in orphans
            )
        )
    if unexplained:
        broadcaster.publish({"type": "kill_switch", "event": "position_mismatch",
                             "tickets": unexplained})
        await notify_owner(
            "⚠️ REKONSILIASI (PRD 5.8): posisi hilang dari broker tanpa deal "
            f"penutup: {unexplained}. Order di-mark FAILED, kill-switch aktif."
        )
        await kill_switch.check_position_mismatch(unexplained)
    broadcaster.publish({"type": "positions", "open": len(body.positions),
                         "closed": [c["ticket"] for c in closed]})
    return {"ok": True, "open": len(body.positions),
            "closed": [c["ticket"] for c in closed],
            "orphans": [o["order_id"] for o in orphans],
            "unexplained": unexplained}


async def broadcaster_publish_orphans(orphans: list[dict]) -> None:
    """SSE broadcast adopsi orphan (dipanggil dalam transaksi, publish di luar)."""
    for o in orphans:
        broadcaster.publish({"type": "orphan", **o})
