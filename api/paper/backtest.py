"""Event-driven backtest for strategy #1 (PRD 5.4).

Uses the SAME decide() and risk gate as the paper runner (signal parity by
construction). Two cost modes:

  - Legacy constant (default): spread 0.50 USD + slippage 0.10 USD per fill.
  - Calibrated (cost_model=CostModel, PRD 5.2): spread per sesi =
    Dukascopy x faktor koreksi HFM/Dukascopy per sesi + haircut 20%,
    komisi per lot round-turn, slippage per fill dari model. Lihat
    paper/costs.py.

Execution model (PRD v2.2 §8.2, execution=ExecutionModel dari
paper/execution.py): swap per malam (triple Rabu server), latency fill di
open bar berikutnya, rejection spread/gap, partial fill, market closure.
execution=None mempertahankan perilaku lama (fill di close bar sinyal,
tanpa swap/rejection) untuk kompatibilitas pemanggil lama.

Run:  .venv/bin/python -m paper.backtest --tf 5m --days 17
      .venv/bin/python -m paper.backtest --tf 15m --start 2026-09-07 --end 2026-11-20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from collections import deque
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app import db, regime
from app.data_quality import market_closed_minutes
from app.ingest import session_of
from app.risk import RiskContext, risk_gate
from paper import store
from paper.broker import PaperBroker, PaperPosition
from paper.costs import CostModel
from paper.execution import (
    ExecutionModel,
    default_execution_model,
    is_triple_swap_day,
    rollover_crossings,
)
from paper.runner import db_timezone_offset_h
from strategies.broker_time import broker_utc_offset_hours, stored_to_utc
from strategies import london_breakout as _default_strategy
from strategies.london_breakout import StrategyParams  # re-export (kompatibilitas)

SYMBOL = "XAUUSD"

SPREAD_DEFAULT = 0.50
SLIPPAGE_DEFAULT = 0.10

# CLI memakai nama pendek; DB menyimpan timeframe kanonik PRD (M1/M5/...).
CANONICAL_TF = {"1m": "M1", "5m": "M5", "15m": "M15",
                "1h": "H1", "4h": "H4", "1d": "D1"}


def canonical_tf(timeframe: str) -> str:
    return CANONICAL_TF.get(timeframe, timeframe)


async def load_history_rows(conn, timeframe: str, start: datetime, end: datetime) -> list[dict]:
    rows = await conn.execute(
        """
        SELECT ts, open, high, low, close, volume FROM candles
        WHERE symbol = %s AND timeframe = %s AND ts >= %s AND ts <= %s
        ORDER BY ts ASC
        """,
        (SYMBOL, canonical_tf(timeframe), start, end),
    )
    return await rows.fetchall()


def to_utc_candles(rows, db_tz_offset_h: int) -> list[dict]:
    out = []
    for row in rows:
        wall = row["ts"]  # aware, DB session tz; wall clock == broker clock
        offset_h = broker_utc_offset_hours(wall)
        ts_utc = stored_to_utc(wall, db_tz_offset_h, offset_h)
        out.append({
            "ts": ts_utc, "open": float(row["open"]), "high": float(row["high"]),
            "low": float(row["low"]), "close": float(row["close"]),
            "volume": float(row.get("volume") or 0),
        })
    return out


def run_backtest(candles: list[dict], *, tf_seconds: int, equity0: float = 10000.0,
                 spread: float = SPREAD_DEFAULT, slippage: float = SLIPPAGE_DEFAULT,
                 params: StrategyParams | None = None,
                 cost_model: CostModel | None = None,
                 strategy=_default_strategy,
                 symbol: str = "XAUUSD",
                 contract_size: float = 100.0,
                 context_bars: int = 0,
                 regime_filter: bool = False,
                 allowed_regimes: list | None = None,
                 execution: ExecutionModel | None = None) -> dict:
    """Event-driven backtest bar-per-bar dengan decide() yang sama dengan live.

    cost_model=None -> biaya legacy konstan (spread/slippage argumen).
    cost_model=CostModel -> spread per sesi terkalibrasi + komisi + slippage.
    strategy: modul strategi (decide/StrategyParams/STRATEGY_ID); default
    london_breakout. symbol/contract_size: multipair P2 (BTCUSD 1 BTC/lot).
    context_bars: jumlah bar sejarah lintas hari yang diberikan ke decide()
    (0 = hanya candle hari berjalan, perilaku lama strategi #1/#2; strategi
    dengan lookback > 1 hari seperti BTC Donchian 24 bar H1 butuh > 0).
    regime_filter: aktifkan gate regime (PRD v2.2 §6) dengan classifier
    app.regime yang SAMA dengan live - bukan filter custom backtest.
    allowed_regimes: regime yang diizinkan strategi; default = baca dari
    modul strategi (ALLOWED_REGIMES), [] = tanpa syarat (karena strategi
    sudah punya guard sendiri). UNKNOWN selalu = blokir bila ada syarat.
    Regime pada SIGNAL/ORDER/POSITION selalu dicatat di trade (audit).
    execution: ExecutionModel (paper/execution.py, PRD v2.2 §8.2) -
    swap/latency/rejection/partial fill/market closure. None = perilaku
    lama (fill di close bar sinyal, tanpa swap/rejection).
    """
    params = params or strategy.StrategyParams(tf_seconds=tf_seconds)
    assert params is not None
    strategy_id = strategy.STRATEGY_ID
    broker = PaperBroker(force_close_hour_utc=params.force_close_utc)
    settings = {"allowed_symbols": [symbol], "max_volume": 0.10,
                "max_spread": params.max_spread_abs,  # ambang A9 per simbol (BTC 100, XAU 0.50)
                # AUDIT-A2: gate memakai persen dari saldo awal hari, bukan
                # USD. 1% x 10.000 = 100 USD -> ambang halt backtest tetap
                # sama dengan hasil historis.
                "kill_switch_triggers": {"daily_drawdown_pct": 1.0},
                "max_orders_per_min": 10}
    slip = cost_model.slippage_usd_per_fill if cost_model else slippage
    balance = equity0
    position: PaperPosition | None = None
    trades: list[dict] = []
    day = None
    trades_today = 0
    daily_realized = 0.0
    day_candles: list[dict] = []  # candle hari berjalan (ts datetime, tanpa isoformat)
    use_hist = context_bars > 0
    hist: deque = deque(maxlen=context_bars) if use_hist else deque()
    commission_total = 0.0
    swap_total = 0.0
    position_swap = 0.0          # akumulasi swap posisi berjalan (ditagih saat close)
    fills: list[dict] = []       # semua fill (entry/exit) utk distribusi slippage
    rejections: list[dict] = []  # order ditolak/dibatalkan + alasan (audit)
    pending: dict | None = None  # order menunggu fill (latency fill_delay_bars)
    prev_now: datetime | None = None
    # Regime (PRD v2.2 §6): definisi SAMA dengan live (app.regime murni).
    # State hysteresis per bar + hasil terbaru (utk gate & pencatatan).
    if allowed_regimes is None:
        allowed_regimes = regime.allowed_regimes_for(strategy)
    regime_params = regime.default_params_for_symbol(symbol)
    regime_state: dict | None = None
    regime_last = None  # RegimeResult terakhir (bar saat ini)
    regime_bar_open = datetime.min.replace(tzinfo=timezone.utc)
    _regime_stats: dict = {"labels": {}, "blocked": 0}
    # Window regime HARUS kontinu (semua bar, bukan hanya saat flat) - sama
    # dengan live yang mengambil candle berkelanjutan dari DB. Deque decide()
    # (hist) membeku saat posisi terbuka dan membuat lubang palsu.
    regime_hist: deque = deque(maxlen=320)

    for i, bar in enumerate(candles):
        now = bar["ts"] + timedelta(seconds=tf_seconds)
        if now.date() != day:
            day = now.date()
            trades_today = 0
            daily_realized = 0.0
            day_candles = []
        sprd = cost_model.spread_at(now) if cost_model else spread          # biaya fill
        sprd_obs = cost_model.filter_spread_at(now) if cost_model else spread  # teramati
        median15 = cost_model.spread_median_15m(now) if cost_model else None

        # Regime (PRD v2.2 §6) per bar dari series KONTINU - sama dengan
        # live (runner mengambil candle berkelanjutan dari DB). Dihitung
        # SELALU: label regime per trade wajib ada di laporan §8.3 (per
        # regime); GATE entry tetap hanya saat regime_filter.
        regime_hist.append(bar)
        regime_last = regime.classify(
            symbol=symbol, now=now, candles=list(regime_hist),
            liquidity={"ts": now, "spread": sprd_obs,
                       "spread_median_15m": median15, "fresh": True},
            params=regime_params, state=regime_state)
        regime_state = regime_last.state
        regime_bar_open = bar["ts"]
        tick = {"ts_utc": now, "bid": bar["close"] - sprd / 2,
                "ask": bar["close"] + sprd / 2, "spread": sprd}
        # kutipan teramati: untuk decide() dan risk gate (meniru live)
        tick_obs = {"ts_utc": now, "bid": bar["close"] - sprd_obs / 2,
                    "ask": bar["close"] + sprd_obs / 2, "spread": sprd_obs}

        # 1) Eksekusi pending order (latency: fill di open bar yang jatuh
        #    tempo; PRD v2.2 §8.2 latency/rejection/partial fill/closure).
        if pending is not None and (
                execution is None or execution.fill_delay_bars <= 0
                or i >= pending["signal_bar"] + execution.fill_delay_bars):
            intent = pending["intent"]
            reject_reason = None
            if execution is not None:
                if execution.block_entry_closed_market and market_closed_minutes(
                        symbol, bar["ts"]):
                    reject_reason = "MARKET_CLOSED"
                elif (execution.max_spread_fill is not None
                      and sprd > execution.max_spread_fill):
                    reject_reason = "SPREAD_TOO_WIDE"
                elif (execution.max_gap_usd is not None
                      and abs(bar["open"] - pending["signal_close"])
                      > execution.max_gap_usd):
                    reject_reason = "REQUOTE_GAP"
            if reject_reason is not None:
                rejections.append({
                    "ts": now.isoformat(), "reason": reject_reason,
                    "side": intent.side, "volume": intent.volume,
                    "signal_close": pending["signal_close"],
                    "fill_open": bar["open"], "spread_at_fill": round(sprd, 3),
                    "gap_usd": round(bar["open"] - pending["signal_close"], 3),
                })
                pending = None
            else:
                volume = intent.volume
                fill_status = "FILLED"
                if execution is not None and execution.partial_fill_enabled:
                    ratio = _partial_fill_ratio(bar, candles, i, execution)
                    if ratio < 1.0:
                        volume = round(volume * ratio, 2)
                        fill_status = "PARTIAL"
                if volume < 0.01:
                    rejections.append({
                        "ts": now.isoformat(), "reason": "PARTIAL_BELOW_MIN",
                        "side": intent.side, "volume": intent.volume,
                        "fill_volume": volume, "spread_at_fill": round(sprd, 3),
                    })
                else:
                    entry = (bar["open"] + sprd / 2 + slip if intent.side == "BUY"
                             else bar["open"] - sprd / 2 - slip)
                    position = PaperPosition(
                        order_id=str(i), side=intent.side, volume=volume,
                        entry_price=entry, sl=intent.sl, tp=intent.tp,
                        opened_at=now, strategy=strategy_id,
                        contract_size=contract_size)
                    risk_usd = balance * 0.005
                    position_swap = 0.0
                    trades.append({
                        "entry_bar": i, "side": intent.side, "volume": volume,
                        "entry_price": round(entry, 2), "sl": intent.sl, "tp": intent.tp,
                        "opened_at": now.isoformat(), "risk_usd": round(risk_usd, 2),
                        "reason": intent.reason, "session": session_of(now),
                        "spread_at_entry": round(sprd, 3),
                        "filter_spread_at_entry": round(sprd_obs, 3),
                        "status": fill_status,
                        "signal_close": pending["signal_close"],
                        "gap_usd": round(bar["open"] - pending["signal_close"], 3),
                        "regime": pending["regime"],
                        "regime_confidence": pending["regime_confidence"],
                        "slippage_entry_price": round(slip, 3),
                    })
                    fills.append({"ts": now.isoformat(), "kind": "ENTRY",
                                  "side": intent.side, "price": round(entry, 2),
                                  "spread": round(sprd, 3),
                                  "slippage_price": round(slip, 3),
                                  "volume": volume, "status": fill_status})
                    trades_today += 1
                pending = None

        # 2) Kelola posisi terbuka: SL/TP/time exit (termasuk bar entry -
        #    posisi yang dibuka di open bar ini bisa kena SL/TP intra-bar).
        if position is not None:
            event = broker.on_bar(position, bar["open"], bar["high"], bar["low"],
                                  bar["close"], sprd, now, slippage=slip)
            if event is not None:
                commission = cost_model.commission_usd(position.volume) if cost_model else 0.0
                swap = round(position_swap, 2)
                net = round(event.profit - commission - swap, 2)
                balance = round(balance + net, 2)
                daily_realized = round(daily_realized + net, 2)
                commission_total = round(commission_total + commission, 2)
                # swap_total sudah terakumulasi per rollover (bagian 3);
                # swap posisi TIDAK ditambah lagi di sini (hindari dobel).
                trades[-1].update({
                    "exit_price": event.price, "exit_reason": event.reason,
                    "gross_profit": event.profit, "commission_usd": commission,
                    "swap_usd": swap, "profit": net,
                    "closed_at": now.isoformat(),
                    "risk_usd": trades[-1]["risk_usd"],
                    "r_multiple": round(net / trades[-1]["risk_usd"], 3)
                    if trades[-1]["risk_usd"] else None,
                    "slippage_exit_price": round(slip, 3),
                })
                fills.append({"ts": now.isoformat(), "kind": event.reason,
                              "side": "EXIT", "price": event.price,
                              "spread": round(sprd, 3),
                              "slippage_price": round(slip, 3),
                              "volume": position.volume, "status": "FILLED"})
                position = None
                position_swap = 0.0

        # 3) Swap rollover untuk posisi yang masih terbuka (PRD §8.2):
        #    hanya saat pasar buka pada saat rollover; triple hari Rabu server.
        if position is not None and execution is not None and execution.swap_enabled:
            for cross in rollover_crossings(
                    prev_now, now, rollover_utc_hour=execution.rollover_utc_hour):
                if market_closed_minutes(symbol, cross):
                    continue
                triple = is_triple_swap_day(
                    cross, triple_weekday_server=execution.swap_triple_weekday_server)
                s = execution.swap_usd(position.side, position.volume, triple=triple)
                position_swap = round(position_swap + s, 2)
                swap_total = round(swap_total + s, 2)
        prev_now = now

        # 4) Sinyal baru (decide() sama dengan live; entry legacy di close
        #    bar sinyal, atau ditunda jadi pending bila latency aktif).
        if position is None and pending is None and trades_today < 1:
            day_candles.append(bar)
            if use_hist:
                hist.append(bar)
                ctx_candles: list[dict] = list(hist)
            else:
                ctx_candles = day_candles
            context = {
                "symbol": symbol,
                "now": now,
                "candles": ctx_candles,
                "liquidity": {"ts": now, "bid": tick_obs["bid"], "ask": tick_obs["ask"],
                              "spread": sprd_obs, "spread_median_15m": median15,
                              "fresh": True},
                "positions": [],
                "trades_today": trades_today,
                "risk": {"equity": balance, "risk_per_trade": 0.005, "max_volume": 0.10,
                         "max_spread": params.max_spread_abs},
            }
            intent = strategy.decide(context, params)
            if intent is not None:
                if regime_filter and regime_last is not None:
                    # Gate entry (PRD §6.2/6.5): UNKNOWN memblokir strategi
                    # yang mensyaratkan regime. Regime TIDAK mengubah risk
                    # limit - hanya kelayakan entry.
                    if not regime.regime_permits_entry(regime_last.label,
                                                       allowed_regimes):
                        _regime_stats["blocked"] += 1
                        _regime_stats["labels"][regime_last.label] = \
                            _regime_stats["labels"].get(regime_last.label, 0) + 1
                        continue
                decision = risk_gate(
                    {"symbol": intent.symbol, "side": intent.side, "volume": intent.volume,
                     "sl": intent.sl, "tp": intent.tp},
                    RiskContext(settings=settings, bid=tick_obs["bid"], ask=tick_obs["ask"],
                                tick_age_s=0.1, daily_pnl=daily_realized,
                                orders_last_minute=0))
                if decision.ok:
                    if execution is not None and execution.fill_delay_bars > 0:
                        # Latency: order menunggu, diisi di open bar berikutnya.
                        pending = {
                            "intent": intent, "signal_close": bar["close"],
                            "signal_bar": i,
                            "regime": (regime_last.label
                                       if regime_last else None),
                            "regime_confidence": (regime_last.confidence
                                                  if regime_last else None),
                        }
                    else:
                        entry = (tick["ask"] + slip if intent.side == "BUY"
                                 else tick["bid"] - slip)
                        position = PaperPosition(
                            order_id=str(i), side=intent.side, volume=intent.volume,
                            entry_price=entry, sl=intent.sl, tp=intent.tp,
                            opened_at=now, strategy=strategy_id,
                            contract_size=contract_size)
                        risk_usd = balance * 0.005
                        position_swap = 0.0
                        trades.append({
                            "entry_bar": i, "side": intent.side, "volume": intent.volume,
                            "entry_price": round(entry, 2), "sl": intent.sl, "tp": intent.tp,
                            "opened_at": now.isoformat(), "risk_usd": round(risk_usd, 2),
                            "reason": intent.reason, "session": session_of(now),
                            "spread_at_entry": round(sprd, 3),
                            "filter_spread_at_entry": round(sprd_obs, 3),
                            "status": "FILLED",
                            "regime": (regime_last.label
                                       if regime_last else None),
                            "regime_confidence": (regime_last.confidence
                                                  if regime_last else None),
                            "slippage_entry_price": round(slip, 3),
                        })
                        fills.append({"ts": now.isoformat(), "kind": "ENTRY",
                                      "side": intent.side, "price": round(entry, 2),
                                      "spread": round(sprd, 3),
                                      "slippage_price": round(slip, 3),
                                      "volume": intent.volume, "status": "FILLED"})
                        trades_today += 1

    if pending is not None:  # sisa order yang tidak pernah terisi
        rejections.append({"ts": candles[-1]["ts"].isoformat() if candles else "",
                           "reason": "END_UNFILLED",
                           "side": pending["intent"].side,
                           "volume": pending["intent"].volume})

    if position is not None:  # mark the last open position at the final close
        last = candles[-1]
        sprd = cost_model.spread_at(last["ts"]) if cost_model else spread
        exit_price = (last["close"] - sprd / 2 - slip if position.side == "BUY"
                      else last["close"] + sprd / 2 + slip)
        diff = (exit_price - position.entry_price if position.side == "BUY"
                else position.entry_price - exit_price)
        gross = round(diff * contract_size * position.volume, 2)
        commission = cost_model.commission_usd(position.volume) if cost_model else 0.0
        swap = round(position_swap, 2)
        net = round(gross - commission - swap, 2)
        balance = round(balance + net, 2)
        commission_total = round(commission_total + commission, 2)
        # swap_total sudah terakumulasi per rollover; jangan dobelkan.
        trades[-1].update({"exit_price": round(exit_price, 2), "exit_reason": "END",
                           "gross_profit": gross, "commission_usd": commission,
                           "swap_usd": swap, "profit": net,
                           "closed_at": last["ts"].isoformat(),
                           "r_multiple": round(net / (balance * 0.005), 3) if balance else None})

    out = summarize(trades, equity0, balance, spread, slippage, cost_model=cost_model,
                    commission_total=commission_total, strategy_id=strategy_id,
                    tf_seconds=tf_seconds, bars_total=len(candles),
                    execution=execution, rejections=rejections, fills=fills,
                    swap_total=swap_total)
    out["regime"] = _regime_summary(_regime_stats, trades, regime_filter,
                                    allowed_regimes, regime_last, symbol)
    return out


def _partial_fill_ratio(bar: dict, candles: list[dict], i: int,
                        execution: ExecutionModel) -> float:
    """Rasio fill volume (0..1] untuk partial fill (PRD §8.2).

    Bar dengan tick volume di bawah partial_volume_ratio x median volume
    20 bar terakhir dianggap tipis: hanya partial_fill_fraction yang
    terisi, sisanya dibatalkan. Deterministik, tanpa RNG.
    """
    ratio = execution.partial_volume_ratio
    if ratio is None:
        return 1.0
    window = [float(c.get("volume") or 0) for c in candles[max(0, i - 20):i + 1]]
    med = statistics.median(window) if window else 0.0
    vol = float(bar.get("volume") or 0)
    if med <= 0:
        return 1.0
    if vol < ratio * med:
        return max(0.0, min(1.0, execution.partial_fill_fraction))
    return 1.0


def _regime_summary(stats: dict, trades: list[dict], regime_filter: bool,
                    allowed_regimes: list | None, regime_last, symbol: str) -> dict:
    """Ringkasan regime (PRD §6.4: evaluasi performa per regime)."""
    closed = [t for t in trades if "profit" in t and t.get("regime") not in (None, "REGIME_OFF")]
    by_label: dict[str, dict] = {}
    for t in closed:
        lab = t["regime"]
        d = by_label.setdefault(lab, {"trades": 0, "net_usd": 0.0, "wins": 0})
        d["trades"] += 1
        d["net_usd"] = round(d["net_usd"] + t["profit"], 2)
        d["wins"] += 1 if t["profit"] > 0 else 0
    for d in by_label.values():
        d["winrate"] = round(d["wins"] / d["trades"], 4) if d["trades"] else None
    return {
        "enabled": bool(regime_filter),
        "classifier_version": regime.REGIME_VERSION,
        "params": "default_params_for_symbol(%s)" % symbol,
        "allowed_regimes": list(allowed_regimes or []),
        "labels_seen": stats["labels"],
        "blocked_entries": stats["blocked"],
        "breakdown": by_label,
    }


def _pctl(values: list[float], q: float) -> float | None:
    """Percentile linear interpolation (q in 0..1); None untuk list kosong."""
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return round(xs[0], 4)
    pos = q * (len(xs) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return round(xs[lo] * (1 - frac) + xs[hi] * frac, 4)


def _dist(values: list[float]) -> dict | None:
    """Distribusi ringkas: min/p50/mean/p90/max (PRD §8.3 distribusi)."""
    if not values:
        return None
    return {"min": round(min(values), 4), "p50": _pctl(values, 0.5),
            "mean": round(statistics.mean(values), 4),
            "p90": _pctl(values, 0.9), "max": round(max(values), 4)}


def _bucket_metrics(subset: list[dict]) -> dict:
    """Metrik penuh satu kelompok trade (sesi/regime/hari/bucket spread)."""
    n = len(subset)
    wins = [t for t in subset if t["profit"] > 0]
    losses = [t for t in subset if t["profit"] <= 0]
    gw = sum(t["profit"] for t in wins)
    gl = abs(sum(t["profit"] for t in losses))
    pnls = [t["profit"] for t in subset]
    return {
        "trades": n,
        "net_usd": round(sum(pnls), 2),
        "winrate": round(len(wins) / n, 4) if n else None,
        "profit_factor": round(gw / gl, 3) if gl else None,
        "expectancy_usd": round(statistics.mean(pnls), 2) if pnls else None,
    }


def summarize(trades: list[dict], equity0: float, balance: float, spread: float,
              slippage: float, *, cost_model: CostModel | None = None,
              commission_total: float = 0.0,
              strategy_id: str = "london_breakout",
              tf_seconds: int | None = None, bars_total: int | None = None,
              execution: ExecutionModel | None = None,
              rejections: list[dict] | None = None,
              fills: list[dict] | None = None,
              swap_total: float = 0.0) -> dict:
    """Metrik wajib PRD v2.2 §8.3 (semua dalam USD kecuali disebut lain).

    Metodologi (dilaporkan juga di kunci ``methodology``):
    - Sharpe per trade = mean(PnL)/stdev(PnL). Sharpe harian = mean/hari
      stdev/hari x sqrt(252) (annualized, 252 hari trading).
    - Sortino: penyebut deviasi downside (akar rata-rata kuadrat PnL
      negatif), bukan stdev penuh; harian annualized sama dengan Sharpe.
    - Max drawdown: puncak-ke-lembah terbesar kurva ekuiti closed-trade;
      durasi = interval terpanjang puncak sampai pemulihan (menit).
    - Exposure time = total menit posisi terbuka / menit window data.
    - Tail loss (CVaR 95) = rata-rata 5% trade terburuk.
    - CI 95% expectancy = mean +/- 1.96 x se (se = stdev/sqrt(n));
      aproksimasi normal, sampel kecil = interval lebar (jujur).
    """
    closed = [t for t in trades if "profit" in t]
    wins = [t for t in closed if t["profit"] > 0]
    losses = [t for t in closed if t["profit"] <= 0]
    gross_win = sum(t["profit"] for t in wins)
    gross_loss = abs(sum(t["profit"] for t in losses))
    curve = [equity0]
    for t in closed:
        curve.append(round(curve[-1] + t["profit"], 2))
    peak = equity0
    max_dd = 0.0
    for value in curve:
        peak = max(peak, value)
        max_dd = max(max_dd, peak - value)
    pnls = [t["profit"] for t in closed]
    rs = [t["r_multiple"] for t in closed if t.get("r_multiple") is not None]
    by_hour: dict[str, int] = {}
    by_weekday: dict[str, int] = {}
    by_session: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    by_day: dict[str, float] = {}
    by_day_trades: dict[str, int] = {}
    for t in closed:
        opened = datetime.fromisoformat(t["opened_at"])
        hour_key = str(opened.hour)
        by_hour[hour_key] = by_hour.get(hour_key, 0) + 1
        by_weekday[opened.strftime("%a")] = by_weekday.get(opened.strftime("%a"), 0) + 1
        by_session[t.get("session", "-")] = by_session.get(t.get("session", "-"), 0) + 1
        by_reason[t["exit_reason"]] = by_reason.get(t["exit_reason"], 0) + 1
        day_key = t.get("closed_at", "")[:10]
        by_day[day_key] = by_day.get(day_key, 0.0) + t["profit"]
        by_day_trades[day_key] = by_day_trades.get(day_key, 0) + 1
    std = statistics.stdev(pnls) if len(pnls) > 2 else 0.0
    sharpe = round(statistics.mean(pnls) / std, 3) if std > 0 else None
    daily = list(by_day.values())
    dstd = statistics.stdev(daily) if len(daily) > 2 else 0.0
    sharpe_daily = (round(statistics.mean(daily) / dstd * (252 ** 0.5), 3)
                    if dstd > 0 else None)
    # Sortino (PRD §8.3): deviasi downside, bukan stdev penuh.
    downside_sq = [min(p, 0.0) ** 2 for p in pnls]
    ddev = (statistics.mean(downside_sq) ** 0.5) if pnls else 0.0
    sortino_per_trade = (round(statistics.mean(pnls) / ddev, 3)
                         if pnls and ddev > 0 else None)
    daily_downside_sq = [min(d, 0.0) ** 2 for d in daily]
    ddev_daily = (statistics.mean(daily_downside_sq) ** 0.5) if daily else 0.0
    sortino_daily = (round(statistics.mean(daily) / ddev_daily * (252 ** 0.5), 3)
                     if daily and ddev_daily > 0 else None)
    # Holding time & exposure time (PRD §8.3).
    holdings_min: list[float] = []
    for t in closed:
        try:
            o = datetime.fromisoformat(t["opened_at"])
            c = datetime.fromisoformat(t["closed_at"])
            holdings_min.append(max(0.0, (c - o).total_seconds() / 60.0))
        except (KeyError, ValueError, TypeError):
            continue
    window_minutes = (bars_total * tf_seconds / 60.0
                      if bars_total and tf_seconds else None)
    exposure_pct = (round(100.0 * sum(holdings_min) / window_minutes, 2)
                    if window_minutes and window_minutes > 0 else None)
    # Durasi drawdown terpanjang (puncak -> pemulihan penuh), menit.
    # Standard "longest drawdown duration": interval dari puncak kurva ke
    # saat ekuiti kembali menyamai puncak; DD yang belum pulih di akhir
    # window dilaporkan terpisah (drawdown_open_at_end_min).
    peak2 = equity0
    max_dd_duration_min = 0.0
    dd_duration_open_min: float | None = None
    peak_ts: datetime | None = None
    in_dd = False
    for t, value in zip(closed, curve[1:]):
        try:
            cts = datetime.fromisoformat(t["closed_at"])
        except (KeyError, ValueError, TypeError):
            continue
        if value >= peak2:
            if in_dd and peak_ts is not None:
                dur = (cts - peak_ts).total_seconds() / 60.0
                max_dd_duration_min = max(max_dd_duration_min, dur)
                in_dd = False
            peak2 = value
            peak_ts = cts
        else:
            in_dd = True
            if peak_ts is not None:
                dur = (cts - peak_ts).total_seconds() / 60.0
                max_dd_duration_min = max(max_dd_duration_min, dur)
    if in_dd and peak_ts is not None and closed:
        dd_duration_open_min = (
            datetime.fromisoformat(closed[-1]["closed_at"]) - peak_ts
        ).total_seconds() / 60.0
    # Tail loss / CVaR 95 & worst trade (PRD §8.3).
    tail_loss = None
    worst_trade = None
    if pnls:
        k = max(1, -(-len(pnls) * 5 // 100))  # ceil(5%)
        tail_loss = round(statistics.mean(sorted(pnls)[:k]), 2)
        worst_trade = round(min(pnls), 2)
    # CI 95% expectancy (aproksimasi normal, metodologi dijelaskan).
    ci95 = None
    if len(pnls) >= 2 and std > 0:
        se = std / (len(pnls) ** 0.5)
        mean_pnl = statistics.mean(pnls)
        ci95 = [round(mean_pnl - 1.96 * se, 2), round(mean_pnl + 1.96 * se, 2)]
    # Distribusi spread (entry) & slippage per fill (PRD §8.3).
    spread_entries = [float(t["spread_at_entry"]) for t in closed
                      if t.get("spread_at_entry") is not None]
    slip_fills = [float(f.get("slippage_price") or 0.0) for f in (fills or [])]
    # Breakdown per kelompok dengan metrik penuh (PRD §8.3: per sesi/regime/
    # hari/kondisi spread).
    by_session_full: dict[str, dict] = {}
    for key in by_session:
        subset = [t for t in closed if t.get("session", "-") == key]
        by_session_full[key] = _bucket_metrics(subset)
    by_weekday_full: dict[str, dict] = {}
    for key in by_weekday:
        subset = [t for t in closed
                  if datetime.fromisoformat(t["opened_at"]).strftime("%a") == key]
        by_weekday_full[key] = _bucket_metrics(subset)
    by_day_full: dict[str, dict] = {}
    for key in by_day:
        by_day_full[key] = {"net_usd": round(by_day[key], 2),
                            "trades": by_day_trades[key]}
    # Bucket spread: kuartil spread entry yang teramati; bucket [lo, hi)
    # kecuali bucket terakhir [lo, hi].
    spread_buckets: dict[str, dict] = {}
    if len(spread_entries) >= 4:
        qs = [_pctl(spread_entries, q) for q in (0.25, 0.5, 0.75)]
        edges = [min(spread_entries)] + qs + [max(spread_entries)]
        labels = ["q1_rendah", "q2", "q3", "q4_tinggi"]
        for idx, label in enumerate(labels):
            lo, hi = edges[idx], edges[idx + 1]
            subset = [t for t in closed
                      if t.get("spread_at_entry") is not None
                      and lo <= float(t["spread_at_entry"]) <= hi
                      and (idx == 3 or float(t["spread_at_entry"]) < hi)]
            spread_buckets[label] = _bucket_metrics(subset)
            spread_buckets[label]["range"] = [round(lo, 4), round(hi, 4)]
    rej_by_reason: dict[str, int] = {}
    for r in (rejections or []):
        rej_by_reason[r.get("reason", "?")] = rej_by_reason.get(r.get("reason", "?"), 0) + 1
    if cost_model is not None:
        cost_report = cost_model.as_dict()
        cost_report["commission_total_usd"] = commission_total
        cost_report["swap_total_usd"] = round(swap_total, 2)
    else:
        cost_report = {"spread_usd": spread, "slippage_usd_per_fill": slippage,
                       "swap_total_usd": round(swap_total, 2)}
    return {
        "strategy": strategy_id,
        "trades": len(closed),
        "wins": len(wins), "losses": len(losses),
        "winrate": round(len(wins) / len(closed), 4) if closed else None,
        "avg_win_usd": round(statistics.mean([t["profit"] for t in wins]), 2) if wins else None,
        "avg_loss_usd": round(statistics.mean([t["profit"] for t in losses]), 2) if losses else None,
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else None,
        "expectancy_usd": round(statistics.mean(pnls), 2) if pnls else None,
        "expectancy_r": round(statistics.mean(rs), 3) if rs else None,
        "expectancy_ci95": ci95,
        "sharpe_per_trade": sharpe,
        "sharpe_daily_annualized": sharpe_daily,
        "sortino_per_trade": sortino_per_trade,
        "sortino_daily_annualized": sortino_daily,
        "max_drawdown_usd": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd / peak, 4) if peak else None,
        "max_drawdown_duration_min": round(max_dd_duration_min, 1) if max_dd_duration_min else 0.0,
        "drawdown_open_at_end_min": (round(dd_duration_open_min, 1)
                                     if dd_duration_open_min else None),
        "net_profit_usd": round(balance - equity0, 2),
        "final_balance": balance,
        "exposure_pct": exposure_pct,
        "avg_holding_min": round(statistics.mean(holdings_min), 1) if holdings_min else None,
        "median_holding_min": _pctl(holdings_min, 0.5),
        "max_holding_min": round(max(holdings_min), 1) if holdings_min else None,
        "tail_loss_cvar95_usd": tail_loss,
        "worst_trade_usd": worst_trade,
        "worst_day_usd": round(min(daily), 2) if daily else None,
        "best_day_usd": round(max(daily), 2) if daily else None,
        "spread_distribution": _dist(spread_entries),
        "slippage_distribution": _dist(slip_fills),
        "commission_total_usd": round(commission_total, 2),
        "swap_total_usd": round(swap_total, 2),
        "rejections": {"total": len(rejections or []), "by_reason": rej_by_reason},
        "execution": execution.as_dict() if execution else None,
        "cost_model": cost_report,
        "exits": by_reason, "entries_by_hour_utc": by_hour,
        "entries_by_weekday": by_weekday,
        "entries_by_session": by_session,
        "by_session": by_session_full,
        "by_weekday": by_weekday_full,
        "by_day": by_day_full,
        "by_spread_bucket": spread_buckets,
        "curve": curve,
        "methodology": {
            "sharpe_per_trade": "mean(PnL)/stdev(PnL)",
            "sharpe_daily": "mean(harian)/stdev(harian) x sqrt(252)",
            "sortino": "penyebut = deviasi downside (akar rata-rata kuadrat PnL<0)",
            "max_drawdown": "puncak-ke-lembah kurva ekuiti closed-trade",
            "max_drawdown_duration": "interval terpanjang puncak->pemulihan (menit)",
            "exposure_pct": "total menit posisi terbuka / menit window data",
            "tail_loss_cvar95": "rata-rata 5% trade terburuk",
            "expectancy_ci95": "mean +/- 1.96 x se (aproksimasi normal)",
            "spread_bucket": "kuartil spread entry teramati dalam window",
            "net_profit": "setelah spread, komisi, slippage, dan swap",
        },
        "trades_detail": closed,
    }


def render_report(result: dict, meta: dict) -> str:
    cm = result.get("cost_model") or {}
    spread_txt = (f"{cm['spread_usd']:.2f}" if cm.get("spread_usd") is not None
                  else "per sesi (kalibrasi)")
    lines = [
        f"# Backtest {result['strategy']} ({meta['tf']})",
        "",
        f"- Periode: {meta['start']} .. {meta['end']} (UTC, data candle {meta['tf']})",
        f"- Equity awal: {meta['equity']:.2f} USD; risiko per trade 0.5%",
        f"- Biaya: spread {spread_txt} USD, slippage "
        f"{cm.get('slippage_usd_per_fill', 0):.2f} USD per fill; komisi "
        f"{result.get('commission_total_usd', 0)} USD; swap {result.get('swap_total_usd', 0)} USD",
        "",
        "| Metrik | Nilai |",
        "| --- | --- |",
        f"| Trades | {result['trades']} |",
        f"| Winrate | {result['winrate'] if result['winrate'] is not None else '-'} |",
        f"| Profit factor | {result['profit_factor'] if result['profit_factor'] is not None else '-'} |",
        f"| Expectancy | {result['expectancy_usd']} USD / trade ({result['expectancy_r']} R) |",
        f"| CI 95% expectancy | {result.get('expectancy_ci95')} |",
        f"| Sharpe (per trade) | {result['sharpe_per_trade']} |",
        f"| Sortino (per trade) | {result.get('sortino_per_trade')} |",
        f"| Max drawdown | {result['max_drawdown_usd']} USD ({result['max_drawdown_pct']}) |",
        f"| Durasi max DD | {result.get('max_drawdown_duration_min')} menit |",
        f"| Net profit | {result['net_profit_usd']} USD |",
        f"| Exposure | {result.get('exposure_pct')}% |",
        f"| Avg holding | {result.get('avg_holding_min')} menit |",
        f"| Tail loss (CVaR95) | {result.get('tail_loss_cvar95_usd')} USD |",
        f"| Worst day | {result.get('worst_day_usd')} USD |",
        f"| Rejections | {result.get('rejections')} |",
        f"| Exit mix | {result['exits']} |",
        f"| Entry per jam UTC | {result['entries_by_hour_utc']} |",
        f"| Entry per hari | {result['entries_by_weekday']} |",
        f"| Per sesi | {result.get('by_session')} |",
        f"| Per bucket spread | {result.get('by_spread_bucket')} |",
        "",
        "Catatan: sampel pendek, bukan validasi walk-forward (P2). "
        "Hasil backtest bukan jaminan performa live.",
    ]
    return "\n".join(lines) + "\n"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Quick backtest strategy #1")
    parser.add_argument("--tf", default="5m", choices=["1m", "5m", "15m", "1h"])
    parser.add_argument("--days", type=int, default=0, help="lookback from latest candle")
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--equity", type=float, default=10000.0)
    parser.add_argument("--spread", type=float, default=SPREAD_DEFAULT)
    parser.add_argument("--slippage", type=float, default=SLIPPAGE_DEFAULT)
    parser.add_argument("--execution", choices=["model", "legacy"], default="model",
                        help="model: swap/latency/rejection/closure (PRD v2.2 8.2); "
                             "legacy: perilaku lama tanpa execution model")
    parser.add_argument("--save-db", action="store_true", help="write trades as REPLAY rows")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    tf_seconds = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}[args.tf]
    await db.init_pool()
    async with db.pool().connection() as conn:
        db_tz = await db_timezone_offset_h(conn)
        if args.days:
            row = await conn.execute(
                "SELECT max(ts) AS m FROM candles WHERE symbol=%s AND timeframe=%s",
                (SYMBOL, canonical_tf(args.tf)))
            latest = (await row.fetchone())["m"]
            start = latest - timedelta(days=args.days)
            end = latest
        else:
            start = datetime.fromisoformat(args.start) if args.start else datetime(2026, 1, 1, tzinfo=timezone.utc)
            end = datetime.fromisoformat(args.end) if args.end else datetime.now(timezone.utc)
        rows = await load_history_rows(conn, args.tf, start, end)
        if args.save_db:
            await conn.execute("DELETE FROM paper_orders WHERE mode = 'REPLAY'")
    await db.close_pool()

    candles = to_utc_candles(rows, db_tz)
    execution = (default_execution_model(SYMBOL) if args.execution == "model" else None)
    result = run_backtest(candles, tf_seconds=tf_seconds, equity0=args.equity,
                          spread=args.spread, slippage=args.slippage,
                          execution=execution)
    meta = {"tf": args.tf, "start": candles[0]["ts"].isoformat() if candles else "",
            "end": candles[-1]["ts"].isoformat() if candles else "", "equity": args.equity}
    result["meta"] = meta
    print(json.dumps({k: v for k, v in result.items() if k != "trades_detail"}, indent=1))

    if args.save_db and candles:
        await _save_replay_rows(result)
    if args.out_json:
        with open(args.out_json, "w") as fh:
            json.dump(result, fh, indent=1, default=str)
    if args.out_md:
        with open(args.out_md, "w") as fh:
            fh.write(render_report(result, meta))


async def _save_replay_rows(result: dict) -> None:
    await db.init_pool()
    async with db.pool().connection() as conn:
        for t in result["trades_detail"]:
            await conn.execute(
                """
                INSERT INTO paper_orders (mode, strategy, symbol, side, volume, sl, tp,
                                          status, risk_decision, entry_price, exit_price,
                                          profit, reason, opened_at, closed_at)
                VALUES ('REPLAY', %s, %s, %s, %s, %s, %s, 'CLOSED', %s, %s, %s, %s, %s, %s, %s)
                """,
                (result["strategy"], SYMBOL, t["side"], t["volume"], t["sl"], t["tp"],
                 json.dumps({"backtest": True, "exit_reason": t["exit_reason"]}),
                 t["entry_price"], t["exit_price"], t["profit"], t["reason"],
                 datetime.fromisoformat(t["opened_at"]),
                 datetime.fromisoformat(t["closed_at"])))
    await db.close_pool()
    print(f"saved {len(result['trades_detail'])} REPLAY rows to paper_orders")


if __name__ == "__main__":
    asyncio.run(main())
