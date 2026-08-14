# Copyright (c) 2026 Lumine. All rights reserved.
"""Application configuration loaded from environment variables.

Uses pydantic-settings for validation and type coercion.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Lumine application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Environment ───────────────────────────────────────────────────────
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # ── Database ──────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://lumine:lumine@localhost:5432/lumine"
    database_pool_size: int = 20
    database_pool_overflow: int = 10
    database_echo: bool = False

    # ── Redis ─────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_pool_size: int = 10

    # ── LLM Gateway (9router) ─────────────────────────────────────────────
    llm_gateway_url: str = "http://localhost:8080"
    llm_gateway_api_key: str = ""
    llm_daily_budget_usd: float = 50.0
    llm_request_timeout_s: int = 120
    llm_default_model: str = "deepseek-v4"

    # ── MT5 Bridge ────────────────────────────────────────────────────────
    mt5_command_channel: str = "mt5:commands"
    mt5_result_channel: str = "mt5:results"
    mt5_response_timeout_s: int = 30

    # ── Trading ───────────────────────────────────────────────────────────
    max_exposure_per_trade: float = 0.02  # 2% of equity
    risk_per_trade: float = 0.01  # 1% of equity
    default_stop_loss_atr_multiplier: float = 2.0
    kill_switch_enabled: bool = False
    # Risk-engine limits (ADR-0016, Sprint 3 risk_validator).
    max_total_exposure: float = 0.05  # 5% total notional / equity
    max_correlated_exposure: float = 0.03  # 3% correlated book
    max_daily_loss_pct: float = 0.03  # 3% daily-loss halt
    max_position_count: int = 10  # per-strategy open position cap
    min_volume: float = 0.01
    broker_max_volume: float = 100.0
    # XAUUSD pip value in account currency per lot: 0.1 pip * 100 oz.
    pip_value_per_lot: float = 10.0
    # XAUUSD pip size in price units (1 pip = 0.1 price move).
    pip_size: float = 0.1
    # Redis key under which a reconciliation/risk mismatch arms the kill switch.
    kill_switch_key: str = "kill:switch"

    # ── Data mode (B-05) ──────────────────────────────────────────────────
    # True = routers serve deterministic demo_data (no storage wiring);
    # False = repositories read/write PostgreSQL (orders/positions).
    demo_data: bool = True

    # ── Decision cycle (D3-12) ────────────────────────────────────────────
    decision_cycle_timeout_s: int = 60  # total soft deadline for one cycle

    # ── API ───────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"  # nosec B104 — wajib bind all-interfaces di container
    api_port: int = 8000
    api_rate_limit_per_minute: int = 120
    hmac_secret_key: str = ""  # Override in production; noqa: S105

    # ── Session auth (internal, replaces Authelia/Keycloak) ─────────────
    # Bootstrap credentials seeded idempotently into the users table on
    # startup. Override via env in production .env (same file that holds
    # HMAC_SECRET_KEY). Defaults preserve the pre-migration demo logins so
    # existing operators can authenticate after the upgrade.
    session_ttl_seconds: int = 43_200  # 12h
    # True di production (HTTPS via Cloudflare): browser drop cookie non-Secure
    # di beberapa konfigurasi (extension/privacy). Origin tetap HTTP, tapi
    # browser menerima cookie Secure karena koneksi browser→CF adalah HTTPS.
    session_cookie_secure: bool = False
    superadmin_password: str = "Lumine@2026!"  # noqa: S105 — bootstrap seed
    admin_password: str = "lumine-admin"  # noqa: S105 — bootstrap seed
    trader_password: str = "lumine2026"  # noqa: S105 — bootstrap seed

    # ── SSE ───────────────────────────────────────────────────────────────
    sse_heartbeat_interval_s: int = 30
    sse_max_gap_events: int = 100

    # ── Feature flags ─────────────────────────────────────────────────────
    feature_flag_prefix: str = "LUMINE_FEATURE_"

    # ── Paths ─────────────────────────────────────────────────────────────
    # D3-8: prompts live in docs/prompts/ (auditable artifact outside src/).
    # PROMPT_DIR env override enables test isolation and non-repo deployments.
    prompt_dir_env: str = ""  # absolute path override; empty = derive from repo root

    @property
    def prompt_dir(self) -> Path:
        """Return the absolute path to the prompts directory.

        Defaults to <repo_root>/docs/prompts/ (D3-8). Override via PROMPT_DIR.
        """
        if self.prompt_dir_env:
            return Path(self.prompt_dir_env)
        # src/lumine/shared/config.py -> parents[4] = repo_root/docs/prompts
        return Path(__file__).resolve().parents[4] / "docs" / "prompts"

    @property
    def schema_dir(self) -> Path:
        """Return the absolute path to the schema directory."""
        return Path(__file__).resolve().parent.parent / "schemas"


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the singleton Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def override_settings(settings: Settings) -> None:
    """Override settings for testing. Use with caution."""
    global _settings
    _settings = settings
