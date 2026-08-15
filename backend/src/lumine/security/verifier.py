# Copyright (c) 2026 Lumine. All rights reserved.
"""Read-only verification of ADR-0017 audit hash chains and WORM anchors."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from lumine.security.hashchain import (
    CANONICALIZATION_VERSION,
    CHAIN_ORDER_COLUMN,
    CHAIN_PK_COLUMN,
    CHAINED_TABLES,
    compute_chain_pair,
    genesis_prev_hash,
)
from lumine.shared.config import get_settings

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import Any


class ChainVerificationError(RuntimeError):
    """Raised when an audit chain or WORM anchor is structurally invalid."""


@dataclass(frozen=True)
class VerificationResult:
    """Verification outcome for one chained table."""

    table_name: str
    row_count: int
    head_hash: str | None
    failures: tuple[str, ...]

    @property
    def valid(self) -> bool:
        """Return whether the table has no chain verification failures."""
        return not self.failures


def _row_mapping(row: Any) -> dict[str, Any]:
    mapping = row._mapping
    return dict(mapping)


def verify_rows(rows: Sequence[Mapping[str, Any]], *, table_name: str) -> VerificationResult:
    """Verify ordered chain rows without mutating the database."""
    if table_name not in CHAINED_TABLES:
        message = f"unsupported chained table: {table_name}"
        raise ValueError(message)

    previous = genesis_prev_hash()
    failures: list[str] = []
    head_hash: str | None = None
    previous_order: tuple[str, str] | None = None
    order_column = CHAIN_ORDER_COLUMN[table_name]
    pk_column = CHAIN_PK_COLUMN[table_name]

    for position, row in enumerate(rows, start=1):
        row_id = str(row.get(pk_column, row.get("id", position)))
        version = row.get("canonicalization_version", CANONICALIZATION_VERSION)
        if version != CANONICALIZATION_VERSION:
            failures.append(
                f"{table_name}[{position}] unsupported canonicalization_version "
                f"for {row_id}: expected {CANONICALIZATION_VERSION}, got {version}"
            )
        order_key = (str(row.get(order_column, "")), row_id)
        if previous_order is not None and order_key <= previous_order:
            failures.append(
                f"{table_name}[{position}] ordering violation for {row_id}: "
                f"expected after {previous_order[1]}"
            )
        previous_order = order_key
        stored_prev = str(row.get("prev_hash", ""))
        stored_self = str(row.get("self_hash", ""))
        if stored_prev != previous:
            failures.append(
                f"{table_name}[{position}] prev_hash mismatch for {row_id}: "
                f"expected {previous}, got {stored_prev}"
            )

        _, expected_self = compute_chain_pair(row, prev_hash=stored_prev)
        if stored_self != expected_self:
            failures.append(
                f"{table_name}[{position}] self_hash mismatch for {row_id}: "
                f"expected {expected_self}, got {stored_self}"
            )
        previous = stored_self
        head_hash = stored_self

    return VerificationResult(
        table_name=table_name,
        row_count=len(rows),
        head_hash=head_hash,
        failures=tuple(failures),
    )


def verify_worm_payload(
    raw: bytes,
    *,
    expected: dict[str, Any],
    table_name: str,
    anchor_seq: int,
) -> None:
    """Verify canonical JSON and identity of one WORM anchor payload."""
    try:
        actual = json.loads(raw)
    except json.JSONDecodeError as exc:
        message = "WORM payload is not valid JSON"
        raise ChainVerificationError(message) from exc

    if actual != expected:
        message = f"WORM payload mismatch for {table_name}/{anchor_seq}"
        raise ChainVerificationError(message)
    canonical = json.dumps(actual, sort_keys=True, separators=(",", ":")).encode()
    if canonical != raw:
        message = f"WORM payload is not canonical JSON for {table_name}/{anchor_seq}"
        raise ChainVerificationError(message)


async def _read_table(session: AsyncSession, table_name: str) -> list[dict[str, Any]]:
    order_column = CHAIN_ORDER_COLUMN[table_name]
    pk_column = CHAIN_PK_COLUMN[table_name]
    query = text(
        f"SELECT * FROM {table_name} ORDER BY {order_column} ASC, {pk_column} ASC"  # noqa: S608  # nosec B608 — identifiers from module-level allowlists only
    )
    result = await session.execute(query)
    return [_row_mapping(row) for row in result]


async def verify_database(database_url: str) -> tuple[VerificationResult, ...]:
    """Verify every chained table using a read-only session."""
    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    results: list[VerificationResult] = []
    try:
        async with session_factory() as session:
            for table in CHAINED_TABLES:
                rows = await _read_table(session, table)
                results.append(verify_rows(rows, table_name=table))
    finally:
        await engine.dispose()
    return tuple(results)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=get_settings().database_url,
        help="SQLAlchemy async PostgreSQL URL",
    )
    return parser


async def _run(database_url: str) -> int:
    results = await verify_database(database_url)
    output: list[str] = []
    for result in results:
        status = "PASS" if result.valid else "FAIL"
        output.append(
            f"{status} {result.table_name}: rows={result.row_count} head={result.head_hash or '-'}"
        )
        output.extend(f"  {failure}" for failure in result.failures)
    print("\n".join(output))
    return 0 if all(result.valid for result in results) else 1


def main() -> int:
    args = _build_parser().parse_args()
    try:
        return asyncio.run(_run(args.database_url))
    except Exception as exc:
        print(f"FAIL verifier: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
