"""Test Layer 0 fakta deterministik + wiring ke specialist/synthesizer (t_2a1fbf01).

Fokus: fakta TIDAK boleh mengarang angka (data kurang = insufficient_data/null),
dan specialist/synthesizer menerima angka nyata (harga, ATR, akun) alih-alih
menerima candle mentah dengan field yang tidak ada (penyebab keputusan "null"
pada siklus 07:12).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app import llm_agent_loop, llm_facts, llm_specialists

NOW = datetime(2026, 11, 26, 7, 5, tzinfo=timezone.utc)


def _candles(n: int, start: float = 3500.0, step: float = 0.5) -> list[dict]:
    rows: list[dict] = []
    price = start
    for i in range(n):
        ts = datetime(2026, 11, 26, 3, 0, tzinfo=timezone.utc).timestamp() + i * 300
        rows.append({
            "ts": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
            "open": price,
            "high": price + step,
            "low": price - step,
            "close": price + step / 2,
        })
        price += step
    return rows


# ── indikator ──────────────────────────────────────────────────────────────
def test_indicators_on_uptrend():
    facts = llm_facts.timeframe_facts(_candles(260), recent_bars=5)
    assert facts["status"] == "ok"
    assert facts["ema_stack"] == "bullish_stack"
    assert facts["ema20"] and facts["ema50"] and facts["ema200"]
    assert facts["ema20"] > facts["ema200"]
    assert facts["ema20_slope_pct"] > 0
    assert facts["rsi14"] == pytest.approx(100.0, abs=0.01)
    assert facts["atr14"] is not None and facts["atr14"] > 0
    assert facts["atr_pct"] > 0
    assert len(facts["recent_bars"]) == 5
    assert facts["range_high"] > facts["range_low"]


def test_insufficient_data_is_not_zero():
    facts = llm_facts.timeframe_facts(_candles(5))
    assert facts["status"] == "ok"          # 5 candle cukup untuk close/range
    assert facts["ema200"] is None          # tetapi BUKAN angka karangan
    assert facts["rsi14"] is None
    assert facts["atr14"] is None
    assert facts["ema_stack"] == "unknown"


def test_empty_candles_marked_insufficient():
    facts = llm_facts.timeframe_facts([])
    assert facts == {"status": "insufficient_data", "candles": 0}


# ── perakitan fakta ────────────────────────────────────────────────────────
def _ctx_with_symbol() -> dict:
    return {
        "now_utc": NOW.isoformat(timespec="seconds"),
        "session": {"name": "asia"},
        "halted": False,
        "calendar": {
            "status": "ok",
            "source": "faireconomy.media",
            "next_high_impact_utc": "2026-11-26T08:30:00+00:00",
            "minutes_to_next_high_impact": 85.0,
            "events": [{"title": "Core PCE", "time_utc": "2026-11-26T08:30:00+00:00",
                        "impact": "High", "forecast": "0.2%", "previous": "0.3%"}],
        },
        "sentiment": {"status": "ok", "value": 41},
        "fundamental": {"status": "stale", "dxy": {"value": 103.2}},
        "symbols": {
            "XAUUSD": {
                "candles": {tf: _candles(260) for tf in llm_facts.TF_ORDER},
                "market_structure": {"M5": {"structure": {"trend": "bullish"}}},
                "liquidity": {"spread_avg": 0.21, "tick_count": 900},
                "fib_zones": [{"direction": "UP", "levels": {"0.618": 3480.0}}],
                "open_positions": [],
                "llm_positions": [],
            }
        },
    }


def test_build_facts_wires_macro_and_symbols():
    facts = llm_facts.build_facts(_ctx_with_symbol(),
                                  {"account": {"daily_drawdown_pct": 0.4}}, NOW)
    assert facts["facts_version"] == llm_facts.FACTS_VERSION
    assert facts["symbols"]["XAUUSD"]["status"] == "ok"
    assert facts["symbols"]["XAUUSD"]["price"] is not None
    assert facts["symbols"]["XAUUSD"]["candle_age_min"] is not None
    assert facts["macro"]["calendar"]["minutes_to_next_high_impact"] == 85.0
    assert facts["macro"]["calendar"]["events"][0]["title"] == "Core PCE"
    assert facts["portfolio"]["account"]["daily_drawdown_pct"] == 0.4


def test_symbol_facts_spread_dan_levels():
    """Spread/ATR dan level S/R dihitung server, bukan dikarang LLM."""
    ctx = _ctx_with_symbol()
    ctx["symbols"]["XAUUSD"]["market_structure"] = {
        "M5": {"structure": {"trend": "bullish"},
               "nearest_sr": {"support": 3495.0, "resistance": 3505.0}}}
    facts = llm_facts.build_facts(ctx, {"account": {}}, NOW)
    sym = facts["symbols"]["XAUUSD"]
    spread = sym["spread"]
    assert spread["avg"] == pytest.approx(0.21)
    assert spread["atr_m5"] is not None and spread["atr_m5"] > 0
    assert spread["ratio"] is not None
    assert spread["threshold"] == llm_facts.SPREAD_ATR_THRESHOLD
    levels = sym["levels"]
    assert levels["support"] == 3495.0
    assert levels["resistance"] == 3505.0
    assert levels["buffer"] is not None
    assert levels["sl_long"] < 3495.0          # buffer di bawah support
    assert levels["sl_short"] > 3505.0         # buffer di atas resistance
    assert isinstance(levels["squeeze"], bool)


def test_portfolio_slice_membawa_atr_dan_spread():
    """Irisan portofolio wajib membawa atr_m5 + spread (bukan hanya posisi)."""
    facts = llm_facts.build_facts(_ctx_with_symbol(), {"account": {}}, NOW)
    sl = llm_specialists._slice_raw({"facts": facts}, "portfolio", "XAUUSD")
    sym = sl["symbols"]["XAUUSD"]
    assert sym["atr_m5"] is not None and sym["atr_m5"] > 0
    assert sym["spread"]["threshold"] == llm_facts.SPREAD_ATR_THRESHOLD
    assert "llm_positions" in sym


def test_build_facts_never_raises_on_garbage():
    facts = llm_facts.build_facts({"symbols": {"XAUUSD": None, "BTCUSD": "rusak"}}, None, NOW)
    assert facts["symbols"]["XAUUSD"]["status"] == "insufficient_data"
    assert facts["symbols"]["BTCUSD"]["status"] == "insufficient_data"
    assert facts["portfolio"] == {}


# ── irisan per peran ───────────────────────────────────────────────────────
def _ctx_with_facts() -> dict:
    ctx = _ctx_with_symbol()
    ctx["facts"] = llm_facts.build_facts(ctx, {
        "account": {"equity_start_usd": 10000.0, "daily_drawdown_pct": 0.4},
        "risk_limits": {"exposure_max_usd": 30000.0},
        "legs": [{"symbol": "BTCUSD", "is_llm": True}],
    }, NOW)
    return ctx


def test_technical_slice_gets_facts_not_raw_candles():
    ctx = _ctx_with_facts()
    tech = llm_specialists._slice(ctx, "technical", "XAUUSD")
    payload = tech["symbols"]["XAUUSD"]
    assert "candles" not in payload
    assert "timeframes" in payload and "structure" in payload
    assert payload["timeframes"]["M5"]["ema20"] is not None
    assert payload["liquidity"]["spread_avg"] == 0.21


def test_macro_and_sentiment_slice_use_facts():
    ctx = _ctx_with_facts()
    macro = llm_specialists._slice(ctx, "macro", "XAUUSD")
    assert macro["macro"]["calendar"]["minutes_to_next_high_impact"] == 85.0
    sentiment = llm_specialists._slice(ctx, "sentiment", "XAUUSD")
    assert sentiment["sentiment"] == ctx["facts"]["macro"]["sentiment"]
    assert sentiment["fundamental"] == ctx["facts"]["macro"]["fundamental"]


def test_portfolio_slice_has_account_and_limits():
    ctx = _ctx_with_facts()
    portfolio = llm_specialists._slice(ctx, "portfolio", "XAUUSD")
    assert portfolio["account"]["equity_start_usd"] == 10000.0
    assert portfolio["guards"]["exposure_max_usd"] == 30000.0
    assert "legs" not in portfolio["portfolio"]


def test_snapshot_has_price_and_account_no_candles():
    ctx = _ctx_with_facts()
    snap = llm_specialists._snapshot(ctx, "XAUUSD")
    assert snap["facts"]["price"] is not None
    assert snap["account"]["equity_start_usd"] == 10000.0
    encoded = json.dumps(snap, default=str)
    # Tidak ada array candle OHLC mentah: hanya jumlahnya (structure["M5"]["candles"]).
    assert '"recent_bars"' in encoded
    assert len(encoded) < 12000, f"snapshot terlalu besar: {len(encoded)} char"
    assert snap["other_positions"][0]["symbol"] == "BTCUSD"


# ── portofolio deterministik ───────────────────────────────────────────────
class _FakeConn:
    pass


@pytest.mark.asyncio
async def test_collect_portfolio_computes_exposure_and_worst_case(monkeypatch):
    async def fake_fetchone(conn, query, params=None):
        return {"pnl": -120.0}

    monkeypatch.setattr(llm_agent_loop, "fetchone", fake_fetchone)
    settings = {
        "initial_balance": 10000.0,
        "symbol_specs": {"XAUUSD": {"tick_size": 0.01, "tick_value": 1.0,
                                    "slippage": 0.35, "commission_per_lot_usd": 7.0}},
        "llm_risk": {"max_orders_per_day": 10, "max_orders_per_min": 2},
    }
    ctx = {
        "risk_limits": {"exposure_max_usd": 30000.0, "daily_drawdown_halt_pct": 3.0},
        "symbols": {
            "XAUUSD": {
                "open_positions": [{"ticket": "t1", "side": "BUY", "volume": 0.1,
                                    "open_price": 3500.0, "sl": 3490.0, "tp": 3520.0,
                                    "profit": -12.5, "is_llm": True}],
                "llm_positions": [{"price_now": 3550.0, "is_llm": True}],
            }
        },
    }
    out = await llm_agent_loop._collect_portfolio(_FakeConn(), settings, ctx)
    assert out["equity_start_usd"] == 10000.0
    assert out["daily_pnl_usd"] == -120.0
    assert out["daily_drawdown_pct"] == 1.2
    assert out["open_positions"] == 1
    assert out["exposure_usd"] == pytest.approx(35500.0, rel=1e-6)
    # (|3500-3490| + 0.35) * 100 * 0.1 + 7 * 0.1
    assert out["worst_case_loss_usd"] == pytest.approx(104.2, rel=1e-6)
    assert out["account"]["exposure_pct"] == pytest.approx(355.0, rel=1e-6)
    assert out["risk_limits"]["max_orders_per_day"] == 10
    assert out["status"] == "ok"


@pytest.mark.asyncio
async def test_collect_portfolio_flags_missing_sl(monkeypatch):
    async def fake_fetchone(conn, query, params=None):
        return {"pnl": 0.0}

    monkeypatch.setattr(llm_agent_loop, "fetchone", fake_fetchone)
    settings = {"initial_balance": 10000.0, "symbol_specs": {"BTCUSD": {
        "tick_size": 0.01, "tick_value": 0.01, "slippage": 5.0}}}
    ctx = {"risk_limits": {}, "symbols": {"BTCUSD": {
        "open_positions": [{"ticket": "b1", "side": "SELL", "volume": 0.1,
                            "open_price": 68000.0, "sl": None, "is_llm": True}],
        "llm_positions": []}}}
    out = await llm_agent_loop._collect_portfolio(_FakeConn(), settings, ctx)
    assert out["worst_case_unknown_legs"] == 1
    assert out["status"] == "partial"
    assert out["exposure_usd"] == pytest.approx(68000.0 * 1.0 * 0.1, rel=1e-6)


# ── wiring pipeline + audit ────────────────────────────────────────────────
class _Resp:
    status_code = 200

    def json(self):
        return {"to_status": "AGENT_HOLD"}


class _FakeHttp:
    def __init__(self):
        self.calls = []

    async def post(self, url, json=None, headers=None, cookies=None, **kwargs):
        self.calls.append((url, json))
        return _Resp()


@pytest.mark.asyncio
async def test_pipeline_reports_missing_and_uses_facts(monkeypatch):
    ctx = _ctx_with_facts()
    seen = {}

    async def fake_run_specialists(http, ctx_in, *, symbol, base, key, model,
                                   on_update=None, **kwargs):
        seen["has_facts"] = isinstance(ctx_in.get("facts"), dict)
        return {
            "technical": {"state": "ok", "data": {"confidence": 0.6}, "model": model,
                          "latency_ms": 1000, "prompt_tokens": 10, "completion_tokens": 5},
            "macro": {"state": "timeout", "error": "timeout > 45s", "model": model,
                      "latency_ms": 45000},
            "sentiment": {"state": "ok", "data": {"confidence": 0.3}, "model": model,
                          "latency_ms": 800},
            "portfolio": {"state": "ok", "data": {"confidence": 0.9}, "model": model,
                          "latency_ms": 700},
        }

    async def fake_synthesize(http, ctx_in, evidence, *, symbol, base, key, model,
                              timeout_s=None, **kwargs):
        return {"data": {"kind": "hold", "symbol": None, "side": None, "volume": None,
                         "sl": None, "tp": None, "reasoning": "uji", "confidence": 0.5},
                "model": model, "latency_ms": 2000, "prompt_tokens": 900,
                "completion_tokens": 60, "missing": ["macro"]}

    async def fake_evidence(http, auth, cycle_id, role, res, symbol):
        return None

    monkeypatch.setattr(llm_specialists, "run_specialists", fake_run_specialists)
    monkeypatch.setattr(llm_specialists, "synthesize", fake_synthesize)
    monkeypatch.setattr(llm_agent_loop, "_post_evidence", fake_evidence)
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.local/v1")
    monkeypatch.setenv("LLM_API_KEY", "k")
    result = await llm_agent_loop._run_parallel_pipeline(
        _FakeHttp(), None, ctx, {"specialist": "s", "synth": "y", "fallback": "f"},
        "cycle-1", "XAUUSD")
    assert seen["has_facts"] is True
    assert result["evidence_missing"] == ["macro"]
    assert result["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_submit_decision_audits_evidence_and_missing(monkeypatch):
    monkeypatch.setenv("LLM_API_BASE", "http://api.local")
    http = _FakeHttp()
    llm_result = {
        "decision": {"kind": "hold", "symbol": None, "side": None, "volume": None,
                     "sl": None, "tp": None, "reasoning": "uji audit", "confidence": 0.4},
        "model": "lucif", "prompt_tokens": 100, "completion_tokens": 20,
        "latency_ms": 26000,
        "evidence": {
            "technical": {"state": "ok", "model": "lucif-flash", "latency_ms": 21000},
            "macro": {"state": "timeout", "model": "lucif-flash", "latency_ms": 45000,
                      "error": "timeout"},
            "sentiment": {"state": "ok", "model": "lucif-flash", "latency_ms": 6000},
            "portfolio": {"state": "ok", "model": "lucif-flash", "latency_ms": 5000},
        },
        "evidence_missing": ["macro"],
    }
    await llm_agent_loop._submit_decision(
        http, {"csrf": "x", "cookies": {}}, "cycle-2", llm_result, _ctx_with_facts())
    url, body = http.calls[-1]
    assert url.endswith("/llm-agent/decisions")
    assert body["evidence"]["macro"]["state"] == "timeout"
    assert set(body["evidence"]) == set(llm_specialists.ROLES)
    assert body["evidence_missing"] == ["macro"]
