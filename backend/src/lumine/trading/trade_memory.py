"""Trade memory service (21 Aug 2026 — P2 learning loop).

Menutup loop self-improvement dengan pengalaman trading NYATA:

    position closed (MT5 sync) -> capture ke trade_memories
        -> digest 20 trade terakhir di-inject ke prompt LLM per cycle
        -> LLM tahu pola menang/kalah sendiri (bukan cuma backtest)

Prinsip (sama dgn backtest scheduler): observe + learn via prompt,
TIDAK mengubah strategi production otomatis.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import select

logger = logging.getLogger("lumine.trading.trade_memory")

# Batas digest: 20 trade terakhir cukup untuk konteks tanpa meledakkan prompt.
DIGEST_LIMIT = 20


def _f(v: Any) -> float | None:
    """Decimal/str/None -> float aman."""
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _lesson(side: str, profit_usd: float | None, pips: float | None) -> str:
    """Pelajaran satu kalimat dari hasil real (deterministik, bukan LLM)."""
    if profit_usd is None:
        return "hasil belum diketahui"
    direction = "BUY" if side.lower() in ("buy", "long") else "SELL"
    if profit_usd > 0:
        p = f" ({pips:+.1f} pips)" if pips is not None else ""
        return f"{direction} profit ${profit_usd:+.2f}{p} — pola entry ini layak diulang"
    if profit_usd < 0:
        p = f" ({pips:+.1f} pips)" if pips is not None else ""
        return f"{direction} loss ${profit_usd:+.2f}{p} — hindari setup serupa / perketat SL"
    return f"{direction} breakeven"


async def capture_closed_position(session: Any, pos: Any) -> bool:
    """Simpan posisi tertutup ke trade_memories (idempotent per position_id).

    Dipanggil position_sync saat posisi berubah open -> closed.
    Return True jika baris baru dibuat.
    """
    from lumine.data.models import TradeMemory

    pid = str(getattr(pos, "position_id", "") or "")
    if not pid:
        return False

    existing = (
        await session.execute(
            select(TradeMemory).where(TradeMemory.position_id == pid).limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False

    entry = _f(getattr(pos, "avg_entry", None))
    # Position model tidak punya mt5_close_price — exit price snapshot
    # terakhir tidak tersimpan; biarkan None (pips juga None, lesson tetap
    # dari profit USD real).
    exit_price: float | None = None
    profit = _f(getattr(pos, "mt5_profit", None))
    symbol = str(getattr(pos, "symbol", "") or "")
    side = str(getattr(pos, "side", "") or "")

    # Pips: butuh exit price; kalau tidak ada (snapshot broker tanpa close
    # price), hitung dari profit/volume sebagai fallback kasar? TIDAK —
    # data cacat fatal. Biarkan None, lesson tetap dari profit USD.
    pips: float | None = None
    if entry is not None and exit_price is not None and entry > 0:
        raw = (exit_price - entry) * (1 if side.lower() in ("buy", "long") else -1)
        # XAUUSD: 1 pip = 0.1 (konvensi broker umum); simpan raw*10
        pips = round(raw * 10, 1)

    opened_at = getattr(pos, "opened_at", None)
    closed_at = getattr(pos, "updated_at", None)
    duration = None
    if opened_at is not None and closed_at is not None:
        duration = max(0, int((closed_at - opened_at).total_seconds() // 60))

    ai_reason = getattr(pos, "ai_reason", None)
    confidence = getattr(pos, "confidence", None)

    session.add(
        TradeMemory(
            position_id=pid,
            mt5_ticket=getattr(pos, "mt5_ticket", None),
            symbol=symbol,
            side=side,
            volume=getattr(pos, "size", Decimal(0)) or Decimal(0),
            entry_price=getattr(pos, "avg_entry", Decimal(0)) or Decimal(0),
            exit_price=(
                Decimal(str(exit_price)) if exit_price is not None else None
            ),
            sl=getattr(pos, "sl", None),
            tp=getattr(pos, "tp", None),
            profit_usd=(
                Decimal(str(profit)) if profit is not None else None
            ),
            pips=Decimal(str(pips)) if pips is not None else None,
            duration_minutes=duration,
            opened_at=opened_at,
            closed_at=closed_at,
            ai_reason=(str(ai_reason) if ai_reason else None),
            confidence=(
                Decimal(str(confidence)) if confidence is not None else None
            ),
            profile_id=None,  # diisi worker bila profil aktif diketahui
            lesson=_lesson(side, profit, pips),
        )
    )
    await session.commit()
    logger.info(
        "[TRADE-MEMORY] captured position=%s ticket=%s %s %s pnl=%s",
        pid[:8],
        getattr(pos, "mt5_ticket", None),
        side,
        symbol,
        profit,
    )
    return True


async def build_trade_memory_digest(session: Any, limit: int = DIGEST_LIMIT) -> str:  # noqa: C901 — digest ringkas multi-kondisi
    """Digest N trade terakhir utk inject ke prompt LLM (ringkas, real).

    Format baris: `2026-08-21 BUY XAUUSD 0.10 @4353.1->4590.0 pnl=$+12.40
    (237.0 pips) conf=0.85 — BUY profit $+12.40 (237.0 pips) — pola layak
    diulang`. Kosong bila belum ada data (jangan placeholder).
    """
    from lumine.data.models import TradeMemory

    try:
        rows = (
            (
                await session.execute(
                    select(TradeMemory)
                    .order_by(TradeMemory.closed_at.desc().nullslast())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
    except Exception:  # nosec B110 — tabel belum dimigrasi pun jangan mati
        return ""

    if not rows:
        return ""

    lines: list[str] = []
    wins = 0
    total_pnl = 0.0
    for r in rows:
        pnl = _f(r.profit_usd)
        pips_v = _f(r.pips)
        conf = _f(r.confidence)
        if pnl is not None:
            total_pnl += pnl
            if pnl > 0:
                wins += 1
        parts = [
            (r.closed_at.strftime("%m-%d") if r.closed_at else "?"),
            r.side.upper(),
            r.symbol,
            f"{_f(r.volume) or 0:.2f}",
            f"@{_f(r.entry_price) or 0:.1f}",
        ]
        exit_p = _f(r.exit_price)
        if exit_p is not None:
            parts.append(f"->{exit_p:.1f}")
        if pnl is not None:
            parts.append(f"pnl=${pnl:+.2f}")
        if pips_v is not None:
            parts.append(f"({pips_v:+.1f}p)")
        if conf is not None:
            parts.append(f"conf={conf:.2f}")
        line = " ".join(parts)
        if r.lesson:
            line += f" — {r.lesson}"
        lines.append(line)

    n = len(rows)
    header = (
        f"TRADE MEMORY ({n} trade nyata terakhir, win {wins}/{n}, "
        f"total P&L ${total_pnl:+.2f}):"
    )
    return header + "\n" + "\n".join(lines)
