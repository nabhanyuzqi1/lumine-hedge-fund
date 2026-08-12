# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for the audit chain verifier (ADR-0017, J5)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path  # noqa: TC003
from typing import Any

import pytest

from lumine.security.hashchain import compute_chain_pair, genesis_prev_hash
from lumine.security.verifier import (
    ChainVerificationError,
    verify_rows,
    verify_worm_payload,
)


def _row(*, prev_hash: str, value: int, row_id: uuid.UUID) -> dict[str, Any]:
    row = {
        "id": row_id,
        "ts": datetime(2026, 1, 1, 12, value, tzinfo=UTC),
        "value": Decimal(value),
        "prev_hash": prev_hash,
        "self_hash": "",
        "canonicalization_version": 1,
    }
    _, row["self_hash"] = compute_chain_pair(row, prev_hash=prev_hash)
    return row


def test_verify_rows_accepts_a_valid_chain() -> None:
    first = _row(prev_hash=genesis_prev_hash(), value=1, row_id=uuid.uuid4())
    second = _row(prev_hash=first["self_hash"], value=2, row_id=uuid.uuid4())

    result = verify_rows([first, second], table_name="workflow_journal")

    assert result.row_count == 2
    assert result.head_hash == second["self_hash"]
    assert result.failures == ()


def test_verify_rows_rejects_a_tampered_middle_row() -> None:
    first = _row(prev_hash=genesis_prev_hash(), value=1, row_id=uuid.uuid4())
    second = _row(prev_hash=first["self_hash"], value=2, row_id=uuid.uuid4())
    second["value"] = Decimal(999)

    result = verify_rows([first, second], table_name="workflow_journal")

    assert result.row_count == 2
    assert any("self_hash mismatch" in failure for failure in result.failures)


def test_verify_rows_rejects_a_broken_link() -> None:
    first = _row(prev_hash=genesis_prev_hash(), value=1, row_id=uuid.uuid4())
    second = _row(prev_hash="f" * 64, value=2, row_id=uuid.uuid4())

    result = verify_rows([first, second], table_name="workflow_journal")

    assert any("prev_hash mismatch" in failure for failure in result.failures)


def test_verify_rows_rejects_unsupported_canonicalization_version() -> None:
    first = _row(prev_hash=genesis_prev_hash(), value=1, row_id=uuid.uuid4())
    first["canonicalization_version"] = 99

    result = verify_rows([first], table_name="workflow_journal")

    assert any("unsupported canonicalization_version" in failure for failure in result.failures)


def test_verify_rows_rejects_out_of_order_rows() -> None:
    first = _row(prev_hash=genesis_prev_hash(), value=2, row_id=uuid.uuid4())
    second = _row(prev_hash=first["self_hash"], value=1, row_id=uuid.uuid4())

    result = verify_rows([first, second], table_name="workflow_journal")

    assert any("ordering violation" in failure for failure in result.failures)


def test_verify_worm_payload_requires_exact_anchor_payload(tmp_path: Path) -> None:
    payload = {
        "table_name": "workflow_journal",
        "anchor_seq": 1,
        "anchored_hash": "a" * 64,
        "anchored_row_id": str(uuid.uuid4()),
        "row_count": 2,
        "anchored_at": "2026-01-01T12:00:00Z",
        "object_key": "anchor.json",
        "backend": "local_append_only",
    }
    path = tmp_path / "anchor.json"
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))

    verify_worm_payload(
        path.read_bytes(),
        expected=payload,
        table_name="workflow_journal",
        anchor_seq=1,
    )

    path.write_text(path.read_text().replace("a" * 64, "b" * 64))
    with pytest.raises(ChainVerificationError, match="WORM payload mismatch"):
        verify_worm_payload(
            path.read_bytes(),
            expected=payload,
            table_name="workflow_journal",
            anchor_seq=1,
        )
