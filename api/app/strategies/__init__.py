"""Strategy registry + statistik live untuk GET /strategies (PRD P1b Strategy Lab).

Sumber kebenaran:
- Registry strategi terdaftar: statis di paket ini (Track A: api/strategies/,
  Track B ML: app/strategies/ — strategi baru wajib punya modul di sana
  sebelum didaftarkan di sini).
- Mode (paper/live/off): settings key `strategy_mode_<id>`; dibaca paper
  runner tiap iterasi (paper/runner.py strategy_mode()) — "off" menghentikan
  entry baru, runner tetap mengelola posisi terbuka.
- Statistik & kurva ekuitas: ledger paper_orders (mode PAPER) + saldo
  paper_state key "runner".
"""

from __future__ import annotations

import json
import math

from ..state_machine import fetchall, fetchone

PAPER_LEDGER_MODE = "PAPER"     # paper_orders.mode untuk ledger paper
DEFAULT_START_BALANCE = 10000.0  # paper/store.DEFAULT_STATE["balance"]
PAPER_GATE_DAYS = 20            # gerbang UI Strategy Lab sebelum tombol Live
VALID_MODES = ("paper", "live", "off")

REGISTRY: list[dict] = [
    {
        "id": "london_breakout",
        "name": "London Breakout + Spread Filter",
        "track": "A",
        "symbol": "XAUUSD",  # simbol yang di-trade strategi (paper runner SYMBOL)
        "desc": "Breakout range sesi Asia + filter spread rata-rata 15 menit "
                "(PRD 5.3). Gerbang: paper 20 hari sebelum live.",
        "mode_key": "strategy_mode_london_breakout",
        "state_key": "runner",  # legacy: state paper strategi #1
    },
    {
        "id": "mean_reversion",
        "name": "Mean Reversion (Bollinger re-entry)",
        "track": "A",  # rule-based; Track B = ML (PRD 5.3)
        "symbol": "XAUUSD",  # simbol yang di-trade strategi (paper runner SYMBOL)
        "desc": "Mean reversion Bollinger (SMA20 +/- 2.5 sigma): harga menembus "
                "band lalu re-entry, target ke mean. Gerbang: paper 20 hari.",
        "mode_key": "strategy_mode_mean_reversion",
        "state_key": "runner_mean_reversion",
    },
    {
        "id": "btc_range_breakout",
        "name": "BTC Range Breakout 24/7",
        "track": "A",
        "symbol": "BTCUSD",
        "desc": "Breakout channel Donchian 24 bar H1 + filter volatilitas ATR, "
                "24/7 khas crypto. SL = 1.5 x ATR, TP 1.5R. Gerbang: paper 20 hari.",
        "mode_key": "strategy_mode_btc_range_breakout",
        "state_key": "runner_btc_range_breakout",
    },
]


def _stats(closed: list[dict], start_balance: float) -> dict:
    """Winrate, profit factor, max drawdown, sharpe, kurva ekuitas (paper).

    Semua field numerik (bukan null) — UI Strategy Lab memformat langsung.
    Profit factor di-cap 99.0 bila tidak pernah loss (tanpa pembagian nol).
    """
    profits = [float(o["profit"] or 0) for o in closed]
    n = len(profits)
    wins = sum(1 for p in profits if p > 0)
    gross_profit = sum(p for p in profits if p > 0)
    gross_loss = -sum(p for p in profits if p < 0)

    curve = [round(start_balance, 2)]
    for p in profits:
        curve.append(round(curve[-1] + p, 2))
    peak = curve[0]
    max_dd = 0.0
    for v in curve:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak)

    mean = sum(profits) / n if n else 0.0
    variance = sum((p - mean) ** 2 for p in profits) / n if n else 0.0
    std = math.sqrt(variance)

    return {
        "trades": n,
        "win": round(wins / n, 4) if n else 0.0,
        "pf": (round(gross_profit / gross_loss, 2) if gross_loss > 1e-9
               else (99.0 if gross_profit > 0 else 0.0)),
        "dd": round(max_dd, 4),
        "sharpe": round(mean / std, 2) if std > 1e-12 else 0.0,
        "curve": curve,
    }


# ── Enrichment untuk SATU sumber Lab + Dashboard (AUDIT-C) ─────────────────
EQUITY_MINI_POINTS = 30            # titik terakhir kurva ekuitas yang dikirim
UNREGISTERED_STATUS = "UNREGISTERED"  # belum ada baris di tabel `strategies`
BREAKER_STATES = ("CLOSED", "OPEN", "HALF_OPEN")


def _iso(value) -> str | None:
    """datetime -> ISO-8601 string (None tetap None)."""
    return value.isoformat() if value is not None else None


def _breaker(raw) -> dict:
    """Normalisasi circuit_breaker JSONB supervisor -> bentuk stabil UI."""
    data = raw if isinstance(raw, dict) else {}
    state = str(data.get("state") or "CLOSED").upper()
    if state not in BREAKER_STATES:
        state = "CLOSED"
    try:
        errors = int(data.get("consecutive_errors") or 0)
    except (TypeError, ValueError):
        errors = 0
    opened_at = data.get("opened_at")
    return {
        "state": state,
        "consecutive_errors": errors,
        "opened_at": opened_at if isinstance(opened_at, str) else None,
        "last_error": data.get("last_error") or None,
    }


async def _mode_map(conn, keys: list[str]) -> dict[str, str]:
    """Baca semua settings `strategy_mode_*` sekaligus (hindari N+1)."""
    rows = await fetchall(
        conn, "SELECT key, value FROM settings WHERE key = ANY(%s)", (keys,))
    modes: dict[str, str] = {}
    for row in rows:
        raw = row["value"]
        text = (raw if isinstance(raw, str) else "").strip().lower()
        if text in VALID_MODES:
            modes[row["key"]] = text
    return modes


async def _paused_strategy_ids(conn) -> set[str]:
    """Daftar strategi yang di-pause kill-switch (mode PAUSE_STRATEGY)."""
    row = await fetchone(
        conn, "SELECT value FROM settings WHERE key = 'paused_strategies'")
    raw = row["value"] if row else None
    return {str(s) for s in raw} if isinstance(raw, list) else set()


async def strategy_summaries(conn) -> list[dict]:
    """Satu entri per strategi terdaftar, terenrich untuk Lab DAN Dashboard.

    Satu-satunya sumber daftar strategi paper/shadow (keputusan AUDIT-C):
    Strategy Lab memakai daftar + rekap di sini, panel paper/shadow di
    Dashboard memfilter `mode` dari respons yang sama, sehingga jumlah dan
    angkanya selalu 1:1. `/shadow/runs` hanya untuk detail sinyal.

    Field per strategi (selain field lama: track/desc/symbol/curve/balance):
    - mode: paper | live | off (settings `strategy_mode_<id>`).
    - status: lifecycle supervisor (tabel `strategies`), \"UNREGISTERED\"
      bila baris belum ada (DB test baru / strategi belum di-import).
    - active + pause_reasons: status efektif; contoh alasan
      kill_switch:paused, breaker:open, lifecycle:disabled.
    - lifecycle: {registered, status, enabled, current_version,
      breaker_state, consecutive_errors, updated_at}.
    - pnl: {realized, start_balance, balance, return_pct, open_trades,
      currency} dari ledger paper_orders (mode PAPER) + paper_state.
    - winrate: alias numerik field `win` (0..1).
    - equity_mini: <= 30 titik terakhir kurva ekuitas ({t, v}), t dari
      closed_at/created_at order; titik pertama = start_balance.
    - shadow: run shadow terbaru strategi ini (run_id/status/label/
      signal_count) atau null.
    """
    ids = [m["id"] for m in REGISTRY]
    state_rows = await fetchall(conn, "SELECT key, value, updated_at FROM paper_state")
    states = {r["key"]: (dict(r["value"] or {}), r["updated_at"]) for r in state_rows}

    ledger: dict[str, list] = {sid: [] for sid in ids}
    for row in await fetchall(
        conn,
        """
        SELECT strategy, status, profit, created_at, closed_at
        FROM paper_orders
        WHERE mode = %s AND strategy = ANY(%s) AND status IN ('OPEN', 'CLOSED')
        ORDER BY created_at, id
        """,
        (PAPER_LEDGER_MODE, ids),
    ):
        ledger.setdefault(row["strategy"], []).append(row)

    mode_map = await _mode_map(conn, [m["mode_key"] for m in REGISTRY])
    paused_ids = await _paused_strategy_ids(conn)

    lifecycle = {
        r["strategy_id"]: r
        for r in await fetchall(
            conn,
            """
            SELECT strategy_id, status, enabled, current_version,
                   circuit_breaker, updated_at
            FROM strategies WHERE strategy_id = ANY(%s)
            """,
            (ids,),
        )
    }
    latest_shadow = {
        r["strategy_id"]: r
        for r in await fetchall(
            conn,
            """
            SELECT DISTINCT ON (strategy_id)
                   strategy_id, run_id, strategy_version, label, status,
                   signal_count, created_at, completed_at
            FROM shadow_runs WHERE strategy_id = ANY(%s)
            ORDER BY strategy_id, created_at DESC, id DESC
            """,
            (ids,),
        )
    }

    summaries = []
    for meta in REGISTRY:
        sid = meta["id"]
        ledger_rows = ledger.get(sid, [])
        closed = [r for r in ledger_rows if r["status"] == "CLOSED"]
        open_rows = [r for r in ledger_rows if r["status"] == "OPEN"]
        total_profit = sum(float(r["profit"] or 0) for r in closed)

        state, updated_at = states.get(meta["state_key"], ({}, None))
        if not state:
            start_balance = DEFAULT_START_BALANCE
            current_balance = round(start_balance + total_profit, 2)
        else:
            current_balance = float(state.get("balance") or DEFAULT_START_BALANCE)
            start_balance = round(current_balance - total_profit, 2)

        stats = _stats(closed, start_balance)
        mode = mode_map.get(meta["mode_key"], "paper")

        life = lifecycle.get(sid)
        if life is None:
            life_status, life_enabled = UNREGISTERED_STATUS, False
            current_version, life_updated = None, None
            breaker = _breaker(None)
        else:
            life_status = str(life["status"] or UNREGISTERED_STATUS)
            life_enabled = bool(life["enabled"])
            current_version = life["current_version"]
            life_updated = life["updated_at"]
            breaker = _breaker(life["circuit_breaker"])

        pause_reasons: list[str] = []
        if sid in paused_ids:
            pause_reasons.append("kill_switch:paused")
        if breaker["state"] != "CLOSED":
            pause_reasons.append(f"breaker:{breaker['state'].lower()}")
        if life is None:
            pause_reasons.append("lifecycle:unregistered")
        elif not life_enabled or life_status in ("DRAFT", "DISABLED", "ARCHIVED"):
            pause_reasons.append(f"lifecycle:{life_status.lower()}")

        # Titik kurva dengan waktu: ledger paper -> dipotong 30 terakhir.
        points: list[tuple[str | None, float]] = [(None, round(start_balance, 2))]
        running = start_balance
        for row in closed:
            running = round(running + float(row["profit"] or 0), 2)
            points.append((_iso(row["closed_at"] or row["created_at"]), running))
        equity_mini = [{"t": t, "v": v} for t, v in points[-EQUITY_MINI_POINTS:]]

        shadow_row = latest_shadow.get(sid)
        shadow = None
        if shadow_row is not None:
            shadow = {
                "run_id": str(shadow_row["run_id"]),
                "status": shadow_row["status"],
                "label": shadow_row["label"],
                "strategy_version": shadow_row["strategy_version"],
                "signal_count": int(shadow_row["signal_count"] or 0),
                "is_simulation": True,
                "created_at": _iso(shadow_row["created_at"]),
                "completed_at": _iso(shadow_row["completed_at"]),
            }

        summary = {
            **{k: meta[k] for k in ("id", "name", "track", "desc", "symbol")},
            "mode": mode,
            "status": life_status,
            "active": not pause_reasons,
            "pause_reasons": pause_reasons,
            "lifecycle": {
                "registered": life is not None,
                "status": life_status,
                "enabled": life_enabled,
                "current_version": current_version,
                "breaker_state": breaker["state"],
                "consecutive_errors": breaker["consecutive_errors"],
                "breaker_opened_at": breaker["opened_at"],
                "updated_at": _iso(life_updated),
            },
            **stats,
            "winrate": stats["win"],
            "pnl": {
                "realized": round(float(total_profit), 2),
                "start_balance": round(float(start_balance), 2),
                "balance": current_balance,
                "return_pct": (round(total_profit / start_balance * 100, 4)
                               if start_balance > 0 else 0.0),
                "open_trades": len(open_rows),
                "currency": "USD",
            },
            "equity_mini": equity_mini,
            "shadow": shadow,
            "balance": current_balance,
            "paper_days": len(state.get("days_observed") or []),
            "open_position": state.get("position"),
            "runner_updated_at": _iso(updated_at),
        }
        if mode == "live" and summary["paper_days"] < PAPER_GATE_DAYS:
            summary["warning"] = (
                f"gerbang paper belum lolos ({summary['paper_days']}/"
                f"{PAPER_GATE_DAYS} hari); belum ada live runner — mode hanya "
                "preferensi, tidak memicu order broker"
            )
        summaries.append(summary)
    return summaries


async def set_mode(conn, strategy_id: str, mode: str) -> dict | None:
    """Set mode strategi. None bila strategy_id tidak terdaftar."""
    meta = next((m for m in REGISTRY if m["id"] == strategy_id), None)
    if meta is None:
        return None
    await conn.execute(
        """
        INSERT INTO settings (key, value, updated_at) VALUES (%s, %s, now())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """,
        (meta["mode_key"], json.dumps(mode)),
    )
    summaries = await strategy_summaries(conn)
    return next(s for s in summaries if s["id"] == strategy_id)
