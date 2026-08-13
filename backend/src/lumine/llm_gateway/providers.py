# Copyright (c) 2026 Lumine. All rights reserved.

"""Model registry implementations."""

import logging
from typing import Optional

from lumine.llm_gateway.__init__ import ModelSpec, ModelStatus, ModelTier
from lumine.data.session import get_db_session

logger = logging.getLogger(__name__)


class SimpleModelRegistry:
    """Simple in-memory registry for development/sandbox."""

    def __init__(self):
        self._models: dict[str, ModelSpec] = {}
        self._default_tier_models: dict[ModelTier, str] = {}

    def register_model(self, spec: ModelSpec) -> None:
        """Register a model specification."""
        self._models[spec.model_version_id] = spec

        if spec.status == ModelStatus.PRODUCTION:
            if spec.tier not in self._default_tier_models:
                self._default_tier_models[spec.tier] = spec.model_version_id

    def get_model(self, model_version_id: str) -> Optional[ModelSpec]:
        """Resolve model version ID to full spec."""
        return self._models.get(model_version_id)

    def list_models(
        self,
        tier: Optional[ModelTier] = None,
        status: Optional[ModelStatus] = None,
    ) -> list[ModelSpec]:
        """List models filtered by tier/status."""
        results = []
        for model in self._models.values():
            if tier and model.tier != tier:
                continue
            if status and model.status != status:
                continue
            results.append(model)
        return results

    def resolve_model_for_tier(self, preferred_tier: ModelTier) -> Optional[ModelSpec]:
        """Get best available production model for given tier."""
        model_id = self._default_tier_models.get(preferred_tier)
        if model_id:
            return self.get_model(model_id)

        # Fallback: find any production model in tier
        for model in self.list_models(status=ModelStatus.PRODUCTION):
            if model.tier == preferred_tier:
                return model

        return None


class DatabaseModelRegistry(SimpleModelRegistry):
    """Registry backed by PostgreSQL model_versions table."""

    async def load_from_database(self) -> int:
        """Load all production models from database. Returns count loaded."""
        session = await get_db_session()
        count = 0

        try:
            # Query model versions (Phase 3 registry tables)
            # This is a simplified query - adjust based on actual schema
            sql = """
            SELECT model_version_id, provider, model_name, tier, status,
                   base_cost_per_million_tokens, max_timeout_seconds,
                   rate_limit_requests_per_minute, fallback_order
            FROM model_versions
            WHERE status = 'production'
            """
            result = await session.execute(sql)

            for row in result.fetchall():
                model = ModelSpec(
                    model_version_id=row.model_version_id,
                    provider=row.provider,
                    model_name=row.model_name,
                    tier=ModelTier(row.tier),
                    status=ModelStatus(row.status),
                    base_cost_per_million_tokens=row.base_cost_per_million_tokens or 0.0,
                    max_timeout_seconds=row.max_timeout_seconds or 30,
                    rate_limit_requests_per_minute=row.rate_limit_requests_per_minute or 60,
                    fallback_order=row.fallback_order or [],
                )
                self.register_model(model)
                count += 1

            logger.info(f"Loaded {count} production models into registry")

        except Exception as e:
            logger.error(f"Failed to load models from database: {e}")
            raise
        finally:
            await session.close()

        return count

    async def get_model(self, model_version_id: str) -> Optional[ModelSpec]:
        """Override to ensure fresh load from database."""
        if model_version_id in self._models:
            return self._models[model_version_id]

        # Fallback: query database directly
        session = await get_db_session()
        try:
            sql = """
            SELECT model_version_id, provider, model_name, tier, status,
                   base_cost_per_million_tokens, max_timeout_seconds,
                   rate_limit_requests_per_minute, fallback_order
            FROM model_versions
            WHERE model_version_id = :model_version_id
            """
            result = await session.execute(sql, {"model_version_id": model_version_id})
            row = result.fetchone()

            if row:
                model = ModelSpec(
                    model_version_id=row.model_version_id,
                    provider=row.provider,
                    model_name=row.model_name,
                    tier=ModelTier(row.tier),
                    status=ModelStatus(row.status),
                    base_cost_per_million_tokens=row.base_cost_per_million_tokens or 0.0,
                    max_timeout_seconds=row.max_timeout_seconds or 30,
                    rate_limit_requests_per_minute=row.rate_limit_requests_per_minute or 60,
                    fallback_order=row.fallback_order or [],
                )
                self._models[model_version_id] = model
                return model

        except Exception as e:
            logger.error(f"Database lookup failed for {model_version_id}: {e}")
        finally:
            await session.close()

        return None


class UsageRecorder:
    """Async usage recorder for llm_usage append-only table."""

    async def record(self, usage_record: "UsageRecord") -> None:
        """Insert usage record into llm_usage table."""
        session = await get_db_session()

        try:
            record = LLMUsage(
                model_version_id=usage_record.model_version_id,
                provider=usage_record.provider,
                model_name=usage_record.model_name,
                timestamp=usage_record.timestamp,
                tokens_prompt=usage_record.tokens_prompt,
                tokens_completion=usage_record.tokens_completion,
                cost_usd=usage_record.cost_usd,
                lineage_id=usage_record.lineage_id,
                role=usage_record.role,
                fallback_hops=usage_record.fallback_hops,
                error=usage_record.error,
            )
            session.add(record)
            await session.commit()
            logger.debug(f"Usage record inserted: {usage_record.model_version_id}")

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to insert usage record: {e}")
            raise
        finally:
            await session.close()

    async def get_daily_total(self, date: str) -> float:
        """Get total cost for specific date."""
        session = await get_db_session()

        try:
            sql = """
            SELECT COALESCE(SUM(cost_usd), 0) as total
            FROM llm_usage
            WHERE DATE(timestamp) = :date
            """
            result = await session.execute(sql, {"date": date})
            row = result.fetchone()
            return float(row.total) if row else 0.0

        finally:
            await session.close()

    async def get_lineage_costs(self, lineage_id: str) -> dict:
        """Get costs broken down by role for a lineage decision."""
        session = await get_db_session()

        try:
            sql = """
            SELECT role, SUM(cost_usd) as total, COUNT(*) as call_count
            FROM llm_usage
            WHERE lineage_id = :lineage_id
            GROUP BY role
            """
            result = await session.execute(sql, {"lineage_id": lineage_id})
            rows = result.fetchall()

            return {
                row.role: {"total_cost": float(row.total), "call_count": row.call_count}
                for row in rows
            }

        finally:
            await session.close()


def format_model_display(model: ModelSpec) -> str:
    """Human-readable model display string."""
    return f"{model.provider}/{model.model_name}"
