# Copyright (c) 2026 Lumine. All rights reserved.
"""Level 3 integration tests for reasoning trace storage (D7-11, D3-11)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import select

from lumine.autogen_pipeline.traces import ReasoningTraceError, write_trace
from lumine.data.models import ModelVersion, ReasoningTrace
from tests.integration.factories import seed_model

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def _model(db_session: AsyncSession) -> ModelVersion:
    return await seed_model(db_session)


class TestReasoningTraceWriter:
    def _trace_args(self, model_id: uuid.UUID) -> dict[str, object]:
        return {
            "workflow_run_id": f"wf-{uuid.uuid4().hex[:8]}",
            "stage_run_id": f"stage-{uuid.uuid4().hex[:8]}",
            "role": "technical_analyst",
            "model_version_id": model_id,
            "prompt_sent": "You are the Technical Analyst...",
            "response_raw": '{"bias": "bullish", "argument": "hh", "confidence": 0.7}',
            "parsed_output": {"bias": "bullish", "confidence": 0.7},
            "prompt_hash": "c" * 64,
            "lineage_id": None,  # no lineage row yet — FK stays unset
        }

    async def test_write_trace_persists_hashes(
        self, db_session, _model  # type: ignore[no-untyped-def]  # noqa: ANN001
    ) -> None:
        args = self._trace_args(_model.id)
        trace_id = await write_trace(db_session, **args)  # type: ignore[arg-type]

        stmt = select(ReasoningTrace).where(ReasoningTrace.trace_id == trace_id)
        trace = (await db_session.execute(stmt)).scalar_one()
        assert trace.role == "technical_analyst"
        assert trace.prompt_hash == "c" * 64
        assert trace.response_hash == __import__("hashlib").sha256(
            args["response_raw"].encode("utf-8")  # type: ignore[union-attr]
        ).hexdigest()
        assert trace.parsed_output is not None  # type: ignore[union-attr]

    async def test_invalid_fk_fails_closed(
        self, db_session, _model  # type: ignore[no-untyped-def]  # noqa: ANN001
    ) -> None:
        args = self._trace_args(uuid.uuid4())  # bogus model FK
        with pytest.raises(ReasoningTraceError):
            await write_trace(db_session, **args)  # type: ignore[arg-type]
