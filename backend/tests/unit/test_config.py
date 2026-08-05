# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for shared/config.py — Settings singleton and overrides."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lumine.shared.config import Settings, get_settings, override_settings

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class TestSettingsDefaults:
    """Verify default values match those declared in the Settings class."""

    def test_environment_defaults_to_development(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        settings = Settings()
        assert settings.environment == "development"

    def test_debug_is_false_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEBUG", raising=False)
        settings = Settings()
        assert settings.debug is False

    def test_database_url_has_default_localhost(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        settings = Settings()
        assert "localhost" in settings.database_url

    def test_pool_size_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATABASE_POOL_SIZE", raising=False)
        monkeypatch.delenv("DATABASE_POOL_OVERFLOW", raising=False)
        settings = Settings()
        assert settings.database_pool_size == 20
        assert settings.database_pool_overflow == 10

    def test_redis_url_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REDIS_URL", raising=False)
        settings = Settings()
        assert settings.redis_url == "redis://localhost:6379/0"

    def test_llm_gateway_defaults(self) -> None:
        settings = Settings()
        assert settings.llm_gateway_url == "http://localhost:8080"
        assert settings.llm_daily_budget_usd == 50.0
        assert settings.llm_default_model == "deepseek-v4"

    def test_trading_risk_defaults(self) -> None:
        settings = Settings()
        assert settings.max_exposure_per_trade == 0.02
        assert settings.risk_per_trade == 0.01
        assert settings.default_stop_loss_atr_multiplier == 2.0
        assert settings.kill_switch_enabled is False

    def test_api_defaults(self) -> None:
        settings = Settings()
        assert settings.api_host == "0.0.0.0"
        assert settings.api_port == 8000
        assert settings.api_rate_limit_per_minute == 120

    def test_mt5_channel_defaults(self) -> None:
        settings = Settings()
        assert settings.mt5_command_channel == "mt5:commands"
        assert settings.mt5_result_channel == "mt5:results"
        assert settings.mt5_response_timeout_s == 30

    def test_sse_defaults(self) -> None:
        settings = Settings()
        assert settings.sse_heartbeat_interval_s == 30
        assert settings.sse_max_gap_events == 100


class TestSettingsOverride:
    """Verify that settings can be overridden via constructor kwargs."""

    def test_override_environment(self) -> None:
        s = Settings(environment="production")
        assert s.environment == "production"

    def test_override_database_url(self) -> None:
        s = Settings(database_url="postgresql+asyncpg://test:test@db:5432/test")
        assert "test" in s.database_url

    def test_extra_fields_are_ignored(self) -> None:
        """Per model_config extra='ignore'."""
        s = Settings(not_a_real_field=123)
        assert not hasattr(s, "not_a_real_field")


class TestSettingsPathProperties:
    """Verify prompt_dir and schema_dir point to expected locations."""

    def test_prompt_dir_ends_with_prompts(self) -> None:
        settings = Settings()
        assert settings.prompt_dir.name == "prompts"

    def test_schema_dir_ends_with_schemas(self) -> None:
        settings = Settings()
        assert settings.schema_dir.name == "schemas"

    def test_prompt_dir_override_via_constructor(
        self, tmp_path: Path
    ) -> None:
        # config.py:74-83 — prompt_dir_env is an absolute-path override;
        # an empty value derives <repo_root>/docs/prompts instead.
        s = Settings(prompt_dir_env=str(tmp_path))
        assert s.prompt_dir == tmp_path

    def test_prompt_dir_override_via_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # D3-8: PROMPT_DIR_ENV enables test isolation and non-repo
        # deployments — the pydantic-settings env binding must feed the
        # prompt_dir property, not just the constructor kwarg.
        monkeypatch.setenv("PROMPT_DIR_ENV", str(tmp_path))
        s = Settings()
        assert s.prompt_dir == tmp_path


class TestSingleton:
    """Verify get_settings returns the same instance and override_settings works."""

    def test_get_settings_returns_same_instance(self) -> None:
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_override_settings_replaces_singleton(self) -> None:
        original = get_settings()
        custom = Settings(environment="staging")
        try:
            override_settings(custom)
            assert get_settings() is custom
            assert get_settings().environment == "staging"
        finally:
            override_settings(original)
            assert get_settings() is original
