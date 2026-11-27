"""Unit test harness evaluasi gerbang paper (scripts/eval_gate_paper.py).

Murni fungsi — tanpa DB. Kriteria gerbang dideklarasikan di
docs/QA_F2LLM4_kriteria_gerbang.md.
"""
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import eval_gate_paper as eg  # noqa: E402


def _ts(day: int, hour: int):
    return datetime(2026, 12, day, hour, tzinfo=timezone.utc)


# ---------------------------------------------------------------- profit factor

def test_pf_mixed():
    assert eg.profit_factor([100.0, -50.0, 30.0, -20.0]) == pytest.approx(130.0 / 70.0)


def test_pf_no_loss_is_inf():
    assert eg.profit_factor([10.0, 20.0]) == float("inf")


def test_pf_empty_and_zero():
    assert eg.profit_factor([]) is None
    assert eg.profit_factor([0.0, 0.0]) is None


# ---------------------------------------------------------------- max drawdown

def test_dd_basic():
    eq = [100.0, 120.0, 90.0, 110.0, 80.0]
    dd_usd, dd_pct = eg.max_drawdown(eq)
    assert dd_usd == pytest.approx(40.0)  # peak 120 -> 80
    assert dd_pct == pytest.approx(100.0 / 3.0, abs=0.01)  # dibulatkan 2 desimal


def test_dd_monotonic_up():
    assert eg.max_drawdown([100.0, 110.0, 120.0]) == (0.0, 0.0)


def test_dd_empty():
    assert eg.max_drawdown([]) == (0.0, 0.0)


# ---------------------------------------------------------------- working days

def test_working_days_excludes_weekend():
    # 2026-12-05 Sabtu, 2026-12-06 Minggu
    days = eg.working_days([date(2026, 12, 4), date(2026, 12, 5), date(2026, 12, 6), date(2026, 12, 7)])
    assert days == [date(2026, 12, 4), date(2026, 12, 7)]


def test_working_days_dedup():
    assert eg.working_days([date(2026, 12, 4)] * 3) == [date(2026, 12, 4)]


# ---------------------------------------------------------------- session dist

def _trade(day, hour, profit, symbol="XAUUSD"):
    return {"symbol": symbol, "side": "BUY", "volume": 0.01, "status": "CLOSED",
            "profit": profit, "opened_at": _ts(day, hour), "closed_at": _ts(day, hour + 1)}


def test_session_distribution_uses_session_of():
    trades = [_trade(1, 2, 10.0), _trade(1, 8, -5.0), _trade(1, 13, 7.0), _trade(1, 17, -2.0)]
    dist = eg.session_distribution(trades)
    assert dist["asia"]["trades"] == 1 and dist["asia"]["net"] == 10.0
    assert dist["london"]["trades"] == 1 and dist["london"]["net"] == -5.0
    assert dist["london_newyork"]["trades"] == 1 and dist["london_newyork"]["net"] == 7.0
    assert dist["newyork"]["trades"] == 1 and dist["newyork"]["net"] == -2.0


# ---------------------------------------------------------------- decision ratio

def test_decision_ratio():
    dec = [{"decision": "order"}, {"decision": "close"}, {"decision": "hold"}, {"decision": "invalid"}]
    r = eg.decision_ratio(dec)
    assert r["total"] == 4 and r["valid"] == 2 and r["hold"] == 1 and r["invalid"] == 1
    assert r["valid_ratio"] == 0.5


def test_decision_ratio_empty_is_none():
    assert eg.decision_ratio([]) is None


# ---------------------------------------------------------------- evaluate E2E

def _closed_trades(profits, day=1, hour=8):
    return [_trade(day, hour + i, p) for i, p in enumerate(profits)]


def test_evaluate_lulus():
    # 25 hari kerja trade, 120 trade, PF 2.0, DD kecil
    trades = []
    for d in range(1, 26):  # 25 hari (Des 1-25; Sabtu/Minggu tetap dihitung trade, hari kerja dihitung terpisah)
        for i in range(5):
            trades.append(_trade(d, 8 + i % 6, 20.0 if (d + i) % 3 else -10.0))
    # pastikan >= 20 hari kerja: Des 2026 -> Senin-Jumat 1-25 = 18 hari kerja; tambah 28-31
    for d in (28, 29, 30, 31):
        for i in range(2):
            trades.append(_trade(d, 8, 20.0))
    res = eg.evaluate(trades, None, 10000.0, commission_per_lot=0.0)
    assert res["metrics"]["trades"] == 133
    assert res["metrics"]["working_days"] >= 20
    assert res["metrics"]["profit_factor"] > 1.3
    assert res["gate"]["profit_factor"]["pass"] is True
    assert res["gate"]["duration"]["pass"] is True
    assert res["gate"]["volume"]["pass"] is True
    assert res["verdict"] == "LULUS"


def test_evaluate_gagal_pf_dan_dd():
    trades = _closed_trades([-50.0] * 10 + [10.0] * 5, day=1)
    res = eg.evaluate(trades, None, 1000.0, commission_per_lot=0.0,
                      thresholds={"min_working_days": 0, "min_trades": 0})
    assert res["metrics"]["profit_factor"] == pytest.approx(50.0 / 500.0)
    assert res["gate"]["profit_factor"]["pass"] is False
    assert res["gate"]["max_drawdown"]["pass"] is False
    assert res["verdict"] == "GAGAL"


def test_evaluate_data_belum_cukup():
    res = eg.evaluate([], None, 10000.0, commission_per_lot=0.0,
                      thresholds={"min_working_days": 0, "min_trades": 0})
    assert res["verdict"] == "DATA_BELUM_CUKUP"


def test_evaluate_durasi_belum_cukup_bukan_gagal():
    # PF dan DD bagus tapi baru 1 hari kerja / 1 trade -> DATA_BELUM_CUKUP
    res = eg.evaluate(_closed_trades([5.0]), None, 10000.0, commission_per_lot=0.0)
    assert res["verdict"] == "DATA_BELUM_CUKUP"


def test_evaluate_komisi_dipotong():
    # 1 trade profit gross 10, volume 1 lot, komisi 7 -> net 3
    trades = [{"symbol": "XAUUSD", "side": "BUY", "volume": 1.0, "status": "CLOSED",
               "profit": 10.0, "opened_at": _ts(1, 8), "closed_at": _ts(1, 9)}]
    res = eg.evaluate(trades, None, 1000.0, commission_per_lot=7.0,
                      thresholds={"min_working_days": 0, "min_trades": 0})
    assert res["metrics"]["net_profit"] == pytest.approx(3.0)
    assert res["metrics"]["ending_equity"] == pytest.approx(1003.0)


def test_evaluate_hari_kerja_dari_keputusan_hold():
    # trade hanya 1 hari, tapi hold decisions mencakup 22 hari kerja
    trades = _closed_trades([5.0], day=1)
    dec = [{"decision": "hold", "ts": _ts(d, 10)} for d in range(1, 32)]
    res = eg.evaluate(trades, dec, 10000.0, commission_per_lot=0.0,
                      thresholds={"min_working_days": 20, "min_trades": 1})
    assert res["metrics"]["working_days"] >= 20
    assert res["metrics"]["decisions"]["hold"] == 31
    assert res["verdict"] == "LULUS"


def test_render_markdown_tanpa_decisions():
    res = eg.evaluate(_closed_trades([5.0, -2.0]), None, 10000.0, commission_per_lot=0.0,
                      thresholds={"min_working_days": 0, "min_trades": 0})
    md = eg.render_markdown(res)
    assert "N/A (audit keputusan belum tersedia" in md
    assert "Verdict gerbang" in md


# ---------------------------------------------------------------- sumber orders

def test_close_profit_from_prices_xauusd_sell():
    # SELL 0.10 @3633.87 -> 3629.00 = +48.7 (match DEAL_PROFIT broker)
    assert eg.close_profit_from_prices("XAUUSD", "SELL", 0.10, 3633.87, 3629.00, 100.0) == 48.70


def test_close_profit_from_prices_buy():
    assert eg.close_profit_from_prices("XAUUSD", "BUY", 0.03, 3629.22, 3623.13, 100.0) == -18.27


def test_close_profit_from_prices_btcusd_contract_1():
    # BTCUSD contract_size 1: BUY 0.01 @97000 -> 97100 = +1.0
    assert eg.close_profit_from_prices("BTCUSD", "BUY", 0.01, 97000.0, 97100.0, 1.0) == 1.0


def test_close_profit_from_prices_harga_tidak_lengkap():
    assert eg.close_profit_from_prices("XAUUSD", "SELL", 0.1, None, 3600.0, 100.0) is None
    assert eg.close_profit_from_prices("XAUUSD", "SELL", 0.1, 3600.0, None, 100.0) is None


def test_orders_row_to_trade_reported_nonzero():
    row = {"symbol": "XAUUSD", "side": "SELL", "volume": 0.1, "sl": None, "tp": None,
           "status": "FILLED_THEN_CLOSED", "price_filled": 3633.87,
           "created_at": _ts(1, 8), "resolved_at": _ts(1, 9),
           "close_payload": {"profit": 48.7, "close_price": 3629.0}}
    t = eg.orders_row_to_trade(row, 100.0)
    assert t["profit"] == 48.7 and t["profit_source"] == "reported"
    assert t["status"] == "CLOSED"


def test_orders_row_to_trade_profit_nol_dihitung_dari_harga():
    # bug EA: CLOSE command selalu lapor profit 0.0 -> dihitung dari harga
    row = {"symbol": "XAUUSD", "side": "SELL", "volume": 0.05, "sl": None, "tp": None,
           "status": "FILLED_THEN_CLOSED", "price_filled": 3630.09,
           "created_at": _ts(1, 8), "resolved_at": _ts(1, 9),
           "close_payload": {"profit": 0.0, "close_price": 3633.2}}
    t = eg.orders_row_to_trade(row, 100.0)
    assert t["profit"] == -15.55
    assert t["profit_source"] == "computed"


def test_orders_row_to_trade_profit_nol_tanpa_harga_tetap_unknown():
    row = {"symbol": "XAUUSD", "side": "BUY", "volume": 0.02, "sl": None, "tp": None,
           "status": "FILLED_THEN_CLOSED", "price_filled": None,
           "created_at": _ts(1, 8), "resolved_at": _ts(1, 9),
           "close_payload": {"profit": 0.0}}
    t = eg.orders_row_to_trade(row, 100.0)
    assert t["profit"] == 0.0 and t["profit_source"] == "unknown"


def test_orders_row_to_trade_status_failed_tidak_dianggap_closed():
    row = {"symbol": "XAUUSD", "side": "BUY", "volume": 0.02, "sl": None, "tp": None,
           "status": "FAILED", "price_filled": None,
           "created_at": _ts(1, 8), "resolved_at": _ts(1, 9),
           "close_payload": None}
    t = eg.orders_row_to_trade(row, 100.0)
    assert t["status"] == "FAILED"
    res = eg.evaluate([t], None, 10000.0, commission_per_lot=0.0,
                      thresholds={"min_working_days": 0, "min_trades": 0})
    assert res["metrics"]["trades"] == 0


def test_evaluate_dengan_computed_profit_dilaporkan():
    trades = [{"symbol": "XAUUSD", "side": "SELL", "volume": 0.05, "status": "CLOSED",
               "profit": -15.55, "profit_source": "computed",
               "opened_at": _ts(1, 8), "closed_at": _ts(1, 9)}]
    res = eg.evaluate(trades, None, 10000.0, commission_per_lot=0.0,
                      thresholds={"min_working_days": 0, "min_trades": 0})
    assert res["metrics"]["profit_source_counts"] == {"computed": 1}
    md = eg.render_markdown(res)
    assert "Sumber profit" in md and "computed: 1" in md


def test_fetch_decisions_db_parsing():
    class FakeCursor:
        def __init__(self):
            self.rows = [({"kind": "order", "symbol": "XAUUSD"}, _ts(1, 8)),
                         ({"kind": "hold", "symbol": None}, _ts(1, 9))]

        def execute(self, q, params):
            pass

        def fetchall(self):
            return self.rows

    class FakeConn:
        def execute(self, q, params=None):
            return FakeCursor()

    dec = eg.fetch_decisions_db(FakeConn(), None, None)
    assert [d["decision"] for d in dec] == ["order", "hold"]
    assert dec[0]["symbol"] == "XAUUSD"
    ratio = eg.decision_ratio(dec)
    assert ratio["valid"] == 1 and ratio["hold"] == 1 and ratio["total"] == 2
