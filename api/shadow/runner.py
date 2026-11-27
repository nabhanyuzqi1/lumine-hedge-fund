"""Shadow strategy runner (PRD v2.2 §9): sinyal live TANPA order ke broker.

Menerima data live yang SAMA dengan paper runner (HFM tick log + candles +
regime classifier yang sama), menjalankan decide() strategi di sandbox
supervisor (source='SHADOW'), mencatat sinyal lengkap ke shadow_signals
(harga referensi, spread, timestamp, regime, alasan, label versi), dan
mensimulasikan fill dengan model biaya konservatif (shadow/fill.py).

BATAS KERAS (PRD 9.2): shadow tidak boleh mengirim order ke broker. Modul
ini tidak meng-import app.bridge / app.worker / kill-switch, tidak memanggil
endpoint order, dan tidak menulis ke orders / bridge_commands /
paper_orders. Posisi & P&L shadow adalah SIMULASI (is_simulation=TRUE,
saldo `sim_balance`). Tripwire di main() memverifikasi ledger order tidak
berubah selama proses berjalan.

Run:  .venv/bin/python -m shadow.runner [--once] [--status]
"""
from __future__ import annotations

import asyncio
import importlib
import signal
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from app import db, regime, supervisor
from app.risk import RiskContext, risk_gate
from paper import feed
from paper.broker import PaperBroker, PaperPosition, unrealized
from paper.runner import POLL_S, TICK_WINDOW_MIN, LIQUIDITY_FRESH_S
from paper.runner import build_context, log, record_regime
from shadow import store
from shadow.fill import FillModel, fill_model_from_settings
from shadow.specs import ShadowSpec, load_specs, params_hash

MODE = "SHADOW"
REGIME_KEY = "SHADOW_REGIME_STATES"
REGIME_RECORDED_KEY = "SHADOW_REGIME_RECORDED"


def code_commit() -> str | None:
    """Commit kode yang diuji (PRD 9.2: label perubahan kode)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False)
        if out.returncode == 0:
            return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


async def _decide(conn, **kwargs):
    """Indirection untuk test; produksi = supervisor sandbox (PRD §5)."""
    return await supervisor.decide(conn, **kwargs)


def shadow_enabled(settings: dict) -> bool:
    v = settings.get("shadow_enabled", True)
    if isinstance(v, str):
        return v.strip().lower() not in ("off", "false", "0", "no")
    return bool(v)


def _params_for(spec: ShadowSpec):
    """StrategyParams modul + override spec (field tak dikenal diabaikan)."""
    mod = importlib.import_module(spec.module)
    cls = getattr(mod, "StrategyParams")
    known = set(cls.__dataclass_fields__) if hasattr(cls, "__dataclass_fields__") else {}
    merged = {k: v for k, v in (spec.params or {}).items() if k in known}
    return cls(**merged)


async def run_iteration(conn, state: dict, *, spec: ShadowSpec, run_id,
                        settings: dict, params, tick: dict, candles: list[dict],
                        spread_median, now: datetime, allow_entry: bool,
                        regime_result=None, code_commit_hash: str | None = None,
                        fill_model: FillModel | None = None) -> list[str]:
    """Satu siklus keputusan satu versi shadow. Mutasi state (sim posisi)."""
    logs: list[str] = []
    fm = fill_model or FillModel()
    if params is None:
        params = _params_for(spec)
    broker = PaperBroker(force_close_hour_utc=getattr(params, "force_close_utc", None))
    bid, ask = float(tick["bid"]), float(tick["ask"])
    phash = params_hash(spec.params)

    # ── 1. Kelola posisi simulasi terbuka (SL/TP/time exit, tick path) ────
    pos = PaperPosition(**state["position"]) if state.get("position") else None
    if pos is not None:
        event = broker.on_price(pos, bid, ask, now)
        if event is not None:
            exit_px = fm.exit_price(pos.side, event.price)
            pnl = fm.pnl_usd(side=pos.side, entry=pos.entry_price, exit=exit_px,
                             volume=pos.volume, contract_size=pos.contract_size)
            commission = fm.commission_usd(pos.volume)
            net = round(pnl - commission, 2)
            state["sim_balance"] = round(state["sim_balance"] + net, 2)
            state["position"] = None
            await store.record_exit(
                conn, int(pos.order_id), exit_price=exit_px, pnl_usd=net,
                cost_usd=commission, exit_reason=event.reason, closed_at=now)
            logs.append(f"SIM CLOSE {pos.side} {pos.volume} #{pos.order_id} "
                        f"{event.reason} @ {exit_px:.2f} pnl(sim) {net:+.2f} "
                        f"sim_balance {state['sim_balance']:.2f}")

    open_pnl = unrealized(pos, bid, ask) if pos is not None else 0.0
    equity = round(state["sim_balance"] + open_pnl, 2)

    # ── 2. Entry: hanya saat fresh, tanpa posisi, dan versi aktif ────────
    if not (allow_entry and pos is None):
        return logs
    day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    trades_today = (await store.run_stats(conn, run_id, day_start))["filled"]
    context = build_context(
        symbol=spec.symbol, now=now, candles=candles, tick=tick,
        spread_median=spread_median, fresh=True, positions=[],
        trades_today=trades_today, equity=equity, settings=settings)
    decision = await _decide(
        conn, strategy_id=spec.strategy_id, strategy_version=spec.strategy_version,
        module=spec.module, context=context, params=asdict(params),
        symbol=spec.symbol, timeframe=spec.timeframe, source=MODE,
        settings=settings, seed_status=MODE)
    if decision.rejected:
        # Supervisor menolak (fault/breaker/status): signals row REJECTED
        # sudah ditulis supervisor; simpan detailnya di shadow_signals.
        sig_id = await store.insert_signal(
            conn, run_id=run_id, signal_ref=decision.signal_id,
            strategy_id=spec.strategy_id, strategy_version=spec.strategy_version,
            label=spec.label, symbol=spec.symbol, timeframe=spec.timeframe,
            ts=now, ref_bid=bid, ref_ask=ask, spread=float(tick["spread"]),
            spread_median_15m=spread_median, regime_label=None,
            regime_confidence=None, side=None, volume=None, sl=None, tp=None,
            reason=f"supervisor rejected: {decision.reason}",
            params_hash=phash, code_commit=code_commit_hash,
            sim_status="REJECTED", sim_fill_price=None, sim_cost_usd=None,
            detail={"reject_reason": decision.reason,
                    "reason_code": decision.reason_code,
                    "breaker": decision.breaker})
        logs.append(f"REJECTED by supervisor: {decision.reason} (shadow sig #{sig_id})")
        return logs
    if decision.intent is None:
        return logs  # valid tanpa entry: bukan sinyal, tanpa baris

    it = decision.intent
    order = {"symbol": it["symbol"], "side": it["side"], "volume": it["volume"],
             "sl": it["stop_loss"], "tp": it["take_profit"]}

    # ── 3. Gate regime (PRD §6): SAMA dengan paper runner ─────────────────
    if regime_result is not None:
        allowed = regime.allowed_regimes_for(
            importlib.import_module(spec.module))
        if not regime.regime_permits_entry(regime_result.label, allowed):
            sig_id = await store.insert_signal(
                conn, run_id=run_id, signal_ref=decision.signal_id,
                strategy_id=spec.strategy_id, strategy_version=spec.strategy_version,
                label=spec.label, symbol=spec.symbol, timeframe=spec.timeframe,
                ts=now, ref_bid=bid, ref_ask=ask, spread=float(tick["spread"]),
                spread_median_15m=spread_median,
                regime_label=regime_result.label,
                regime_confidence=regime_result.confidence,
                side=it["side"], volume=it["volume"], sl=it["stop_loss"],
                tp=it["take_profit"],
                reason=f"ENTRY BLOCKED by regime {regime_result.label} "
                       f"(allowed={allowed}): {regime_result.reason}",
                params_hash=phash, code_commit=code_commit_hash,
                sim_status="REGIME_BLOCKED", sim_fill_price=None,
                sim_cost_usd=None,
                detail={"allowed_regimes": allowed,
                        "regime_reason": regime_result.reason})
            await record_regime(conn, symbol=spec.symbol, timeframe=spec.timeframe,
                                result=regime_result, context="SIGNAL",
                                ref_type="shadow_signal", ref_id=sig_id)
            logs.append(f"ENTRY BLOCKED by regime {regime_result.label} "
                        f"(shadow sig #{sig_id})")
            return logs
        await record_regime(conn, symbol=spec.symbol, timeframe=spec.timeframe,
                            result=regime_result, context="SIGNAL",
                            ref_type="shadow_signal", ref_id=None)

    # ── 4. Risk gate (statistik shadow-scope, bukan paper/live) ───────────
    tick_age = max((now - tick["ts_utc"]).total_seconds(), 0.0)
    risk = risk_gate(order, RiskContext(
        settings=settings, bid=bid, ask=ask, tick_age_s=tick_age,
        daily_pnl=await store.daily_pnl(conn, run_id, day_start),
        orders_last_minute=await store.orders_last_minute(
            conn, run_id, now - timedelta(minutes=1))))
    if not risk.ok:
        sig_id = await store.insert_signal(
            conn, run_id=run_id, signal_ref=decision.signal_id,
            strategy_id=spec.strategy_id, strategy_version=spec.strategy_version,
            label=spec.label, symbol=spec.symbol, timeframe=spec.timeframe,
            ts=now, ref_bid=bid, ref_ask=ask, spread=float(tick["spread"]),
            spread_median_15m=spread_median,
            regime_label=regime_result.label if regime_result else None,
            regime_confidence=regime_result.confidence if regime_result else None,
            side=it["side"], volume=it["volume"], sl=it["stop_loss"],
            tp=it["take_profit"],
            reason="risk gate: " + "; ".join(risk.reasons),
            params_hash=phash, code_commit=code_commit_hash,
            sim_status="REJECTED", sim_fill_price=None, sim_cost_usd=None,
            detail={"risk_reasons": list(risk.reasons)})
        logs.append(f"REJECTED by risk gate: {risk.reasons} (shadow sig #{sig_id})")
        return logs

    # ── 5. Fill konservatif + catat sinyal lengkap (PRD 9.2) ──────────────
    entry = fm.entry_price(it["side"], bid, ask)
    commission = fm.commission_usd(it["volume"])
    slip_cost = fm.slippage_cost_usd(it["volume"], spec.contract_size)
    sig_id = await store.insert_signal(
        conn, run_id=run_id, signal_ref=decision.signal_id,
        strategy_id=spec.strategy_id, strategy_version=spec.strategy_version,
        label=spec.label, symbol=spec.symbol, timeframe=spec.timeframe,
        ts=now, ref_bid=bid, ref_ask=ask, spread=float(tick["spread"]),
        spread_median_15m=spread_median,
        regime_label=regime_result.label if regime_result else None,
        regime_confidence=regime_result.confidence if regime_result else None,
        side=it["side"], volume=it["volume"], sl=it["stop_loss"],
        tp=it["take_profit"], reason=it.get("reason") or "shadow signal",
        params_hash=phash, code_commit=code_commit_hash, sim_status="FILLED",
        sim_fill_price=entry, sim_cost_usd=round(commission + slip_cost, 2),
        detail={"risk": "PASS",
                "cost": {"commission_round_turn_usd": commission,
                         "slippage_usd_per_fill": fm.slippage,
                         "slippage_cost_usd": slip_cost},
                "strategy_version": spec.strategy_version})
    state["position"] = asdict(PaperPosition(
        order_id=str(sig_id), side=it["side"], volume=it["volume"],
        entry_price=entry, sl=it["stop_loss"], tp=it["take_profit"],
        opened_at=now, strategy=spec.strategy_id, contract_size=spec.contract_size))
    logs.append(f"SIM ENTRY {it['side']} {it['volume']} @ {entry:.2f} "
                f"SL {it['stop_loss']:.2f} TP {it['take_profit']:.2f} "
                f"(shadow sig #{sig_id}, {it.get('reason') or ''})")
    return logs


if __name__ == "__main__":  # python -m shadow.runner
    from shadow.__main__ import cli
    cli()
