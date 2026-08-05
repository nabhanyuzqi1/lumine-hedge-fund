# Copyright (c) 2026 Lumine. All rights reserved.
"""Prompt registry loader (D3-8).

``docs/prompts/registry.yaml`` is the human-editable source of truth listing
every prompt version with its SHA-256 hash. The loader verifies each file's
actual hash against the manifest at startup — a mismatch is fatal (principle
#6: reproducibility; failures stop the pipeline, not hide it).

Database persistence (``prompt_versions`` upsert) is split into
:func:`upsert_prompt_versions` so the pure loader stays unit-testable without
a database. Call the upsert from app startup or integration tests.

Contract sources:
- ``docs/04-communication-and-prompts/prompt-storage.md`` — file layout, hash
  semantics, variables/output_schema contracts.
- ``docs/04-communication-and-prompts/prompt-versioning.md`` — loader contract.
- ``docs/15-implementation/sprint-evidence/sprint-3-decision-engine.md`` D3-8
  — registry.yaml manifest format.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

# Regex for ``{{ var }}`` / ``{{var}}`` / ``{{   var   }}`` placeholders.
# Liquid-style templating (prompt-storage.md:66). Matches one variable name
# per placeholder; whitespace inside the braces is tolerated.
_PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")

_REGISTRY_FILENAME = "registry.yaml"


class PromptRegistryError(Exception):
    """Base class for prompt registry failures."""


class MissingRegistryFileError(PromptRegistryError):
    """``registry.yaml`` is absent from the prompt directory."""


class MissingPromptFileError(PromptRegistryError):
    """A ``prompt_ref`` listed in the manifest does not exist on disk."""


class HashMismatchError(PromptRegistryError):
    """A prompt file's actual SHA-256 differs from ``expected_hash``.

    Fatal on load — a tampered prompt must never silently serve (D3-8).
    """


class PromptNotFoundError(PromptRegistryError):
    """``get_prompt`` asked for an unknown (sub_role, version)."""


class MissingVariableError(PromptRegistryError):
    """A template variable referenced in the body was not supplied.

    Missing variables are a validation failure, not a silent fallback
    (prompt-storage.md:95).
    """


@dataclass(frozen=True, slots=True)
class PromptPins:
    """Immutable provenance pins stored alongside a rendered prompt.

    These are what get written to ``lineage_records.prompt_version_id`` and
    ``reasoning_traces.prompt_hash`` so a decision is replayable: resolve the
    version, recompute the hash, reproduce the prompt. A divergent hash on
    replay = alert (the file changed under a pinned version).
    """

    sub_role: str
    version: str
    prompt_ref: str
    prompt_hash: str


@dataclass(frozen=True, slots=True)
class PromptBundle:
    """A loaded, hash-verified prompt ready for templating.

    ``text`` is the prompt *body* (frontmatter stripped) — what the LLM sees.
    ``pins.prompt_hash`` is the SHA-256 of the *full file bytes* (frontmatter
    included), so edits to either frontmatter or body are detectable drift.
    """

    text: str
    variables: list[str]
    output_schema: dict[str, object]
    pins: PromptPins
    model_tier_hint: str = "cost-efficient"


@dataclass(slots=True)
class _ManifestEntry:
    """Parsed row from registry.yaml before file verification."""

    sub_role: str
    version: str
    prompt_ref: str
    expected_hash: str
    model_tier_hint: str
    variables: list[str]
    output_schema_ref: str


@dataclass(slots=True)
class Registry:
    """In-memory map of verified prompts keyed by (sub_role, version)."""

    _bundles: dict[tuple[str, str], PromptBundle] = field(default_factory=dict)

    def register(self, bundle: PromptBundle) -> None:
        """Add or replace a prompt bundle keyed by (sub_role, version)."""
        key = (bundle.pins.sub_role, bundle.pins.version)
        self._bundles[key] = bundle

    def get_prompt(self, sub_role: str, version: str) -> PromptBundle:
        """Return the bundle for ``(sub_role, version)`` or raise if absent."""
        key = (sub_role, version)
        try:
            return self._bundles[key]
        except KeyError:
            msg = f"no prompt registered for {sub_role}@{version}"
            raise PromptNotFoundError(msg) from None

    def list_prompts(self) -> list[tuple[str, str]]:
        """Return every ``(sub_role, version)`` key currently registered."""
        return list(self._bundles)

    def __iter__(self) -> Iterator[PromptBundle]:
        """Iterate over all registered prompt bundles."""
        return iter(self._bundles.values())

    def __len__(self) -> int:
        """Return the number of registered prompt bundles."""
        return len(self._bundles)


# ── loading ───────────────────────────────────────────────────────────────────


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strip_frontmatter(raw: str) -> str:
    """Return the prompt body with a leading YAML frontmatter block removed.

    A frontmatter block starts at column 0 with ``---`` and ends at the next
    line that is exactly ``---``. If no well-formed block is present, the
    input is returned unchanged.
    """
    if not raw.startswith("---"):
        return raw
    lines = raw.splitlines(keepends=True)
    # lines[0] is the opening "---..."; find the closing fence.
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return "".join(lines[idx + 1 :]).lstrip("\n")
    # No closing fence — treat the whole thing as the body.
    return raw


def _load_output_schema(prompt_dir: Path, ref: str) -> dict[str, object]:
    """Resolve an ``output_schema_ref`` to a JSON-Schema dict.

    ``ref`` is relative to ``prompt_dir`` (e.g. ``schemas/analyst_output.json``).
    A bare JSON string (no path separator, parses as JSON) is also accepted so
    the manifest can inline a schema for tiny prompts.
    """
    if "/" not in ref and ref.lstrip().startswith("{"):
        return dict(json.loads(ref))
    schema_path = prompt_dir / ref
    return dict(json.loads(schema_path.read_text(encoding="utf-8")))


def _parse_manifest(prompt_dir: Path) -> list[_ManifestEntry]:
    reg_path = prompt_dir / _REGISTRY_FILENAME
    if not reg_path.is_file():
        msg = f"registry manifest not found: {reg_path}"
        raise MissingRegistryFileError(msg)
    data = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
    return [
        _ManifestEntry(
            sub_role=raw["sub_role"],
            version=raw["version"],
            prompt_ref=raw["prompt_ref"],
            expected_hash=raw["expected_hash"],
            model_tier_hint=raw.get("model_tier_hint", "cost-efficient"),
            variables=list(raw.get("variables", [])),
            output_schema_ref=raw["output_schema_ref"],
        )
        for raw in data.get("prompts", [])
    ]


def load_registry(prompt_dir: Path) -> Registry:
    """Parse ``registry.yaml``, verify every hash, build a :class:`Registry`.

    Verification is all-or-nothing: any missing file or hash mismatch raises
    before any prompt is served, so the registry is never in a half-loaded
    state (safe-state by default).
    """
    entries = _parse_manifest(prompt_dir)
    registry = Registry()
    for entry in entries:
        file_path = prompt_dir / entry.prompt_ref
        if not file_path.is_file():
            msg = f"prompt file missing for {entry.sub_role}@{entry.version}: {file_path}"
            raise MissingPromptFileError(msg)
        raw_bytes = file_path.read_bytes()
        actual_hash = _sha256_hex(raw_bytes)
        if actual_hash != entry.expected_hash:
            msg = (
                f"hash mismatch for {entry.sub_role}@{entry.version}: "
                f"expected {entry.expected_hash}, got {actual_hash}"
            )
            raise HashMismatchError(msg)
        body = _strip_frontmatter(raw_bytes.decode("utf-8"))
        output_schema = _load_output_schema(prompt_dir, entry.output_schema_ref)
        bundle = PromptBundle(
            text=body,
            variables=entry.variables,
            output_schema=output_schema,
            pins=PromptPins(
                sub_role=entry.sub_role,
                version=entry.version,
                prompt_ref=entry.prompt_ref,
                prompt_hash=actual_hash,
            ),
            model_tier_hint=entry.model_tier_hint,
        )
        registry.register(bundle)
    return registry


# ── templating ────────────────────────────────────────────────────────────────


def render(bundle: PromptBundle, variables: dict[str, object]) -> str:
    """Substitute ``{{ var }}`` placeholders with supplied values.

    Every placeholder in the body must be supplied — a missing variable is a
    fatal :class:`MissingVariableError`, never a silent literal leak
    (prompt-storage.md:95).
    """

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            msg = f"missing template variable: {name}"
            raise MissingVariableError(msg)
        return str(variables[name])

    return _PLACEHOLDER_RE.sub(_replace, bundle.text)


# ── database persistence ──────────────────────────────────────────────────────


async def upsert_prompt_versions(
    session: AsyncSession,
    registry: Registry,
) -> None:
    """Idempotently seed/update ``prompt_versions`` rows from the registry.

    A row is matched on ``version`` (unique constraint) and refreshed if the
    file hash changed. New rows are created with ``status='production'`` so
    the runtime loader only emits production prompts at runtime. Call this
    from app startup after :func:`load_registry` succeeds.

    Split from the pure loader so unit tests can exercise hashing/parsing
    without a database; the DB upsert is covered by integration tests.
    """
    # Local import keeps the loader importable without SQLAlchemy/asyncpg at
    # module load (e.g. for pure unit-test collection). Mirrors the lazy-import
    # pattern used in tests/integration/conftest.py.
    from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: PLC0415

    from lumine.data.models import PromptVersion  # noqa: PLC0415

    for bundle in registry:
        pins = bundle.pins
        stmt = pg_insert(PromptVersion).values(
            sub_role=pins.sub_role,
            version=pins.version,
            prompt_ref=pins.prompt_ref,
            prompt_hash=pins.prompt_hash,
            variables=dict.fromkeys(bundle.variables, None),
            output_schema=bundle.output_schema,
            status="production",
        )
        # On conflict (same version), refresh hash/ref/variables/schema so the
        # DB mirror tracks the manifest. status is not downgraded here.
        stmt = stmt.on_conflict_do_update(
            index_elements=["version"],
            set_={
                "prompt_hash": pins.prompt_hash,
                "prompt_ref": pins.prompt_ref,
                "variables": dict.fromkeys(bundle.variables, None),
                "output_schema": bundle.output_schema,
            },
        )
        await session.execute(stmt)
    await session.commit()


__all__: Sequence[str] = (
    "HashMismatchError",
    "MissingPromptFileError",
    "MissingRegistryFileError",
    "MissingVariableError",
    "PromptBundle",
    "PromptNotFoundError",
    "PromptPins",
    "PromptRegistryError",
    "Registry",
    "load_registry",
    "render",
    "upsert_prompt_versions",
)
