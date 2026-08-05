# Copyright (c) 2026 Lumine. All rights reserved.
"""Unit tests for shared/logging.py — structlog configuration."""

from __future__ import annotations

from lumine.shared.logging import configure_logging, get_logger


class TestConfigureLogging:
    """Verify logging configuration runs without errors."""

    def test_configure_logging_does_not_raise(self) -> None:
        """configure_logging should be safe to call in any environment."""
        configure_logging()

    def test_configure_logging_is_idempotent(self) -> None:
        """Calling configure_logging multiple times must not raise."""
        configure_logging()
        configure_logging()


class TestGetLogger:
    """Verify get_logger returns a bound logger."""

    def test_get_logger_returns_logger(self) -> None:
        logger = get_logger("test_module")
        assert hasattr(logger, "info")
        assert hasattr(logger, "bind")

    def test_get_logger_without_name(self) -> None:
        logger = get_logger()
        assert hasattr(logger, "info")

    def test_logger_can_log_at_info_level(self) -> None:
        logger = get_logger("test_module")
        logger.info("hello", extra="data")
