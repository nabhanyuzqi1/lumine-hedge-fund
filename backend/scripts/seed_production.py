#!/usr/bin/env python3
"""seed_production.py — Seed produksi Lumine (B-08 fondasi + TCA backfill).

Menjalankan di VPS:
    docker compose -f docker-compose.vps.yml run --rm api python -m scripts.seed_production

Idempotent (skip kalau versi/record sudah ada). Bagian:
1. Seed registry versions (model, prompt, strategy, policy, feature, regime, calendar)
2. Backfill: orders status=filled → LineageRecord + Fill + TcaRecord
   (benchmark = arrival mid dari bars_1m di decision_ts; slippage_bps;
    TCA evidence ADR-0040)
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from lumine.data.models import (
    CalendarVersion,
    FeatureVersion,
    Fill,
    LineageRecord,
    ModelVersion,
    PolicyVersion,
    PromptVersion,
    RegimeVersion,
    StrategyVersion,
    TcaRecord,
    Order,
    Bars1M,
)
from lumine.data.session import get_sessionmaker

BOOK = "default"
STRATEGY = "momentum_sma20"


async def _seed_registry(session) -> dict[str, uuid.UUID]:
    """Seed version registry rows (idempotent). Return ids map."""
    ids: dict[str, uuid.UUID] = {}

    # ── Model ────────────────────────────────────────────────────────────
    row = (
        await session.execute(
            select(ModelVersion).where(ModelVersion.version == "deepseek-v4-prod")
        )
    ).scalar_one_or_none()
    if row is None:
        row = ModelVersion(
            version="deepseek-v4-prod",
            status="production",
            provider="9router",
            model_id="deepseek/deepseek-v4",
            tier="primary",
            context_window=131072,
            params={"temperature": 0.2, "budget_tokens": 4096},
        )
        session.add(row)
        await session.flush()
    ids["model"] = row.id

    # ── Prompts (per sub-role) ───────────────────────────────────────────
    for sub_role in ("technical_analyst", "macro_analyst", "risk_officer"):
        ver = f"prompt-{sub_role}-v1"
        row = (
            await session.execute(
                select(PromptVersion).where(PromptVersion.version == ver)
            )
        ).scalar_one_or_none()
        if row is None:
            row = PromptVersion(
                version=ver,
                status="production",
                sub_role=sub_role,
                prompt_hash=hashlib.sha256(f"lumine:{sub_role}:v1".encode()).hexdigest(),
                prompt_ref=f"docs/04-communication-and-prompts/agents/{sub_role}.md",
                variables={"symbol": "XAUUSD"},
                output_schema={"type": "object", "properties": {"action": {"type": "string"}}},
            )
            session.add(row)
            await session.flush()
        ids[f"prompt:{sub_role}"] = row.id

    # ── Strategy ─────────────────────────────────────────────────────────
    row = (
        await session.execute(
            select(StrategyVersion).where(StrategyVersion.version == "strategy-v1")
        )
    ).scalar_one_or_none()
    if row is None:
        row = StrategyVersion(
            version="strategy-v1",
            status="production",
            name=STRATEGY,
            book=BOOK,
            description="SMA20 + volume momentum (deterministic backtest engine)",
            params={"sma_window": 20, "volume_min": 1000},
            entry_rules={"signal": "sma20_cross", "direction": "both"},
            exit_rules={"stop_loss_bps": 500, "take_profit_bps": 1000},
            source="docs/15-implementation",
        )
        session.add(row)
        await session.flush()
    ids["strategy"] = row.id

    # ── Policy ───────────────────────────────────────────────────────────
    row = (
        await session.execute(
            select(PolicyVersion).where(PolicyVersion.version == "policy-v1")
        )
    ).scalar_one_or_none()
    if row is None:
        row = PolicyVersion(
            version="policy-v1",
            status="production",
            scope="risk",
            policy_hash=hashlib.sha256(b"lumine:risk:policy:v1").hexdigest(),
            policy={"max_position_pct": 0.05, "max_drawdown_pct": 0.2, "kill_switch": True},
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        )
        session.add(row)
        await session.flush()
    ids["policy"] = row.id

    # ── Feature ──────────────────────────────────────────────────────────
    row = (
        await session.execute(
            select(FeatureVersion).where(
                FeatureVersion.name == "market_features",
                FeatureVersion.version == "v1",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = FeatureVersion(
            name="market_features",
            version="v1",
            status="production",
            params={"sma": 20, "rsi": 14, "atr": 14},
            code_hash=hashlib.sha256(b"lumine:features:v1").hexdigest(),
            warmup_required=20,
        )
        session.add(row)
        await session.flush()
    ids["feature"] = row.id

    # ── Regime ───────────────────────────────────────────────────────────
    row = (
        await session.execute(
            select(RegimeVersion).where(RegimeVersion.version == "regime-v1")
        )
    ).scalar_one_or_none()
    if row is None:
        row = RegimeVersion(
            version="regime-v1",
            status="production",
            name="trend_classifier",
            code_hash=hashlib.sha256(b"lumine:regime:v1").hexdigest(),
            buckets={"regimes": ["bull", "bear", "range"]},
            description="SMA200 trend + ADX regime classifier",
        )
        session.add(row)
        await session.flush()
    ids["regime"] = row.id

    # ── Calendar ─────────────────────────────────────────────────────────
    row = (
        await session.execute(
            select(CalendarVersion).where(CalendarVersion.version == "calendar-v1")
        )
    ).scalar_one_or_none()
    if row is None:
        row = CalendarVersion(
            version="calendar-v1",
            status="production",
            name="forex_24x5",
            params={"sessions": ["asia", "london", "newyork"]},
            code_hash=hashlib.sha256(b"lumine:calendar:v1").hexdigest(),
            description="Forex 24x5 calendar (weekend closed)",
        )
        session.add(row)
        await session.flush()
    ids["calendar"] = row.id

    await session.commit()
    return ids


async def _arrival_mid(session, symbol: str, ts: datetime) -> Decimal | None:
    """Arrival mid dari bars_1m terdekat <= ts (benchmark ADR-0040)."""
    row = (
        await session.execute(
            select(Bars1M)
            .where(Bars1M.symbol == symbol, Bars1M.ts <= ts)
            .order_by(Bars1M.ts.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return (row.open + row.close) / Decimal("2")


async def _backfill_fills(session, ids: dict[str, uuid.UUID]) -> int:
    """Orders status=filled tanpa Fill → Lineage + Fill + TcaRecord."""
    orders = (
        await session.execute(
            select(Order).where(Order.status == "filled")
        )
    ).scalars().all()

    existing = set(
        (await session.execute(select(Fill.lineage_id))).scalars().all()
    )
    done = 0
    for order in orders:
        # order_id bukan lineage_id — buat lineage baru per order (dedupe via fill.order_id? tidak ada kolom)
        # gunakan deterministic lineage_id = uuid5(order_id) agar idempotent
        lin_id = uuid.uuid5(uuid.NAMESPACE_URL, f"lumine:order:{order.order_id}")
        if lin_id in existing:
            continue

        ts = order.updated_at or order.created_at
        benchmark = await _arrival_mid(session, order.symbol, ts)
        if benchmark is None:
            continue  # belum ada bars di ts itu — skip backfill

        fill_price = order.price or benchmark
        slippage_bps = (
            (fill_price - benchmark) / benchmark * Decimal("10000")
            if benchmark
            else Decimal("0")
        )

        lineage = LineageRecord(
            lineage_id=lin_id,
            decision_ts=ts,
            book=BOOK,
            strategy_id=ids["strategy"],
            symbol=order.symbol,
            side=order.side,
            verdict="BUY" if order.side == "buy" else "SELL",
            size=order.volume,
            fill_price=fill_price,
            model_version_ids={"technical_analyst": ids["model"]},
            prompt_version_ids={
                "technical_analyst": ids["prompt:technical_analyst"],
                "macro_analyst": ids["prompt:macro_analyst"],
                "risk_officer": ids["prompt:risk_officer"],
            },
            policy_version_id=ids["policy"],
            feature_version_id=ids["feature"],
            regime_version_id=ids["regime"],
            calendar_version_id=ids["calendar"],
        )
        session.add(lineage)
        await session.flush()

        fill = Fill(
            lineage_id=lin_id,
            ts=ts,
            symbol=order.symbol,
            side="BUY" if order.side == "buy" else "SELL",
            size=order.volume,
            price=fill_price,
            commission=Decimal("0"),
            slippage=slippage_bps,
            book=BOOK,
            strategy_id=ids["strategy"],
        )
        session.add(fill)
        await session.flush()

        tca = TcaRecord(
            fill_id=fill.fill_id,
            benchmark_price=benchmark,
            slippage_bps=slippage_bps,
            slippage_cost_ccy=slippage_bps / Decimal("10000") * order.volume * benchmark,
            decision_ts=ts,
            regime_id="regime-v1",
            broker_id="hfm",
            account_id="235158357",
            benchmark_source="arrival_mid",
        )
        session.add(tca)
        existing.add(lin_id)
        done += 1

    await session.commit()
    return done


async def main() -> None:
    async with get_sessionmaker()() as session:
        ids = await _seed_registry(session)
        print(f"[SEED] registry OK: model={ids['model']} strategy={ids['strategy']} policy={ids['policy']}")
        n = await _backfill_fills(session, ids)
        print(f"[SEED] TCA backfill: {n} fills + tca_records dibuat")
    print("[SEED] selesai")


if __name__ == "__main__":
    asyncio.run(main())
