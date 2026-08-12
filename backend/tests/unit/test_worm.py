# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for the WORM sink interface, stub, and local implementation."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from lumine.security.worm_local import LocalWorm, _key_for
from lumine.security.worm_stub import AnchorPayload, NullWorm, WormSink


def _payload(table_name: str = "lineage_records", anchor_seq: int = 1) -> AnchorPayload:
    return AnchorPayload(
        table_name=table_name,
        anchor_seq=anchor_seq,
        anchored_hash="a" * 64,
        anchored_row_id="12345678-1234-5678-1234-567812345678",
        row_count=1000,
        anchored_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        object_key=_key_for(table_name, anchor_seq),
        backend="local_append_only",
    )


class TestKeyFor:
    def test_deterministic_and_content_independent(self) -> None:
        # Same table+seq always maps to the same key, regardless of hash.
        assert _key_for("lineage_records", 3) == _key_for("lineage_records", 3)
        assert _key_for("lineage_records", 3) != _key_for("lineage_records", 4)
        assert _key_for("lineage_records", 3) != _key_for("workflow_journal", 3)

    def test_key_shape(self) -> None:
        key = _key_for("lineage_records", 1)
        assert key.endswith(".anchor.json")
        # 16 hex chars from the sha256 prefix.
        assert len(key) == 16 + len(".anchor.json")


class TestWormSinkContract:
    def test_interface_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            WormSink()  # type: ignore[abstract]

    def test_nullworm_returns_stub_backend(self) -> None:
        assert NullWorm().backend == "object_lock_stub"

    @pytest.mark.parametrize("method", ["store", "read", "exists"])
    async def test_nullworm_raises_not_implemented(self, method: str) -> None:
        sink = NullWorm()
        arg = _payload() if method == "store" else "key"
        with pytest.raises(NotImplementedError, match="Phase 11"):
            await getattr(sink, method)(arg)


class TestLocalWorm:
    async def test_store_then_read_roundtrip(self, tmp_path) -> None:  # noqa: ANN001
        sink = LocalWorm(tmp_path)
        payload = _payload()
        await sink.store(payload)
        assert await sink.exists(payload.object_key)
        raw = await sink.read(payload.object_key)
        assert json.loads(raw)["anchored_hash"] == "a" * 64
        assert json.loads(raw)["backend"] == "local_append_only"

    async def test_store_is_write_once(self, tmp_path) -> None:  # noqa: ANN001
        sink = LocalWorm(tmp_path)
        payload = _payload()
        await sink.store(payload)
        with pytest.raises(RuntimeError, match="already exists"):
            await sink.store(payload)

    async def test_key_is_hashed_not_readable_table_name(self, tmp_path) -> None:  # noqa: ANN001
        sink = LocalWorm(tmp_path)
        await sink.store(_payload(table_name="lineage_records", anchor_seq=1))
        # Object key is a hash prefix, not "lineage_records".
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert "lineage_records" not in files[0].name

    async def test_read_missing_key_raises(self, tmp_path) -> None:  # noqa: ANN001
        sink = LocalWorm(tmp_path)
        with pytest.raises(FileNotFoundError):
            await sink.read("nope.anchor.json")