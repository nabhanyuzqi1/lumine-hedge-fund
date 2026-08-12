# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for the hash-chain core (ADR-0017 canonicalization + pairing)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from lumine.security.hashchain import (
    CANONICALIZATION_VERSION,
    canonical_json,
    compute_chain_pair,
    compute_self_hash,
    genesis_prev_hash,
    present_row_for_hash,
    sha256_hex,
)


def _naive() -> datetime:
    # A naive datetime is the deliberately-invalid input under test.
    return datetime(2026, 1, 1, 12, 0, 0)  # noqa: DTZ001 — test fixture


class TestGenesis:
    def test_genesis_hash_is_sha256_of_literal(self) -> None:
        expected = sha256_hex(b"GENESIS")
        assert genesis_prev_hash() == expected
        # Matches the ADR-0017 contract: SHA-256("GENESIS"), 64 hex chars.
        assert len(genesis_prev_hash()) == 64


class TestCanonicalJson:
    def test_sorted_keys_and_compact_separators(self) -> None:
        row = {"b": 2, "a": 1}
        assert canonical_json(row) == b'{"a":1,"b":2}'

    def test_excludes_self_hash_column(self) -> None:
        row = {"a": 1, "self_hash": "x" * 64}
        assert canonical_json(row) == b'{"a":1}'

    def test_no_trailing_newline_or_whitespace(self) -> None:
        assert canonical_json({"a": 1}) == b'{"a":1}'
        assert canonical_json({"a": 1}).endswith(b"}")

    def test_naive_datetime_is_hard_error(self) -> None:
        with pytest.raises(ValueError, match="naive"):
            canonical_json({"ts": _naive()})

    def test_aware_datetime_serializes_utc_z(self) -> None:
        aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        assert canonical_json({"ts": aware}) == b'{"ts":"2026-01-01T12:00:00Z"}'

    def test_decimal_normalizes_without_trailing_zeros(self) -> None:
        row = {"price": Decimal("1.5000")}
        assert canonical_json(row) == b'{"price":"1.5"}'

    def test_decimal_zero_normalizes(self) -> None:
        row = {"qty": Decimal("0.0000")}
        assert canonical_json(row) == b'{"qty":"0"}'

    def test_uuid_lowercase(self) -> None:
        uid = uuid.UUID("12345678-1234-5678-1234-567812345678")
        assert canonical_json({"id": uid}) == (b'{"id":"12345678-1234-5678-1234-567812345678"}')

    def test_nested_jsonb_sorted_recursively(self) -> None:
        row = {"proposal": {"z": 1, "a": {"y": 2, "x": 1}}}
        assert canonical_json(row) == b'{"proposal":{"a":{"x":1,"y":2},"z":1}}'

    def test_null_serializes_as_literal_null(self) -> None:
        assert canonical_json({"opt": None}) == b'{"opt":null}'

    def test_deterministic_across_calls(self) -> None:
        row = {"b": Decimal("2.0"), "a": [1, {"c": 3}]}
        assert canonical_json(row) == canonical_json(row)


class TestComputeSelfHash:
    def test_formula_prev_hash_plus_canonical(self) -> None:
        prev = genesis_prev_hash()
        row = {"id": uuid.uuid4(), "ts": datetime(2026, 1, 1, tzinfo=UTC), "v": 1}
        payload = present_row_for_hash(row, prev_hash=prev)
        expected = sha256_hex(prev.encode("utf-8") + canonical_json(payload))
        assert compute_self_hash(prev, payload) == expected
        # And the pair helper agrees.
        p, s = compute_chain_pair(row, prev_hash=prev)
        assert p == prev
        assert s == expected

    def test_prev_hash_is_included_in_payload(self) -> None:
        prev = genesis_prev_hash()
        payload = present_row_for_hash({"a": 1}, prev_hash=prev)
        assert payload["prev_hash"] == prev
        assert canonical_json(payload) == b'{"a":1,"prev_hash":"' + prev.encode() + b'"}'

    def test_self_hash_excluded_from_payload(self) -> None:
        payload = present_row_for_hash({"a": 1, "self_hash": "x" * 64}, prev_hash="p")
        assert "self_hash" not in payload
        assert payload == {"a": 1, "prev_hash": "p"}

    def test_different_prev_hash_changes_self_hash(self) -> None:
        row = {"a": 1}
        _, s1 = compute_chain_pair(row, prev_hash="p1")
        _, s2 = compute_chain_pair(row, prev_hash="p2")
        assert s1 != s2

    def test_canonicalization_version_constant(self) -> None:
        # The version is stored on every chained row; a bump must be a
        # deliberate, reviewed change.
        assert CANONICALIZATION_VERSION == 1
