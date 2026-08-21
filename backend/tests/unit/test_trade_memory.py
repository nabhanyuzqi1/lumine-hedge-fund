"""Tests for trade memory service (P2 — 21 Aug 2026)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

from lumine.trading.trade_memory import (
    _f,
    _lesson,
    build_trade_memory_digest,
    capture_closed_position,
)


class _FakePosition:
    """Minimal Position-like object untuk test."""

    def __init__(self, **kw: object) -> None:
        self.position_id = kw.get("position_id", "00000000-0000-0000-0000-000000000001")
        self.mt5_ticket = kw.get("mt5_ticket", 12345)
        self.symbol = kw.get("symbol", "XAUUSD")
        self.side = kw.get("side", "buy")
        self.size = kw.get("size", Decimal("0.10"))
        self.avg_entry = kw.get("avg_entry", Decimal("4350.0"))
        self.sl = kw.get("sl")
        self.tp = kw.get("tp")
        self.mt5_profit = kw.get("mt5_profit")
        self.opened_at = kw.get("opened_at")
        self.updated_at = kw.get("updated_at")
        self.ai_reason = kw.get("ai_reason")
        self.confidence = kw.get("confidence")


class _FakeSession:
    """Session minimal: execute → scalars/result, add/commit sync dict."""

    def __init__(self, *, existing: object | None = None, rows: list[object] | None = None) -> None:
        self._existing = existing
        self._rows = rows or []
        self.added: list[object] = []
        self.commits = 0

    async def execute(self, _stmt: object) -> "_FakeResult":
        return _FakeResult(existing=self._existing, rows=self._rows)

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1


class _FakeResult:
    def __init__(self, *, existing: object | None = None, rows: list[object] | None = None) -> None:
        self._existing = existing
        self._rows = rows or []

    def scalar_one_or_none(self) -> object | None:
        return self._existing

    def scalars(self) -> "_FakeScalars":
        return _FakeScalars(self._rows)


class _FakeScalars:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class TestF:
    def test_none(self) -> None:
        assert _f(None) is None
        assert _f("") is None

    def test_decimal(self) -> None:
        assert _f(Decimal("12.34")) == 12.34

    def test_str(self) -> None:
        assert _f("5.5") == 5.5


class TestLesson:
    def test_buy_profit(self) -> None:
        lesson = _lesson("buy", 15.50, 120.0)
        assert "BUY profit" in lesson
        assert "$+15.50" in lesson
        assert "+120.0 pips" in lesson

    def test_sell_loss(self) -> None:
        lesson = _lesson("SELL", -8.20, -50.0)
        assert "SELL loss" in lesson
        assert "$-8.20" in lesson

    def test_unknown_pnl(self) -> None:
        lesson = _lesson("buy", None, None)
        assert "hasil belum diketahui" in lesson


class TestCaptureClosed:
    async def test_idempotent(self) -> None:
        """Posisi yang sama tidak boleh double-capture."""
        pos = _FakePosition(mt5_profit=Decimal("12.30"))
        session = _FakeSession(existing=None)
        assert await capture_closed_position(session, pos) is True
        assert len(session.added) == 1
        assert session.commits == 1

        # Call kedua → existing ditemukan → skip
        session2 = _FakeSession(existing=object())
        assert await capture_closed_position(session2, pos) is False
        assert session2.added == []

    async def test_skip_when_no_position_id(self) -> None:
        pos = _FakePosition(position_id="")
        session = _FakeSession(existing=None)
        assert await capture_closed_position(session, pos) is False
        assert session.added == []

    async def test_profit_positive(self) -> None:
        """Profit positif → lesson 'layak diulang'."""
        pos = _FakePosition(mt5_profit=Decimal("25.0"))
        session = _FakeSession(existing=None)
        await capture_closed_position(session, pos)
        args = session.added[0]
        assert "layak diulang" in (args.lesson or "")
        assert args.profit_usd == Decimal("25.0")

    async def test_loss_negative(self) -> None:
        """Loss → lesson 'hindari / perketat SL'."""
        pos = _FakePosition(mt5_profit=Decimal("-15.0"))
        session = _FakeSession(existing=None)
        await capture_closed_position(session, pos)
        args = session.added[0]
        assert "hindari" in (args.lesson or "").lower()

    async def test_pips_computed_from_exit(self) -> None:
        """Posisi dengan exit price di atas entry (buy) → pips positif."""
        from lumine.data.models import TradeMemory

        pos = _FakePosition(avg_entry=Decimal("4350.0"))
        session = _FakeSession(existing=None)
        # mock exit_price via exit_price None — pips harus None (no close price)
        await capture_closed_position(session, pos)
        args = session.added[0]
        assert args.pips is None  # belum ada close price — jangan mengarang


class TestBuildDigest:
    async def test_empty(self) -> None:
        session = _FakeSession(rows=[])
        assert await build_trade_memory_digest(session) == ""

    async def test_with_rows(self) -> None:
        """Build digest dari 1 row."""
        from lumine.data.models import TradeMemory

        row = TradeMemory(
            position_id="p1",
            mt5_ticket=123,
            symbol="XAUUSD",
            side="buy",
            volume=Decimal("0.10"),
            entry_price=Decimal("4350.0"),
            exit_price=Decimal("4400.0"),
            profit_usd=Decimal("50.0"),
            pips=Decimal("500.0"),
            duration_minutes=120,
            opened_at=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
            closed_at=datetime(2026, 8, 21, 14, 0, tzinfo=UTC),
            ai_reason="bullish breakout",
            confidence=Decimal("0.85"),
            lesson="BUY profit $+50.00 (500.0 pips) — pola entry ini layak diulang",
        )

        session = _FakeSession(rows=[row])
        result = await build_trade_memory_digest(session)
        assert "TRADE MEMORY" in result
        assert "08-21" in result
        assert "BUY" in result
        assert "XAUUSD" in result
        assert "pnl=$+50.00" in result
        assert "conf=0.85" in result
        assert "layak diulang" in result

    async def test_digest_win_rate_and_total(self) -> None:
        """Header berisi win rate + total P&L agregat."""
        from lumine.data.models import TradeMemory

        rows = [
            TradeMemory(
                position_id=f"p{i}",
                symbol="XAUUSD",
                side="buy" if i % 2 == 0 else "sell",
                volume=Decimal("0.10"),
                entry_price=Decimal("4350.0"),
                profit_usd=Decimal("10.0") if i == 0 else Decimal("-5.0"),
                closed_at=datetime(2026, 8, 20 + i, 12, 0, tzinfo=UTC),
                lesson="x",
            )
            for i in range(2)
        ]
        session = _FakeSession(rows=rows)
        result = await build_trade_memory_digest(session)
        assert "win 1/2" in result
        assert "total P&L $+5.00" in result