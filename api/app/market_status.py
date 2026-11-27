"""Status pasar per simbol (GET /market/status, gate order, gate candle).

Kontrak GET /market/status?symbol=:

    {symbol, market_status: 'OPEN'|'CLOSED'|'UNKNOWN',
     market_close_reason: null|'weekend'|'session'|'holiday'|'broker'|'no_data',
     trade_mode: 'FULL'|'CLOSEONLY'|'DISABLED'|null,
     last_tick_ts, last_tick_age_s, next_open_ts, ea_seen_s,
     source: 'ea'|'session'|'derived'}

Sumber kebenaran berlapis (yang paling kuat menang):

1. ``ea`` — EA mengirim status broker-nya sendiri lewat POST /bridge/heartbeat
   (field opsional ``market_status``/``market_close_reason``/``trade_mode``).
   Ini satu-satunya sumber yang tahu kondisi broker sebenarnya (maintenance,
   holiday bursa, SYMBOL_TRADE_MODE). Berlaku selama laporannya segar
   (``EA_STATUS_TTL_S``).
2. ``session`` — tabel ``market_sessions`` (migrasi o015): jendela jam pasar
   per simbol di zona waktu barisnya. Simbol 24/7 (BTCUSD, semua 7 hari
   00:00-24:00) TIDAK PERNAH ditutup oleh jadwal.
3. ``derived`` — tidak ada laporan EA dan tidak ada baris sesi: dipakai bukti
   feed (tick yang lolos freeze guard pipeline ingest). Feed hidup = OPEN,
   feed diam >= ``FEED_CLOSED_MIN_S`` = CLOSED ('no_data'), selain itu
   UNKNOWN. Tidak pernah menebak OPEN tanpa bukti.

Kenapa feed dipakai sebagai bukti ketiga dan bukan "umur tick" biasa: EA tetap
mengirim kutipan beku ~1-2/detik saat pasar tutup (terukur 203.159 tick
XAUUSD hari Minggu 22 Nov 2026), jadi ``last_tick_age_s`` kecil TIDAK
membuktikan pasar buka. Yang membuktikan adalah tick yang lolos freeze guard
(harga bergerak) — pipeline ingest sudah menghitungnya.

Gate order (POST /orders) memakai fungsi yang sama, dengan satu syarat
tambahan ``enforceable()``: 409 hanya dikirim bila jalur eksekusi benar-benar
ada (EA terhubung segar). Tanpa EA, order tidak mungkin dieksekusi sama
sekali, dan penolakan berbasis jam dinding akan mengunci order yang sah
(temuan nyata: suite pytest berjalan di jam mana pun, termasuk jendela tutup
harian 04:59-06:00 WIB dan akhir pekan, tanpa EA terhubung).

Modul ini juga menyimpan laporan terakhir EA in-memory (dipakai pipeline
ingest untuk berhenti membuat bar datar) plus persist ringan ke settings
``market_status_last`` (throttled, untuk audit; TIDAK dipakai sebagai dasar
keputusan agar status basi pasca-restart tidak pernah dipercaya).
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from . import db, kill_switch, market, market_sessions

STATUS_OPEN = "OPEN"
STATUS_CLOSED = "CLOSED"
STATUS_UNKNOWN = "UNKNOWN"
STATUSES = (STATUS_OPEN, STATUS_CLOSED, STATUS_UNKNOWN)

REASON_WEEKEND = "weekend"
REASON_SESSION = "session"
REASON_HOLIDAY = "holiday"
REASON_BROKER = "broker"
REASON_NO_DATA = "no_data"
REASONS = (REASON_WEEKEND, REASON_SESSION, REASON_HOLIDAY, REASON_BROKER, REASON_NO_DATA)

TRADE_MODE_FULL = "FULL"
TRADE_MODE_CLOSEONLY = "CLOSEONLY"
TRADE_MODE_DISABLED = "DISABLED"
TRADE_MODES = (TRADE_MODE_FULL, TRADE_MODE_CLOSEONLY, TRADE_MODE_DISABLED)
# Nilai mentah MT5 (ENUM_SYMBOL_TRADE_MODE) yang diterima selain string.
_TRADE_MODE_BY_INT = {"0": TRADE_MODE_FULL, "1": TRADE_MODE_CLOSEONLY,
                      "2": TRADE_MODE_DISABLED}

# Laporan EA lebih tua dari ini tidak dipercaya (EA heartbeat tiap ~2 dtk).
EA_STATUS_TTL_S = 60.0
# Jalur eksekusi dianggap ada bila EA terlihat (poll/tick/heartbeat) sedekat ini.
EA_LINK_FRESH_S = 90.0
# Bukti feed: tick diam selama ini = pasar tutup menurut data (sama dengan
# FREEZE_TIMEOUT_S pipeline ingest, satu definisi beku untuk satu sistem).
FEED_CLOSED_MIN_S = 600.0
# Persist ringan ke settings: paling sering sekali per 30 dtk.
PERSIST_EVERY_S = 30.0

SETTINGS_KEY = "market_status_last"

_lock = threading.Lock()
_reports: dict[str, dict] = {}          # symbol -> laporan ternormalisasi
_global_report: dict | None = None      # heartbeat tanpa field symbol
_published: dict[str, str] = {}         # symbol -> status terakhir yang di-SSE
_last_persist_mono = 0.0


def now_utc() -> datetime:
    """Jam UTC sekarang (satu titik injeksi untuk test yang butuh jam tetap)."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- normalisasi

def normalize_status(value) -> str | None:
    """'open'/'CLOSED'/... -> status kanonik; nilai asing -> None (diabaikan)."""
    if value is None:
        return None
    text = str(value).strip().upper()
    return text if text in STATUSES else None


def normalize_trade_mode(value) -> str | None:
    """Terima string ('full', 'CLOSEONLY') atau int ENUM MT5 (0/1/2)."""
    if value is None:
        return None
    if isinstance(value, bool):  # bool adalah int di Python: bukan trade mode
        return None
    if isinstance(value, (int, float)):
        return _TRADE_MODE_BY_INT.get(str(int(value)))
    text = str(value).strip().upper()
    if text in TRADE_MODES:
        return text
    return _TRADE_MODE_BY_INT.get(text)


def normalize_reason(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text if text in REASONS else None


def _parse_symbol_time(value) -> str | None:
    """symbol_time dari EA: string apa adanya (ISO/jam broker) atau epoch."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    return text or None


# ---------------------------------------------------------------- laporan EA

def record_report(symbol: str | None, *, market_status=None,
                  market_close_reason=None, trade_mode=None,
                  symbol_time=None, tick_age_s=None,
                  now: datetime | None = None) -> dict:
    """Simpan laporan status EA terakhir. Return {'changed': bool, 'status': ...}.

    Semua field opsional: yang tidak dikirim EA TIDAK menghapus nilai
    sebelumnya (EA versi lama tidak mengirim apa pun -> registry tetap kosong,
    tidak ada 422 dan tidak ada status palsu).
    """
    global _global_report
    now = now or now_utc()
    sym = (symbol or "").strip().upper()
    status = normalize_status(market_status)
    mode = normalize_trade_mode(trade_mode)
    reason = normalize_reason(market_close_reason)
    if sym == "" and status is None and mode is None:
        return {"changed": False, "status": None}

    entry = {
        "market_status": status,
        "market_close_reason": reason,
        "trade_mode": mode,
        "symbol_time": _parse_symbol_time(symbol_time),
        "tick_age_s": _as_float(tick_age_s),
        "received_at": now,
        "received_mono": time.monotonic(),
    }
    with _lock:
        if sym == "":
            prev = _global_report
            _global_report = _merge(prev, entry)
            merged = _global_report
        else:
            prev = _reports.get(sym)
            _reports[sym] = _merge(prev, entry)
            merged = _reports[sym]
    resolved = merged.get("market_status")
    changed = resolved is not None and _published.get(sym) != resolved
    if changed:
        _published[sym] = resolved
    return {"changed": changed, "symbol": sym,
            "status": {"symbol": sym, "market_status": resolved,
                       "market_close_reason": merged.get("market_close_reason"),
                       "trade_mode": merged.get("trade_mode")}}


def _merge(prev: dict | None, entry: dict) -> dict:
    """Laporan baru menimpa field yang dikirim; field absen mempertahankan nilai.

    Semua kunci kontrak selalu ada (None bila tidak pernah dilaporkan) supaya
    pembaca registry tidak perlu membedakan "belum ada" dari "None".
    """
    out = {key: None for key in ("market_status", "market_close_reason",
                                 "trade_mode", "symbol_time", "tick_age_s")}
    out.update(prev or {})
    for key, value in entry.items():
        if key in ("received_at", "received_mono"):
            out[key] = value
        elif value is not None:
            out[key] = value
    return out


def _as_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def report(symbol: str | None) -> dict | None:
    """Laporan terakhir untuk simbol (fallback ke laporan global), atau None."""
    sym = (symbol or "").strip().upper()
    with _lock:
        entry = _reports.get(sym) or _global_report
        if entry is None:
            return None
        # Normalisasi lewat _merge: konsumen (decide(), route, test) selalu
        # mendapat seluruh kunci kontrak walau entri masuk lewat jalur lain.
        out = _merge(None, dict(entry))
    out["age_s"] = max(0.0, time.monotonic() - float(out.get("received_mono") or 0.0))
    return out


def closed_flag(symbol: str | None) -> bool:
    """True bila EA melaporkan simbol TUTUP (dipakai pipeline ingest, murni memori).

    Hanya laporan segar yang dipercaya: status CLOSED yang tersisa dari
    berjam-jam lalu tidak boleh membekukan penulisan bar.
    """
    rep = report(symbol)
    return bool(rep and rep.get("market_status") == STATUS_CLOSED
                and float(rep.get("age_s") or 0.0) <= EA_STATUS_TTL_S)


def clear() -> None:
    """Kosongkan registry (test / restart kontrol)."""
    global _global_report, _last_persist_mono
    with _lock:
        _reports.clear()
        _published.clear()
        _global_report = None
    _last_persist_mono = 0.0


# ---------------------------------------------------------------- keputusan

def _is_247(rows: list[dict] | None) -> bool:
    """True bila baris sesi menutupi 7 hari penuh (crypto 24/7)."""
    enabled = [r for r in (rows or []) if r.get("enabled", True)]
    if {int(r["weekday"]) for r in enabled} != set(range(7)):
        return False
    return all(int(r["open_minute"]) == 0 and int(r["close_minute"]) >= 1440
               for r in enabled)


def _closure_reason(rows: list[dict] | None, now: datetime) -> str:
    """'weekend' bila penutupan jatuh di Sabtu/Minggu (waktu baris sesi), else 'session'."""
    tz_name = None
    for row in rows or []:
        if row.get("enabled", True):
            tz_name = row.get("timezone")
            break
    local = now.astimezone(market_sessions._tz(tz_name))
    return REASON_WEEKEND if local.weekday() >= 5 else REASON_SESSION


def decide(symbol: str, *, rows: list[dict] | None, now: datetime,
           report_entry: dict | None = None, feed_age_s: float | None = None,
           tick: dict | None = None, ea_seen_s: float | None = None,
           next_open_ts: datetime | None = None) -> dict:
    """Fungsi murni: susun status pasar dari bukti yang sudah dikumpulkan."""
    sym = (symbol or "").strip().upper()
    status: str = STATUS_UNKNOWN
    reason: str | None = None
    source: str = "derived"
    trade_mode: str | None = None

    ea_fresh = bool(report_entry and float(report_entry.get("age_s") or 0.0) <= EA_STATUS_TTL_S)
    ea_status = report_entry.get("market_status") if ea_fresh else None
    if ea_fresh:
        trade_mode = report_entry.get("trade_mode")

    if ea_status in (STATUS_OPEN, STATUS_CLOSED):
        status = ea_status
        source = "ea"
        if status == STATUS_CLOSED:
            reason = report_entry.get("market_close_reason") or REASON_BROKER
    elif rows:
        open_, _label = market_sessions.session_open(rows, now)
        if _is_247(rows):
            open_ = True
        if open_:
            status, source, reason = STATUS_OPEN, "session", None
        else:
            status, source = STATUS_CLOSED, "session"
            reason = _closure_reason(rows, now)
    else:
        # Tanpa jadwal: hanya bukti feed. Tidak pernah menebak OPEN tanpa bukti.
        if feed_age_s is not None and feed_age_s <= EA_LINK_FRESH_S:
            status, source = STATUS_OPEN, "derived"
        elif feed_age_s is None:
            status, source, reason = STATUS_UNKNOWN, "derived", REASON_NO_DATA
        elif feed_age_s >= FEED_CLOSED_MIN_S:
            status, source, reason = STATUS_CLOSED, "derived", REASON_NO_DATA
        else:
            status, source, reason = STATUS_UNKNOWN, "derived", REASON_NO_DATA

    last_tick_ts = None
    last_tick_age_s = None
    if tick is not None:
        ts = tick.get("ts")
        age = _as_float(ts)
        if age is not None:
            last_tick_age_s = max(0.0, now.timestamp() - age)
            last_tick_ts = datetime.fromtimestamp(age, tz=timezone.utc).isoformat()
        ex = tick.get("exchange_ts")
        if last_tick_ts is None and ex is not None:
            last_tick_ts = _parse_symbol_time(ex)

    return {
        "symbol": sym,
        "market_status": status,
        # Alasan penutupan hanya bermakna saat CLOSED / UNKNOWN; OPEN selalu null.
        "market_close_reason": reason if status in (STATUS_CLOSED, STATUS_UNKNOWN) else None,
        "trade_mode": trade_mode,
        "last_tick_ts": last_tick_ts,
        "last_tick_age_s": _round1(last_tick_age_s),
        "next_open_ts": next_open_ts.isoformat() if next_open_ts else None,
        "ea_seen_s": _round1(ea_seen_s),
        "source": source,
    }


def _round1(value: float | None) -> float | None:
    return None if value is None else round(float(value), 1)


def _next_open(rows: list[dict] | None, now: datetime,
               status: str) -> datetime | None:
    """Waktu buka berikutnya; None bila sudah buka / 24-7 / tidak terjadwal."""
    if status != STATUS_CLOSED or not rows or _is_247(rows):
        return None
    try:
        return market_sessions.next_open(rows, now)
    except Exception:  # noqa: BLE001 - jadwal rusak tidak boleh menggagalkan status
        return None


_UNSET = object()


async def resolve(symbol: str, *, now: datetime | None = None,
                  rows=_UNSET, conn=None) -> dict:
    """Status pasar satu simbol (kontrak GET /market/status).

    `rows` boleh diisi pemanggil yang sudah membaca market_sessions (preflight);
    `_UNSET` = baca DB di sini. Kegagalan baca sesi -> status 'derived' (bukan
    raise): endpoint status tidak boleh 500 hanya karena DB sesi bermasalah.
    """
    from . import ingest as ingest_mod

    sym = (symbol or "").strip().upper()
    now = now or now_utc()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    session_rows = rows
    if session_rows is _UNSET:
        try:
            if conn is not None:
                session_rows = (await market_sessions.load_rows(conn, [sym])).get(sym) or []
            else:
                async with db.pool().connection() as own:
                    session_rows = (await market_sessions.load_rows(own, [sym])).get(sym) or []
        except Exception as exc:  # noqa: BLE001 - fail-soft, alasan di log pemanggil
            print(f"[market_status] baca market_sessions gagal ({sym}): {exc!r}", flush=True)
            session_rows = []

    try:
        feed_age_s = ingest_mod.get_pipeline().feed_age_s(sym)
    except Exception:  # noqa: BLE001 - pipeline belum ada: tidak ada bukti feed
        feed_age_s = None

    status = decide(sym, rows=session_rows, now=now, report_entry=report(sym),
                    feed_age_s=feed_age_s, tick=market.latest(sym),
                    ea_seen_s=kill_switch.ea_last_seen_age_s(),
                    next_open_ts=None)
    nxt = _next_open(session_rows, now, status["market_status"])
    status["next_open_ts"] = nxt.isoformat() if nxt else None
    _publish_if_changed(sym, status)
    return status


def _publish_if_changed(symbol: str, status: dict) -> None:
    """SSE type='market' hanya saat status simbol benar-benar berubah."""
    current = status.get("market_status")
    with _lock:
        prev = _published.get(symbol)
        if prev == current:
            return
        _published[symbol] = current
    try:
        from .sse import broadcaster

        broadcaster.publish({"type": "market", **status})
    except Exception:  # noqa: BLE001 - SSE tidak boleh menggagalkan status
        pass


def enforceable() -> bool:
    """True bila penolakan order berbasis status pasar punya jalur eksekusi.

    Syarat: EA terlihat segar (poll/tick/heartbeat) ATAU ada laporan status EA
    yang segar. Tanpa keduanya tidak ada yang bisa mengeksekusi order dan jam
    dinding saja tidak cukup untuk menolak (lihat docstring modul).
    """
    age = kill_switch.ea_last_seen_age_s()
    if age is not None and age <= EA_LINK_FRESH_S:
        return True
    with _lock:
        for entry in list(_reports.values()) + ([_global_report] if _global_report else []):
            if entry and float(entry.get("received_mono") or 0.0) and \
                    time.monotonic() - float(entry["received_mono"]) <= EA_STATUS_TTL_S:
                return True
    return False


# ---------------------------------------------------------------- persist

def snapshot() -> dict:
    """Ringkasan registry untuk persist/observability."""
    with _lock:
        out = {sym: _jsonable(entry) for sym, entry in _reports.items()}
        if _global_report:
            out[""] = _jsonable(_global_report)
    return out


def _jsonable(entry: dict) -> dict:
    return {
        "market_status": entry.get("market_status"),
        "market_close_reason": entry.get("market_close_reason"),
        "trade_mode": entry.get("trade_mode"),
        "symbol_time": entry.get("symbol_time"),
        "tick_age_s": entry.get("tick_age_s"),
        "received_at": (entry.get("received_at").isoformat()
                        if isinstance(entry.get("received_at"), datetime) else None),
    }


async def persist_throttled(*, force: bool = False, min_interval_s: float = PERSIST_EVERY_S) -> bool:
    """Tulis registry ke settings ``market_status_last`` (throttled, best-effort).

    Throttle mencegah heartbeat 2 detik EA menjadi beban tulis DB. Kegagalan
    (DB sibuk, key terkunci) diabaikan: status pasar tidak boleh bergantung
    pada keberhasilan audit.
    """
    global _last_persist_mono
    now = time.monotonic()
    if not force and now - _last_persist_mono < min_interval_s:
        return False
    data = snapshot()
    if not data:
        return False
    _last_persist_mono = now
    try:
        await db.set_setting(SETTINGS_KEY, {"by_symbol": data,
                                           "updated_at": now_utc().isoformat()})
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[market_status] persist gagal (diabaikan): {exc!r}", flush=True)
        return False
