"""Contract tests for the strategy template (Fund2 PRD 5.3).

Run standalone:
    cd ~/fund2/strategies/_template && ../../api/.venv/bin/python -m pytest -q test_strategy.py

These pass against the untouched scaffold, with ONE intentional exception:
``test_identity_declared`` fails until you replace STRATEGY_ID="template":
the rename is mandatory before a strategy can be registered. When you copy
the template, keep these tests (they enforce the format contract) and add
strategy-logic tests in api/tests/test_<strategy_id>.py.
"""

from __future__ import annotations

import copy
import dataclasses
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from strategy import STRATEGY_ID, OrderIntent, StrategyParams, decide

BANNED_TOKENS = (
    "datetime.now(",  # clock
    "utcnow(",  # clock
    "time.time(",  # clock
    "random",  # RNG
    "open(",  # file I/O
    "requests.",  # HTTP I/O
    "urllib",  # HTTP I/O
)


def make_context(**overrides) -> dict:
    # 8 bar M5 berakhir tepat di `now` (bar terakhir close 08:05) -> fresh.
    base = datetime.fromisoformat("2026-11-23T08:05:00+00:00")
    ctx = {
        "symbol": "XAUUSD",
        "now": base.isoformat(),
        "candles": [
            {
                "ts": (base - timedelta(minutes=5 * (8 - i))).isoformat(),
                "open": 3355.0,
                "high": 3356.0,
                "low": 3354.0,
                "close": 3355.0,
                "volume": 0,
            }
            for i in range(8)
        ],
        "liquidity": {
            "ts": "2026-11-23T08:05:00+00:00",
            "bid": 3361.0,
            "ask": 3361.35,
            "spread": 0.35,
            "spread_median_15m": 0.30,
            "fresh": True,
        },
        "positions": [],
        "trades_today": 0,
        "risk": {
            "equity": 10000.0,
            "risk_per_trade": 0.005,
            "max_volume": 0.10,
            "max_spread": 0.50,
        },
    }
    ctx.update(overrides)
    return ctx


def test_identity_declared():
    assert STRATEGY_ID and STRATEGY_ID != "template", "ganti STRATEGY_ID dari template"


def test_frozen_dataclasses():
    intent = OrderIntent("XAUUSD", "BUY", 0.01, 1.0, 2.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(intent, "volume", 0.02)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(StrategyParams(), "max_volume", 0.20)


def test_pure_module_source():
    """Heuristic: modul strategi tidak boleh menyembunyikan I/O / jam / RNG."""
    import strategy

    src = inspect.getsource(strategy)
    for token in BANNED_TOKENS:
        assert token not in src, f"purity: token terlarang {token!r} di modul strategi"


def test_context_not_mutated():
    ctx = make_context()
    frozen = copy.deepcopy(ctx)
    decide(ctx)
    assert ctx == frozen, "decide() memutasi context; context wajib read-only"


def test_deterministic():
    a = decide(make_context())
    b = decide(make_context())
    assert a == b


@pytest.mark.parametrize(
    "override",
    [
        {"now": "2026-11-22T08:05:00+00:00"},  # weekend
        {"candles": []},
        {"liquidity": {**make_context()["liquidity"], "fresh": False}},
        {"positions": [{"ticket": 1}]},
        {"trades_today": 1},
    ],
)
def test_standard_guards_block(override):
    assert decide(make_context(**override)) is None


def test_returns_none_or_valid_intent():
    intent = decide(make_context())
    if intent is None:
        return
    assert isinstance(intent, OrderIntent)
    assert intent.side in {"BUY", "SELL"}
    assert intent.volume > 0
    assert intent.sl > 0 and intent.tp > 0, "SL/TP wajib (risk gate)"
    assert intent.symbol == "XAUUSD"
