# Copyright (c) 2026 Lumine. All rights reserved.
"""WORM (write-once, read-many) sink interface + Object Lock stub (ADR-0017).

The anchor payload (chain head + row count) is written to two sinks:

1. ``audit_anchors`` (DB) — the queryable copy.
2. A WORM sink — the tamper-evident copy that the app role cannot
   overwrite or delete (D12-8 revokes UPDATE/DELETE/TRUNCATE).

Sprint 7 runs local-first: the real S3/B2 Object Lock backend is a
Phase 11 operator action (bucket creation + retention policy). This
module defines the interface both backends implement and ships a
``NullWorm`` stub whose ``backend`` value is ``"object_lock_stub"`` —
the wiring point Phase 11 replaces with a real object-lock client with
zero code change in ``anchoring.py``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


# Payload exchanged between the DB anchor row and the WORM sink.
# ``object_key`` is sink-specific: for the local sink it is the hashed
# filename; for an object-lock backend it is the bucket object key.
@dataclass(frozen=True)
class AnchorPayload:
    """One immutable anchor payload (ADR-0017 anchor record)."""

    table_name: str
    anchor_seq: int
    anchored_hash: str
    anchored_row_id: str
    row_count: int
    anchored_at: str  # ISO 8601 UTC (Z suffix)
    object_key: str
    backend: str


class WormSink(ABC):
    """Write-once sink contract (ADR-0017)."""

    backend: str  # constant per implementation

    @abstractmethod
    async def store(self, payload: AnchorPayload) -> None:
        """Persist ``payload``; must fail if the object key already exists.

        Write-once semantics are the sink's responsibility: an existing
        object with the same key raises, because re-anchoring the same
        seq with a different hash is a tamper signal.
        """

    @abstractmethod
    async def read(self, object_key: str) -> bytes:
        """Return the raw stored payload bytes for ``object_key``."""

    @abstractmethod
    async def exists(self, object_key: str) -> bool:
        """Return whether ``object_key`` is already stored."""


_STUB_MSG = "object-lock backend is a Phase 11 operator action"


class NullWorm(WormSink):
    """Object-lock backend stub (Phase 11 wires the real client)."""

    backend = "object_lock_stub"

    async def store(self, payload: AnchorPayload) -> None:  # noqa: D102
        raise NotImplementedError(_STUB_MSG)

    async def read(self, object_key: str) -> bytes:  # noqa: D102
        raise NotImplementedError(_STUB_MSG)

    async def exists(self, object_key: str) -> bool:  # noqa: D102
        raise NotImplementedError(_STUB_MSG)


__all__ = ("AnchorPayload", "NullWorm", "WormSink")
