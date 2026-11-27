"""Pre-flight gate deterministik sebelum LLM dipanggil (t_afd7fe4e).

Temuan kartu: 6 dari 10 siklus terakhir berakhir AGENT_INVALID karena order
ditolak/diabaikan broker (pasar tutup retcode 10018, EA offline, spread), dan
setiap siklus itu menghabiskan 50-110 detik LLM. Gate ini dijalankan DI AWAL
setiap siklus, tanpa LLM, dan memblok siklus sebelum token dibakar.

Urutan lapisan (semua harus lolos untuk satu simbol):

  stage=control         kill-switch, pause breaker LLM, daily drawdown
  stage=market_session  jam sesi simbol dari tabel `market_sessions`
  stage=ea              heartbeat EA (`ea_last_seen_at`) + simbol trading-enabled
  stage=market_data     harga terakhir ada, tick age <= max_tick_age_s,
                        spread <= max_spread

Sifat penting:
- Deterministik: hanya membaca state yang sudah ada (settings, tabel sesi,
  tick terakhir di memori API, drawdown). Tidak ada LLM, tidak ada fetch baru.
- Fail-closed: data yang tidak bisa dibuktikan = blok (tick hilang, sesi tidak
  punya baris, EA tidak ada heartbeat), kecuali dinyatakan lain di komentar
  tiap cek. Memblok siklus jauh lebih murah daripada order ke pasar tutup.
- Tidak menulis apa pun: audit `cycle_skipped` dilakukan pemanggil (endpoint
  API) supaya modul ini tetap murni dan mudah diuji.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from . import kill_switch, market, market_sessions, risk

STAGE_CONTROL = "control"
STAGE_SESSION = "market_session"
STAGE_EA = "ea"
STAGE_DATA = "market_data"

# Kode alasan (stabil, dipakai audit + test).
CODE_KILL_SWITCH = "kill_switch_active"
CODE_AGENT_PAUSE = "llm_agent_paused"
CODE_DRAWDOWN = "daily_drawdown_limit"
CODE_EA_OFFLINE = "ea_offline"
CODE_EA_NEVER_SEEN = "ea_never_seen"
CODE_SYMBOL_DISABLED = "symbol_trade_disabled"
CODE_NO_TICK = "tick_missing"
CODE_STALE_TICK = "tick_stale"
CODE_SPREAD = "spread_too_wide"
CODE_NO_PRICE = "price_missing"
CODE_SESSION = "market_closed"

# Cek per simbol, urut sesuai rantai di kartu.
_CHECK_ORDER = (STAGE_SESSION, STAGE_EA, STAGE_DATA)


def _check(code: str, stage: str, ok: bool, message: str, **detail) -> dict:
    return {"code": code, "stage": stage, "ok": bool(ok), "message": message,
            **({"detail": detail} if detail else {})}


def _money(value: float | None) -> str:
    return "-" if value is None else f"{value:.5f}"


def control_checks(settings: dict, *, drawdown_pct: float | None) -> list[dict]:
    """Lapisan kontrol global (tidak per simbol)."""
    checks: list[dict] = []

    state = kill_switch.normalize_state(settings.get("kill_switch"))
    if state["active"] and state["mode"] != "PAUSE_STRATEGY":
        checks.append(_check(
            CODE_KILL_SWITCH, STAGE_CONTROL, False,
            f"kill-switch aktif (mode {state['mode']}): {state.get('reason') or '-'}",
            mode=state["mode"], activated_at=state.get("activated_at"),
        ))
    else:
        checks.append(_check(CODE_KILL_SWITCH, STAGE_CONTROL, True,
                             "kill-switch tidak aktif"))

    pause = settings.get("llm_agent_pause")
    if isinstance(pause, dict) and pause.get("active"):
        checks.append(_check(
            CODE_AGENT_PAUSE, STAGE_CONTROL, False,
            f"agent LLM di-pause circuit breaker: {pause.get('reason') or '-'}",
        ))
    else:
        checks.append(_check(CODE_AGENT_PAUSE, STAGE_CONTROL, True,
                             "agent LLM tidak di-pause"))

    from .drawdown import limit_pct

    limit = limit_pct(settings)
    if limit is None:
        checks.append(_check(CODE_DRAWDOWN, STAGE_CONTROL, True,
                             "trigger drawdown harian dimatikan owner"))
    elif drawdown_pct is None:
        # Drawdown tidak terbaca = tidak bisa dibuktikan di bawah ambang.
        # Fail-closed, sejalan dengan gate order (drawdown tak terbaca ditolak).
        checks.append(_check(CODE_DRAWDOWN, STAGE_CONTROL, False,
                             "drawdown harian tidak terbaca (fail-closed)"))
    elif float(drawdown_pct) >= float(limit):
        checks.append(_check(
            CODE_DRAWDOWN, STAGE_CONTROL, False,
            f"drawdown harian {float(drawdown_pct):.2f}% >= ambang {float(limit)}%",
            drawdown_pct=float(drawdown_pct), limit_pct=float(limit),
        ))
    else:
        checks.append(_check(
            CODE_DRAWDOWN, STAGE_CONTROL, True,
            f"drawdown harian {float(drawdown_pct):.2f}% < ambang {float(limit)}%",
            drawdown_pct=float(drawdown_pct), limit_pct=float(limit),
        ))
    return checks


def _ea_threshold_s(settings: dict) -> float:
    """Ambang offline EA efektif: kill_switch_triggers.ea_offline_seconds."""
    default = float(kill_switch.DEFAULT_TRIGGERS["ea_offline_seconds"])
    raw = settings.get("kill_switch_triggers")
    if not isinstance(raw, dict):
        return default
    value = raw.get("ea_offline_seconds")
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _num(settings: dict, key: str, default: float) -> float:
    try:
        return float(settings.get(key, default))
    except (TypeError, ValueError):
        return default


def symbol_checks(symbol: str, *, sessions: list[dict], tick: dict | None,
                  ea_age_s: float | None, settings: dict,
                  now: datetime, status: dict | None = None) -> list[dict]:
    """Rantai cek satu simbol: sesi -> EA -> data pasar.

    `status` (opsional) = hasil app.market_status untuk simbol ini. Bila EA
    melaporkan CLOSED (source='ea'), cek sesi digagalkan dengan alasan broker
    walau tabel jadwal bilang buka: libur bursa / maintenance broker tidak
    pernah ada di tabel sesi, dan EA adalah satu-satunya saksi kondisi broker.
    """
    checks: list[dict] = []

    # 1. Sesi pasar dari tabel (bukan hardcode).
    open_, reason = market_sessions.session_open(sessions, now)
    ea_closed = bool(status and status.get("market_status") == "CLOSED"
                     and status.get("source") == "ea")
    if ea_closed:
        open_ = False
        reason = (f"market_closed: EA melaporkan pasar tutup "
                  f"({status.get('market_close_reason') or 'broker'})")
    elif status and status.get("market_status") == "OPEN" and status.get("source") == "ea":
        open_ = True
        reason = "market terbuka menurut EA"
    checks.append(_check(
        CODE_SESSION if not open_ else "market_session_open",
        STAGE_SESSION, open_,
        reason if not open_ else f"pasar buka: {reason}",
        windows=len(sessions),
        **({"market_status_source": status.get("source")} if status else {}),
    ))

    # 2. Heartbeat EA + simbol trading-enabled.
    threshold = _ea_threshold_s(settings)
    if ea_age_s is None:
        checks.append(_check(
            CODE_EA_NEVER_SEEN, STAGE_EA, False,
            "EA belum pernah terlihat (tidak ada heartbeat)",
            offline_threshold_s=threshold))
    elif float(ea_age_s) > threshold:
        checks.append(_check(
            CODE_EA_OFFLINE, STAGE_EA, False,
            f"EA offline {float(ea_age_s):.1f}s > ambang {threshold:.1f}s",
            age_s=round(float(ea_age_s), 1), offline_threshold_s=threshold))
    else:
        checks.append(_check(
            "ea_online", STAGE_EA, True,
            f"EA terakhir terlihat {float(ea_age_s):.1f}s lalu "
            f"(ambang {threshold:.1f}s)",
            age_s=round(float(ea_age_s), 1), offline_threshold_s=threshold))

    # Trading-enabled per simbol: EA v5 belum mengirim flag ini, jadi yang
    # tersedia hanya tick (bid/ask terisi). Bila EA kelak mengirim
    # `trade_enabled`, nilainya MENANG atas dugaan (False -> blok).
    trade_enabled = (tick or {}).get("trade_enabled")
    if trade_enabled is False:
        checks.append(_check(
            CODE_SYMBOL_DISABLED, STAGE_EA, False,
            f"{symbol} dilaporkan EA tidak trading-enabled"))
    elif trade_enabled is True:
        checks.append(_check("symbol_trade_enabled", STAGE_EA, True,
                             f"{symbol} trading-enabled menurut EA"))
    else:
        checks.append(_check(
            "symbol_trade_enabled_unknown", STAGE_EA, True,
            f"{symbol}: EA belum melaporkan status trading-enabled "
            "(dibuktikan lewat tick di cek data pasar)",
            reported=False))

    # 3. Data pasar: harga terakhir, umur tick, spread.
    # Ambang spread per simbol diambil dari `symbol_specs.<SYM>.spread_abs_max_usd`
    # (sama dengan gate order risk.py A9): satu angka global akan memblok BTCUSD
    # selamanya karena spread BTC ~USD 39 vs XAU ~0.3.
    max_tick_age = _num(settings, "max_tick_age_s", 3.0)
    spec = risk.symbol_spec(symbol, settings) or {}
    max_spread = _num(spec, "spread_abs_max_usd",
                      _num(settings, "max_spread", 0.50))
    if not tick:
        checks.append(_check(CODE_NO_TICK, STAGE_DATA, False,
                             f"tidak ada tick terakhir untuk {symbol}"))
        checks.append(_check(CODE_NO_PRICE, STAGE_DATA, False,
                             "harga terakhir tidak tersedia"))
        return checks
    bid, ask = tick.get("bid"), tick.get("ask")
    if bid is None or ask is None or float(bid) <= 0 or float(ask) <= 0:
        checks.append(_check(CODE_NO_PRICE, STAGE_DATA, False,
                             f"harga terakhir tidak lengkap (bid={bid} ask={ask})"))
    else:
        checks.append(_check(CODE_NO_PRICE, STAGE_DATA, True,
                             f"harga terakhir bid={_money(float(bid))} "
                             f"ask={_money(float(ask))}"))
    age = None
    if tick.get("ts") is not None:
        try:
            age = max(0.0, time.time() - float(tick["ts"]))
        except (TypeError, ValueError):
            age = None
    if age is None:
        checks.append(_check(CODE_STALE_TICK, STAGE_DATA, False,
                             "umur tick tidak bisa dihitung (fail-closed)"))
    elif age > max_tick_age:
        checks.append(_check(
            CODE_STALE_TICK, STAGE_DATA, False,
            f"tick basi {age:.1f}s > max_tick_age_s {max_tick_age:.1f}s",
            age_s=round(age, 1), max_tick_age_s=max_tick_age))
    else:
        checks.append(_check(CODE_STALE_TICK, STAGE_DATA, True,
                             f"tick segar {age:.1f}s (<= {max_tick_age:.1f}s)",
                             age_s=round(age, 1), max_tick_age_s=max_tick_age))
    spread = tick.get("spread")
    if spread is None and bid is not None and ask is not None:
        try:
            spread = float(ask) - float(bid)
        except (TypeError, ValueError):
            spread = None
    if spread is None:
        checks.append(_check(CODE_SPREAD, STAGE_DATA, False,
                             "spread tidak tersedia (fail-closed)"))
    elif float(spread) > max_spread:
        checks.append(_check(
            CODE_SPREAD, STAGE_DATA, False,
            f"spread {float(spread):.5f} > max_spread {max_spread:.5f}",
            spread=float(spread), max_spread=max_spread))
    else:
        checks.append(_check(CODE_SPREAD, STAGE_DATA, True,
                             f"spread {float(spread):.5f} <= {max_spread:.5f}",
                             spread=float(spread), max_spread=max_spread))
    return checks


def evaluate(*, settings: dict, symbols: list[str], sessions: dict[str, list[dict]],
             ticks: dict[str, dict | None], ea_age_s: float | None,
             drawdown_pct: float | None, now: datetime | None = None,
             statuses: dict[str, dict] | None = None) -> dict:
    """Susun hasil pre-flight dari state yang sudah dikumpulkan (murni).

    `symbols` = kandidat siklus ini (sudah difilter policy allowed_symbols /
    jadwal hari oleh pemanggil). Kembalian selalu berbentuk sama, juga saat
    semua diblok, supaya pemanggil bisa mencatat alasan apa adanya.
    `statuses` = hasil app.market_status per simbol (opsional); hanya laporan
    EA yang boleh mengubah hasil cek sesi (lihat symbol_checks).
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    control = control_checks(settings, drawdown_pct=drawdown_pct)
    control_ok = all(c["ok"] for c in control)

    per_symbol: dict[str, dict] = {}
    allowed: list[str] = []
    blocked: list[dict] = []
    for symbol in symbols:
        sym = str(symbol).upper()
        checks = symbol_checks(sym, sessions=sessions.get(sym) or [],
                               tick=ticks.get(sym), ea_age_s=ea_age_s,
                               settings=settings, now=now,
                               status=(statuses or {}).get(sym))
        ok = control_ok and all(c["ok"] for c in checks)
        per_symbol[sym] = {"ok": ok, "checks": checks, "blocked_by_context": not control_ok}
        if ok:
            allowed.append(symbol)
            continue
        first_fail = next((c for c in checks if not c["ok"]), None)
        if first_fail is None:  # hanya kontrol global yang memblok
            first_fail = next(c for c in control if not c["ok"])
        blocked.append({
            "symbol": sym,
            "code": first_fail["code"],
            "stage": first_fail["stage"],
            "message": first_fail["message"],
        })

    reason = None
    if blocked:
        parts = [f"{b['symbol']}: {b['code']} ({b['stage']}) - {b['message']}"
                 for b in blocked]
        reason = "preflight_blocked: " + " | ".join(parts)
    elif not symbols:
        reason = "preflight_blocked: tidak ada simbol kandidat siklus ini"
    return {
        "ok": bool(allowed),
        "now_utc": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "allowed": allowed,
        "blocked": blocked,
        "symbols": per_symbol,
        "control": {"ok": control_ok, "checks": control},
        "reason": reason,
    }


async def run_preflight(conn, settings: dict, symbols: list[str],
                        now: datetime | None = None) -> dict:
    """Kumpulkan state (sesi, tick, EA, drawdown) lalu evaluasi rantai.

    Dipanggil dari proses API (punya `market._latest` + heartbeat in-memory).
    Tidak pernah raise untuk hal yang bisa diprediksi: kegagalan baca sesi /
    drawdown menghasilkan blok dengan kode yang jelas alias fail-closed.
    """
    from . import llm_risk

    now = now or datetime.now(timezone.utc)
    started = time.monotonic()
    wanted = [str(s).upper() for s in symbols]
    try:
        sessions = await market_sessions.load_rows(conn, wanted)
    except Exception as exc:  # noqa: BLE001 - fail-closed dengan alasan jelas
        sessions = {}
        session_error = f"{type(exc).__name__}: {exc}"[:200]
        for sym in wanted:
            sessions[sym] = []
        result = evaluate(settings=settings, symbols=wanted, sessions=sessions,
                          ticks={sym: market.latest(sym) for sym in wanted},
                          ea_age_s=kill_switch.ea_last_seen_age_s(),
                          drawdown_pct=None, now=now)
        result["error"] = f"baca market_sessions gagal: {session_error}"
        result["latency_ms"] = int((time.monotonic() - started) * 1000)
        return result
    ticks = {sym: market.latest(sym) for sym in wanted}
    # Status pasar dari modul yang sama dengan /market/status & gate order.
    # Rows sesi sudah dibaca di atas (tanpa query tambahan); kegagalan apa pun
    # di sini tidak boleh menggagalkan pre-flight: status None = cek sesi murni.
    statuses: dict[str, dict] = {}
    try:
        from . import market_status

        for sym in wanted:
            statuses[sym] = await market_status.resolve(
                sym, now=now, rows=sessions.get(sym) or [])
    except Exception as exc:  # noqa: BLE001 - fail-soft, alasan dicatat
        statuses = {}
        status_error = f"{type(exc).__name__}: {exc}"[:200]
    else:
        status_error = None
    try:
        drawdown_pct = await llm_risk.daily_drawdown_pct(conn, settings)
    except Exception as exc:  # noqa: BLE001 - fail-closed (None -> blok)
        drawdown_pct = None
        dd_error = f"{type(exc).__name__}: {exc}"[:200]
    else:
        dd_error = None
    result = evaluate(settings=settings, symbols=wanted, sessions=sessions,
                      ticks=ticks, ea_age_s=kill_switch.ea_last_seen_age_s(),
                      drawdown_pct=drawdown_pct, now=now, statuses=statuses)
    if dd_error:
        result["error"] = f"baca drawdown gagal: {dd_error}"
    if status_error:
        result["status_error"] = f"baca market_status gagal: {status_error}"
    result["latency_ms"] = int((time.monotonic() - started) * 1000)
    return result


# ── Prometheus-friendly ringkasan (dipakai /llm-agent/latency & dashboard) ──
def summarise_checks(result: dict) -> list[dict]:
    """Ratakan cek kontrol + per simbol menjadi daftar ringkas untuk UI."""
    out = [{**c, "symbol": None} for c in (result.get("control") or {}).get("checks", [])]
    for sym, block in (result.get("symbols") or {}).items():
        for c in block.get("checks") or []:
            out.append({**c, "symbol": sym})
    return out
