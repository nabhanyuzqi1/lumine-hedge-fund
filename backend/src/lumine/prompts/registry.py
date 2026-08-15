# Copyright (c) 2026 Lumine. All rights reserved.
"""Prompt registry with SHA-256 hash validation and versioning (ADR-0015).

Provides typed access to prompt files with automatic hash verification,
variable extraction, and output schema loading. Registry data is loaded from
`docs/prompts/registry.yaml` and cached for performance.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ── Exceptions ────────────────────────────────────────────────────────────────


class RegistryError(Exception):
    """Base exception for registry operations."""



class MissingRegistryFileError(RegistryError):
    """registry.yaml is absent or unreadable."""



class MissingPromptFileError(RegistryError):
    """A prompt file referenced in registry.yaml is absent."""



class HashMismatchError(RegistryError):
    """Expected SHA-256 does not match computed hash of the prompt file."""



class PromptNotFoundError(RegistryError):
    """No prompt bundle exists for the given (sub_role, version)."""



class MissingVariableError(RegistryError):
    """render() was called without a declared template variable."""

    def __init__(self, variable: str) -> None:
        super().__init__(f"missing declared variable: {variable}")
        self.variable = variable


# ── Data contracts ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PromptPins:
    """Immutable hash pin for a prompt bundle — used for drift detection."""

    sub_role: str
    version: str
    prompt_ref: str
    prompt_hash: str  # SHA-256 hex of full file bytes


@dataclass(frozen=True)
class PromptBundle:
    """Loaded + validated prompt ready for LLM consumption."""

    pins: PromptPins
    text: str
    variables: list[str]
    output_schema: dict[str, Any]
    model_tier_hint: str = "cost-efficient"


@dataclass(frozen=True)
class PromptRef:
    """Reference to a prompt file in the repository."""

    sub_role: str
    version: str
    prompt_ref: str
    expected_hash: str
    model_tier_hint: str = "cost-efficient"
    variables: list[str] = field(default_factory=list)
    output_schema_ref: str | None = None


@dataclass(frozen=True)
class LoadedPrompt:
    """Prompt loaded from disk with validated hash."""

    ref: PromptRef
    content: str
    computed_hash: str

    def validate(self) -> bool:
        """Verify prompt hash matches registry expectation."""
        return self.computed_hash == self.ref.expected_hash


class Registry:
    """Prompt registry loader with hash validation."""

    def __init__(self, base_path: Path | None = None):
        """Initialize registry loader.

        Args:
            base_path: Path to directory containing registry.yaml.
                       If not provided, defaults to docs/prompts/ at cwd.

        """
        if base_path is None:
            self._base_path = Path.cwd() / "docs" / "prompts"
        else:
            self._base_path = base_path

        self._prompts: dict[str, dict[str, PromptRef]] = {}
        self._bundle_cache: dict[tuple[str, str], PromptBundle] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        """Load registry.yaml and parse all prompt refs."""
        registry_path = self._base_path / "registry.yaml"

        if not registry_path.exists():
            msg = f"Registry file not found: {registry_path}"
            raise FileNotFoundError(msg)

        with open(registry_path, encoding="utf-8") as f:
            registry_data = yaml.safe_load(f)

        prompts_by_subrole: dict[str, dict[str, PromptRef]] = {}

        for entry in registry_data.get("prompts", []):
            sub_role = entry["sub_role"]
            version = entry["version"]

            ref = PromptRef(
                sub_role=sub_role,
                version=version,
                prompt_ref=entry["prompt_ref"],
                expected_hash=entry["expected_hash"],
                model_tier_hint=entry.get("model_tier_hint", "cost-efficient"),
                variables=entry.get("variables", []),
                output_schema_ref=entry.get("output_schema_ref"),
            )

            if sub_role not in prompts_by_subrole:
                prompts_by_subrole[sub_role] = {}

            prompts_by_subrole[sub_role][version] = ref

        # Validate all prompt hashes immediately (eager validation)
        for sub_role, versions in prompts_by_subrole.items():
            for version, ref in versions.items():
                prompt_path = self._base_path / ref.prompt_ref

                if not prompt_path.exists():
                    msg = f"Prompt file not found: {prompt_path}"
                    raise MissingPromptFileError(msg)

                with open(prompt_path, "rb") as f:
                    raw_bytes = f.read()
                computed_hash = hashlib.sha256(raw_bytes).hexdigest()

                if computed_hash != ref.expected_hash:
                    msg = (
                        f"Hash mismatch for {sub_role}@{version}: "
                        f"expected {ref.expected_hash}, got {computed_hash}"
                    )
                    raise HashMismatchError(msg)

                # Validate output schema file exists if referenced
                if ref.output_schema_ref:
                    schema_path = self._base_path / ref.output_schema_ref
                    if not schema_path.exists():
                        raise FileNotFoundError(f"Output schema not found: {schema_path}")

        self._prompts = prompts_by_subrole

    def get_latest(self, sub_role: str) -> PromptRef | None:
        """Get latest prompt version for a sub-role.

        Args:
            sub_role: The agent sub-role (e.g., technical_analyst, macro_analyst)

        Returns:
            Latest PromptRef or None if not found

        """
        versions = self._prompts.get(sub_role, {})
        if not versions:
            return None

        # Return highest version (assume vN ordering works lexicographically)
        latest_version = max(versions.keys(), key=lambda v: [int(x) for x in v[1:].split(".")])
        return versions[latest_version]

    def get(self, sub_role: str, version: str) -> PromptRef | None:
        """Get specific prompt version for a sub-role.

        Args:
            sub_role: The agent sub-role
            version: Version string (e.g., v1, v2)

        Returns:
            PromptRef or None if not found

        """
        versions = self._prompts.get(sub_role, {})
        return versions.get(version)

    def list_prompts(self) -> list[tuple[str, str]]:
        """Return list of (sub_role, version) tuples."""
        result: list[tuple[str, str]] = []
        for sub_role, versions in self._prompts.items():
            for version in versions:
                result.append((sub_role, version))
        return result

    def list_versions(self, sub_role: str) -> list[str]:
        """List all versions for a sub-role."""
        versions = self._prompts.get(sub_role, {})
        return list(versions.keys())

    def list_subroles(self) -> list[str]:
        """List all available sub-roles in registry."""
        return list(self._prompts.keys())

    def get_variables(self, sub_role: str) -> list[str]:
        """Return declared template variables for the latest version of a sub-role.

        Args:
            sub_role: The agent sub-role

        Returns:
            Declared variable names, or [] when the sub-role is unknown
            or the latest version declares none.

        """
        ref = self.get_latest(sub_role)
        if ref is None:
            return []
        return list(ref.variables)

    def __len__(self) -> int:
        """Return count of registered prompts."""
        return sum(len(v) for v in self._prompts.values())

    def __iter__(self):
        """Iterate over all bundles."""
        for sub_role, versions in self._prompts.items():
            for version in versions:
                yield self.get_prompt(sub_role, version)

    def get_prompt(self, sub_role: str, version: str) -> PromptBundle:
        """Get prompt bundle by sub-role and version.

        Args:
            sub_role: The agent sub-role
            version: Version string (e.g., v1, v2)

        Returns:
            PromptBundle with content and metadata

        Raises:
            PromptNotFoundError: If prompt doesn't exist
            HashMismatchError: If hash validation fails

        """
        cache_key = (sub_role, version)
        if cache_key in self._bundle_cache:
            return self._bundle_cache[cache_key]

        ref = self.get(sub_role, version)
        if ref is None:
            msg = f"No prompt found for {sub_role}@{version}"
            raise PromptNotFoundError(msg)

        # Load from disk
        prompt_path = self._base_path / ref.prompt_ref

        if not prompt_path.exists():
            msg = f"Prompt file not found: {prompt_path}"
            raise MissingPromptFileError(msg)

        with open(prompt_path, "rb") as f:
            raw_bytes = f.read()

        content = raw_bytes.decode("utf-8")
        computed_hash = hashlib.sha256(raw_bytes).hexdigest()

        # Verify hash
        if computed_hash != ref.expected_hash:
            msg = (
                f"Hash mismatch for {sub_role}@{version}: "
                f"expected {ref.expected_hash}, got {computed_hash}"
            )
            raise HashMismatchError(msg)

        # Strip YAML frontmatter (--- delimited header) if present
        text = content
        if text.startswith("---"):
            lines = text.split("\n")
            # Find closing --- marker on its own line
            for i, line in enumerate(lines[1:], start=1):
                if line.strip() == "---":
                    # Body starts after this line
                    text = "\n".join(lines[i+1:])
                    break
            else:
                # No closing marker found, keep full content
                text = content

        # Load output schema
        output_schema: dict[str, Any] = {}
        if ref.output_schema_ref:
            schema_path = self._base_path / ref.output_schema_ref
            if not schema_path.exists():
                raise FileNotFoundError(f"Output schema not found: {schema_path}")
            with open(schema_path, encoding="utf-8") as f:
                output_schema = json.load(f)

        pins = PromptPins(
            sub_role=sub_role,
            version=version,
            prompt_ref=ref.prompt_ref,
            prompt_hash=computed_hash,
        )

        bundle = PromptBundle(
            pins=pins,
            text=text,
            variables=ref.variables,
            output_schema=output_schema,
            model_tier_hint=ref.model_tier_hint,
        )

        self._bundle_cache[cache_key] = bundle
        return bundle

    def render(self, bundle: PromptBundle, ctx: dict[str, Any]) -> str:
        """Render a prompt bundle with context variables (Liquid-style).

        Uses simple Jinja2/f-string style {{variable}} substitution.

        Args:
            bundle: The prompt bundle to render
            ctx: Variable substitutions

        Returns:
            Rendered prompt string

        Raises:
            MissingVariableError: If declared variable is missing from context
            or if template contains undeclared variables

        """
        result = bundle.text

        for var in bundle.variables:
            if var not in ctx:
                raise MissingVariableError(var)

            value = str(ctx[var])

            # Match {{var}}, {{var }}, {{ var}}, {{ var }}, {{  var  }} (whitespace tolerant)
            # Pattern: literal {{ with optional whitespace around variable name, literal }}
            pattern = rf"\{{{{\s*{re.escape(var)}\s*}}}}"
            # Use lambda to avoid backreference issues in replacement; bind loop
            # var via default arg (B023 — late-binding fix).
            result = re.sub(pattern, lambda m, v=value: v, result)

        # Check for remaining unrendered placeholders (undeclared variables)
        remaining = re.findall(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}", result)
        if remaining:
            # Find first undeclared variable
            for var in remaining:
                if var not in bundle.variables:
                    raise MissingVariableError(var)

        return result


def load_registry(prompts_path: Path | None = None) -> Registry:
    """Load and return a Registry instance.

    Args:
        prompts_path: Path to directory containing registry.yaml.
                     If not provided, defaults to docs/prompts/ at cwd.

    Returns:
        Configured Registry instance

    Raises:
        MissingRegistryFileError: If registry.yaml is missing

    """
    try:
        return Registry(base_path=prompts_path)
    except FileNotFoundError as e:
        msg = str(e)
        if "Registry file not found" in msg:
            raise MissingRegistryFileError(msg) from e
        raise


__all__ = [
    "HashMismatchError",
    "LoadedPrompt",
    "MissingPromptFileError",
    "MissingRegistryFileError",
    "MissingVariableError",
    "PromptBundle",
    "PromptNotFoundError",
    "PromptPins",
    "PromptRef",
    "Registry",
    "RegistryError",
    "load_registry",
    "render",
]


def render(bundle: PromptBundle, ctx: dict[str, Any]) -> str:
    """Render a prompt bundle with context variables (Liquid-style).

    Uses simple Jinja2/f-string style {{variable}} substitution.

    Args:
        bundle: The prompt bundle to render
        ctx: Variable substitutions

    Returns:
        Rendered prompt string

    Raises:
        MissingVariableError: If declared variable is missing from context
        or if template contains undeclared variables

    """
    result = bundle.text

    for var in bundle.variables:
        if var not in ctx:
            raise MissingVariableError(var)

        value = str(ctx[var])

        # Match {{var}}, {{var }}, {{ var}}, {{ var }}, {{  var  }} (whitespace tolerant)
        # Pattern: literal {{ with optional whitespace around variable name, literal }}
        pattern = rf"\{{{{\s*{re.escape(var)}\s*}}}}"
        # Use lambda to avoid backreference issues in replacement; bind loop
        # var via default arg (B023 — late-binding fix).
        result = re.sub(pattern, lambda m, v=value: v, result)

    # Check for remaining unrendered placeholders (undeclared variables)
    remaining = re.findall(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}", result)
    if remaining:
        # Find first undeclared variable
        for var in remaining:
            if var not in bundle.variables:
                raise MissingVariableError(var)

    return result
