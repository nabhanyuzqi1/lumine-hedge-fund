# Copyright (c) 2026 Lumine. All rights reserved.
"""Structured logging configuration using structlog.

All log output is JSON-formatted for ingest into Grafana/Loki.
"""

from __future__ import annotations

import structlog

from lumine.shared.config import get_settings


def configure_logging() -> None:
    """Configure structlog for production JSON output."""
    settings = get_settings()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if settings.environment == "development"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(structlog.processors, settings.log_level, 20),
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Return a bound logger for the given module name."""
    logger: structlog.BoundLogger = structlog.get_logger(name or __name__)
    return logger.bind(module=name)
