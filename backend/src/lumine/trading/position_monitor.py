"""Deterministic position monitor (19 Aug 2026 — P0).

Menerapkan BREAKEVEN / TRAILING_STOP / CUT_LOSS secara DETERMINISTIC
(bukan bergantung pada LLM decision cycle). LLM hanya menghasilkan
proposal; perlindungan posisi berjalan otomatis di Python berdasarkan
profil aktif.

Aturan per posisi open (dari profil aktif):
- Break-even: saat R-multiple >= be_after_r -> geser SL ke entry (± spread)
- Trailing:   saat R-multiple >= trail_after_r -> geser SL = harga - trail_dist
- Cut-loss:   saat P&L <= -cutloss_frac x equity -> tutup penuh

State per posisi disimpan di Redis (idempotent; tidak spam MODIFY).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("lumine.trading.position_monitor")

STATE_KEY = "lumine:position:state"  # hash ticket → json {be_done, trail_level}
MONITOR_INTERVAL_SECONDS = 5.0


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _compute_r(
    side: str,
    entry: float,
    sl: float | None,
    price: float,
) -> float | None:
    """R-multiple dari posisi (berbasis SL). None jika SL tidak ada."""
    if not sl:
        return None
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    if side.lower() in ("buy", "long"):
        return (price - entry) / risk
    return (entry - price) / risk


async def _next_sl(
    side: str,
    entry: float,
    sl: float | None,
    price: float,
    *,
    profile: dict[str, Any],
    spread: float,
) -> float | None:
    """Hitung SL baru untuk BREAKEVEN atau TRAILING_STOP."""
    trail_mult = float(profile.get("trail_after_r", 1.0) or 1.0)
    # Trailing: SL = harga - trail_mult x ATR-risk; ATR-risk = |entry - sl_awal|
    if not sl:
        return None
    atr_risk = abs(entry - sl)
    if side.lower() in ("buy", "long"):
        return round(price - trail_mult * atr_risk, 5)
    return round(price + trail_mult * atr_risk, 5)


async def run_position_monitor(  # noqa: C901, PLR0912, PLR0915 — monitor deterministik banyak branch
    *,
    get_sessionmaker: Any,
    get_redis: Any,
    bridge_factory: Any,
    publisher: Any | None = None,
) -> None:
    """Loop monitor. Jalankan sebagai lifespan task."""
    from lumine.trading.execution_intent import ExecutionIntent
    from lumine.trading.mt5_bridge import (
        create_close_order_command,
        create_modify_command,
    )

    while True:
        try:
            r = await get_redis()
            # 1. Profil aktif
            from lumine.trading.profiles import get_active_profile

            profile = await get_active_profile(r)
            be_after_r = float(profile.get("be_after_r", 0.5) or 0.5)
            trail_after_r = float(profile.get("trail_after_r", 1.0) or 1.0)

            # 2. Live bid + equity (XAUUSD) dari Redis status
            bid = None
            equity = None
            st = await r.hgetall("mt5:status")
            if isinstance(st, dict):
                st = {
                    (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
                    for k, v in st.items()
                }
                try:
                    bid = float(st.get("bid") or 0) or None
                except (TypeError, ValueError):
                    bid = None
                try:
                    equity = float(st.get("equity") or 0) or None
                except (TypeError, ValueError):
                    equity = None
            if not bid:
                await asyncio.sleep(MONITOR_INTERVAL_SECONDS)
                continue

            # 2b. Cutloss daily-cap (19 Aug 2026 P0): deterministic — tidak
            #     menunggu LLM. Day-start equity disimpan di Redis (reset
            #     otomatis saat tanggal berganti via key ber-tanggal).
            day = datetime.now(UTC).strftime("%Y-%m-%d")
            day_equity_key = f"lumine:risk:day_start_equity:{day}"
            day_start = await r.get(day_equity_key)
            if day_start is None:
                if equity is not None:
                    await r.set(day_equity_key, str(equity), ex=48 * 3600)
                    day_start = equity
                else:
                    day_start = None
            else:
                try:
                    day_start = float(day_start)
                except (TypeError, ValueError):
                    day_start = None
            # max daily loss fraction (default 3%)
            max_daily_loss = 0.03
            try:
                _mdl = await r.hget("lumine:system_config", "max_daily_loss_pct")
                if _mdl is not None:
                    max_daily_loss = float(_mdl)
            except Exception:  # nosec B110 — fallback default
                pass

            # 3. Posisi open dari DB
            from sqlalchemy import select

            from lumine.data.models import Position

            async with get_sessionmaker()() as session:
                rows = (
                    await session.execute(
                        select(Position).where(Position.status == "open")
                    )
                ).scalars().all()
                open_positions = [
                    {
                        "ticket": p.mt5_ticket,
                        "position_id": str(p.position_id),
                        "symbol": p.symbol,
                        "side": p.side,
                        "size": float(p.size or 0),
                        "entry": float(p.avg_entry or 0),
                        "sl": float(p.sl) if p.sl else None,
                        "tp": float(p.tp) if p.tp else None,
                    }
                    for p in rows
                    if p.mt5_ticket is not None
                ]

            if not open_positions:
                await asyncio.sleep(MONITOR_INTERVAL_SECONDS)
                continue

            # 4. State per ticket
            state_raw = await r.hgetall(STATE_KEY)
            states: dict[int, dict[str, Any]] = {}
            if state_raw:
                for k, v in state_raw.items():
                    tk = int(k.decode() if isinstance(k, bytes) else k)
                    try:
                        states[tk] = json.loads(v.decode() if isinstance(v, bytes) else v)
                    except (ValueError, TypeError):
                        states[tk] = {}

            for pos in open_positions:
                ticket = pos["ticket"]
                entry = pos["entry"]
                sl = pos["sl"]
                side = pos["side"]
                st_pos = states.get(ticket, {})
                r_val = await _compute_r(side, entry, sl, bid)

                intent: str | None = None
                new_sl: float | None = None
                reason = ""

                # BREAKEVEN (sekali per posisi)
                if r_val is not None and r_val >= be_after_r and not st_pos.get("be_done"):
                    new_sl = round(entry, 5)
                    intent = ExecutionIntent.BREAKEVEN
                    reason = f"BE hit (R={r_val:.2f} ≥ {be_after_r})"
                    st_pos["be_done"] = True

                # TRAILING (setelah BE/atau langsung saat R ≥ trail_after_r)
                elif r_val is not None and r_val >= trail_after_r:
                    candidate = await _next_sl(side, entry, sl, bid, profile=profile, spread=0.0)
                    # Hanya geser ke arah profit (monotonic trailing)
                    if candidate is not None:
                        if (side.lower() in ("buy", "long") and (sl is None or candidate > sl)) or (side.lower() in ("sell", "short") and (sl is None or candidate < sl)):
                            intent = ExecutionIntent.TRAILING_STOP
                            new_sl = candidate
                            reason = f"Trail (R={r_val:.2f} ≥ {trail_after_r})"

                if intent is None:
                    continue

                # Kirim MODIFY (BE/trailing) atau CLOSE (cutloss)
                bridge = await bridge_factory()
                if intent in (ExecutionIntent.BREAKEVEN, ExecutionIntent.TRAILING_STOP):
                    msg = create_modify_command(
                        __import__("uuid").UUID(pos["position_id"]),
                        ticket,
                        stop_loss=new_sl,
                        intent=str(intent),
                        reason=reason,
                    )
                    try:
                        await bridge.send_command(msg)
                        logger.info("[MONITOR] %s ticket=%s sl=%s (%s)", intent, ticket, new_sl, reason)
                    except ValueError:
                        pass  # idempotent — sudah dikirim
                else:
                    msg = create_close_order_command(
                        __import__("uuid").UUID(pos["position_id"]),
                        ticket,
                        reason=str(intent),
                    )
                    try:
                        await bridge.send_command(msg)
                        logger.info("[MONITOR] %s ticket=%s (%s)", intent, ticket, reason)
                    except ValueError:
                        pass

                # Persist state
                states[ticket] = st_pos
                await r.hset(STATE_KEY, str(ticket), json.dumps(st_pos))

            # 5. CUT_LOSS daily-cap (deterministic flatten) — 19 Aug 2026 P0.
            #     Jika P&L harian (equity - day_start) turun di bawah -max_daily_loss
            #     → tutup SEMUA posisi open, tanpa menunggu LLM cycle.
            if equity is not None and day_start is not None and open_positions:
                day_pnl = equity - day_start
                loss_cap = max_daily_loss * day_start
                if day_pnl <= -loss_cap:
                    logger.warning(
                        "[MONITOR] CUT_LOSS daily-cap triggered: pnl=%.2f cap=-%.2f (%.1f%%)",
                        day_pnl, loss_cap, max_daily_loss * 100,
                    )
                    bridge = await bridge_factory()
                    for pos in open_positions:
                        ticket = pos["ticket"]
                        msg = create_close_order_command(
                            __import__("uuid").UUID(pos["position_id"]),
                            ticket,
                            reason="CUT_LOSS_DAILY_CAP",
                        )
                        try:
                            await bridge.send_command(msg)
                            logger.info("[MONITOR] CUT_LOSS flatten ticket=%s", ticket)
                        except ValueError:
                            pass

        except Exception:  # nosec B110 — monitor tidak boleh mati
            logger.exception("position monitor error")

        await asyncio.sleep(MONITOR_INTERVAL_SECONDS)
