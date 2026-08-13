# Copyright (c) 2026 Lumine. All rights reserved.
"""Hash-chained audit journal core (ADR-0017, audit-tamper-evidence.md D12-7).

Each append-only audit row carries ``prev_hash`` and ``self_hash``:

- ``prev_hash``  = SHA-256 of the previous row's canonical JSON.
- ``self_hash``  = SHA-256 of ``prev_hash || canonical_json(self without self_hash)``.
- The first row in a chain has ``prev_hash = SHA-256("GENESIS")``.

Chains are per-table and independent, so a write to one table does not
stall another. Canonicalization follows the ADR-0017 byte-exact rules.

This module is pure and side-effect free: it computes hashes and
serialization only. Persistence (audit_anchors, WORM sink, role
hardening) lives in ``anchoring.py`` and migrations.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

# Version of the canonical-JSON rules (ADR-0017, ``canonicalization_version``
# column on chained rows). Bump only when the rules change; old rows must
# stay hashable with their recorded version.
CANONICALIZATION_VERSION = 1

# The chain-start marker; SHA-256("GENESIS") seeds every chain head.
GENESIS = "GENESIS"

# Tables that participate in tamper-evidence (ADR-0017 scope, V1).
CHAINED_TABLES = ("lineage_records", "workflow_journal", "reasoning_traces")

# Anchor cadence (audit-tamper-evidence.md: N rows or M minutes, first to fire).
ANCHOR_EVERY_N_ROWS = 1000
ANCHOR_EVERY_M_MINUTES = 5

# Per-table ordering for chain reads. Chains are ordered by the row's
# write clock column, with the table PK as deterministic tie-break —
# the same order the verifier replays.
CHAIN_ORDER_COLUMN: dict[str, str] = {
    "lineage_records": "created_at",
    "workflow_journal": "ts",
    "reasoning_traces": "ts",
}
CHAIN_PK_COLUMN: dict[str, str] = {
    "lineage_records": "lineage_id",
    "workflow_journal": "id",
    "reasoning_traces": "trace_id",
}


def sha256_hex(payload: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of ``payload``."""
    return hashlib.sha256(payload).hexdigest()


def genesis_prev_hash() -> str:
    """Return the chain-start ``prev_hash``: SHA-256("GENESIS")."""
    return sha256_hex(GENESIS.encode("utf-8"))


def _canonicalize_ts(value: datetime) -> str:
    """Serialize a datetime to UTC ISO 8601 with Z suffix (ADR-0017).

    Naive timestamps are a hard error (the spec forbids them at write
    time — a naive value would serialize differently across processes).
    """
    if value.tzinfo is None:
        # Hard error: a naive timestamp would serialize with a local offset
        # depending on the host, making the hash non-replayable.
        raise ValueError("naive datetime in chained row — must be timezone-aware")  # noqa: EM101 — pattern used across bridge/types.py
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonicalize_value(value: Any) -> Any:  # noqa: ANN401 — JSONB payloads are arbitrary JSON
    """Recursively canonicalize a single value per ADR-0017.

    - JSONB values are recursively sorted by key (via ``json.dumps``
      ``sort_keys`` on the nested payload below).
    - NUMERIC serializes as plain decimal string with no trailing zeros
      and no scientific notation.
    - UUIDs serialize as lowercase canonical text.
    - NULL stays ``None`` (serializes as JSON ``null``).
    """
    if isinstance(value, Decimal):
        normalized = value.normalize()
        if normalized == 0:
            normalized = normalized.quantize(Decimal(1))
        return str(normalized)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return _canonicalize_ts(value)
    if isinstance(value, dict):
        return {str(k): _canonicalize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_canonicalize_value(v) for v in value]
    return value


def canonical_json(row: Mapping[str, Any]) -> bytes:
    """Canonical JSON of a row per ADR-0017.

    ``self_hash`` is excluded from the payload; every other column
    (including ``prev_hash``) is included. Output is deterministic and
    byte-exact: recursively canonicalized values, sorted keys,
    ``separators=(",", ":")``, ``default=str``, no trailing newline.
    """
    payload = {k: _canonicalize_value(v) for k, v in row.items() if k != "self_hash"}
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def compute_self_hash(prev_hash: str, row_without_self_hash: Mapping[str, Any]) -> str:
    """``self_hash`` = SHA-256(prev_hash || canonical_json(self)) per ADR-0017.

    The payload already carries ``prev_hash`` as a column (the spec's
    canonical JSON includes it, excluding only ``self_hash``); the
    explicit prepend is part of the formula.
    """
    return sha256_hex(prev_hash.encode("utf-8") + canonical_json(row_without_self_hash))


def orm_payload(record: Any) -> dict[str, Any]:  # noqa: ANN401 — SQLAlchemy mapped classes are not structurally typed
    """Serialize an ORM row to the canonical hash payload.

    Every persisted column except ``self_hash``/``prev_hash`` (which the
    hash formulas handle: ``prev_hash`` is injected by
    :func:`present_row_for_hash`, ``self_hash`` is excluded) is included,
    so the payload byte-matches a re-read row. The caller must have set
    every column the DB will persist — including Python-side defaults
    (``created_at``/``ts``) and ``canonicalization_version`` — before
    calling; a ``None`` here would hash differently from the re-read.
    """
    columns = [c.name for c in record.__table__.columns if c.name not in ("self_hash", "prev_hash")]
    return {name: getattr(record, name) for name in columns}


def present_row_for_hash(row: Mapping[str, Any], *, prev_hash: str) -> dict[str, Any]:
    """Build the dict whose canonical JSON feeds ``self_hash``.

    ``self_hash`` is excluded; ``prev_hash`` is injected as a column so
    the canonical payload matches what a re-read row would produce.
    """
    presented = {k: v for k, v in row.items() if k != "self_hash"}
    presented["prev_hash"] = prev_hash
    return presented


def compute_chain_pair(row: Mapping[str, Any], *, prev_hash: str) -> tuple[str, str]:
    """Return ``(prev_hash, self_hash)`` for a new row.

    The caller passes the chain head (from ``read_last_hash``) and a row
    that already carries every persisted column (including any
    pre-generated PK), so both hashes are final at insert time.
    """
    presented = present_row_for_hash(row, prev_hash=prev_hash)
    return prev_hash, compute_self_hash(prev_hash, presented)


# Stable per-table advisory lock keys (32-bit). Never changed; a different
# key would let two processes append concurrently and fork the chain.
_LOCK_KEY: dict[str, int] = {
    "lineage_records": 0x4C52_414E_01,
    "workflow_journal": 0x5746_4A52_02,
    "reasoning_traces": 0x5254_5241_03,
}
# The base table is never hashed into the chain payload (it is an anchor
# table, not a chained table), so it does not appear in _LOCK_KEY.


async def with_chain_lock[T](
    session: AsyncSession,
    table_name: str,
    callback: Callable[[], Awaitable[T]],
) -> T:
    """Serialize chain appends on ``table_name`` (per-table advisory lock).

    The chain head read + hash pair computation + INSERT must be atomic
    per table, otherwise two concurrent writers could read the same head
    and fork the chain (a spurious verifier break). The xact-level
    advisory lock is released at COMMIT/ROLLBACK and covers the whole
    caller transaction.
    """
    lock_key = _LOCK_KEY[table_name]  # KeyError = programming error
    # Static SQL literal (no interpolation) + bound parameter — S608-safe.
    sql = "SELECT pg_advisory_xact_lock(:key)"
    stmt = text(sql).bindparams(key=lock_key)
    await session.execute(stmt)
    return await callback()


async def append_chained(
    session: AsyncSession,
    table_name: str,
    row: Mapping[str, Any],
) -> tuple[str, str]:
    """Return ``(prev_hash, self_hash)`` for a chained append.

    Runs inside ``with_chain_lock``: reads the current chain head, computes
    the pair for ``row`` (which must already carry every persisted column,
    incl. ``canonicalization_version`` and any pre-generated PK), and
    returns the pair for the caller to store on the row before INSERT.
    """
    prev_hash = await read_last_hash(session, table_name)
    return compute_chain_pair(row, prev_hash=prev_hash)


async def read_last_hash(session: AsyncSession, table_name: str) -> str:
    """Return the chain head (last ``self_hash``) of ``table_name``.

    An empty chain returns the genesis hash. The row order matches the
    verifier's replay order (write clock column, PK tie-break).

    The table/column names are resolved exclusively from the module-level
    allowlists above (never from caller input), so the f-string SQL is
    injection-safe; ``# noqa: S608`` documents that the identifiers are
    not user-controlled.
    """
    if table_name not in CHAIN_ORDER_COLUMN:
        msg = f"not a chained table: {table_name!r}"
        raise ValueError(msg)
    order_col = CHAIN_ORDER_COLUMN[table_name]
    pk_col = CHAIN_PK_COLUMN[table_name]
    # Identifiers are resolved only from the module-level allowlists
    # (CHAIN_ORDER_COLUMN / CHAIN_PK_COLUMN) — never from caller input.
    sql = f"SELECT self_hash FROM {table_name} ORDER BY {order_col} DESC, {pk_col} DESC LIMIT 1"  # noqa: S608  # nosec B608 — identifiers from module-level allowlists only
    stmt = text(sql)
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        return genesis_prev_hash()
    return str(row[0])


async def read_chain_head(session: AsyncSession, table_name: str) -> tuple[str, uuid.UUID] | None:
    """Return ``(self_hash, row_id)`` of the chain head, or ``None`` when empty.

    The head is the anchor's target row: the last row in chain replay
    order (write clock column DESC, PK tie-break). Rows are
    table-allowlisted exactly like :func:`read_last_hash`.
    """
    if table_name not in CHAIN_ORDER_COLUMN:
        msg = f"not a chained table: {table_name!r}"
        raise ValueError(msg)
    order_col = CHAIN_ORDER_COLUMN[table_name]
    pk_col = CHAIN_PK_COLUMN[table_name]
    # Identifiers come only from the module-level allowlists (S608-safe).
    sql = (
        f"SELECT self_hash, {pk_col} FROM {table_name} "  # noqa: S608  # nosec B608 — identifiers from module-level allowlists only
        f"ORDER BY {order_col} DESC, {pk_col} DESC LIMIT 1"
    )
    result = await session.execute(text(sql))
    row = result.first()
    if row is None:
        return None
    return str(row[0]), row[1]


__all__ = (
    "ANCHOR_EVERY_M_MINUTES",
    "ANCHOR_EVERY_N_ROWS",
    "CANONICALIZATION_VERSION",
    "CHAINED_TABLES",
    "GENESIS",
    "append_chained",
    "canonical_json",
    "compute_chain_pair",
    "compute_self_hash",
    "genesis_prev_hash",
    "present_row_for_hash",
    "read_chain_head",
    "read_last_hash",
    "sha256_hex",
    "with_chain_lock",
)
