# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for prompt registry."""

from pathlib import Path

import pytest

from lumine.prompts.registry import Registry


@pytest.fixture
def sample_registry_path(tmp_path: Path):
    """Create a temporary registry.yaml for testing."""
    # Hashes are computed from the exact bytes written below so the fixture
    # stays correct across platforms (no hardcoded/line-ending drift).
    import hashlib

    tech_prompt = "# Technical Analyst Prompt"
    macro_prompt = "# Macro Analyst Prompt"
    tech_hash = hashlib.sha256(tech_prompt.encode()).hexdigest()
    macro_hash = hashlib.sha256(macro_prompt.encode()).hexdigest()

    registry_content = f"""
prompts:
- sub_role: technical_analyst
  version: v1
  prompt_ref: prompts/technical_analyst@v1.prompt
  expected_hash: {tech_hash}
  model_tier_hint: cost-efficient
  variables:
  - symbol
  - atr_14
  output_schema_ref: schemas/analyst_output.json
- sub_role: macro_analyst
  version: v1
  prompt_ref: prompts/macro_analyst@v1.prompt
  expected_hash: {macro_hash}
  model_tier_hint: context-rich
  variables:
  - symbol
  - us_10y
  output_schema_ref: schemas/analyst_output.json
"""

    registry_file = tmp_path / "registry.yaml"
    registry_file.write_text(registry_content, encoding="utf-8")

    # Create dummy prompt files
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    (prompts_dir / "technical_analyst@v1.prompt").write_text(
        tech_prompt, encoding="utf-8"
    )
    (prompts_dir / "macro_analyst@v1.prompt").write_text(
        macro_prompt, encoding="utf-8"
    )

    # Output schema referenced by output_schema_ref entries
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()
    (schemas_dir / "analyst_output.json").write_text(
        '{"type": "object", "required": ["symbol", "bias"], '
        '"properties": {"symbol": {"type": "string"}, "bias": {"type": "string"}}}',
        encoding="utf-8",
    )

    return tmp_path


class TestRegistryInitialization:
    """Test registry loading and initialization."""

    def test_load_registry_from_path(self, sample_registry_path: Path):
        """Registry loads successfully from provided path."""
        registry = Registry(base_path=sample_registry_path)

        assert "technical_analyst" in registry.list_subroles()
        assert "macro_analyst" in registry.list_subroles()

    def test_list_subroles(self, sample_registry_path: Path):
        """List all registered sub-roles."""
        registry = Registry(base_path=sample_registry_path)

        subroles = registry.list_subroles()

        assert len(subroles) == 2
        assert set(subroles) == {"technical_analyst", "macro_analyst"}

    def test_list_versions(self, sample_registry_path: Path):
        """List all versions for a sub-role."""
        registry = Registry(base_path=sample_registry_path)

        versions = registry.list_versions("technical_analyst")

        assert versions == ["v1"]


class TestGetPrompt:
    """Test getting prompt references."""

    def test_get_latest(self, sample_registry_path: Path):
        """Get latest version of a prompt."""
        registry = Registry(base_path=sample_registry_path)

        ref = registry.get_latest("technical_analyst")

        assert ref is not None
        assert ref.sub_role == "technical_analyst"
        assert ref.version == "v1"
        assert ref.model_tier_hint == "cost-efficient"

    def test_get_specific_version(self, sample_registry_path: Path):
        """Get specific version of a prompt."""
        registry = Registry(base_path=sample_registry_path)

        ref = registry.get("technical_analyst", "v1")

        assert ref is not None
        assert ref.prompt_ref == "prompts/technical_analyst@v1.prompt"

    def test_get_nonexistent_subrole(self, sample_registry_path: Path):
        """Get returns None for non-existent sub-role."""
        registry = Registry(base_path=sample_registry_path)

        ref = registry.get("nonexistent", "v1")

        assert ref is None


class TestPromptVariables:
    """Test variable extraction."""

    def test_get_variables(self, sample_registry_path: Path):
        """Get expected template variables."""
        registry = Registry(base_path=sample_registry_path)

        variables = registry.get_variables("technical_analyst")

        assert "symbol" in variables
        assert "atr_14" in variables


class TestLoadedPrompt:
    """Test LoadedPrompt class."""

    def test_prompt_hash_validation(self, sample_registry_path: Path):
        """get_prompt computes and validates the prompt hash at load."""
        registry = Registry(base_path=sample_registry_path)

        loaded = registry.get_prompt("technical_analyst", "v1")

        assert loaded is not None
        assert loaded.pins.sub_role == "technical_analyst"
        assert loaded.pins.prompt_hash == registry.get("technical_analyst", "v1").expected_hash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
