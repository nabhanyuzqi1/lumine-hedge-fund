# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for anchor coordination (ADR-0017): cadence, seq, dual sink."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from lumine.security.anchoring import AnchorError, maybe_anchor
from lumine.security.worm_stub import AnchorPayload, NullWorm, WormSink

_TABLE = "lineage_records"
_HASH = "b" * 64
_ROW_ID = uuid.uuid4()


class _Result:
    """Minimal ``Result`` stand-in exposing ``first()``."""

    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def first(self) -> tuple[Any, ...] | None:
        return self._row


class _ScriptedSession:
    """AsyncSession stand-in that replays scripted execute results.

    ``results`` is consumed in order across the whole ``maybe_anchor``
    call: anchor_state SELECT, chain-head SELECT, then the state UPSERT.
    Exhausted results return an empty row (``None``), mirroring genesis.
    """

    def __init__(self, results: list[tuple[Any, ...] | None]) -> None:
        self.results = results
        self.added: list[Any] = []
        self.executed: list[Any] = []

    async def execute(self, stmt: Any, params: Any | None = None) -> _Result:  # noqa: ANN401
        self.executed.append(stmt)
        if self.results:
            return _Result(self.results.pop(0))
        return _Result(None)

    def add(self, obj: Any) -> None:  # noqa: ANN401
        self.added.append(obj)


class _FailingWorm(WormSink):
    """WORM sink that always fails — exercises the breach path."""

    backend = "test_failing"

    async def store(self, payload: AnchorPayload) -> None:  # noqa: D102
        raise RuntimeError("sink unavailable")

    async def read(self, object_key: str) -> bytes:  # noqa: D102, ARG002
        raise NotImplementedError

    async def exists(self, object_key: str) -> bool:  # noqa: D102, ARG002
        raise NotImplementedError


def _state_row(
    seq: int,
    count: int,
    ts: datetime,
) -> tuple[Any, ...]:
    return (_TABLE, seq, count, ts)


def _head_row() -> tuple[Any, ...]:
    return (_HASH, _ROW_ID)


def _now() -> datetime:
    return datetime.now(UTC)


class TestCadence:
    async def test_not_fired_within_both_thresholds(self) -> None:
        # diff = 500 rows (< 1000), elapsed < 5 min -> no anchor.
        session = _ScriptedSession([_state_row(1, 1000, _now())])
        await maybe_anchor(session, table_name=_TABLE, row_count=1500, worm=NullWorm())
        assert session.added == []

    async def test_fires_on_n_rows(self) -> None:
        # diff = 1000 rows -> N threshold trips regardless of time.
        session = _ScriptedSession([_state_row(1, 1000, _now()), _head_row()])
        await maybe_anchor(session, table_name=_TABLE, row_count=2000, worm=NullWorm())
        anchors = [o for o in session.added if type(o).__name__ == "AuditAnchor"]
        assert len(anchors) == 1
        assert anchors[0].anchor_seq == 2
        assert anchors[0].anchored_hash == _HASH
        assert anchors[0].anchored_row_id == _ROW_ID

    async def test_fires_on_m_minutes(self) -> None:
        # elapsed 6 min > 5 min -> M threshold trips with few rows.
        old_ts = _now() - timedelta(minutes=6)
        session = _ScriptedSession([_state_row(1, 1000, old_ts), _head_row()])
        await maybe_anchor(session, table_name=_TABLE, row_count=1005, worm=NullWorm())
        anchors = [o for o in session.added if type(o).__name__ == "AuditAnchor"]
        assert len(anchors) == 1

    async def test_first_anchor_fires_immediately(self) -> None:
        # No state row -> prev_ts None -> M threshold is "inf" -> anchor.
        session = _ScriptedSession([None, _head_row()])
        await maybe_anchor(session, table_name=_TABLE, row_count=10, worm=NullWorm())
        anchors = [o for o in session.added if type(o).__name__ == "AuditAnchor"]
        assert len(anchors) == 1
        assert anchors[0].anchor_seq == 1

    async def test_empty_chain_skips_anchor(self) -> None:
        # Cadence fired but the chain has no rows -> nothing to anchor.
        session = _ScriptedSession([None, None])
        await maybe_anchor(session, table_name=_TABLE, row_count=10, worm=NullWorm())
        assert session.added == []


class TestFailureSemantics:
    async def test_worm_failure_records_security_event_not_anchor(self) -> None:
        # A failed WORM write must never stall the chain: record a
        # chain_anchor_break event and let the caller transaction proceed.
        session = _ScriptedSession([None, _head_row()])
        await maybe_anchor(session, table_name=_TABLE, row_count=10, worm=_FailingWorm())
        events = [o for o in session.added if type(o).__name__ == "SecurityEvent"]
        assert len(events) == 1
        assert events[0].event_type == "chain_anchor_break"
        assert events[0].severity == "high"
        assert not [o for o in session.added if type(o).__name__ == "AuditAnchor"]

    async def test_nullworm_stub_is_not_a_breach(self) -> None:
        # NotImplementedError from the Phase 11 stub is expected: the DB
        # anchor still proceeds and no security event is recorded.
        session = _ScriptedSession([None, _head_row(), None])
        await maybe_anchor(session, table_name=_TABLE, row_count=10, worm=NullWorm())
        anchors = [o for o in session.added if type(o).__name__ == "AuditAnchor"]
        assert len(anchors) == 1
        assert not [o for o in session.added if type(o).__name__ == "SecurityEvent"]

    async def test_state_row_written_with_upsert(self) -> None:
        session = _ScriptedSession([None, _head_row(), None])
        await maybe_anchor(session, table_name=_TABLE, row_count=10, worm=NullWorm())
        upserts = [s.text for s in session.executed if "ON CONFLICT" in s.text]
        assert len(upserts) == 1
        assert "anchor_state" in upserts[0]

    async def test_anchor_error_propagates_min_max(self) -> None:
        # When the state write itself fails the caller must see an
        # AnchorError (safe state: never silently swallow a DB failure).
        class _FailingStateSession(_ScriptedSession):
            async def execute(self, stmt: Any, params: Any | None = None) -> _Result:  # noqa: ANN401
                if "ON CONFLICT" in stmt.text:
                    raise RuntimeError("simulated state write failure")
                return await super().execute(stmt, params)

        session = _FailingStateSession([None, _head_row(), None])
        with pytest.raises(AnchorError):
            await maybe_anchor(session, table_name=_TABLE, row_count=10, worm=NullWorm())