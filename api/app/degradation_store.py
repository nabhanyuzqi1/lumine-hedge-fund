"""Persistence + collector untuk degradation detection (PRD v2.2 §10).

Pemisahan dari app.degradation (murni): modul ini satu-satunya yang menyentuh
DB. Sumber data indikator (PRD §10.2):
    - trade closed   : paper_orders (mode PAPER) + positions (live, via orders)
    - MAE/MFE        : candles antara opened_at..closed_at (bar tertutup)
    - equity curve   : saldo kumulatif ledger (start_balance + Σ profit)
    - fill/reject    : orders (live) + paper_orders REJECTED
    - spread aktual  : liquidity_samples (window vs baseline)
    - slippage       : |price_filled - price_requested| order live OPEN
    - regime         : regime_observations (context PERIODIC; tag trade dari
                       context ORDER ref paper_order, fallback PERIODIC)
    - frekuensi      : signals per hari (window vs baseline)
    - divergence     : expectancy R paper vs R live
    - drift fitur    : regime_observations.features (PSI per fitur numerik)

evaluate_strategy(): collect -> evaluate (murni) -> persist state + event +
notifikasi Telegram saat eskalasi. Kegagalan koleksi data TIDAK boleh
menghentikan runner: exception dilempar ke caller yang mengisolasi
(pola yang sama dengan record_regime di paper/runner.py).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from . import db, degradation, regime, telegram_bot

DEG_TABLE = "degradation_state"
EVENT_TABLE = "degradation_events"


def _json(value) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


async def load_state(conn, strategy_id: str) -> dict:
    """State degradation strategi; row absen = DEFAULT_STATE (NORMAL)."""
    row = await conn.execute(
        f"SELECT state FROM {DEG_TABLE} WHERE strategy_id = %s", (strategy_id,))
    found = await row.fetchone()
    state = dict(degradation.DEFAULT_STATE)
    if found and found["state"]:
        state.update(found["state"] or {})
    return state


async def save_state(conn, strategy_id: str, state: dict) -> None:
    """Upsert state + kolom proyeksi (status/indikator utk query cepat UI)."""
    indicators = state.get("indicators") or []
    await conn.execute(
        f"""
        INSERT INTO {DEG_TABLE}
            (strategy_id, status, since, last_evaluated_at, cooldown_until,
             confirm_status, confirm_count, confirm_trades_start, indicators,
             config_version, config_hash, state, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (strategy_id) DO UPDATE SET
            status = EXCLUDED.status,
            since = EXCLUDED.since,
            last_evaluated_at = EXCLUDED.last_evaluated_at,
            cooldown_until = EXCLUDED.cooldown_until,
            confirm_status = EXCLUDED.confirm_status,
            confirm_count = EXCLUDED.confirm_count,
            confirm_trades_start = EXCLUDED.confirm_trades_start,
            indicators = EXCLUDED.indicators,
            config_version = EXCLUDED.config_version,
            config_hash = EXCLUDED.config_hash,
            state = EXCLUDED.state,
            updated_at = now()
        """,
        (strategy_id, state.get("status", "NORMAL"),
         _ts(state.get("since")), _ts(state.get("last_evaluated_at")),
         _ts(state.get("cooldown_until")), state.get("confirm_status"),
         int(state.get("confirm_count") or 0),
         int(state.get("confirm_trades_start") or 0),
         _json(indicators), state.get("config_version", ""),
         state.get("config_hash", ""), _json(state)),
    )


def _ts(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


async def record_event(conn, strategy_id: str, *, trigger: str,
                       from_status: str | None, to_status: str,
                       reason: str = "", indicators=None,
                       config_version: str = degradation.DEGRADATION_VERSION,
                       config_hash: str = "", actor: str | None = None) -> None:
    """Event transisi append-only (degradation_events; PRD §10/§18)."""
    await conn.execute(
        f"""
        INSERT INTO {EVENT_TABLE}
            (strategy_id, from_status, to_status, trigger, reason, indicators,
             config_version, config_hash, actor)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (strategy_id, from_status, to_status, trigger, reason,
         _json(indicators or []), config_version, config_hash, actor),
    )


async def re_enable(conn, *, strategy_id: str, actor: str, note: str,
                    now: datetime | None = None) -> dict:
    """Re-enable owner (PRD §10.3): status -> NORMAL + event REENABLE_OWNER.

    approval owner diverifikasi caller (API: admin + 2FA step-up). Raise
    ValueError bila strategi sudah NORMAL (tidak ada yang di-re-enable).
    """
    now = now or datetime.now(timezone.utc)
    async with conn.transaction():
        state = await load_state(conn, strategy_id)
        new_state = degradation.re_enable_state(
            state, now=now, actor=actor, note=note)
        await save_state(conn, strategy_id, new_state)
        await record_event(
            conn, strategy_id, trigger="REENABLE_OWNER",
            from_status=str(state.get("status")), to_status="NORMAL",
            reason=f"re-enable owner: {note}",
            indicators=state.get("indicators") or [],
            config_version=str(state.get("config_version")
                               or degradation.DEGRADATION_VERSION),
            config_hash=str(state.get("config_hash") or ""),
            actor=actor)
    return new_state


async def statuses(conn) -> dict[str, str]:
    """Semua status degradation (gate runner/risk: 1 query per loop)."""
    row = await conn.execute(
        f"SELECT COALESCE(json_object_agg(strategy_id, status), '{{}}'::json) "
        f"AS data FROM {DEG_TABLE}")
    found = await row.fetchone()
    return dict(found["data"] or {}) if found else {}


async def state_rows(conn) -> list[dict]:
    """Semua baris state + event terakhir (monitoring UI)."""
    rows = await conn.execute(
        f"""
        SELECT s.strategy_id, s.status, s.since, s.last_evaluated_at,
               s.cooldown_until, s.indicators, s.config_version, s.config_hash,
               s.state, s.updated_at
        FROM {DEG_TABLE} s ORDER BY s.strategy_id
        """)
    return [dict(r) for r in await rows.fetchall()]


async def recent_events(conn, strategy_id: str, limit: int = 20) -> list[dict]:
    rows = await conn.execute(
        f"""
        SELECT from_status, to_status, trigger, reason, indicators,
               config_version, actor, created_at
        FROM {EVENT_TABLE} WHERE strategy_id = %s
        ORDER BY id DESC LIMIT %s
        """,
        (strategy_id, max(1, min(int(limit), 100))))
    return [dict(r) for r in await rows.fetchall()]


# ── Collector: rakit inputs dari DB (PRD §10.2) ─────────────────────────────
async def _paper_trades(conn, *, strategy_id: str, symbol: str,
                        contract_size: float, limit: int) -> tuple[list[dict], int]:
    """Trade closed paper terakhir + total counter (utk konfirmasi new-data).

    R = profit / (|entry - sl| × contract_size × volume); tanpa SL valid ->
    R None (trade tetap dihitung utk PF/profit, tidak utk expectancy).
    """
    rows = await conn.execute(
        """
        SELECT id, profit, entry_price, sl, volume, side, opened_at, closed_at
        FROM paper_orders
        WHERE strategy = %s AND mode = 'PAPER' AND status = 'CLOSED'
        ORDER BY closed_at DESC LIMIT %s
        """,
        (strategy_id, limit))
    recent = [dict(r) for r in await rows.fetchall()]
    total_row = await conn.execute(
        "SELECT count(*) AS n FROM paper_orders "
        "WHERE strategy = %s AND mode = 'PAPER' AND status = 'CLOSED'",
        (strategy_id,))
    total = int((await total_row.fetchone())["n"])
    regime_by_id = await _trade_regime_tags(conn, [str(r["id"]) for r in recent])
    out = []
    for r in recent:
        out.append({
            "profit": float(r["profit"] or 0),
            "r": _r_multiple(r["profit"], r["entry_price"], r["sl"],
                             r["volume"], contract_size),
            "regime": regime_by_id.get(str(r["id"])),
            "closed_at": r["closed_at"],
            "opened_at": r["opened_at"],
            "entry_price": float(r["entry_price"]) if r["entry_price"] else None,
            "sl": float(r["sl"]) if r["sl"] else None,
            "volume": float(r["volume"]) if r["volume"] else None,
            "_side": str(r["side"] or "BUY"),
        })
    return out, total


def _r_multiple(profit, entry, sl, volume, contract_size) -> float | None:
    """R multiple trade: profit / risiko USD (jarak SL × contract × lot)."""
    try:
        if None in (profit, entry, sl, volume) or not contract_size:
            return None
        risk = abs(float(entry) - float(sl)) * float(contract_size) * float(volume)
        if risk <= 0:
            return None
        return float(profit) / risk
    except (TypeError, ValueError):
        return None


async def _trade_regime_tags(conn, order_ids: list[str]) -> dict[str, str]:
    """Tag regime per trade dari regime_observations context='ORDER'."""
    if not order_ids:
        return {}
    rows = await conn.execute(
        """
        SELECT ref_id, regime FROM regime_observations
        WHERE context = 'ORDER' AND ref_type = 'paper_order'
          AND ref_id = ANY(%s)
        """,
        (order_ids,))
    return {str(r["ref_id"]): str(r["regime"]) for r in await rows.fetchall()}


async def _mae_mfe_fill(conn, trades: list[dict], *, symbol: str,
                        timeframe: str) -> None:
    """Isi mae_r/mfe_r per trade dari candles antara opened_at..closed_at.

    MAE = pergerakan advers terhadap entry; MFE = favorable. Satuan R
    (dibagi jarak SL). Trade tanpa candles/risk valid dibiarkan None.
    """
    valid = [t for t in trades
             if t.get("opened_at") and t.get("closed_at")
             and t.get("entry_price") and t.get("sl") and t.get("volume")
             and t.get("r") is not None]
    if not valid:
        return
    start = min(t["opened_at"] for t in valid) - timedelta(hours=2)
    end = max(t["closed_at"] for t in valid) + timedelta(hours=2)
    rows = await conn.execute(
        """
        SELECT ts, high, low FROM candles
        WHERE symbol = %s AND timeframe = %s AND ts >= %s AND ts <= %s
        ORDER BY ts
        """,
        (symbol, timeframe, start, end))
    candles = [(r["ts"], float(r["high"]), float(r["low"]))
               for r in await rows.fetchall()]
    for t in valid:
        risk = abs(t["entry_price"] - t["sl"]) * t["volume"]
        if risk <= 0:
            continue
        window = [c for c in candles
                  if t["opened_at"] <= c[0] <= t["closed_at"]]
        if not window:
            continue
        hi = max(c[1] for c in window)
        lo = min(c[2] for c in window)
        if t["_side"] == "BUY":
            mae_price, mfe_price = t["entry_price"] - lo, hi - t["entry_price"]
        else:
            mae_price, mfe_price = hi - t["entry_price"], t["entry_price"] - lo
        t["mae_r"] = max(mae_price, 0.0) / risk
        t["mfe_r"] = max(mfe_price, 0.0) / risk


async def _live_trades(conn, *, strategy_id: str, contract_size: float,
                       limit: int) -> list[dict]:
    """Trade live closed (positions via orders.strategy) utk divergence."""
    rows = await conn.execute(
        """
        SELECT p.profit, p.open_price, p.sl, p.volume, p.side,
               p.open_time, p.close_time
        FROM positions p JOIN orders o ON p.order_id = o.id
        WHERE o.strategy = %s AND p.status = 'CLOSED'
          AND p.close_time IS NOT NULL
        ORDER BY p.close_time DESC LIMIT %s
        """,
        (strategy_id, limit))
    out = []
    for r in await rows.fetchall():
        out.append({
            "profit": float(r["profit"] or 0),
            "r": _r_multiple(r["profit"], r["open_price"], r["sl"],
                             r["volume"], contract_size),
            "side": r["side"],
            "closed_at": r["close_time"].isoformat() if r["close_time"] else "",
        })
    return out


async def _orders_window(conn, *, strategy_id: str, since: datetime) -> list[dict]:
    """Order terminal live dalam window (fill/rejection + slippage)."""
    rows = await conn.execute(
        """
        SELECT status, action, price_requested, price_filled, created_at
        FROM orders WHERE strategy = %s AND created_at >= %s
        """,
        (strategy_id, since))
    return [dict(r) for r in await rows.fetchall()]


async def _paper_rejections(conn, *, strategy_id: str,
                            since: datetime) -> list[dict]:
    """Rejection paper dalam window (status REJECTED)."""
    rows = await conn.execute(
        """
        SELECT status, created_at FROM paper_orders
        WHERE strategy = %s AND mode = 'PAPER' AND status = 'REJECTED'
          AND created_at >= %s
        """,
        (strategy_id, since))
    return [dict(r) for r in await rows.fetchall()]


async def _spread_series(conn, *, symbol: str, start: datetime,
                         end: datetime) -> list[float]:
    """Spread rata-rata per menit dari liquidity_samples (aktual)."""
    rows = await conn.execute(
        """
        SELECT spread_avg FROM liquidity_samples
        WHERE symbol = %s AND window_start >= %s AND window_start < %s
        ORDER BY window_start
        """,
        (symbol, start, end))
    return [float(r["spread_avg"]) for r in await rows.fetchall()]


async def _regime_counts(conn, *, symbol: str, timeframe: str,
                         start: datetime, end: datetime) -> dict[str, int]:
    """Distribusi label regime (context PERIODIC) dalam window."""
    rows = await conn.execute(
        """
        SELECT regime, count(*) AS n FROM regime_observations
        WHERE symbol = %s AND timeframe = %s AND context = 'PERIODIC'
          AND ts >= %s AND ts < %s
        GROUP BY regime
        """,
        (symbol, timeframe, start, end))
    return {str(r["regime"]): int(r["n"]) for r in await rows.fetchall()}


async def _signal_freq(conn, *, strategy_id: str, now: datetime,
                       p: degradation.DegradationParams) -> dict:
    """Frekuensi sinyal: count window vs baseline (rate harian)."""
    window_start = now - timedelta(days=p.recent_window_days)
    baseline_start = window_start - timedelta(days=p.baseline_window_days)
    row = await conn.execute(
        """
        SELECT count(*) FILTER (WHERE created_at >= %s) AS window,
               count(*) FILTER (WHERE created_at >= %s AND created_at < %s)
                   AS baseline
        FROM signals WHERE strategy_id = %s AND source IN ('PAPER', 'LIVE')
        """,
        (window_start, baseline_start, window_start, strategy_id))
    found = await row.fetchone() or {}
    return {"window": int(found.get("window") or 0),
            "window_days": p.recent_window_days,
            "baseline": int(found.get("baseline") or 0),
            "baseline_days": p.baseline_window_days}


async def _feature_samples(conn, *, symbol: str, timeframe: str,
                           start: datetime, end: datetime) -> dict[str, list]:
    """Sampel fitur numerik dari regime_observations.features (PSI drift)."""
    rows = await conn.execute(
        """
        SELECT features FROM regime_observations
        WHERE symbol = %s AND timeframe = %s AND context = 'PERIODIC'
          AND ts >= %s AND ts < %s
        """,
        (symbol, timeframe, start, end))
    numeric = {"atr", "atr_ratio", "adx", "ma_slope_atr_per_bar",
               "realized_vol", "vol_pctile", "spread", "spread_p95",
               "tick_rate_per_min"}
    out: dict[str, list] = {}
    for r in await rows.fetchall():
        feats = r["features"] or {}
        if not isinstance(feats, dict):
            continue
        for key in numeric:
            val = feats.get(key)
            if isinstance(val, (int, float)):
                out.setdefault(key, []).append(float(val))
    return out


# ── Orkestrator: collect -> evaluate -> persist ─────────────────────────────
def _symbol_spec(settings: dict, symbol: str) -> float:
    """Contract size terverifikasi utk konversi R (fallback 100 = XAUUSD)."""
    spec = (settings.get("symbol_specs") or {}).get(symbol) or {}
    try:
        value = float(spec.get("contract_size"))
    except (TypeError, ValueError):
        return 100.0
    return value if value > 0 else 100.0


async def collect_inputs(conn, *, strategy_id: str, symbol: str, timeframe: str,
                         now: datetime,
                         settings: dict) -> dict:
    """Rakit semua input indikator dari DB (PRD §10.2). Caller menyediakan
    settings + now; query memakai window dari params efektif."""
    p = degradation.load_params(settings)
    contract = _symbol_spec(settings, symbol)
    window_start = now - timedelta(days=p.recent_window_days)
    baseline_start = window_start - timedelta(days=p.baseline_window_days)

    trades, closed_total = await _paper_trades(
        conn, strategy_id=strategy_id, symbol=symbol, contract_size=contract,
        limit=p.trade_window)
    await _mae_mfe_fill(conn, trades, symbol=symbol, timeframe=timeframe)

    live = await _live_trades(conn, strategy_id=strategy_id,
                              contract_size=contract, limit=p.trade_window)

    # Fill/rejection: order live + rejection paper dalam window terhangat.
    orders = await _orders_window(conn, strategy_id=strategy_id,
                                  since=window_start)
    orders += await _paper_rejections(conn, strategy_id=strategy_id,
                                      since=window_start)

    spread_now = await _spread_series(conn, symbol=symbol,
                                      start=window_start, end=now)
    spread_base = await _spread_series(conn, symbol=symbol,
                                       start=baseline_start,
                                       end=window_start)
    # Slippage live: |fill - requested| order OPEN dalam window.
    slippage_now = [
        abs(float(o["price_filled"]) - float(o["price_requested"]))
        for o in orders
        if o.get("action") == "OPEN" and o.get("price_filled") is not None
        and o.get("price_requested") is not None]
    slippage_base = await _live_slippage_baseline(
        conn, strategy_id=strategy_id, start=baseline_start,
        end=window_start)

    regime_now = await _regime_counts(conn, symbol=symbol, timeframe=timeframe,
                                      start=window_start, end=now)
    regime_base = await _regime_counts(conn, symbol=symbol, timeframe=timeframe,
                                       start=baseline_start,
                                       end=window_start)
    feats_now = await _feature_samples(conn, symbol=symbol,
                                       timeframe=timeframe,
                                       start=window_start, end=now)
    feats_base = await _feature_samples(conn, symbol=symbol,
                                        timeframe=timeframe,
                                        start=baseline_start,
                                        end=window_start)

    # Equity curve dari ledger paper: start_balance + kumulatif profit
    # (start_balance dibaca dari paper_state runner strategi bila ada).
    start_balance = await _paper_start_balance(conn, strategy_id=strategy_id)
    equity_curve = [{"ts": "", "equity": float(start_balance)}]
    running = float(start_balance)
    for t in sorted(trades, key=lambda x: x["closed_at"]):
        running += float(t["profit"] or 0)
        equity_curve.append({"ts": t["closed_at"], "equity": round(running, 2)})

    return {
        "trades": trades,
        "closed_trades_total": closed_total,
        "equity_curve": equity_curve,
        "orders": orders,
        "spread_current": spread_now,
        "spread_baseline": spread_base,
        "slippage_current": slippage_now,
        "slippage_baseline": slippage_base,
        "regime_counts": regime_now,
        "baseline_regime_counts": regime_base,
        "signal_freq": await _signal_freq(conn, strategy_id=strategy_id,
                                          now=now, p=p),
        "paper_r": [t["r"] for t in trades if t["r"] is not None],
        "live_r": [t["r"] for t in live if t["r"] is not None],
        "features_baseline": feats_base,
        "features_current": feats_now,
    }


async def _live_slippage_baseline(conn, *, strategy_id: str, start: datetime,
                                  end: datetime) -> list[float]:
    rows = await conn.execute(
        """
        SELECT price_requested, price_filled FROM orders
        WHERE strategy = %s AND action = 'OPEN'
          AND price_requested IS NOT NULL AND price_filled IS NOT NULL
          AND created_at >= %s AND created_at < %s
        """,
        (strategy_id, start, end))
    return [abs(float(r["price_filled"]) - float(r["price_requested"]))
            for r in await rows.fetchall()]


async def _paper_start_balance(conn, *, strategy_id: str) -> float:
    """Saldo awal ledger strategi dari paper_state (fallback 10.000)."""
    row = await conn.execute(
        "SELECT value FROM paper_state WHERE key = %s",
        (f"runner_{strategy_id}",))
    found = await row.fetchone()
    if found:
        try:
            return float((found["value"] or {}).get("balance") or 0) or 10000.0
        except (TypeError, ValueError):
            return 10000.0
    return 10000.0


async def evaluate_strategy(conn, *, strategy_id: str, symbol: str,
                            timeframe: str, now: datetime,
                            settings: dict,
                            notify: bool = True) -> degradation.DegradationResult:
    """Satu siklus degradation strategi (PRD §10): collect -> evaluate ->
    persist state + event + notifikasi eskalasi. Return hasil evaluasi.

    Caller (runner) memanggil per eval_interval_s; kegagalan dilempar agar
    diisolasi per strategi seperti decide() lainnya.
    """
    params = degradation.load_params(settings)
    state = await load_state(conn, strategy_id)
    inputs = await collect_inputs(conn, strategy_id=strategy_id, symbol=symbol,
                                  timeframe=timeframe, now=now,
                                  settings=settings)
    result = degradation.evaluate(strategy_id=strategy_id, now=now,
                                  params=params, state=state, inputs=inputs)
    await save_state(conn, strategy_id, result.state)
    if result.escalated:
        await record_event(
            conn, strategy_id, trigger="EVALUATION",
            from_status=result.previous_status, to_status=result.status,
            reason=result.reason,
            indicators=[vars(i) for i in result.indicators],
            config_version=result.config_version,
            config_hash=result.config_hash, actor="degradation:evaluator")
        if notify:
            await _notify_escalation(result)
    return result


async def _notify_escalation(result: degradation.DegradationResult) -> None:
    """Notifikasi Telegram eskalasi (non-fatal; dedup di telegram_bot)."""
    firing = [i for i in result.indicators if i.severity > 0 and i.sample_ok]
    lines = ["; ".join(f"{i.name}={i.value}" for i in firing[:4])]
    try:
        await telegram_bot.notify_owner(
            f"[DEGRADATION] {result.strategy_id}: "
            f"{result.previous_status} -> {result.status}\n"
            f"{result.reason[:300]}\n"
            f"{lines[0][:300]}")
    except Exception:  # noqa: BLE001 - notifikasi tidak boleh jatuhkan runner
        pass


# ═══ EOF ═══
