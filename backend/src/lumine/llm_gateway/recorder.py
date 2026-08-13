# Copyright (c) 2026 Lumine. All rights reserved.

"""Usage recording for LLM Gateway — cost tracking per D6-7."""

import logging
from datetime import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
import uuid

from lumine.data.models import LLMUsage
from lumine.data.session import get_db_session

logger = logging.getLogger(__name__)


@dataclass
class UsageRecord:
    """Usage record for llm_usage table insertion."""

    model_version_id: uuid.UUID
    role: str
    tier: str
    prompt_version_id: Optional[uuid.UUID] = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: Decimal = Decimal("0.0")
    fallback_hops: int = 0
    degraded: bool = False
    lane: Optional[str] = None
    lineage_id: Optional[uuid.UUID] = None


class UsageRecorder:
    """Async usage recorder for llm_usage append-only table."""

    def __init__(self, session=None):
        """Initialize usage recorder with optional session (for testing)."""
        self._session = session

    @property
    def session(self):
        """Get current session (from init or get_db_session)."""
        return self._session if self._session is not None else None

    @session.setter
    def session(self, value):
        """Set session (for testing)."""
        self._session = value

    async def record(self, usage_record: UsageRecord) -> None:
        """Insert usage record into llm_usage table."""
        db_session = self._session
        close_on_exit = False

        print(f"[DEBUG Recorder] session id={id(db_session) if db_session else None}, has_records_attr={hasattr(db_session, 'records') if db_session else False}")

        # Check if this is a fake/test session with .records list
        if hasattr(db_session, 'records'):
            print(f"[DEBUG FakeSession] Appending to records list on session id={id(db_session)}")
            record = LLMUsage(
                role=usage_record.role,
                tier=usage_record.tier,
                model_version_id=usage_record.model_version_id,
                prompt_version_id=usage_record.prompt_version_id,
                tokens_in=usage_record.tokens_in,
                tokens_out=usage_record.tokens_out,
                cost_usd=Decimal(str(usage_record.cost_usd)),
                fallback_hops=usage_record.fallback_hops,
                degraded=usage_record.degraded,
                lane=usage_record.lane,
                lineage_id=usage_record.lineage_id,
            )
            db_session.records.append(record)
            logger.debug(f"Usage record added to test session: {usage_record.model_version_id}")
            return

        if db_session is None:
            db_session = await get_db_session()
            close_on_exit = True

        try:
            record = LLMUsage(
                role=usage_record.role,
                tier=usage_record.tier,
                model_version_id=usage_record.model_version_id,
                prompt_version_id=usage_record.prompt_version_id,
                tokens_in=usage_record.tokens_in,
                tokens_out=usage_record.tokens_out,
                cost_usd=Decimal(str(usage_record.cost_usd)),
                fallback_hops=usage_record.fallback_hops,
                degraded=usage_record.degraded,
                lane=usage_record.lane,
                lineage_id=usage_record.lineage_id,
            )
            db_session.add(record)
            await db_session.commit()
            logger.debug(f"Usage record inserted: {usage_record.model_version_id}")

        except Exception as e:
            if hasattr(db_session, 'rollback'):
                await db_session.rollback()
            logger.error(f"Failed to insert usage record: {e}")
            raise
        finally:
            if close_on_exit and hasattr(db_session, 'close'):
                await db_session.close()

    async def get_daily_total(self, date: str) -> float:
        """Get total cost for specific date (YYYY-MM-DD format)."""
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

    async def get_weekly_total(self, weeks_ago: int = 0) -> float:
        """Get total cost for week starting N weeks ago."""
        from datetime import timedelta

        session = await get_db_session()

        try:
            start_date = (datetime.utcnow() - timedelta(weeks=weeks_ago)).date()
            end_date = start_date + timedelta(days=6)

            sql = """
            SELECT COALESCE(SUM(cost_usd), 0) as total
            FROM llm_usage
            WHERE DATE(timestamp) >= :start_date AND DATE(timestamp) <= :end_date
            """
            result = await session.execute(sql, {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            })
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

    async def get_model_costs(self, model_version_id: str, days: int = 30) -> float:
        """Get total cost for a model over the last N days."""
        from datetime import timedelta

        session = await get_db_session()

        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).date()

            sql = """
            SELECT COALESCE(SUM(cost_usd), 0) as total
            FROM llm_usage
            WHERE model_version_id = :model_version_id
              AND DATE(timestamp) >= :cutoff_date
            """
            result = await session.execute(sql, {
                "model_version_id": model_version_id,
                "cutoff_date": cutoff_date.isoformat(),
            })
            row = result.fetchone()
            return float(row.total) if row else 0.0

        finally:
            await session.close()

    async def get_top_models(self, days: int = 30, limit: int = 10) -> list[dict]:
        """Get top costing models over the last N days."""
        from datetime import timedelta

        session = await get_db_session()

        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).date()

            sql = """
            SELECT
                model_version_id,
                model_name,
                provider,
                SUM(cost_usd) as total_cost,
                SUM(tokens_prompt + tokens_completion) as total_tokens,
                COUNT(*) as call_count
            FROM llm_usage
            WHERE DATE(timestamp) >= :cutoff_date
            GROUP BY model_version_id, model_name, provider
            ORDER BY total_cost DESC
            LIMIT :limit
            """
            result = await session.execute(sql, {
                "cutoff_date": cutoff_date.isoformat(),
                "limit": limit,
            })
            rows = result.fetchall()

            return [
                {
                    "model_version_id": row.model_version_id,
                    "model_name": row.model_name,
                    "provider": row.provider,
                    "total_cost": float(row.total_cost),
                    "total_tokens": row.total_tokens,
                    "call_count": row.call_count,
                }
                for row in rows
            ]

        finally:
            await session.close()
