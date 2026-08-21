"""Tests for research router series builder (P5 — 21 Aug 2026)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from lumine.api.routers.research import _build_series


class _FakePos:
    """Minimal Position-like object untuk test series builder."""

    def __init__(self, *, book: str, profit: float, ts: str) -> None:
        self.book = book
        self.mt5_profit = Decimal(str(profit))
        self.updated_at = datetime.fromisoformat(ts).replace(tzinfo=UTC)


class TestBuildSeries:
    def test_empty(self) -> None:
        result = _build_series([])
        assert result["paper"] == []
        assert result["real"] == []
        assert result["paper_final_pnl"] == 0.0
        assert result["real_final_pnl"] == 0.0
        assert "seimbang" in result["insight"]

    def test_kumulatif_paper(self) -> None:
        """Dua trade paper berturut — kumulatif bertambah."""
        rows = [
            _FakePos(book="paper", profit=10.0, ts="2026-08-01T10:00:00+00:00"),
            _FakePos(book="paper", profit=-4.0, ts="2026-08-02T10:00:00+00:00"),
        ]
        result = _build_series(rows)
        assert result["paper"] == [
            {"ts": "2026-08-01T10:00:00+00:00", "pnl": 10.0},
            {"ts": "2026-08-02T10:00:00+00:00", "pnl": 6.0},
        ]
        assert result["paper_final_pnl"] == 6.0

    def test_real_vs_paper_insight(self) -> None:
        """Real lebih baik dari paper → insight real outperforms."""
        rows = [
            _FakePos(book="paper", profit=-20.0, ts="2026-08-01T10:00:00+00:00"),
            _FakePos(book="default", profit=15.0, ts="2026-08-01T11:00:00+00:00"),
        ]
        result = _build_series(rows)
        assert result["paper_final_pnl"] == -20.0
        assert result["real_final_pnl"] == 15.0
        assert "Real outperforms Paper" in result["insight"]
        assert result["real"] == [{"ts": "2026-08-01T11:00:00+00:00", "pnl": 15.0}]

    def test_paper_better_insight(self) -> None:
        """Paper lebih baik → insight eksekusi real lebih buruk."""
        rows = [
            _FakePos(book="paper", profit=30.0, ts="2026-08-01T10:00:00+00:00"),
            _FakePos(book="default", profit=5.0, ts="2026-08-01T11:00:00+00:00"),
        ]
        result = _build_series(rows)
        assert "Paper outperforms Real" in result["insight"]

    def test_campuran_urutan_tidak_mempengaruhi_final(self) -> None:
        """Final P&L per book = jumlah semua trade (urut independent)."""
        rows = [
            _FakePos(book="default", profit=1.0, ts="2026-08-01T10:00:00+00:00"),
            _FakePos(book="paper", profit=2.0, ts="2026-08-01T10:00:00+00:00"),
            _FakePos(book="default", profit=3.0, ts="2026-08-01T11:00:00+00:00"),
            _FakePos(book="paper", profit=-1.0, ts="2026-08-01T11:00:00+00:00"),
        ]
        result = _build_series(rows)
        assert result["paper_final_pnl"] == 1.0
        assert result["real_final_pnl"] == 4.0
