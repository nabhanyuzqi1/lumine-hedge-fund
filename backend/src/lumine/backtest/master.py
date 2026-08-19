"""Master backtest (18 Aug 2026) — user request.

"1 master backtest. ambil data candle 1 tahun, backtest perhari sampai
1 tahun atau backtest sesuai profile yang dipilih. hasilnya di simpan dan
dipakai untuk improve prompt ai dan data ai lagi, siklus di ulang terus
sampai LLM bisa melihat pola atau pattern dari XAUUSD."

Alur:
1. Load bars 1 tahun dari DB (bars_{tf}, until now, sejak now-365d).
2. Jalankan engine backtest (rules-based SMA/vol untuk baseline) dengan
   parameter dari profile aktif (risk, SL/TP mult).
3. Simpan hasil ke `backtest_runs` (metrics + equity + learning digest).
4. Learning digest dikonsumsi worker → di-inject ke analyst prompt
   (`backtest_learnings`) → LLM aware pola historis XAUUSD (loop).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from lumine.backtest.engine import run_backtest_from_rows
from lumine.data.models import (
    BacktestRun,
    Bars1D,
    Bars1H,
    Bars1M,
    Bars4H,
    Bars5M,
    Bars15M,
)

BAR_MODELS = {
    "1m": Bars1M,
    "5m": Bars5M,
    "15m": Bars15M,
    "1h": Bars1H,
    "4h": Bars4H,
    "1d": Bars1D,
}

# Batas bar yang masuk akal per TF per tahun (hard guard — jangan blow-up)
MAX_BARS_PER_TF = {
    "1m": 60_000,  # 1 tahun 1m = 376k — ambil ~3.5 bulan
    "5m": 120_000,  # 1 tahun 5m = 75k — cukup penuh
    "15m": 60_000,
    "1h": 60_000,  # 1 tahun 1h = 8.7k
    "4h": 30_000,
    "1d": 5_000,  # 1 tahun 1d = 365
}


async def load_bars_year(session: Any, symbol: str, timeframe: str) -> list[dict[str, Any]]:
    """Load bars sejak 365 hari (limit per TF) — oldest-first."""
    model = BAR_MODELS.get(timeframe)
    if model is None:
        return []
    since = datetime.now(UTC) - timedelta(days=365)
    limit = MAX_BARS_PER_TF.get(timeframe, 60_000)
    try:
        rows = (
            await session.execute(
                select(model)
                .where(model.symbol == symbol, model.ts >= since)
                .order_by(model.ts.asc())
                .limit(limit)
            )
        ).scalars().all()
    except Exception:
        return []
    return [
        {
            "ts": r.ts.isoformat(),
            "open": float(r.open),
            "high": float(r.high),
            "low": float(r.low),
            "close": float(r.close),
            "volume": r.volume,
        }
        for r in rows
    ]


def build_learning_digest(result: Any) -> str:
    """Ringkas hasil backtest jadi teks pendek untuk prompt LLM."""
    m = result.metrics
    digest = (
        f"Backtest {result.timeframe} ({result.symbol}): "
        f"{m.trade_count} trades, return {float(m.total_return_pct) * 100:.2f}%, "
        f"win-rate {float(m.win_rate_pct) * 100:.1f}%, "
        f"max-DD {float(m.max_drawdown_pct) * 100:.2f}%, "
        f"sharpe-like {float(m.sharpe_like):.2f}."
    )
    return digest


async def run_master_backtest(
    session: Any,
    *,
    symbol: str = "XAUUSD",
    timeframe: str = "1h",
    profile_id: str = "scalping_1m",
    persist: bool = True,
) -> dict[str, Any]:
    """Run master backtest 1 tahun untuk satu profil → simpan hasil."""
    rows = await load_bars_year(session, symbol, timeframe)
    result = run_backtest_from_rows(rows, symbol, timeframe)
    m = result.metrics

    digest = build_learning_digest(result)
    out = {
        "profile_id": profile_id,
        "timeframe": timeframe,
        "symbol": symbol,
        "bar_count": len(rows),
        "metrics": {
            "total_return_pct": float(m.total_return_pct),
            "max_drawdown_pct": float(m.max_drawdown_pct),
            "win_rate_pct": float(m.win_rate_pct),
            "trade_count": m.trade_count,
            "sharpe_like": float(m.sharpe_like),
        },
        "equity": [float(v) for v in result.equity[-500:]],
        "learning_digest": digest,
        "created_at": datetime.now(UTC).isoformat(),
    }

    if persist:
        try:
            session.add(
                BacktestRun(
                    profile_id=profile_id,
                    timeframe=timeframe,
                    symbol=symbol,
                    bar_count=len(rows),
                    metrics_json=out["metrics"],
                    equity_json=out["equity"],
                    learning_digest=digest,
                )
            )
            await session.commit()
        except Exception:
            await session.rollback()
    return out


async def get_latest_learning_digest(session: Any, profile_id: str) -> str:
    """Digest backtest terbaru untuk satu profil — inject ke prompt LLM."""
    try:
        row = (
            await session.execute(
                select(BacktestRun)
                .where(BacktestRun.profile_id == profile_id)
                .order_by(BacktestRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is not None:
            return row.learning_digest
    except Exception:
        pass
    return ""


async def get_latest_runs(session: Any, profile_id: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """List hasil master backtest terbaru (untuk UI Backtest tab)."""
    try:
        q = select(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(limit)
        if profile_id:
            q = q.where(BacktestRun.profile_id == profile_id)
        rows = (await session.execute(q)).scalars().all()
        return [
            {
                "id": str(r.id),
                "profile_id": r.profile_id,
                "timeframe": r.timeframe,
                "symbol": r.symbol,
                "bar_count": r.bar_count,
                "metrics": r.metrics_json,
                "learning_digest": r.learning_digest,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    except Exception:
        return []
