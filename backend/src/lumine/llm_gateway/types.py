# Copyright (c) 2026 Lumine. All rights reserved.
"""Wire types for the 9router LLM gateway (D3-2, D6-1, D6-2).

Carries the logical request contract from llm-gateway.md and the
resolved model route from the registry. ``ModelTier`` values are the
Phase 3 enum strings that land in ``model_versions.tier`` and
``llm_usage.tier``.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from collections.abc import Sequence


def _default_model() -> str:
    """Return the configured gateway model name (avoids import cycle)."""
    from lumine.shared.config import get_settings

    return get_settings().llm_default_model


class ModelTier(StrEnum):
    """Static model tier (D6-1). Values are the DB enum strings."""

    COST_EFFICIENT = "cost-efficient"
    CONTEXT_RICH = "context-rich"
    STRONGEST = "strongest"


class ModelRoute(BaseModel):
    """A resolved, production-only model version ready to call."""

    model_version_id: uuid.UUID
    version: str
    provider: str
    model: str
    tier: ModelTier
    context_window: int
    params: dict[str, object]


class ChatMessage(BaseModel):
    """One OpenAI-style chat message."""

    role: str
    content: str


class RouterRequest(BaseModel):
    """Logical request contract from llm-gateway.md, mapped to the wire."""

    model_version_id: uuid.UUID
    # Resolved model name (registry output); defaults to the configured
    # gateway model so direct calls never leak a hardcoded name.
    model: str = Field(default_factory=_default_model)
    role: str
    tier: ModelTier
    lineage_id: uuid.UUID
    prompt_ref: str
    prompt_hash: str
    idempotency_key: str
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float = 0.2
    max_tokens: int = 4096


class GatewayResponse(BaseModel):
    """Parsed response from the gateway (usage echoed for llm_usage)."""

    content: str
    model_used: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


__all__: Sequence[str] = (
    "ChatMessage",
    "GatewayResponse",
    "ModelRoute",
    "ModelTier",
    "RouterRequest",
)
