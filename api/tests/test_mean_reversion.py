"""Tests for strategy #2: Bollinger mean reversion, re-entry trigger (PRD P2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from strategies.mean_reversion import STRATEGY_ID, OrderIntent, decide

DAY = "2026-11-23"  # Monday
BASE = datetime.fromisoformat(DAY).replace(tzinfo=timezone.utc)

# Reference scenario: flat 3355 all day; pierce bar 09:20 (close 3342, low 3341),
# re-entry bar 09:25 (close 3346, low 3344).
# Band over the last 20 closes: SMA 3353.90, sigma 3.36, lower 3345.50.


def candle(index, o, h, l, c):
    ts = BASE + timedelta(minutes=5 * index)
    return {"ts": ts.isoformat(), "open": o, "high": h, "low": l, "close": c, "volume": 0}


def day_candles(pierce_close=3342.0, pierce_low=3341.0, pierce_high=3355.0,
                reentry_close=3346.0, reentry_low=3344.0, reentry_high=3349.0,
                pierce_index=112) -> list[dict]:
    """84 Asia bars (00:00-07:00) + London bars + pierce bar + re-entry bar."""
    out = [candle(i, 3355.0, 3356.0, 3354.0, 3355.0) for i in range(pierce_index)]
    out.append(candle(pierce_index, 3355.0, pierce_high, pierce_low, pierce_close))
    out.append(candle(pierce_index + 1, pierce_close, reentry_high, reentry_low,
                      reentry_close))
    return out


def ctx(candles, now=None, spread=0.30, median=0.25, fresh=True,
        positions=None, trades_today=0, equity=10000.0, **risk_extra):
    now = now or f"{DAY}T09:30:30+00:00"  # re-entry bar closed at 09:30
    return {
        "symbol": "XAUUSD",
        "now": now,
        "candles": candles,
        "liquidity": {
            "ts": now,
            "bid": 3346.0,
            "ask": 3346.0 + spread,
            "spread": spread,
            "spread_median_15m": median,
            "fresh": fresh,
        },
        "positions": positions or [],
        "trades_today": trades_today,
        "risk": {
            "equity": equity,
            "risk_per_trade": 0.005,
            "max_volume": 0.10,
            "max_spread": 0.50,
            **risk_extra,
        },
    }


# ---------------------------------------------------------------- entries


def test_buy_reentry_emits_intent_with_sl_tp():
    intent = decide(ctx(day_candles()))
    assert intent is not None
    assert intent.side == "BUY"
    assert intent.symbol == "XAUUSD"
    assert intent.strategy == STRATEGY_ID
    assert intent.sl == 3340.9  # below the pierce bar low (structure stop)
    assert intent.tp == pytest.approx(3353.9)  # target: the mean (SMA20)
    assert intent.sl_distance == pytest.approx(5.1)
    assert intent.volume == pytest.approx(0.09)  # 50 USD risk / (5.1 x 100)
    assert "mean reversion" in intent.reason


def test_sell_reentry_emits_intent_with_sl_tp():
    candles = day_candles(pierce_close=3366.0, pierce_low=3365.0, pierce_high=3367.0,
                          reentry_close=3362.0, reentry_low=3361.0, reentry_high=3363.0)
    intent = decide(ctx(candles))
    assert intent is not None
    assert intent.side == "SELL"
    assert intent.sl == 3367.1  # above the pierce bar high
    assert intent.tp == pytest.approx(3355.9)  # target: the mean (SMA20)
    assert intent.volume == pytest.approx(0.09)


def test_no_entry_without_pierce():
    assert decide(ctx(day_candles(pierce_close=3355.0, pierce_low=3354.0))) is None


def test_no_entry_when_prev_close_not_beyond_band():
    # pierce bar closes above the lower band: no piercing, just noise
    assert decide(ctx(day_candles(pierce_close=3347.0))) is None


def test_no_entry_when_close_still_beyond_band():
    # re-entry bar closes below the lower band: reversion not confirmed
    assert decide(ctx(day_candles(reentry_close=3340.0))) is None


def test_no_entry_outside_entry_window():
    # re-entry bar at 06:55 (before London) and at 16:05 (after window)
    early = day_candles(pierce_index=83)  # pierce 06:50, re-entry 06:55
    assert decide(ctx(early, now=f"{DAY}T07:00:30+00:00")) is None
    late = day_candles(pierce_index=191)  # pierce 15:55, re-entry 16:00
    assert decide(ctx(late, now=f"{DAY}T16:05:30+00:00")) is None


# ---------------------------------------------------------------- guards


def test_no_entry_when_bar_not_closed():
    assert decide(ctx(day_candles(), now=f"{DAY}T09:25:30+00:00")) is None


def test_no_entry_on_stale_candle():
    assert decide(ctx(day_candles(), now=f"{DAY}T09:33:00+00:00")) is None


def test_no_entry_on_unfresh_liquidity():
    assert decide(ctx(day_candles(), fresh=False)) is None


def test_no_entry_on_stale_liquidity():
    candles = day_candles()
    context = ctx(candles)
    context["liquidity"]["ts"] = f"{DAY}T09:00:00+00:00"  # > 120 s old
    assert decide(context) is None


def test_no_entry_on_wide_spread():
    assert decide(ctx(day_candles(), spread=0.80)) is None
    # median-driven threshold: 2 x 0.25 = 0.50, spread 0.55 exceeds it
    assert decide(ctx(day_candles(), spread=0.55, median=0.25)) is None


def test_no_entry_with_open_position():
    positions = [{"order_id": "x", "side": "BUY", "volume": 0.1,
                  "entry_price": 3350.0, "sl": 3340.0, "tp": 3360.0}]
    assert decide(ctx(day_candles(), positions=positions)) is None


def test_no_entry_when_one_trade_today():
    assert decide(ctx(day_candles(), trades_today=1)) is None


def test_no_entry_on_weekend():
    saturday = datetime.fromisoformat("2026-11-21").replace(tzinfo=timezone.utc)
    candles = day_candles()
    context = ctx(candles)
    context["now"] = (saturday + timedelta(minutes=5 * 113)).isoformat()
    assert decide(context) is None


def test_no_entry_with_short_history():
    assert decide(ctx(day_candles()[:15])) is None


# ---------------------------------------------------------------- risk shape


def test_sl_too_far_is_skipped():
    # deep pierce pushes the structure stop beyond the 15 USD gate bound
    assert decide(ctx(day_candles(pierce_close=3330.0, pierce_low=3325.0))) is None


def test_tp_behind_entry_is_skipped():
    # re-entry close already above the mean: no room to revert (BUY)
    assert decide(ctx(day_candles(reentry_close=3356.0))) is None


def test_low_rr_is_skipped():
    # close near the mean but stop still wide: RR below the 0.6 floor
    assert decide(ctx(day_candles(reentry_close=3353.0))) is None


def test_volume_floor_is_skipped():
    # risk budget cannot buy the minimum volume
    assert decide(ctx(day_candles(), equity=100.0)) is None


def test_intent_is_frozen_dataclass():
    intent = decide(ctx(day_candles()))
    assert isinstance(intent, OrderIntent)
    with pytest.raises(Exception):
        intent.side = "SELL"
