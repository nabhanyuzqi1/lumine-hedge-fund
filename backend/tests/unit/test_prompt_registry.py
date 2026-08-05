# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for prompts/registry.py — D3-8 prompt registry loader.

Covers: registry.yaml parsing, SHA-256 hash verification (mismatch = fatal),
``get_prompt(sub_role, version) -> PromptBundle``, Liquid-style ``render()``,
and all failure modes (missing registry, missing prompt file, hash drift,
unknown prompt, missing template variable).

No database here — the DB upsert (``upsert_prompt_versions``) is exercised at
integration level. See ``tests/integration/test_prompt_registry.py``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import yaml

from lumine.prompts.registry import (
    HashMismatchError,
    MissingPromptFileError,
    MissingRegistryFileError,
    MissingVariableError,
    PromptBundle,
    PromptNotFoundError,
    PromptPins,
    Registry,
    load_registry,
    render,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any, ClassVar

    from typing_extensions import TypedDict

    class _PromptEntry(TypedDict, total=False):
        sub_role: str
        version: str
        prompt_ref: str
        content: str
        model_tier_hint: str
        variables: list[str]
        output_schema_ref: str


# backend/tests/unit/test_prompt_registry.py -> parents[3] = repo root
REPO_PROMPT_DIR = Path(__file__).resolve().parents[3] / "docs" / "prompts"

_ANALYST_SCHEMA = (
    '{"type": "object", "required": ["symbol", "bias"], '
    '"properties": {"symbol": {"type": "string"}, "bias": {"type": "string"}}}'
)


# ── helpers ───────────────────────────────────────────────────────────────────


def _sha256(content: str) -> str:
    """SHA-256 hex digest of UTF-8 encoded content (matches loader)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_registry(tmp_path: Path, entries: Sequence[_PromptEntry]) -> Path:
    """Build a self-contained prompt_dir with registry.yaml + prompt files.

    Each entry's ``expected_hash`` is computed from its ``content`` so the
    happy path verifies by construction. Tests needing a *broken* registry
    (hash drift, missing file) write files directly instead.
    """
    prompt_dir = tmp_path / "prompts"
    rows: list[dict[str, Any]] = []
    for entry in entries:
        ref = entry["prompt_ref"]
        content = entry["content"]
        _write(prompt_dir / ref, content)
        rows.append(
            {
                "sub_role": entry["sub_role"],
                "version": entry["version"],
                "prompt_ref": ref,
                "expected_hash": _sha256(content),
                "model_tier_hint": entry.get("model_tier_hint", "cost-efficient"),
                "variables": entry.get("variables", ["symbol", "output_schema"]),
                "output_schema_ref": entry.get("output_schema_ref", "schemas/analyst_output.json"),
            }
        )
    _write(prompt_dir / "schemas" / "analyst_output.json", _ANALYST_SCHEMA)
    _write(prompt_dir / "registry.yaml", yaml.safe_dump({"prompts": rows}))
    return prompt_dir


def _analyst_entry(sub_role: str, *, version: str = "v1") -> _PromptEntry:
    body = (
        f"You are the {sub_role} for the XAUUSD committee.\n"
        "Symbol: {{ symbol }}\n"
        "Respond with JSON matching: {{ output_schema }}\n"
    )
    return {
        "sub_role": sub_role,
        "version": version,
        "prompt_ref": f"{sub_role}@{version}.prompt",
        "content": body,
        "variables": ["symbol", "output_schema"],
        "output_schema_ref": "schemas/analyst_output.json",
    }


# ── load_registry: parsing ────────────────────────────────────────────────────


class TestLoadRegistryParsing:
    """Verify load_registry parses registry.yaml into a Registry."""

    def test_returns_registry_instance(self, tmp_path: Path) -> None:
        prompt_dir = _build_registry(tmp_path, [_analyst_entry("technical_analyst")])
        result = load_registry(prompt_dir)
        assert isinstance(result, Registry)

    def test_loads_all_entries(self, tmp_path: Path) -> None:
        entries = [
            _analyst_entry("technical_analyst"),
            _analyst_entry("macro_analyst"),
            _analyst_entry("news_analyst"),
        ]
        prompt_dir = _build_registry(tmp_path, entries)
        registry = load_registry(prompt_dir)
        assert len(registry.list_prompts()) == 3

    def test_list_prompts_returns_sub_role_version_pairs(self, tmp_path: Path) -> None:
        prompt_dir = _build_registry(tmp_path, [_analyst_entry("technical_analyst")])
        registry = load_registry(prompt_dir)
        assert ("technical_analyst", "v1") in registry.list_prompts()


# ── load_registry: hash verification ──────────────────────────────────────────


class TestHashVerification:
    """Verify SHA-256 hash verification — mismatch is fatal (D3-8)."""

    def test_valid_hashes_load_successfully(self, tmp_path: Path) -> None:
        prompt_dir = _build_registry(tmp_path, [_analyst_entry("technical_analyst")])
        # No raise = every expected_hash matched the file on disk.
        registry = load_registry(prompt_dir)
        assert ("technical_analyst", "v1") in registry.list_prompts()

    def test_hash_mismatch_is_fatal(self, tmp_path: Path) -> None:
        prompt_dir = _build_registry(tmp_path, [_analyst_entry("technical_analyst")])
        # Corrupt the registry.yaml with a wrong hash while leaving the file intact.
        reg_path = prompt_dir / "registry.yaml"
        data = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
        data["prompts"][0]["expected_hash"] = "0" * 64
        reg_path.write_text(yaml.safe_dump(data), encoding="utf-8")

        with pytest.raises(HashMismatchError):
            load_registry(prompt_dir)

    def test_missing_prompt_file_is_fatal(self, tmp_path: Path) -> None:
        prompt_dir = _build_registry(tmp_path, [_analyst_entry("technical_analyst")])
        (prompt_dir / "technical_analyst@v1.prompt").unlink()

        with pytest.raises(MissingPromptFileError):
            load_registry(prompt_dir)

    def test_missing_registry_yaml_is_fatal(self, tmp_path: Path) -> None:
        prompt_dir = tmp_path / "empty_prompts"
        prompt_dir.mkdir()

        with pytest.raises(MissingRegistryFileError):
            load_registry(prompt_dir)

    def test_mismatch_error_names_the_prompt(self, tmp_path: Path) -> None:
        prompt_dir = _build_registry(tmp_path, [_analyst_entry("technical_analyst")])
        reg_path = prompt_dir / "registry.yaml"
        data = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
        data["prompts"][0]["expected_hash"] = "1" * 64
        reg_path.write_text(yaml.safe_dump(data), encoding="utf-8")

        with pytest.raises(HashMismatchError, match="technical_analyst"):
            load_registry(prompt_dir)


# ── Registry container: iteration / len / replacement ────────────────────────


class TestRegistryContainer:
    """Anchor the container contract — iteration, length, key replacement."""

    def test_iterates_all_bundles(self, tmp_path: Path) -> None:
        entries = [
            _analyst_entry("technical_analyst"),
            _analyst_entry("macro_analyst"),
        ]
        registry = load_registry(_build_registry(tmp_path, entries))
        roles = {bundle.pins.sub_role for bundle in registry}
        assert roles == {"technical_analyst", "macro_analyst"}

    def test_len_counts_registered_bundles(self, tmp_path: Path) -> None:
        registry = load_registry(
            _build_registry(tmp_path, [_analyst_entry("technical_analyst")])
        )
        assert len(registry) == 1

    def test_register_replaces_same_key(self, tmp_path: Path) -> None:
        # register (registry.py:127-130) is keyed on (sub_role, version) —
        # re-registering the same key must replace, never duplicate.
        prompt_dir = _build_registry(tmp_path, [_analyst_entry("technical_analyst")])
        replacement = _analyst_entry("technical_analyst")
        replacement["content"] = "Replacement body {{ symbol }}\n"
        row = {
            "sub_role": "technical_analyst",
            "version": "v1",
            "prompt_ref": "technical_analyst@v1.prompt",
            "expected_hash": _sha256(replacement["content"]),
            "model_tier_hint": "cost-efficient",
            "variables": ["symbol"],
            "output_schema_ref": "schemas/analyst_output.json",
        }
        _write(prompt_dir / "technical_analyst@v1.prompt", replacement["content"])
        _write(prompt_dir / "registry.yaml", yaml.safe_dump({"prompts": [row]}))
        registry2 = load_registry(prompt_dir)
        assert len(registry2) == 1
        assert registry2.get_prompt("technical_analyst", "v1").text.startswith("Replacement")


# ── get_prompt ────────────────────────────────────────────────────────────────


class TestGetPrompt:
    """Verify get_prompt(sub_role, version) -> PromptBundle."""

    def test_returns_bundle_with_text(self, tmp_path: Path) -> None:
        prompt_dir = _build_registry(tmp_path, [_analyst_entry("technical_analyst")])
        registry = load_registry(prompt_dir)
        bundle = registry.get_prompt("technical_analyst", "v1")
        assert isinstance(bundle, PromptBundle)
        assert "You are the technical_analyst" in bundle.text

    def test_text_excludes_frontmatter(self, tmp_path: Path) -> None:
        # Build a prompt with YAML frontmatter; body must be served, not the
        # frontmatter, while the hash still covers the full file bytes.
        prompt_dir = tmp_path / "prompts"
        content = (
            "---\nsub_role: technical_analyst\nversion: v1\n---\n"
            "You are the Technical Analyst.\nSymbol: {{ symbol }}\n"
        )
        _write(prompt_dir / "technical_analyst@v1.prompt", content)
        _write(prompt_dir / "schemas" / "analyst_output.json", _ANALYST_SCHEMA)
        row = {
            "sub_role": "technical_analyst",
            "version": "v1",
            "prompt_ref": "technical_analyst@v1.prompt",
            "expected_hash": _sha256(content),
            "model_tier_hint": "cost-efficient",
            "variables": ["symbol"],
            "output_schema_ref": "schemas/analyst_output.json",
        }
        _write(prompt_dir / "registry.yaml", yaml.safe_dump({"prompts": [row]}))

        bundle = load_registry(prompt_dir).get_prompt("technical_analyst", "v1")
        assert "---" not in bundle.text
        assert "You are the Technical Analyst." in bundle.text

    def test_returns_declared_variables(self, tmp_path: Path) -> None:
        prompt_dir = _build_registry(tmp_path, [_analyst_entry("technical_analyst")])
        registry = load_registry(prompt_dir)
        bundle = registry.get_prompt("technical_analyst", "v1")
        assert bundle.variables == ["symbol", "output_schema"]

    def test_returns_output_schema_dict(self, tmp_path: Path) -> None:
        prompt_dir = _build_registry(tmp_path, [_analyst_entry("technical_analyst")])
        registry = load_registry(prompt_dir)
        bundle = registry.get_prompt("technical_analyst", "v1")
        assert bundle.output_schema["type"] == "object"
        assert "symbol" in bundle.output_schema["required"]

    def test_pins_carry_sub_role_version_hash_ref(self, tmp_path: Path) -> None:
        prompt_dir = _build_registry(tmp_path, [_analyst_entry("technical_analyst")])
        registry = load_registry(prompt_dir)
        bundle = registry.get_prompt("technical_analyst", "v1")
        pins = bundle.pins
        assert isinstance(pins, PromptPins)
        assert pins.sub_role == "technical_analyst"
        assert pins.version == "v1"
        assert pins.prompt_ref == "technical_analyst@v1.prompt"
        # Hash is 64-char hex (SHA-256) and non-empty.
        assert len(pins.prompt_hash) == 64
        assert all(c in "0123456789abcdef" for c in pins.prompt_hash)

    def test_unknown_sub_role_raises(self, tmp_path: Path) -> None:
        prompt_dir = _build_registry(tmp_path, [_analyst_entry("technical_analyst")])
        registry = load_registry(prompt_dir)
        with pytest.raises(PromptNotFoundError, match="nonexistent"):
            registry.get_prompt("nonexistent", "v1")

    def test_unknown_version_raises(self, tmp_path: Path) -> None:
        prompt_dir = _build_registry(tmp_path, [_analyst_entry("technical_analyst")])
        registry = load_registry(prompt_dir)
        with pytest.raises(PromptNotFoundError, match="v99"):
            registry.get_prompt("technical_analyst", "v99")

    def test_output_schema_resolves_missing_ref(self, tmp_path: Path) -> None:
        # _load_output_schema (registry.py:179-189) treats a ref without a
        # slash and starting with "{" as an inline JSON string — a missing
        # file must otherwise raise, never silently serve an empty schema.
        prompt_dir = tmp_path / "prompts"
        content = "Body {{ symbol }}\n"
        _write(prompt_dir / "technical_analyst@v1.prompt", content)
        # schema_ref points at a file that does not exist on disk.
        row = {
            "sub_role": "technical_analyst",
            "version": "v1",
            "prompt_ref": "technical_analyst@v1.prompt",
            "expected_hash": _sha256(content),
            "model_tier_hint": "cost-efficient",
            "variables": ["symbol"],
            "output_schema_ref": "schemas/missing.json",
        }
        _write(prompt_dir / "registry.yaml", yaml.safe_dump({"prompts": [row]}))

        with pytest.raises(FileNotFoundError):
            load_registry(prompt_dir)

    def test_hash_pin_matches_full_file_bytes(self, tmp_path: Path) -> None:
        # The pin hash must equal SHA-256 of the *full file* (frontmatter
        # included), so post-import edits to frontmatter are detectable drift.
        prompt_dir = _build_registry(tmp_path, [_analyst_entry("technical_analyst")])
        registry = load_registry(prompt_dir)
        bundle = registry.get_prompt("technical_analyst", "v1")
        full_bytes = (prompt_dir / "technical_analyst@v1.prompt").read_bytes()
        assert bundle.pins.prompt_hash == hashlib.sha256(full_bytes).hexdigest()


# ── render ────────────────────────────────────────────────────────────────────


class TestRender:
    """Verify Liquid-style render() — missing variable is fatal (prompt-storage)."""

    def test_substitutes_variables(self, tmp_path: Path) -> None:
        prompt_dir = _build_registry(tmp_path, [_analyst_entry("technical_analyst")])
        bundle = load_registry(prompt_dir).get_prompt("technical_analyst", "v1")
        rendered = render(bundle, {"symbol": "XAUUSD", "output_schema": "{}"})
        assert "{{" not in rendered
        assert "XAUUSD" in rendered
        assert "{}" in rendered

    def test_missing_declared_variable_is_fatal(self, tmp_path: Path) -> None:
        prompt_dir = _build_registry(tmp_path, [_analyst_entry("technical_analyst")])
        bundle = load_registry(prompt_dir).get_prompt("technical_analyst", "v1")
        with pytest.raises(MissingVariableError, match="output_schema"):
            render(bundle, {"symbol": "XAUUSD"})

    def test_missing_template_variable_is_fatal(self, tmp_path: Path) -> None:
        # A {{ var }} present in the body but absent from the supplied dict
        # must not silently leak through as a literal placeholder.
        entry = _analyst_entry("technical_analyst")
        entry["content"] = "Symbol: {{ symbol }} / Extra: {{ not_supplied }}\n"
        entry["variables"] = ["symbol"]  # not_supplied is undeclared
        prompt_dir = _build_registry(tmp_path, [entry])
        bundle = load_registry(prompt_dir).get_prompt("technical_analyst", "v1")
        with pytest.raises(MissingVariableError, match="not_supplied"):
            render(bundle, {"symbol": "XAUUSD"})

    def test_tolerates_whitespace_in_placeholders(self, tmp_path: Path) -> None:
        entry = _analyst_entry("technical_analyst")
        entry["content"] = "Symbol: {{   symbol   }}\n"
        prompt_dir = _build_registry(tmp_path, [entry])
        bundle = load_registry(prompt_dir).get_prompt("technical_analyst", "v1")
        rendered = render(bundle, {"symbol": "XAUUSD", "output_schema": "{}"})
        assert "{{" not in rendered
        assert "XAUUSD" in rendered


# ── repo registry: the real docs/prompts/ ─────────────────────────────────────


class TestRepoRegistry:
    """Smoke-test the actual docs/prompts/ registry shipped with the repo."""

    REQUIRED_PROMPTS: ClassVar[list[tuple[str, str]]] = [
        ("technical_analyst", "v1"),
        ("macro_analyst", "v1"),
        ("news_analyst", "v1"),
        ("smc_analyst", "v1"),
        ("ic_forum", "v1"),
        ("cio_proposer", "v1"),
    ]

    def test_repo_prompt_dir_exists(self) -> None:
        assert REPO_PROMPT_DIR.is_dir(), f"missing prompt dir: {REPO_PROMPT_DIR}"

    def test_loads_all_six_prompts(self) -> None:
        registry = load_registry(REPO_PROMPT_DIR)
        loaded = set(registry.list_prompts())
        for sub_role, version in self.REQUIRED_PROMPTS:
            assert (sub_role, version) in loaded, f"missing {sub_role}@{version}"

    def test_every_prompt_hash_verifies(self) -> None:
        # load_registry raises on any hash mismatch, so reaching get_prompt
        # for every prompt proves all six expected_hash values are correct.
        registry = load_registry(REPO_PROMPT_DIR)
        for sub_role, version in self.REQUIRED_PROMPTS:
            bundle = registry.get_prompt(sub_role, version)
            assert bundle.text, f"empty body for {sub_role}@{version}"
            assert bundle.variables, f"no variables declared for {sub_role}@{version}"
            assert isinstance(bundle.output_schema, dict)

    def test_every_prompt_declares_output_schema_ref(self) -> None:
        registry = load_registry(REPO_PROMPT_DIR)
        for sub_role, version in self.REQUIRED_PROMPTS:
            bundle = registry.get_prompt(sub_role, version)
            assert bundle.output_schema, f"empty output_schema for {sub_role}@{version}"
