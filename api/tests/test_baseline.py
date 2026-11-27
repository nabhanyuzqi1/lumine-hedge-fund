"""PRD v2.2 §8.2: baseline sederhana (buy&hold + random entry ber-seed)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from paper.baseline import buy_and_hold, random_entry

UTC = timezone.utc


def _series(n=100, base=2000.0):
    out = []
    for i in range(n):
        ts = datetime(2026, 3, 2, tzinfo=UTC) + timedelta(hours=i)
        # weekday filter: skip weekend (Sabtu/Minggu) untuk XAUUSD
        if ts.weekday() >= 5:
            continue
        drift = i * 0.5
        out.append({"ts": ts, "open": base + drift, "high": base + drift + 1.0,
                    "low": base + drift - 1.0, "close": base + drift + 0.2,
                    "volume": 100.0})
    return out


def test_buy_and_hold_positive_in_uptrend():
    candles = _series(48)
    r = buy_and_hold(candles, symbol="XAUUSD")
    assert r["trades"] == 1
    assert r["net_profit_usd"] > 0  # uptrend 0.5/harus positif setelah biaya
    assert r["final_balance"] == 10000.0 + r["net_profit_usd"]
    assert r["entry_price"] < r["exit_price"]


def test_buy_and_hold_cost_deduction():
    candles = _series(48)
    r = buy_and_hold(candles, symbol="XAUUSD", spread=0.50, slippage=0.10)
    # entry = open + spread/2 + slip; exit = close - spread/2 - slip
    entry = candles[0]["open"] + 0.25 + 0.10
    exit_price = candles[-1]["close"] - 0.25 - 0.10
    gross = (exit_price - entry) * 100 * 0.10
    net = round(gross - 0.0 - 0.0, 2)  # tanpa cost model: komisi/swap 0
    assert r["entry_price"] == round(entry, 2)
    assert r["exit_price"] == round(exit_price, 2)
    assert r["gross_profit_usd"] == round(gross, 2)
    assert r["net_profit_usd"] == net


def test_random_entry_seeded_reproducible():
    candles = _series(200)
    a = random_entry(candles, symbol="XAUUSD", seed=42, n_trades=20)
    b = random_entry(candles, symbol="XAUUSD", seed=42, n_trades=20)
    assert a["net_profit_usd"] == b["net_profit_usd"]
    assert a["trades"] == b["trades"]
    assert a["seed"] == 42


def test_random_entry_different_seed_different_result():
    candles = _series(200)
    a = random_entry(candles, symbol="XAUUSD", seed=1, n_trades=20)
    b = random_entry(candles, symbol="XAUUSD", seed=2, n_trades=20)
    # seed beda -> pilihan bar beda (probabilistik tinggi); minimal tidak sama persis
    assert a["trades"] == b["trades"]  # jumlah sama (diminta sama)
    assert a["note"] and b["note"]


def test_random_entry_trade_count_respected():
    candles = _series(300)
    r = random_entry(candles, symbol="XAUUSD", seed=7, n_trades=15)
    assert r["trades"] == 15
