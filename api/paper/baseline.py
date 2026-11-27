"""Baseline sederhana untuk pembanding backtest (PRD v2.2 §8.2).

Dua baseline, sama-sama memakai cost model (spread/komisi/slippage) dan
execution model (swap) yang sama dengan strategi:

- buy_and_hold: eksposur mentah arah long dari bar pertama ke terakhir.
  Menjawab "apakah strategi mengalahkan sekedar memegang asetnya?".
- random_entry: entry acak (RNG di-seed dan seed dicatat di config —
  reproducible) dengan SL/TP dan sizing risiko yang sama dengan strategi.
  Menjawab "apakah edge strategi lebih baik dari entry acak?".

Baseline bukan strategi: hasilnya pembanding, bukan klaim profit.
"""
from __future__ import annotations

import random
import statistics
from datetime import datetime, timedelta, timezone

from app.data_quality import market_closed_minutes
from paper.broker import PaperBroker, PaperPosition
from paper.costs import CostModel
from paper.execution import ExecutionModel, is_triple_swap_day, rollover_crossings


def _swap_between(position: PaperPosition, t0: datetime, t1: datetime, symbol: str,
                  execution: ExecutionModel | None) -> float:
    """Total swap posisi yang terbuka sepanjang (t0, t1] (rollover pasar buka)."""
    if execution is None or not execution.swap_enabled:
        return 0.0
    total = 0.0
    for cross in rollover_crossings(t0, t1,
                                    rollover_utc_hour=execution.rollover_utc_hour):
        if market_closed_minutes(symbol, cross):
            continue
        triple = is_triple_swap_day(
            cross, triple_weekday_server=execution.swap_triple_weekday_server)
        total += execution.swap_usd(position.side, position.volume, triple=triple)
    return round(total, 2)


def buy_and_hold(candles: list[dict], *, symbol: str, contract_size: float = 100.0,
                 equity0: float = 10000.0, spread: float = 0.50, slippage: float = 0.10,
                 cost_model: CostModel | None = None,
                 execution: ExecutionModel | None = None,
                 volume: float = 0.10) -> dict:
    """Baseline beli-dan-tahan: entry open pertama (ask+slip), exit close
    terakhir (bid-slip), komisi round-turn, swap per malam, max DD dari
    close series pada volume yang sama."""
    if len(candles) < 2:
        raise ValueError("buy_and_hold butuh >= 2 bar")
    slip = cost_model.slippage_usd_per_fill if cost_model else slippage
    sprd0 = cost_model.spread_at(candles[0]["ts"]) if cost_model else spread
    sprd1 = cost_model.spread_at(candles[-1]["ts"]) if cost_model else spread
    entry = candles[0]["open"] + sprd0 / 2 + slip
    exit_price = candles[-1]["close"] - sprd1 / 2 - slip
    gross = (exit_price - entry) * contract_size * volume
    commission = cost_model.commission_usd(volume) if cost_model else 0.0
    pos = PaperPosition(order_id="bah", side="BUY", volume=volume, entry_price=entry,
                        sl=0.0, tp=0.0, opened_at=candles[0]["ts"],
                        contract_size=contract_size)
    swap = _swap_between(pos, candles[0]["ts"], candles[-1]["ts"], symbol, execution)
    net = round(gross - commission - swap, 2)
    # kurva ekuiti mark-to-market pada close tiap bar (untuk max DD)
    curve = [equity0]
    for c in candles:
        mtm = (c["close"] - entry) * contract_size * volume
        curve.append(round(equity0 + mtm - commission - swap, 2))
    peak = equity0
    max_dd = 0.0
    for v in curve:
        peak = max(peak, v)
        max_dd = max(max_dd, peak - v)
    return {
        "name": "buy_and_hold",
        "trades": 1,
        "volume": volume,
        "entry_price": round(entry, 2),
        "exit_price": round(exit_price, 2),
        "gross_profit_usd": round(gross, 2),
        "commission_usd": round(commission, 2),
        "swap_usd": swap,
        "net_profit_usd": net,
        "return_pct": round(100 * net / equity0, 3),
        "max_drawdown_usd": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd / peak, 4) if peak else None,
        "final_balance": round(equity0 + net, 2),
        "bars": len(candles),
        "note": "baseline eksposur mentah; tanpa SL/TP (risiko tidak terbatas)",
    }


def random_entry(candles: list[dict], *, symbol: str, seed: int,
                 n_trades: int = 30, contract_size: float = 100.0,
                 equity0: float = 10000.0, spread: float = 0.50,
                 slippage: float = 0.10, cost_model: CostModel | None = None,
                 execution: ExecutionModel | None = None,
                 sl_distance_usd: float = 2.0, rr: float = 1.5,
                 risk_per_trade: float = 0.005,
                 force_close_hour_utc: int = 16) -> dict:
    """Baseline entry acak ber-seed: SL/TP dan sizing risiko mengikuti
    konvensi strategi (risiko 0.5% ekuiti per trade, min 0.01 lot, maks
    0.10 lot), time exit jam 16:00 UTC seperti strategi #1 (E1). RNG
    random.Random(seed) — seed dicatat sehingga reproducible."""
    if not candles:
        raise ValueError("tidak ada candle untuk baseline random entry")
    rng = random.Random(seed)
    slip = cost_model.slippage_usd_per_fill if cost_model else slippage
    broker = PaperBroker(force_close_hour_utc=force_close_hour_utc)
    balance = equity0
    trades: list[dict] = []
    openable = [i for i, c in enumerate(candles)
                if not market_closed_minutes(symbol, c["ts"])]
    if not openable:
        raise ValueError("tidak ada bar pasar buka untuk baseline")
    picks = rng.sample(openable, min(n_trades, len(openable)))
    for idx in picks:
        bar = candles[idx]
        sprd = cost_model.spread_at(bar["ts"]) if cost_model else spread
        side = rng.choice(["BUY", "SELL"])
        risk_usd = balance * risk_per_trade
        vol = round(risk_usd / (sl_distance_usd * contract_size), 2)
        vol = max(0.01, min(0.10, vol))
        entry = (bar["close"] + sprd / 2 + slip if side == "BUY"
                 else bar["close"] - sprd / 2 - slip)
        sl = (entry - sl_distance_usd if side == "BUY" else entry + sl_distance_usd)
        tp = (entry + rr * sl_distance_usd if side == "BUY"
              else entry - rr * sl_distance_usd)
        pos = PaperPosition(order_id=str(idx), side=side, volume=vol,
                            entry_price=entry, sl=sl, tp=tp, opened_at=bar["ts"],
                            contract_size=contract_size)
        closed = None
        swap = 0.0
        for j in range(idx + 1, len(candles)):
            b2 = candles[j]
            now = b2["ts"]
            if now.date() != bar["ts"].date():
                # lewat tengah hari: paksa close di open bar hari berikutnya
                sprd2 = cost_model.spread_at(now) if cost_model else spread
                exit_price = (b2["open"] - sprd2 / 2 - slip if side == "BUY"
                              else b2["open"] + sprd2 / 2 + slip)
                closed = ("TIME", exit_price, now)
                break
            sprd2 = cost_model.spread_at(now) if cost_model else spread
            event = broker.on_bar(pos, b2["open"], b2["high"], b2["low"],
                                  b2["close"], sprd2, now, slippage=slip)
            if event is not None:
                closed = (event.reason, event.price, now)
                break
        if closed is None:
            last = candles[-1]
            sprd2 = cost_model.spread_at(last["ts"]) if cost_model else spread
            exit_price = (last["close"] - sprd2 / 2 - slip if side == "BUY"
                          else last["close"] + sprd2 / 2 + slip)
            closed = ("END", exit_price, last["ts"])
        reason, exit_price, closed_at = closed
        diff = (exit_price - entry if side == "BUY" else entry - exit_price)
        gross = diff * contract_size * vol
        commission = cost_model.commission_usd(vol) if cost_model else 0.0
        pos_swap = _swap_between(pos, bar["ts"], closed_at, symbol, execution)
        net = round(gross - commission - pos_swap, 2)
        balance = round(balance + net, 2)
        trades.append({"opened_at": bar["ts"].isoformat(),
                       "closed_at": closed_at.isoformat(),
                       "side": side, "volume": vol, "profit": net,
                       "exit_reason": reason})
    closed_trades = [t for t in trades if "profit" in t]
    wins = [t for t in closed_trades if t["profit"] > 0]
    losses = [t for t in closed_trades if t["profit"] <= 0]
    gw = sum(t["profit"] for t in wins)
    gl = abs(sum(t["profit"] for t in losses))
    pnls = [t["profit"] for t in closed_trades]
    return {
        "name": "random_entry",
        "seed": seed,
        "n_requested": n_trades,
        "trades": len(closed_trades),
        "winrate": round(len(wins) / len(closed_trades), 4) if closed_trades else None,
        "profit_factor": round(gw / gl, 3) if gl else None,
        "expectancy_usd": round(statistics.mean(pnls), 2) if pnls else None,
        "net_profit_usd": round(balance - equity0, 2),
        "final_balance": balance,
        "sl_distance_usd": sl_distance_usd,
        "rr": rr,
        "note": "entry acak ber-seed; pembanding edge, bukan strategi",
    }
