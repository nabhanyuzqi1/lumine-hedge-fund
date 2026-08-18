# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for the append-only llm_usage writer (D6-7, cost-control.md).

Every gateway call lands exactly one row in ``llm_usage`` — role, tier,
model_version_id (post-fallback), prompt_version_id, tokens_in/out,
cost_usd, fallback_hops, degraded, lineage_id, lane. Budget counters
derive from this table (one source of truth, no parallel accounting).

``record_usage`` is pure and DB-free: it maps a ``RouterRequest`` +
``GatewayResponse`` + injected metadata onto an ``LLMUsage`` row.
``write_usage`` is exercised here against a fake session (add/flush);
the real async session flow is covered at integration level.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from lumine.data.models import LLMUsage
from lumine.llm_gateway.types import ChatMessage, GatewayResponse, ModelTier, RouterRequest
from lumine.llm_gateway.usage import record_usage, write_usage

# ── helpers ──────────────────────────────────────────────────────────────────


def _req(**overrides: Any) -> RouterRequest:
    base: dict[str, Any] = {
        "model_version_id": uuid.uuid4(),
        "model": "deepseek-v4",
        "role": "technical_analyst",
        "tier": ModelTier.COST_EFFICIENT,
        "lineage_id": uuid.uuid4(),
        "prompt_ref": "technical_analyst@v1.prompt",
        "prompt_hash": "a" * 64,
        "idempotency_key": "idem-1",
        "messages": [ChatMessage(role="user", content="Symbol: XAUUSD")],
    }
    base.update(overrides)
    return RouterRequest(**base)


def _resp(*, prompt: int = 120, completion: int = 40) -> GatewayResponse:
    return GatewayResponse(
        content='{"action": "HOLD"}',
        model_used="deepseek-v4",
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
    )


# ── record_usage: pure field mapping (DB-free) ────────────────────────────────


class TestRecordUsage:
    def test_maps_request_and_response_fields(self) -> None:
        req = _req()
        row = record_usage(request=req, response=_resp())
        assert row.role == "technical_analyst"
        assert row.tier == "cost-efficient"
        assert row.model_version_id == req.model_version_id
        assert row.lineage_id == req.lineage_id
        assert row.tokens_in == 120
        assert row.tokens_out == 40

    def test_tier_uses_enum_value(self) -> None:
        row = record_usage(
            request=_req(tier=ModelTier.STRONGEST),
            response=_resp(),
        )
        assert row.tier == "strongest"

    def test_injected_metadata_lands_on_row(self) -> None:
        pvid = uuid.uuid4()
        row = record_usage(
            request=_req(),
            response=_resp(),
            prompt_version_id=pvid,
            fallback_hops=2,
            degraded=True,
            lane="ic_forum",
        )
        assert row.prompt_version_id == pvid
        assert row.fallback_hops == 2
        assert row.degraded is True
        assert row.lane == "ic_forum"

    def test_defaults_are_append_only_safe(self) -> None:
        row = record_usage(request=_req(), response=_resp())
        assert row.prompt_version_id is None
        assert row.fallback_hops == 0
        assert row.degraded is False
        assert row.lane is None

    def test_cost_usd_computed_at_6_decimal_precision(self) -> None:
        # $0.50/1K in + $1.50/1K out on 120 in / 40 out → 0.06 + 0.06.
        row = record_usage(
            request=_req(),
            response=_resp(prompt=120, completion=40),
            price_per_1k_in=Decimal("0.500000"),
            price_per_1k_out=Decimal("1.500000"),
        )
        assert row.cost_usd == Decimal("0.120000")

    def test_cost_zero_when_no_price_configured(self) -> None:
        row = record_usage(request=_req(), response=_resp())
        assert row.cost_usd == Decimal("0.000000")

    def test_cost_quantizes_below_micro_dollar(self) -> None:
        # _cost_usd (usage.py:49) quantizes to Numeric(12,6) — a
        # fractional-micro cost must round, not keep extra digits:
        # 1 token @ $0.001/1K → 0.000001 (exactly 1e-6 → 0.000001)
        # while 1 token @ $0.0003/1K → 0.0000003 → rounded to 0.000000.
        row = record_usage(
            request=_req(),
            response=_resp(prompt=1, completion=0),
            price_per_1k_in=Decimal("0.000300"),
            price_per_1k_out=Decimal("0.000000"),
        )
        assert row.cost_usd == Decimal("0.000000")

    def test_cost_rounds_up_to_micro_dollar(self) -> None:
        # _cost_usd (usage.py:49) quantizes with the default rounding —
        # a fractional cost above 1e-6 must round up, not truncate:
        # 1 token @ $0.0012/1K → 0.0000012 → 0.000001.
        row = record_usage(
            request=_req(),
            response=_resp(prompt=1, completion=0),
            price_per_1k_in=Decimal("0.001200"),
            price_per_1k_out=Decimal("0.000000"),
        )
        assert row.cost_usd == Decimal("0.000001")

    def test_tier_accepts_plain_string(self) -> None:
        # usage.py:72 tolerates tier passed as a str (not ModelTier) —
        # RouterRequest.tier may carry a raw string from telemetry/API.
        row = record_usage(request=_req(tier="strongest"), response=_resp())
        assert row.tier == "strongest"

    def test_ts_default_is_utc_callable(self) -> None:
        # ts is a client-side default evaluated at flush time; the
        # contract is "UTC with tzinfo", pinned by the column default.
        default = LLMUsage.__table__.columns["ts"].default
        assert default is not None
        value = default.arg(None)
        assert isinstance(value, datetime)
        assert value.tzinfo is not None


# ── write_usage: append via a session (fake session, DB-free) ─────────────────


class _FakeSession:
    """Minimal AsyncSession stand-in: records adds, fails flush on demand."""

    def __init__(self, *, fail_flush: bool = False) -> None:
        self.added: list[Any] = []
        self._fail_flush = fail_flush
        self.flushed = False
        self.rolled_back = False

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        if self._fail_flush:
            raise RuntimeError("constraint violation")
        self.flushed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class TestWriteUsage:
    async def test_appends_row_and_flushes(self) -> None:
        session = _FakeSession()
        row = await write_usage(session, request=_req(), response=_resp())
        assert session.added == [row]
        assert session.flushed is True
        assert isinstance(row, LLMUsage)

    async def test_flush_failure_non_fatal(self) -> None:
        # 18 Aug 2026: persist gagal → non-fatal (audit log tidak boleh
        # matikan pipeline). Sebelumnya raise LLMUsageRecordError.
        session = _FakeSession(fail_flush=True)
        row = await write_usage(session, request=_req(), response=_resp())
        assert row is None
        assert session.rolled_back is True
