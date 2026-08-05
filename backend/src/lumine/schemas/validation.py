# Copyright (c) 2026 Lumine. All rights reserved.
"""JSON-Schema validation for agent outputs (Phase 4 schema contract).

Agent outputs from the LLM gateway are validated against the JSON-Schema
files under ``docs/prompts/schemas/`` (D4-2/D4-3). Validation is strict:
a non-conforming output is a stage failure, never a relaxed parse
(ADR-0016 determinism; Phase 7 allows retry, not relaxed parsing).

``jsonschema`` raises :class:`jsonschema.ValidationError` on the first
violation; we re-raise as :class:`lumine.shared.errors.SchemaValidationError`
so the pipeline catches one shared error type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lumine.shared.errors import SchemaValidationError

if TYPE_CHECKING:
    from collections.abc import Mapping

try:  # pragma: no cover - import guard for non-DB test collection
    from jsonschema import Draft7Validator
except ImportError as exc:  # pragma: no cover
    message = "jsonschema is required (add it to project dependencies)."
    raise ImportError(message) from exc


def validate_against_schema(
    payload: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> None:
    """Validate ``payload`` against ``schema``; raise on any violation.

    Raises:
        SchemaValidationError: ``payload`` does not conform to ``schema``.
            The message names the offending path(s).

    """
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    if not errors:
        return
    first = errors[0]
    path = "/".join(str(part) for part in first.absolute_path) or "$"
    message = f"schema violation at {path}: {first.message}"
    raise SchemaValidationError(message)


def validation_problem(
    payload: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> str | None:
    """Return the first schema violation as a string, or ``None`` if valid.

    Used to build the ``fix your JSON`` retry hint without raising.
    """
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    if not errors:
        return None
    first = errors[0]
    path = "/".join(str(part) for part in first.absolute_path) or "$"
    return f"schema violation at {path}: {first.message}"


__all__ = ("validate_against_schema", "validation_problem")
