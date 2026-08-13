# Copyright (c) 2026 Lumine. All rights reserved.
"""Prompt registry with SHA-256 hash validation and versioning (ADR-0015).

Provides typed access to prompt files with automatic hash verification,
variable extraction, and output schema loading. Registry data is loaded from
`docs/prompts/registry.yaml` and cached for performance.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


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
            base_path: Base path for relative prompt_refs. Defaults to repo root.
        """
        self._base_path = base_path or Path.cwd()
        self._prompts: dict[str, dict[str, PromptRef]] = {}
        self._loaded_cache: dict[str, LoadedPrompt] = {}
        self._load_registry()
    
    def _load_registry(self) -> None:
        """Load registry.yaml and parse all prompt refs."""
        registry_path = self._base_path / "docs" / "prompts" / "registry.yaml"
        
        if not registry_path.exists():
            msg = f"Registry file not found: {registry_path}"
            raise FileNotFoundError(msg)
        
        with open(registry_path, "r", encoding="utf-8") as f:
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
    
    def list_subroles(self) -> list[str]:
        """List all available sub-roles in registry."""
        return list(self._prompts.keys())
    
    def list_versions(self, sub_role: str) -> list[str]:
        """List all versions for a sub-role."""
        versions = self._prompts.get(sub_role, {})
        return list(versions.keys())
    
    def load(self, sub_role: str, version: str | None = None) -> LoadedPrompt | None:
        """Load prompt content from disk and validate hash.
        
        Args:
            sub_role: The agent sub-role
            version: Optional version string. If None, uses latest.
        
        Returns:
            LoadedPrompt with validated hash or None if not found
        
        Raises:
            ValueError: If hash validation fails
        """
        if version is None:
            ref = self.get_latest(sub_role)
        else:
            ref = self.get(sub_role, version)
        
        if ref is None:
            return None
        
        cache_key = f"{sub_role}:{version or 'latest'}"
        
        if cache_key in self._loaded_cache:
            return self._loaded_cache[cache_key]
        
        # Load from disk
        prompt_path = self._base_path / ref.prompt_ref
        
        if not prompt_path.exists():
            msg = f"Prompt file not found: {prompt_path}"
            raise FileNotFoundError(msg)
        
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Compute hash
        computed_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        
        loaded = LoadedPrompt(
            ref=ref,
            content=content,
            computed_hash=computed_hash,
        )
        
        # Validate hash
        if not loaded.validate():
            msg = (
                f"Hash mismatch for {sub_role}@{version}: "
                f"expected {ref.expected_hash}, got {computed_hash}"
            )
            raise ValueError(msg)
        
        self._loaded_cache[cache_key] = loaded
        return loaded
    
    def get_variables(self, sub_role: str, version: str | None = None) -> list[str]:
        """Get expected template variables for a prompt."""
        ref = self.load(sub_role, version)
        if ref is None:
            return []
        return list(ref.ref.variables)
    
    def get_output_schema_ref(self, sub_role: str, version: str | None = None) -> str | None:
        """Get output schema reference for a prompt."""
        ref = self.load(sub_role, version)
        if ref is None:
            return None
        return ref.ref.output_schema_ref


__all__ = ["PromptRef", "LoadedPrompt", "Registry"]
