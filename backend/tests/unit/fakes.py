# Copyright (c) 2026 Lumine. All rights reserved.
"""Shared fakes for decision-engine unit tests.

A scripted ``FakeGateway`` stands in for the real ``Gateway`` (which
talks to 9router): each test supplies a handler ``str -> str`` (request
idempotency key -> raw model output), and the fake records every request
for assertions. The prompt registry is loaded once from the real
``docs/prompts/`` directory (hash-verified) so tests exercise the true
prompt text and schema files.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from lumine.llm_gateway.budget import BudgetDecision
from lumine.llm_gateway.gateway import GatewayResult
from lumine.llm_gateway.types import GatewayResponse
from lumine.prompts.registry import Registry, load_registry
from lumine.shared.config import get_settings

if TYPE_CHECKING:
    from lumine.llm_gateway.types import RouterRequest

# Scripted response handler: (request) -> raw model output text.
ResponseHandler = Callable[["RouterRequest"], str]


class FakeGateway:
    """In-memory Gateway substitute that records calls and scripts output."""

    def __init__(self, handler: ResponseHandler | None = None) -> None:
        """Configure with an optional response handler (defaults to ``{}``)."""
        self.handler: ResponseHandler = handler or (lambda _request: "{}")
        self.calls: list[RouterRequest] = []

    def complete(
        self,
        request: RouterRequest,
        spend: dict[str, float] | None = None,
    ) -> GatewayResult:
        """Record ``request`` and return a scripted GatewayResponse."""
        return self._record(request)

    async def complete_async(
        self,
        request: RouterRequest,
        spend: dict[str, float] | None = None,
    ) -> GatewayResult:
        """Async variant (pipeline calls this from a running loop)."""
        return self._record(request)

    def _record(self, request: RouterRequest) -> GatewayResult:
        """Shared record-and-respond logic."""
        self.calls.append(request)
        content = self.handler(request)
        response = GatewayResponse(
            content=content,
            model_used="deepseek-v4",
            prompt_tokens=120,
            completion_tokens=40,
            total_tokens=160,
        )
        decision = BudgetDecision(action="allow", degraded=False, warn=False, reason="test")
        return GatewayResult(
            response=response,
            primary={"model": "deepseek-v4"},
            decision=decision,
            degraded=False,
            fallback_hops=0,
        )


@lru_cache(maxsize=1)
def _build_registry() -> Registry:
    """Load the real (hash-verified) prompt registry once per process."""
    return load_registry(get_settings().prompt_dir)


def make_registry() -> Registry:
    """Return the real (hash-verified) prompt registry, loaded once."""
    return _build_registry()


class _EmptyChainResult:
    """Chain-head query result for an empty (genesis) chain.

    Mirrors ``Result.first()`` returning ``None`` when the chained
    table has no rows yet, which ``hashchain.read_last_hash`` maps to
    the genesis hash.
    """

    def first(self) -> None:
        return None


class FakeSession:
    """In-memory AsyncSession stand-in for decision-cycle unit tests.

    Emulates the minimal surface the pipeline uses: ``add`` buffers
    objects, ``commit`` stamps server-generated ids (``lineage_id``,
    ``trace_id``, ``id``) so writers can return them, ``rollback`` is a
    no-op, and ``fail_commit`` simulates a DB outage for safe-state
    tests. No constraints are enforced — this is a decision-logic test
    double, not a database.
    """

    def __init__(
        self,
        *,
        fail_commit: bool = False,
        fail_on_lineage: bool = False,
        fail_backfill_commit: bool = False,
    ) -> None:
        """Configure failure injection modes for safe-state tests.

        ``fail_backfill_commit`` fails the commit *after* the lineage
        INSERT has flushed — i.e. on the orchestrator's atomic backfill
        commit. Used to prove A3 atomicity: the lineage row must be
        rolled back together with the failed backfill.
        """
        self.added: list[Any] = []
        self.fail_commit = fail_commit
        self.fail_on_lineage = fail_on_lineage
        self.fail_backfill_commit = fail_backfill_commit
        self.commits = 0
        self.executed: list[Any] = []
        self._flushed_lineage = False

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def _stamp_ids(self) -> None:
        """Stamp server-generated ids (mirrors gen_random_uuid on INSERT)."""
        for obj in self.added:
            for attr in ("lineage_id", "trace_id", "id"):
                if hasattr(obj, attr) and getattr(obj, attr) is None:
                    setattr(obj, attr, uuid.uuid4())

    async def flush(self) -> None:
        # Flush mirrors the real DB: server defaults (gen_random_uuid)
        # fire at INSERT/flush time, not commit. Used by ``write_lineage``
        # when ``commit=False`` so the orchestrator's atomic backfill
        # path sees the pre-generated lineage_id.
        if self.fail_commit:
            raise RuntimeError("simulated flush failure")
        if self.fail_on_lineage and any(
            hasattr(obj, "book") and hasattr(obj, "verdict") for obj in self.added
        ):
            raise RuntimeError("simulated lineage flush failure")
        self._stamp_ids()
        # Remember that a LineageRecord has flushed so the next commit
        # can simulate a backfill failure (A3 atomicity test).
        if any(hasattr(o, "book") and hasattr(o, "verdict") for o in self.added):
            self._flushed_lineage = True

    async def commit(self) -> None:
        # Distinguish a LineageRecord (has ``book``/``verdict``) from a
        # ReasoningTrace (also carries a ``lineage_id`` FK) so tests can
        # fail exactly at the write-before-dispatch gate.
        if self.fail_commit:
            raise RuntimeError("simulated commit failure")
        if self.fail_on_lineage and any(
            hasattr(obj, "book") and hasattr(obj, "verdict") for obj in self.added
        ):
            raise RuntimeError("simulated lineage commit failure")
        # A3 path: lineage INSERT flushed successfully, but the backfill
        # commit (the orchestrator's single commit) fails. The lineage
        # row must be rolled back, not left orphaned.
        if self.fail_backfill_commit and self._flushed_lineage:
            raise RuntimeError("simulated backfill commit failure")
        self._stamp_ids()
        self.commits += 1

    async def rollback(self) -> None:
        # A3: rollback must drop the flushed-but-uncommitted lineage row
        # so dispatch cannot see it (write-before-dispatch integrity).
        if self._flushed_lineage:
            self.added = [
                o for o in self.added if not (hasattr(o, "book") and hasattr(o, "verdict"))
            ]

    async def refresh(self, _obj: Any) -> None:
        return None

    async def execute(self, stmt: Any, _params: Any = None) -> Any:
        """Record SQLAlchemy statements and return an empty result.

        The production anchoring and backfill paths pass bound parameters as a
        second positional argument; accepting them keeps this fake aligned with
        ``AsyncSession.execute`` while unit tests remain database-free.
        """
        self.executed.append((stmt, _params))
        return _EmptyChainResult()


def analyst_json(**overrides: object) -> str:
    """Return a schema-valid ``analyst_output`` document as JSON text."""
    payload: dict[str, Any] = {
        "sub_role": "technical_analyst",
        "argument": "higher highs with EMA support",
        "confidence": 0.72,
        "bias": "bullish",
        "volatility": {
            "level": "medium",
            "expected_pre_event": "elevated before FOMC",
            "expected_post_event": "settles after release",
            "atr_note": "",
        },
        "plan": {
            "pre_news": "reduce size before high-impact event",
            "post_news": "react after release settles",
            "high_impact_within_24h": False,
        },
    }
    payload.update(overrides)
    return json.dumps(payload)


def ic_output_json(**overrides: object) -> str:
    """Return a schema-valid ``ic_output`` document as JSON text."""
    payload: dict[str, Any] = {
        "recommendation": "BUY",
        "confidence": 0.8,
        "summary": "two bullish, one neutral, one bearish; technical momentum supports long",
        "weights": {
            "technical_analyst": 0.3,
            "macro_analyst": 0.3,
            "news_analyst": 0.2,
            "smc_analyst": 0.2,
        },
        "dissent": "news analyst cautious on headlines",
    }
    payload.update(overrides)
    return json.dumps(payload)


def debate_json(**overrides: object) -> str:
    """Return a schema-valid ``debate_output`` document as JSON text."""
    payload: dict[str, Any] = {
        "summary": "news analyst withdrew objection after macro data; direction holds",
        "consensus_direction": "bullish",
    }
    payload.update(overrides)
    return json.dumps(payload)


def risk_assessment_json(**overrides: object) -> str:
    """Return a schema-valid ``risk_assessment`` document as JSON text."""
    payload: dict[str, Any] = {
        "veto": False,
        "regime_bucket": "trending",
        "risk_notes": "no material qualitative risk",
    }
    payload.update(overrides)
    return json.dumps(payload)


def proposal_json(**overrides: object) -> str:
    """Return a schema-valid ``proposal_v1`` document as JSON text."""
    payload: dict[str, Any] = {
        "version": "v1",
        "decision_ts": "2026-08-05T00:00:00Z",
        "symbol": "XAUUSD",
        "action": "BUY",
        "confidence": 0.78,
        "reasoning": "committee and technicals align",
        "debate_held": False,
        "overrode_ic": False,
        "side": "BUY",
        "size": 0.05,
        "stop_loss": 4340.0,
        "take_profit": 4390.0,
        "analyst_inputs": [
            {
                "sub_role": "technical_analyst",
                "argument": "higher highs",
                "confidence": 0.72,
                "bias": "bullish",
            }
        ],
        "ic_output": {
            "recommendation": "BUY",
            "confidence": 0.8,
            "summary": "bullish",
            "weights": {
                "technical_analyst": 0.4,
                "macro_analyst": 0.2,
                "news_analyst": 0.2,
                "smc_analyst": 0.2,
            },
            "dissent": "",
        },
        "policy_version_id": str(uuid.uuid4()),
        "model_version_ids": {
            "technical_analyst": str(uuid.uuid4()),
            "macro_analyst": str(uuid.uuid4()),
            "news_analyst": str(uuid.uuid4()),
            "smc_analyst": str(uuid.uuid4()),
            "ic_forum": str(uuid.uuid4()),
            "cio_proposer": str(uuid.uuid4()),
        },
        "prompt_version_ids": {
            "technical_analyst": str(uuid.uuid4()),
            "macro_analyst": str(uuid.uuid4()),
            "news_analyst": str(uuid.uuid4()),
            "smc_analyst": str(uuid.uuid4()),
            "ic_forum": str(uuid.uuid4()),
            "cio_proposer": str(uuid.uuid4()),
        },
    }
    payload.update(overrides)
    return json.dumps(payload)


__all__ = (
    "FakeGateway",
    "FakeSession",
    "analyst_json",
    "debate_json",
    "ic_output_json",
    "make_registry",
    "proposal_json",
    "risk_assessment_json",
)
