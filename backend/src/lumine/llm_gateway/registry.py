# Copyright (c) 2026 Lumine. All rights reserved.
"""Model registry resolution (D6-3, D3-4).

``model_versions`` is the only place concrete models are named. Only
``production`` rows are resolvable by the gateway; ``retired`` fails
fast (never a silent substitution); ``sandbox``/``staging`` are routable
only from the Research sandbox, never the live pipeline.

The resolution layer is DB-free: callers inject an in-memory mapping of
row dicts (built by :func:`load_model_versions` from the DB at startup,
or directly in tests).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lumine.data.models import ModelVersion
from lumine.llm_gateway.types import ModelRoute, ModelTier
from lumine.shared.errors import ModelUnavailableError

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession


class ModelRegistry:
    """In-memory map of model_versions rows keyed by UUID."""

    def __init__(self, rows: Mapping[uuid.UUID, dict[str, object]]) -> None:
        """Store ``rows`` keyed by model_version_id."""
        self._rows = dict(rows)

    def get(self, model_version_id: uuid.UUID) -> dict[str, object] | None:
        """Return the raw row for ``model_version_id`` or None."""
        return self._rows.get(model_version_id)

    def __len__(self) -> int:
        """Return the number of registered model versions."""
        return len(self._rows)


def _to_route(model_version_id: uuid.UUID, row: dict[str, object]) -> ModelRoute:
    params_raw = row["params"]
    params = dict(params_raw) if isinstance(params_raw, dict) else {}
    return ModelRoute(
        model_version_id=model_version_id,
        version=str(row["version"]),
        provider=str(row["provider"]),
        model=str(row["model_id"]),
        tier=ModelTier(str(row["tier"])),
        context_window=int(str(row["context_window"])),
        params=params,
    )


def resolve_model(registry: ModelRegistry, model_version_id: uuid.UUID) -> ModelRoute:
    """Resolve ``model_version_id`` to a routable production route.

    Raises:
        ModelUnavailableError: unknown id, or row is not ``production``
            (``retired`` fails fast per D6-3; sandbox/staging are never
            routable from the live pipeline).

    """
    row = registry.get(model_version_id)
    if row is None:
        message = f"unknown model_version_id: {model_version_id}"
        raise ModelUnavailableError(message)
    status = str(row["status"])
    if status != "production":
        reason = "retired" if status == "retired" else f"not production (status={status})"
        message = f"model {model_version_id} is {reason}; only production rows are routable"
        raise ModelUnavailableError(message)
    return _to_route(model_version_id, row)


async def load_model_versions(session: AsyncSession) -> ModelRegistry:
    """Load every ``model_versions`` row into an in-memory registry.

    Runs at startup after migrations; the registry is then queried
    synchronously by :func:`resolve_model`. Only used by app bootstrap
    and integration tests — unit tests inject rows directly.
    """
    from sqlalchemy import select  # noqa: PLC0415

    rows = (await session.execute(select(ModelVersion))).scalars().all()
    return ModelRegistry({row.id: _row_to_dict(row) for row in rows})


def _row_to_dict(row: ModelVersion) -> dict[str, object]:
    """Convert an ORM ModelVersion row to the dict shape tests use."""
    return {
        "version": row.version,
        "status": row.status,
        "provider": row.provider,
        "model_id": row.model_id,
        "tier": row.tier,
        "context_window": row.context_window,
        "params": row.params,
    }


__all__ = ("ModelRegistry", "load_model_versions", "resolve_model")
