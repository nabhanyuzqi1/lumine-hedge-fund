"""Tests for the paper broker (fills, SL/TP/time exits, PnL)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from paper.broker import CloseEvent, PaperBroker, PaperPosition, unrealized

UTC = timezone.utc
NOW = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)


def buy_pos(entry=3361.35, sl=3350.0, tp=3378.75, volume=0.04) -> PaperPosition:
    return PaperPosition(order_id="o1", side="BUY", volume=volume, entry_price=entry,
                         sl=sl, tp=tp, opened_at=NOW)


def sell_pos(entry=3348.5, sl=3360.0, tp=3331.25, volume=0.04) -> PaperPosition:
    return PaperPosition(order_id="o2", side="SELL", volume=volume, entry_price=entry,
                         sl=sl, tp=tp, opened_at=NOW)


class FakeIntent:
    def __init__(self, side, volume=0.04, sl=3350.0, tp=3378.75, strategy="london_breakout"):
        self.side = side
        self.volume = volume
        self.sl = sl
        self.tp = tp
        self.strategy = strategy


# ---------------------------------------------------------------- fill


def test_fill_buy_at_ask():
    pos = PaperBroker().fill(FakeIntent("BUY"), bid=3361.0, ask=3361.35, now=NOW)
    assert pos.entry_price == 3361.35
    assert pos.side == "BUY" and pos.volume == 0.04
    assert pos.sl == 3350.0 and pos.tp == 3378.75


def test_fill_sell_at_bid():
    pos = PaperBroker().fill(FakeIntent("SELL"), bid=3348.5, ask=3348.9, now=NOW)
    assert pos.entry_price == 3348.5


def test_fill_rejects_missing_sl():
    intent = FakeIntent("BUY", sl=None)
    with pytest.raises(ValueError):
        PaperBroker().fill(intent, bid=1, ask=1, now=NOW)


# ---------------------------------------------------------------- on_price


def test_buy_sl_hit():
    event = PaperBroker().on_price(buy_pos(), bid=3349.9, ask=3350.3, now=NOW)
    assert event.reason == "SL"
    assert event.price == 3350.0
    assert event.profit == pytest.approx((3350.0 - 3361.35) * 100 * 0.04, abs=0.01)


def test_buy_tp_hit():
    event = PaperBroker().on_price(buy_pos(), bid=3378.80, ask=3379.1, now=NOW)
    assert event.reason == "TP"
    assert event.profit == pytest.approx((3378.75 - 3361.35) * 100 * 0.04, abs=0.01)


def test_buy_no_exit_inside_range():
    assert PaperBroker().on_price(buy_pos(), bid=3365.0, ask=3365.3, now=NOW) is None


def test_sell_sl_hit():
    event = PaperBroker().on_price(sell_pos(), bid=3359.7, ask=3360.1, now=NOW)
    assert event.reason == "SL"
    assert event.profit == pytest.approx((3348.5 - 3360.0) * 100 * 0.04, abs=0.01)


def test_sell_tp_hit():
    event = PaperBroker().on_price(sell_pos(), bid=3330.8, ask=3331.2, now=NOW)
    assert event.reason == "TP"


def test_sl_wins_when_both_hit_same_tick():
    event = PaperBroker().on_price(buy_pos(), bid=3340.0, ask=3400.0, now=NOW)
    assert event.reason == "SL"


def test_unrealized_matches_closed_pnl():
    pos = buy_pos()
    assert unrealized(pos, bid=3366.35, ask=3366.7) == pytest.approx((3366.35 - 3361.35) * 4, abs=0.01)


# ---------------------------------------------------------------- time exit


def test_time_exit_at_16_utc():
    broker = PaperBroker(force_close_hour_utc=16)
    event = broker.on_price(buy_pos(), bid=3365.0, ask=3365.3,
                            now=datetime(2026, 11, 23, 16, 0, 30, tzinfo=UTC))
    assert event.reason == "TIME"
    assert event.price == 3365.0


def test_no_time_exit_before_16_utc():
    broker = PaperBroker(force_close_hour_utc=16)
    assert broker.on_price(buy_pos(), bid=3365.0, ask=3365.3,
                           now=datetime(2026, 11, 23, 15, 59, tzinfo=UTC)) is None


# ---------------------------------------------------------------- on_bar


def test_on_bar_sl_first_when_both_levels_touched():
    broker = PaperBroker()
    event = broker.on_bar(buy_pos(), bar_open=3361.0, bar_high=3380.0, bar_low=3345.0,
                          bar_close=3350.0, spread=0.4, now=NOW)
    assert event.reason == "SL"
    # bid = low - half = 3344.8 <= SL 3350 -> exit at SL minus slippage (0 default)
    assert event.price == 3350.0


def test_on_bar_tp_hit():
    broker = PaperBroker()
    event = broker.on_bar(buy_pos(), bar_open=3361.0, bar_high=3380.0, bar_low=3360.0,
                          bar_close=3375.0, spread=0.4, now=NOW)
    assert event.reason == "TP"
    assert event.price == 3378.75


def test_on_bar_gap_through_sl_fills_at_open():
    broker = PaperBroker()
    event = broker.on_bar(buy_pos(), bar_open=3340.0, bar_high=3345.0, bar_low=3338.0,
                          bar_close=3339.0, spread=0.4, now=NOW)
    assert event.reason == "SL"
    assert event.price == pytest.approx(3340.0 - 0.2)  # open - half spread


def test_on_bar_time_exit_with_costs():
    broker = PaperBroker(force_close_hour_utc=16)
    event = broker.on_bar(buy_pos(), bar_open=3365.0, bar_high=3366.0, bar_low=3364.0,
                          bar_close=3365.0, spread=0.4, slippage=0.1,
                          now=datetime(2026, 11, 23, 16, 5, tzinfo=UTC))
    assert event.reason == "TIME"
    assert event.price == pytest.approx(3365.0 - 0.2 - 0.1)
    assert event.profit == pytest.approx((event.price - 3361.35) * 100 * 0.04, abs=0.01)


# ---------------------------------------------------------------- multipair (t_f2mp3)


def btc_pos(entry=60300.0, sl=59900.0, tp=61000.0, volume=0.08) -> PaperPosition:
    """Posisi BTCUSD: 1 lot = 1 BTC (t_f2mp1) -> 1 USD harga = 1 USD/lot."""
    return PaperPosition(order_id="btc1", side="BUY", volume=volume, entry_price=entry,
                         sl=sl, tp=tp, opened_at=NOW, strategy="btc_range_breakout",
                         contract_size=1.0)


def test_btc_pnl_uses_contract_size_one():
    broker = PaperBroker(force_close_hour_utc=None)
    event = broker.on_price(btc_pos(), bid=60500.0, ask=60520.0, now=NOW)
    assert event is None  # di antara SL/TP
    event = broker.on_price(btc_pos(), bid=61000.0, ask=61020.0, now=NOW)
    assert event.reason == "TP"
    # (61000 - 60300) x 1.0 x 0.08 = 56 USD (bukan x 100)
    assert event.profit == pytest.approx(56.0)


def test_btc_default_contract_is_xau_compat():
    """Posisi lama tanpa contract_size tetap 100 oz/lot (perilaku lama utuh)."""
    pos = buy_pos()
    assert pos.contract_size == 100.0
    broker = PaperBroker()
    event = broker.on_price(pos, bid=3378.75, ask=3379.0, now=NOW)
    assert event.reason == "TP"
    assert event.profit == pytest.approx((3378.75 - 3361.35) * 100 * 0.04)


def test_no_time_exit_when_disabled():
    """Strategi 24/7 (BTC): force_close_hour_utc=None -> tanpa TIME exit."""
    broker = PaperBroker(force_close_hour_utc=None)
    assert broker.on_price(btc_pos(), bid=60500.0, ask=60520.0,
                           now=datetime(2026, 11, 24, 16, 0, 30, tzinfo=UTC)) is None
    assert broker.on_bar(btc_pos(), bar_open=60500.0, bar_high=60510.0,
                         bar_low=60490.0, bar_close=60505.0, spread=40.0,
                         now=datetime(2026, 11, 24, 16, 5, tzinfo=UTC)) is None
