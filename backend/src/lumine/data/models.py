"""SQLAlchemy ORM models for all Phase 3/5 tables.

Physical schema (Phase 5) is expressed as __table_args__ on the logical
schema (Phase 3). Immutable tables carry no UPDATE/DELETE in their
docstrings — the model is for INSERT + SELECT only.
"""

# Copyright (c) 2026 Lumine. All rights reserved.

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base for all Lumine ORM models."""

    type_annotation_map = {
        uuid.UUID: UUID(as_uuid=True),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Registry tables (versioned, append-only, never deleted)
# ═══════════════════════════════════════════════════════════════════════════════


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("sandbox", "staging", "production", "retired", name="registry_status"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str] = mapped_column(Text, nullable=False)
    context_window: Mapped[int] = mapped_column(BigInteger, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint("version"),
        Index("ix_model_versions_status", "status"),
    )


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("sandbox", "staging", "production", "retired", name="registry_status"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sub_role: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_hash: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_ref: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (UniqueConstraint("version"),)


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("sandbox", "staging", "production", "retired", name="registry_status"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    name: Mapped[str] = mapped_column(Text, nullable=False)
    book: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    entry_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    exit_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("strategy_versions.id"))

    __table_args__ = (UniqueConstraint("version"),)


class PolicyVersion(Base):
    __tablename__ = "policy_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("sandbox", "staging", "production", "retired", name="registry_status"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    scope: Mapped[str] = mapped_column(Text, nullable=False)
    policy_hash: Mapped[str] = mapped_column(Text, nullable=False)
    policy: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("version"),)


# ═══════════════════════════════════════════════════════════════════════════════
# Extended registry tables (ADR-0020, ADR-0034, ADR-0037)
# ═══════════════════════════════════════════════════════════════════════════════


class FeatureVersion(Base):
    """Versioned feature definition. ADR-0020 — feature-store-contract."""

    __tablename__ = "feature_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("sandbox", "staging", "production", "retired", name="registry_status"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    warmup_required: Mapped[int] = mapped_column(nullable=False)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("feature_versions.id"))

    __table_args__ = (
        UniqueConstraint("name", "version"),
        Index("ix_feature_versions_name", "name"),
    )


class RegimeVersion(Base):
    """Versioned regime classifier definition. ADR-0034 — regime-model."""

    __tablename__ = "regime_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("sandbox", "staging", "production", "retired", name="registry_status"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    name: Mapped[str] = mapped_column(Text, nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    buckets: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("version"),)


class CalendarVersion(Base):
    """Versioned market calendar definition. ADR-0037 — market-calendar-contract."""

    __tablename__ = "calendar_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("sandbox", "staging", "production", "retired", name="registry_status"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    name: Mapped[str] = mapped_column(Text, nullable=False)
    holidays: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    sessions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    economic_events: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (UniqueConstraint("version"),)


# ═══════════════════════════════════════════════════════════════════════════════
# Decision table (append-only, forever)
# ═══════════════════════════════════════════════════════════════════════════════


class LineageRecord(Base):
    """Append-only decision record. Immutable — INSERT only, no UPDATE/DELETE.

    Carries all 7 version pins required by ARCHITECTURE.md Invariant #1:
    model (per-agent map), prompt (per-agent map), policy, strategy,
    feature, regime, and calendar. The per-agent model/prompt maps are
    JSONB; the remaining 5 are scalar FKs.
    """

    __tablename__ = "lineage_records"

    lineage_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    decision_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    book: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_versions.id"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    size: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    fill_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 5))

    # ── Per-agent version pins (JSONB) ────────────────────────────────────
    # model_version_ids: {"technical_analyst": UUID, "macro_analyst": UUID, ...}
    model_version_ids: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # prompt_version_ids: {"technical_analyst": UUID, "macro_analyst": UUID, ...}
    prompt_version_ids: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # ── Scalar version pins (FKs) ─────────────────────────────────────────
    # policy_version_id: the active policy (thresholds, debate trigger, routing)
    policy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policy_versions.id"),
        nullable=False,
    )
    # strategy_version_id: the strategy version that fired (denormalized for query)
    strategy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_versions.id"),
        nullable=False,
    )
    # feature_version_id: the feature set definition used (ADR-0020)
    feature_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("feature_versions.id"),
        nullable=True,
    )
    # regime_version_id: the regime classifier version used (ADR-0034)
    regime_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("regime_versions.id"),
        nullable=True,
    )
    # calendar_version_id: the market calendar version used (ADR-0037)
    calendar_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calendar_versions.id"),
        nullable=True,
    )

    # ── Payloads ──────────────────────────────────────────────────────────
    trigger: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    features: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    proposal: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    risk_context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # ── Tamper evidence (ADR-0017): hash-chained append-only row ─────────
    prev_hash: Mapped[str] = mapped_column(Text, nullable=False)
    self_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # Pins the canonical-JSON rules used to hash this row (ADR-0017);
    # must be set explicitly at write time so the pre-insert hash payload
    # byte-matches the verifier's re-read payload.
    canonicalization_version: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default=text("1"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )

    __table_args__ = (
        Index("ix_lineage_decision_ts", "decision_ts"),
        Index("ix_lineage_book_ts", "book", "decision_ts"),
        Index("ix_lineage_strategy", "strategy_id"),
        Index("ix_lineage_verdict", "verdict"),
        Index("ix_lineage_feature_version", "feature_version_id"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Execution state
# ═══════════════════════════════════════════════════════════════════════════════


class Fill(Base):
    """Append-only ledger. Immutable — INSERT only, no UPDATE/DELETE."""

    __tablename__ = "fills"

    fill_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    lineage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lineage_records.lineage_id"),
        nullable=False,
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    size: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 5), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    slippage: Mapped[Decimal] = mapped_column(Numeric(20, 5), nullable=False)
    book: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    # B1: deal MT5 → fills (migrasi c02228f00014); dedupe snapshot deals.
    mt5_ticket: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )

    __table_args__ = (
        Index("ix_fills_lineage", "lineage_id"),
        Index("ix_fills_ts", "ts"),
    )


class Order(Base):
    """Order lifecycle record (B-05: physical table, previously demo-only)."""

    __tablename__ = "orders"

    order_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    portfolio_id: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    order_type: Mapped[str] = mapped_column(Text, nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 5))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    filled_volume: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=Decimal(0))
    rejected_reason: Mapped[str | None] = mapped_column(Text)
    mt5_ticket: Mapped[int | None] = mapped_column(BigInteger)  # ticket MT5 hasil FILLED (migrasi 0013)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_orders_portfolio_status", "portfolio_id", "status"),
        Index("ix_orders_symbol_created", "symbol", "created_at"),
    )


class Position(Base):
    """Derived current state. Mutated on each fill. Rebuildable from fills."""

    __tablename__ = "positions"

    position_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    book: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    size: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    avg_entry: Mapped[Decimal] = mapped_column(Numeric(20, 5), nullable=False)
    sl: Mapped[Decimal | None] = mapped_column(Numeric(20, 5))
    tp: Mapped[Decimal | None] = mapped_column(Numeric(20, 5))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    opened_lineage: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lineage_records.lineage_id"),
        nullable=True,  # posisi MT5 sync (B1) tidak punya lineage pipeline
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    # MT5 ticket (sync B1: posisi open dari MT5 di-identifikasi via ticket;
    # posisi dari fills tidak punya ticket — nullable).
    mt5_ticket: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # B8: unrealized P&L real dari MT5 (broker contract spec) per snapshot.
    mt5_profit: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)

    __table_args__ = (
        Index(
            "ix_positions_open",
            "symbol",
            "book",
            "strategy_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )


class ProcessedCommand(Base):
    """Idempotency gate. One row per dispatched command."""

    __tablename__ = "processed_commands"

    lineage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lineage_records.lineage_id"),
        primary_key=True,
    )
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    result: Mapped[str] = mapped_column(Text, nullable=False)
    replay_count: Mapped[int] = mapped_column(nullable=False, default=0)
    last_replay_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrderStateTransition(Base):
    """Append-only audit log of every order state transition."""

    __tablename__ = "order_state_transitions"

    transition_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    order_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    previous_state: Mapped[str] = mapped_column(String(20), nullable=False)
    new_state: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(100))
    reason: Mapped[str | None] = mapped_column(Text)
    decision_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    lineage_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lineage_records.lineage_id"),
        nullable=False,
    )
    mt5_ticket: Mapped[int | None] = mapped_column(BigInteger)
    transition_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        Index("ix_order_transitions_order_id", "order_id"),
        Index("ix_order_transitions_lineage", "lineage_record_id"),
        Index("ix_order_transitions_decision_ts", "decision_ts"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Market data (append-only, partitioned)
# ═══════════════════════════════════════════════════════════════════════════════


class Tick(Base):
    """Per-tick market data. Daily partitions, 7-day retention.

    PK is (ts, symbol) — the partition key (ts) is part of the composite
    primary key, which is required for unique constraints on partitioned
    tables. This prevents duplicate ticks on reconnect/replay.
    """

    __tablename__ = "ticks"

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    bid: Mapped[Decimal] = mapped_column(Numeric(20, 5), nullable=False)
    ask: Mapped[Decimal] = mapped_column(Numeric(20, 5), nullable=False)
    last: Mapped[Decimal] = mapped_column(Numeric(20, 5), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_ticks_symbol_ts", "symbol", "ts"),
        {"postgresql_partition_by": "RANGE (ts)"},
    )


def _make_bar_table(
    tablename: str,
    *,
    partitioned: bool = False,
    _partition_unit: str | None = None,
) -> type[Base]:
    """Create OHLCV bar tables.

    Each bar table shares the same column structure. Partitioned tables
    (bars_1m, bars_5m) use RANGE partitioning on ts with a composite
    (ts, symbol) primary key. Non-partitioned tables (bars_1h, bars_4h,
    bars_1d) use ts alone as PK.
    """
    table_args: tuple[Index | dict[str, str], ...] = (
        Index(f"ix_{tablename}_ts_brin", "ts", postgresql_using="brin"),
        Index(f"ix_{tablename}_symbol_ts", "symbol", "ts"),
    )
    if partitioned:
        table_args = (*table_args, {"postgresql_partition_by": "RANGE (ts)"})

    attrs: dict[str, Any] = {
        "__tablename__": tablename,
        "__table_args__": table_args,
        "ts": mapped_column(
            DateTime(timezone=True),
            primary_key=True,
            nullable=False,
        ),
        "symbol": mapped_column(
            Text,
            primary_key=partitioned,
            nullable=False,
        ),
        "open": mapped_column(Numeric(20, 5), nullable=False),
        "high": mapped_column(Numeric(20, 5), nullable=False),
        "low": mapped_column(Numeric(20, 5), nullable=False),
        "close": mapped_column(Numeric(20, 5), nullable=False),
        "volume": mapped_column(Numeric(20, 2), nullable=False),
        "source": mapped_column(Text, nullable=False),
    }
    return type(tablename, (Base,), attrs)


Bars1M = _make_bar_table("bars_1m", partitioned=True)
Bars5M = _make_bar_table("bars_5m", partitioned=True)
# 18 Aug 2026: Bars15M ditambahkan — seed EA kirim 15m tapi mapping
# worker TIDAK punya model → 100k bars dibuang diam-diam (data hilang).
Bars15M = _make_bar_table("bars_15m", partitioned=False)
Bars1H = _make_bar_table("bars_1h", partitioned=False)
Bars4H = _make_bar_table("bars_4h", partitioned=False)
Bars1D = _make_bar_table("bars_1d", partitioned=False)


class Signal(Base):
    """Analyst signal dari decision cycle LLM (B5 — migrasi c02228f00015).

    Dipersist setiap cycle selesai (analyst output + IC decision) agar
    dashboard AI committee confidence / signals panel terisi real data.
    """

    __tablename__ = "signals"

    signal_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    run_id: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    analyst: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)  # bullish/bearish/neutral
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_signals_symbol_generated", "symbol", "generated_at"),
        Index("ix_signals_run", "run_id"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Operational tables
# ═══════════════════════════════════════════════════════════════════════════════


class LLMUsage(Base):
    """Append-only cost-accounting log for every LLM call (Phase 6 D6-7).

    Schema aligned to cost-control.md: role, tier, model_version_id
    (post-fallback), prompt_version_id, tokens_in/out, cost_usd,
    fallback_hops, degraded, lineage_id, lane. Budget counters derive
    from this table — one source of truth, no parallel accounting.
    """

    __tablename__ = "llm_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'cost-efficient'"))
    model_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_versions.id"),
        nullable=False,
    )
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompt_versions.id"),
        nullable=True,
    )
    tokens_in: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tokens_out: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    fallback_hops: Mapped[int] = mapped_column(nullable=False, default=0)
    degraded: Mapped[bool] = mapped_column(nullable=False, default=False)
    lane: Mapped[str | None] = mapped_column(Text)
    lineage_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lineage_records.lineage_id"))

    __table_args__ = (
        Index("ix_llm_usage_ts", "ts"),
        Index("ix_llm_usage_role", "role", "ts"),
        Index("ix_llm_usage_tier", "tier", "ts"),
        Index("ix_llm_usage_lane", "lane", "ts"),
        Index("ix_llm_usage_lineage", "lineage_id"),
    )


class ReasoningTrace(Base):
    """One row per LLM call — full prompt, raw response, hashes (Phase 7 D7-11).

    Written synchronously before the stage advances; write failure blocks
    advance. Permanent retention, append-only. Referenced by
    lineage_records.proposal.reasoning_trace_ids.
    """

    __tablename__ = "reasoning_traces"

    trace_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    workflow_run_id: Mapped[str] = mapped_column(Text, nullable=False)
    stage_run_id: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    model_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_versions.id"),
        nullable=False,
    )
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompt_versions.id"),
        nullable=True,
    )
    prompt_sent: Mapped[str] = mapped_column(Text, nullable=False)
    response_raw: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    prompt_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_hash: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    lineage_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lineage_records.lineage_id"))

    # Tamper evidence (ADR-0017): traces are a chained table.
    prev_hash: Mapped[str] = mapped_column(Text, nullable=False)
    self_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # Pins the canonical-JSON rules used to hash this row (ADR-0017);
    # must be set explicitly at write time so the pre-insert hash payload
    # byte-matches the verifier's re-read payload.
    canonicalization_version: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default=text("1"),
    )

    __table_args__ = (
        Index("ix_reasoning_traces_workflow", "workflow_run_id", "ts"),
        Index("ix_reasoning_traces_lineage", "lineage_id"),
        Index("ix_reasoning_traces_role", "role", "ts"),
    )


class MessageSchemaVersion(Base):
    """Versioned inter-agent message schemas (Phase 4 inter-agent-message-versioning).

    Registry of JSON-Schema (draft-07) per message family (analyst_output,
    ic_output, proposal, ...). Only `production` rows emitted at runtime;
    retired rows stay pinned in lineage forever.
    """

    __tablename__ = "message_schema_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    compatibility: Mapped[str] = mapped_column(Text, nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("message_schema_versions.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_message_schema_name_version"),
        Index("ix_message_schema_status", "status"),
    )


class WorkflowJournal(Base):
    """Append-only log of AutoGen workflow execution steps."""

    __tablename__ = "workflow_journal"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    workflow_id: Mapped[str] = mapped_column(Text, nullable=False)
    step_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column()
    input_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    output_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    lineage_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lineage_records.lineage_id"))

    # Tamper evidence (ADR-0017): journal is a chained table.
    prev_hash: Mapped[str] = mapped_column(Text, nullable=False)
    self_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # Pins the canonical-JSON rules used to hash this row (ADR-0017);
    # must be set explicitly at write time so the pre-insert hash payload
    # byte-matches the verifier's re-read payload.
    canonicalization_version: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default=text("1"),
    )

    __table_args__ = (
        Index("ix_wf_journal_ts", "ts"),
        Index("ix_wf_journal_workflow", "workflow_id", "ts"),
        Index("ix_wf_journal_status", "status"),
        Index("ix_wf_journal_lineage", "lineage_id"),
    )


class SecurityEvent(Base):
    """Append-only security audit log."""

    __tablename__ = "security_events"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))

    __table_args__ = (
        Index("ix_security_events_ts", "ts"),
        Index("ix_security_events_type", "event_type", "ts"),
        Index("ix_security_events_severity", "severity", "ts"),
    )


class AuditAnchor(Base):
    """Chain-head anchor (ADR-0017).

    Append-only record that pins the chain head (latest ``self_hash``)
    of a chained table, mirrored to the WORM sink (locally: append-only
    file directory; production: S3/B2 Object Lock Compliance — Phase 11).
    A mismatch between the DB copy and the WORM copy is a tamper signal.
    """

    __tablename__ = "audit_anchors"

    anchor_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    table_name: Mapped[str] = mapped_column(Text, nullable=False)
    anchor_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    anchored_hash: Mapped[str] = mapped_column(Text, nullable=False)
    anchored_row_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    anchored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    worm_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    worm_backend: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("table_name", "anchor_seq", name="uq_audit_anchors_table_seq"),
        Index("ix_audit_anchors_table_ts", "table_name", "anchored_at"),
    )


class AnchorState(Base):
    """Anchor-cadence bookkeeping (ADR-0017).

    One row per chained table tracks the anchor checkpoint: the last
    anchored row count and timestamp. Writers consult this after every
    chain append (inside the per-table chain lock) to decide whether
    the N-rows / M-minutes threshold has fired, so concurrent writers
    cannot double-anchor.
    """

    __tablename__ = "anchor_state"

    table_name: Mapped[str] = mapped_column(Text, primary_key=True)
    last_anchor_seq: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_row_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_anchor_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TcaRecord(Base):
    """Per-fill TCA (ADR-0040) — 1:1 with ``fills``.

    Benchmark is the arrival mid at ``decision_ts`` (DB-authoritative),
    clamped to the next session open when the market is closed. The
    record is the best-execution evidence (MiFID II spirit) and is
    retained permanently.
    """

    __tablename__ = "tca_records"

    tca_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    fill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fills.fill_id"),
        nullable=False,
    )
    benchmark_price: Mapped[Decimal] = mapped_column(Numeric(20, 5), nullable=False)
    slippage_bps: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    slippage_cost_ccy: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    decision_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    regime_id: Mapped[str] = mapped_column(Text, nullable=False)
    broker_id: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    # "arrival_mid" | "session_open" (ADR-0040 benchmark-integrity rule)
    benchmark_source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )

    __table_args__ = (
        UniqueConstraint("fill_id", name="uq_tca_fill"),
        Index("ix_tca_decision_ts", "decision_ts"),
        Index("ix_tca_broker_ts", "broker_id", "decision_ts"),
    )


class User(Base):
    """Internal session-auth user (replaces Authelia/Keycloak).

    Bootstrap users (superadmin/admin/trader) are seeded idempotently at
    startup from Settings; credentials are stored as PBKDF2-HMAC-SHA256
    (hash + per-user salt), never plaintext.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    password_salt: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )

    __table_args__ = (
        Index("ix_users_username", "username"),
    )
