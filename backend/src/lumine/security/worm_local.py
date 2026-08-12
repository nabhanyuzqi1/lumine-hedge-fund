# Copyright (c) 2026 Lumine. All rights reserved.
r"""Local WORM sink (ADR-0017) — append-only directory with hashed filenames.

Dev-time emulation of the S3/B2 Object Lock sink (Phase 11). Each anchor
payload is written to a file whose name is derived ONLY from the
table+seq (sha256 hex prefix), and the write is O_EXCL — an existing
file with the same name is a tamper signal and raises. The app role has
no delete path here; removing files requires operator access to the
host filesystem (the local analogue of the object-lock retention).

Layout::

    <root>/<table_name>/<sha256(f"{table}\\0{seq}")[0:16]>.anchor.json

The JSON payload is the ``AnchorPayload`` dataclass serialized with
sorted keys (mirrors the ADR-0017 canonical form for easy diffing).
``anchored_at`` is stored as ISO 8601 UTC with a Z suffix so a file
copy can be compared byte-exact against a DB re-read.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from lumine.security.worm_stub import AnchorPayload, WormSink

if TYPE_CHECKING:
    from pathlib import Path


def _key_for(table_name: str, anchor_seq: int) -> str:
    """Return the deterministic, content-independent object key.

    The key is derived from table+seq only, so a re-anchor of the same
    seq (different hash) collides and fails — write-once by construction.
    """
    digest = hashlib.sha256(f"{table_name}\0{anchor_seq}".encode()).hexdigest()
    return f"{digest[:16]}.anchor.json"


class LocalWorm(WormSink):
    """Append-only local directory sink (dev/test stand-in for object lock)."""

    backend = "local_append_only"

    def __init__(self, root: Path) -> None:  # noqa: D107 — WORM root dir is self-evident
        self.root = root

    def _path_for(self, object_key: str) -> Path:
        return self.root / object_key

    async def store(self, payload: AnchorPayload) -> None:  # noqa: D102
        path = self._path_for(payload.object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(
            {
                "table_name": payload.table_name,
                "anchor_seq": payload.anchor_seq,
                "anchored_hash": payload.anchored_hash,
                "anchored_row_id": payload.anchored_row_id,
                "row_count": payload.row_count,
                "anchored_at": payload.anchored_at,
                "object_key": payload.object_key,
                "backend": payload.backend,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            with path.open("xb") as fh:  # O_EXCL: refuse overwrite
                fh.write(data)
        except FileExistsError as exc:
            msg = f"worm object already exists (re-anchor of same seq!): {path}"
            raise RuntimeError(msg) from exc

    async def read(self, object_key: str) -> bytes:  # noqa: D102
        return self._path_for(object_key).read_bytes()

    async def exists(self, object_key: str) -> bool:  # noqa: D102
        return self._path_for(object_key).exists()


__all__ = ("LocalWorm", "_key_for")
