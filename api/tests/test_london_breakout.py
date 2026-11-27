"""Tests for strategy #1: London breakout + spread filter (PRD 5.3)."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from strategies.london_breakout import STRATEGY_ID, OrderIntent, decide

DAY = "2026-11-23"  # Monday
# Asia range reference: high 3360.0 / low 3350.0


def candle(ts, o, h, l, c):
    return {"ts": ts, "open": o, "high": h, "low": l, "close": c, "volume": 0}


def day_candles(breakout_close: float | None = None, breakout_hour: int = 7,
                breakout_minute: int = 5) -> list[dict]:
    """84 Asia bars 00:00-07:00 (range exactly 3350-3360) + London bars.

    Asia: open=close=3355; bar 0 has high 3360, bar 1 has low 3350.
    London: 07:00 bar closes 3355 (inside), then the breakout bar.
    """
    base = datetime.fromisoformat(DAY).replace(tzinfo=timezone.utc)
    out = []
    for i in range(84):
        ts = base + timedelta(minutes=5 * i)
        high = 3360.0 if i == 0 else 3356.0
        low = 3350.0 if i == 1 else 3354.0
        out.append(candle(ts.isoformat(), 3355.0, high, low, 3355.0))
    # 07:00 bar: still inside the range
    t7 = base + timedelta(minutes=5 * 84)
    out.append(candle(t7.isoformat(), 3355.0, 3356.0, 3354.0, 3355.0))
    if breakout_close is not None:
        tb = base + timedelta(minutes=5 * 84 + 5 * (breakout_hour - 7) + breakout_minute - 5)
        # breakout bar opens near range edge, closes beyond it
        out.append(
            candle(
                tb.isoformat(),
                3355.0,
                max(3356.0, breakout_close + 0.5),
                min(3354.0, breakout_close - 0.5),
                breakout_close,
            )
        )
    return out


def ctx(candles, now=f"{DAY}T07:05:30+00:00", spread=0.35, median=0.30, fresh=True,
        positions=None, trades_today=0, equity=10000.0, **risk_extra):
    return {
        "symbol": "XAUUSD",
        "now": now,
        "candles": candles,
        "liquidity": {
            "ts": now,
            "bid": 3361.0,
            "ask": 3361.0 + spread,
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


def test_buy_breakout_emits_intent_with_sl_tp():
    candles = day_candles(breakout_close=3361.5)  # close > 3360 + 0.10 buffer
    intent = decide(ctx(candles))
    assert intent is not None
    assert intent.side == "BUY"
    assert intent.symbol == "XAUUSD"
    assert intent.strategy == STRATEGY_ID
    assert intent.sl == 3354.0  # below the breakout candle (structure stop)
    assert intent.tp == pytest.approx(3361.5 + 1.5 * 7.5)  # rr x SL distance
    assert intent.volume == pytest.approx(0.06)  # 50 USD risk / (7.5 x 100)
    assert intent.sl_distance == pytest.approx(7.5)
    assert "3361.5" in intent.reason


def test_sell_breakout_emits_intent_with_sl_tp():
    candles = day_candles(breakout_close=3348.5)  # close < 3350 - 0.10 buffer
    intent = decide(ctx(candles))
    assert intent is not None
    assert intent.side == "SELL"
    assert intent.sl == 3356.0  # above the breakout candle
    assert intent.tp == pytest.approx(3348.5 - 1.5 * 7.5)
    assert intent.volume == pytest.approx(0.06)


def test_no_entry_without_breakout():
    assert decide(ctx(day_candles())) is None  # no breakout bar at all


def test_no_entry_outside_london_window():
    # breakout bar exists but now is still Asia / already London+NY
    candles = day_candles(breakout_close=3361.5)
    assert decide(ctx(candles, now=f"{DAY}T06:55:00+00:00")) is None
    assert decide(ctx(candles, now=f"{DAY}T12:05:00+00:00")) is None


def test_no_late_entry_when_prev_close_already_beyond():
    # breakout happened on the 07:00 bar; the 07:05 bar is continuation
    candles = day_candles(breakout_close=3361.5)
    candles[84] = candle(f"{DAY}T07:00:00+00:00", 3355.0, 3361.0, 3354.0, 3361.0)
    assert decide(ctx(candles)) is None


def test_breakout_buffer_is_required():
    candles = day_candles(breakout_close=3360.05)  # only 0.05 beyond high
    assert decide(ctx(candles)) is None


# ---------------------------------------------------------------- filters


def test_spread_filter_dynamic_threshold():
    candles = day_candles(breakout_close=3361.5)
    # threshold = max(2 x 0.30, 0.50) = 0.60
    assert decide(ctx(candles, spread=0.55)) is not None
    assert decide(ctx(candles, spread=0.65)) is None


def test_spread_filter_without_median_uses_absolute():
    candles = day_candles(breakout_close=3361.5)
    assert decide(ctx(candles, spread=0.55, median=None)) is None
    assert decide(ctx(candles, spread=0.45, median=None)) is not None


def test_stale_liquidity_blocks():
    candles = day_candles(breakout_close=3361.5)
    assert decide(ctx(candles, fresh=False)) is None


def test_stale_candles_block():
    candles = day_candles(breakout_close=3361.5)
    # last bar closed at 07:10; now is 20 min later
    assert decide(ctx(candles, now=f"{DAY}T07:30:00+00:00")) is None


def test_range_too_wide_skipped():
    candles = day_candles(breakout_close=3361.5)
    candles[0] = candle(f"{DAY}T00:00:00+00:00", 3355.0, 3380.0, 3354.0, 3355.0)
    assert decide(ctx(candles)) is None


def test_range_too_narrow_skipped():
    candles = day_candles(breakout_close=3361.5)
    for i in range(84):  # squeeze every Asia bar into a 0.40 range
        ts = candles[i]["ts"]
        candles[i] = candle(ts, 3355.0, 3355.2, 3354.8, 3355.0)
    assert decide(ctx(candles)) is None


# ---------------------------------------------------------------- guards


def test_open_position_blocks():
    candles = day_candles(breakout_close=3361.5)
    pos = [{"side": "BUY", "volume": 0.03, "sl": 3350.0, "tp": 3378.0}]
    assert decide(ctx(candles, positions=pos)) is None


def test_second_trade_same_day_blocks():
    candles = day_candles(breakout_close=3361.5)
    assert decide(ctx(candles, trades_today=1)) is None


def test_weekend_blocks():
    candles = day_candles(breakout_close=3361.5)
    sat = decide(ctx(candles, now="2026-11-21T07:05:30+00:00"))
    assert sat is None


# ---------------------------------------------------------------- sizing


def test_volume_below_minimum_skipped():
    candles = day_candles(breakout_close=3361.5)
    assert decide(ctx(candles, equity=1000.0)) is None  # 5 USD risk -> 0.004 lots


def test_volume_capped_at_hard_max():
    candles = day_candles(breakout_close=3361.5)
    intent = decide(ctx(candles, equity=100000.0))
    assert intent is not None
    assert intent.volume == pytest.approx(0.10)  # raw 0.43 capped at 0.10


def test_volume_respects_settings_max():
    candles = day_candles(breakout_close=3361.5)
    intent = decide(ctx(candles, equity=30000.0, max_volume=0.05))
    assert intent is not None
    assert intent.volume == pytest.approx(0.05)


# ---------------------------------------------------------------- purity


def test_decide_does_not_mutate_context():
    candles = day_candles(breakout_close=3361.5)
    context = ctx(candles)
    frozen = copy.deepcopy(context)
    decide(context)
    assert context == frozen


def test_every_intent_carries_sl_and_tp():
    for close in (3361.5, 3348.5):
        intent = decide(ctx(day_candles(breakout_close=close)))
        assert intent is not None
        assert intent.sl is not None and intent.tp is not None
        if intent.side == "BUY":
            assert intent.sl < 3361.5 < intent.tp
        else:
            assert intent.tp < 3348.5 < intent.sl


# ---------------------------------------------------------------- risk gate


def _risk_gate(order, settings, bid, ask):
    from app.risk import RiskContext, risk_gate

    return risk_gate(order, RiskContext(settings=settings, bid=bid, ask=ask,
                                        tick_age_s=0.1, daily_pnl=0.0,
                                        orders_last_minute=0))


def test_intent_passes_risk_gate():
    intent = decide(ctx(day_candles(breakout_close=3361.5)))
    order = {"symbol": intent.symbol, "side": intent.side, "volume": intent.volume,
             "sl": intent.sl, "tp": intent.tp}
    settings = {"allowed_symbols": ["XAUUSD"], "max_volume": 0.10, "max_spread": 0.50,
                "max_daily_drawdown": 100.0, "max_orders_per_min": 10}
    decision = _risk_gate(order, settings, bid=3361.0, ask=3361.35)
    assert decision.ok, decision.reasons


def test_intent_without_sl_rejected_by_risk_gate():
    # PRD: OrderIntent wajib SL; tanpa SL ditolak risk gate
    order = {"symbol": "XAUUSD", "side": "BUY", "volume": 0.03, "sl": None, "tp": 3378.0}
    settings = {"allowed_symbols": ["XAUUSD"], "max_volume": 0.10, "max_spread": 0.50,
                "max_daily_drawdown": 100.0, "max_orders_per_min": 10}
    decision = _risk_gate(order, settings, bid=3361.0, ask=3361.35)
    assert not decision.ok
    assert any("SL" in r for r in decision.reasons)


def test_broker_time_offsets():
    from datetime import datetime, timezone

    from strategies.broker_time import broker_utc_offset_hours

    tz = timezone.utc
    # Asumsi A1' (terukur 2026-11-22): server A1 = UTC+7 tetap, tanpa DST.
    assert broker_utc_offset_hours(datetime(2026, 1, 15, tzinfo=tz)) == 7
    assert broker_utc_offset_hours(datetime(2026, 6, 15, tzinfo=tz)) == 7
    assert broker_utc_offset_hours(datetime(2026, 11, 21, tzinfo=tz)) == 7


def test_stored_to_utc_conversion():
    from datetime import datetime, timedelta, timezone

    from strategies.broker_time import stored_to_utc

    # Konvensi fund2 (terukur): candle tersimpan di kunci true UTC
    # (jam server A1 = UTC+7 = tz sesi DB) -> konversi identitas.
    from zoneinfo import ZoneInfo

    stored = datetime(2026, 11, 20, 16, 55, tzinfo=ZoneInfo("Asia/Pontianak"))
    assert stored_to_utc(stored, db_tz_offset_h=7, broker_offset_h=7) == stored
    # Formula umum tetap terlindungi untuk sumber data jam-dinding lain.
    assert stored_to_utc(stored, 7, 2) == datetime(2026, 11, 20, 14, 55, tzinfo=timezone.utc)
    assert stored_to_utc(stored, 7, 3) == datetime(2026, 11, 20, 13, 55, tzinfo=timezone.utc)
