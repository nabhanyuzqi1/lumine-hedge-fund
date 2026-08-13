# Copyright (c) 2026 Lumine. All rights reserved.

"""LLM Gateway database models."""

from datetime import datetime
from enum import Enum
import logging
from typing import Optional
from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship
import sys
import os

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

from lumine.data.session import get_db_session
from lumine.data.models.base import Base

logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    """Model tiers per D6-1."""

    STRONGEST = "strongest"        # GPT-5.5/5.6 family
    CONTEXT_RICH = "context_rich"  # DeepSeek V4, Kimi K3
    COST_EFFICIENT = "cost_efficient"  # Qwen 3.7, GLM 5.2


class ModelStatus(str, Enum):
    """Model promotion states."""

    SANDBOX = "sandbox"
    STAGING = "staging"
    PRODUCTION = "production"
    RETIRED = "retired"


class LLMUsage(Base):
    """Usage tracking table per D6-7 — append-only cost accounting."""

    __tablename__ = "llm_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_version_id = Column(String(255), nullable=False)
    provider = Column(String(100), nullable=False)
    model_name = Column(String(100), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    tokens_prompt = Column(Integer, nullable=False, default=0)
    tokens_completion = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    lineage_id = Column(String(255), nullable=True, index=True)
    role = Column(String(100), nullable=False, default="unknown")
    fallback_hops = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_llm_usage_timestamp", "timestamp"),
        Index("idx_llm_usage_lineage", "lineage_id"),
        Index("idx_llm_usage_model", "model_version_id"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "model_version_id": self.model_version_id,
            "provider": self.provider,
            "model_name": self.model_name,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "tokens_prompt": self.tokens_prompt,
            "tokens_completion": self.tokens_completion,
            "cost_usd": self.cost_usd,
            "lineage_id": self.lineage_id,
            "role": self.role,
            "fallback_hops": self.fallback_hops,
            "error": self.error,
        }
