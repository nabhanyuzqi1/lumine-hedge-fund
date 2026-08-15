# Copyright (c) 2026 Lumine. All rights reserved.
"""RPC command worker — Redis Streams consumer (B-04).

Consumes ``rpc:commands`` via the ``rpc-workers`` consumer group and
executes each command handler. Handlers are deterministic in demo mode
(no LLM gateway / storage wiring yet — same contract as demo_data.py);
``halt_trading``/``resume_trading`` operate the real Redis kill switch,
``cancel_order`` mirrors the orders router's demo cancel semantics.

Delivery: at-least-once (XACK after processing). Handlers are idempotent
per command_id (result already stored → skip).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from lumine.api.middleware.auth import (
    AuthenticatedPrincipal,  # noqa: F401  (re-exported for handlers)
)
from lumine.api.sse.publisher import SSEEvent, SSEPublisher
from lumine.data.redis_client import get_redis
from lumine.rpc.queue import GROUP, STREAM, get_result, set_result
from lumine.shared.config import Settings

logger = logging.getLogger(__name__)


async def _handle_run_decision_cycle(payload: dict[str, Any], publisher: SSEPublisher) -> dict[str, Any]:  # noqa: PLR0915 — fixed LLM stage sequence
    """Run a REAL LLM decision cycle (technical analyst → IC forum) via 9router.

    Sebelumnya demo-only (run_id demo-*). Sekarang:
    1. Load bars terakhir dari DB (bars_5m/bars_1h) → hitung indikator
       (atr_14, ema_20/50, rsi_14, ohlc) via lumine.features.indicators
    2. Technical Analyst: LLM call (9router, oc/deepseek-v4-flash-free)
    3. IC Forum: LLM call → verdict (approved/rejected/noop)
    4. Publish SSE events: analyst-outputs + ic-decisions

    Macro/news/smc analyst di-skip (data feeds eksternal belum tersedia);
    technical + IC sudah cukup untuk committee feed LIVE yang bermakna.
    """
    from decimal import Decimal
    from pathlib import Path
    from uuid import uuid4

    from sqlalchemy import select, text

    from lumine.autogen_pipeline.agents.technical_analyst import run_technical_analyst
    from lumine.autogen_pipeline.ic_forum import run_ic_forum
    from lumine.data.models import ModelVersion
    from lumine.data.session import get_sessionmaker
    from lumine.features.indicators import atr, rsi
    from lumine.llm_gateway.budget import BudgetGate
    from lumine.llm_gateway.client import RouterClient
    from lumine.llm_gateway.gateway import Gateway
    from lumine.llm_gateway.registry import load_model_versions
    from lumine.prompts.registry import Registry

    symbol = payload.get("symbol", "XAUUSD")
    settings = Settings()
    now = datetime.now(UTC)
    result: dict[str, Any] = {
        "run_id": f"cycle-{uuid4().hex[:8]}",
        "symbol": symbol,
        "status": "failed",
    }

    async def _run() -> dict[str, Any]:
        """Execute the LLM cycle; raises on failure (caught by caller)."""
        async with get_sessionmaker()() as session:
            # model_version + prompt_version production
            mv = (
                await session.execute(
                    select(ModelVersion).where(ModelVersion.status == "production").limit(1)
                )
            ).scalar_one_or_none()
            if mv is None:
                msg = "no production model_versions row"
                raise RuntimeError(msg)

            # Registry model dari DB (wajib — resolve model_version_id)
            model_registry = await load_model_versions(session)
            client = RouterClient(url=settings.llm_gateway_url, api_key=settings.llm_gateway_api_key)
            gateway = Gateway(registry=model_registry, budget=BudgetGate({}), client=client)
            prompt_registry = Registry(base_path=Path("/app/docs/prompts"))

            # Indikator dari bars_5m (terakhir 60 bar)
            rows = (
                await session.execute(
                    text(
                        "SELECT ts, open, high, low, close, volume FROM bars_5m "
                        "WHERE symbol = :s ORDER BY ts DESC LIMIT 60"
                    ),
                    {"s": symbol},
                )
            ).all()
            bars = [
                {
                    "high": Decimal(str(r.high)),
                    "low": Decimal(str(r.low)),
                    "close": Decimal(str(r.close)),
                }
                for r in reversed(rows)
            ]
            if len(bars) < 15:
                msg = f"insufficient bars_5m for {symbol}: {len(bars)}"
                raise RuntimeError(msg)

            closes = [b["close"] for b in bars]
            atr_14 = float(atr(bars, period=14))
            rsi_14 = float(rsi(bars, period=14))
            ema_20 = float(sum(closes[-20:]) / Decimal(20))
            ema_50 = float(sum(closes[-50:]) / Decimal(min(50, len(closes))))
            last = bars[-1]
            ohlc = f"[{last['close']}, {max(b['high'] for b in bars[-5:])}, {min(b['low'] for b in bars[-5:])}, {closes[-1]}]"

            variables: dict[str, object] = {
                "symbol": symbol,
                "decision_ts": now.isoformat(),
                "atr_14": atr_14,
                "ema_20": round(ema_20, 2),
                "ema_50": round(ema_50, 2),
                "rsi_14": round(rsi_14, 2),
                "ohlc": ohlc,
                "swing_structure": "unknown",
            }

            lineage_id = uuid4()
            # Technical analyst (LLM real)
            analyst = await run_technical_analyst(
                gateway=gateway,
                registry=prompt_registry,
                lineage_id=lineage_id,
                workflow_run_id=result["run_id"],
                stage_run_id="technical_analyst",
                model_version_id=mv.id,
                idempotency_key=f"{lineage_id}:technical_analyst",
                variables=variables,
                session=session,
            )
            await publisher.publish(
                SSEEvent(
                    event_type="analyst_output",
                    channel="analyst-outputs",
                    data={
                        "portfolio_id": "default",
                        "symbol": symbol,
                        "analyst_name": "Technical Analyst",
                        "recommendation": str(analyst.parsed.get("recommendation", "hold")),
                        "confidence": float(analyst.parsed.get("confidence", 0.5)),
                        "reasoning": str(analyst.parsed.get("reasoning", ""))[:500],
                        "timestamp": now.isoformat(),
                    },
                )
            )

            # G3: journal pipeline — analyst step → workflow_journal (hash chain).
            from lumine.autogen_pipeline.journal import log_step

            await log_step(
                session,
                workflow_id=result["run_id"],
                step_name="technical_analyst",
                status="completed",
                duration_ms=int((datetime.now(UTC) - now).total_seconds() * 1000),
                input_snapshot={
                    "symbol": symbol,
                    "ohlc": ohlc,
                    "atr_14": atr_14,
                    "rsi_14": rsi_14,
                    "ema_20": ema_20,
                    "ema_50": ema_50,
                },
                output_snapshot={
                    "recommendation": str(analyst.parsed.get("recommendation", "hold")),
                    "confidence": float(analyst.parsed.get("confidence", 0.5)),
                },
                lineage_id=None,  # cycle ringkas — lineage_records penuh belum dibuat
            )

            # IC Forum (LLM real) — konsumsi analyst output
            ic = await run_ic_forum(
                gateway=gateway,
                registry=prompt_registry,
                lineage_id=lineage_id,
                workflow_run_id=result["run_id"],
                stage_run_id="ic_forum",
                model_version_id=mv.id,
                idempotency_key=f"{lineage_id}:ic_forum",
                symbol=symbol,
                decision_ts=now.isoformat(),
                analyst_inputs=[analyst.parsed],
                session=session,
            )
            action = str(ic.parsed.get("action", "HOLD"))
            confidence = float(ic.parsed.get("confidence", 0.5))
            await publisher.publish(
                SSEEvent(
                    event_type="ic_decision",
                    channel="ic-decisions",
                    data={
                        "decision_id": str(uuid4()),
                        "portfolio_id": "default",
                        "action": action,
                        "positions": [],
                        "confidence": confidence,
                        "reasoning": str(ic.parsed.get("reasoning", ""))[:500],
                        "timestamp": now.isoformat(),
                    },
                )
            )

            # G3: journal pipeline — IC decision step → workflow_journal.
            await log_step(
                session,
                workflow_id=result["run_id"],
                step_name="ic_forum",
                status="completed",
                duration_ms=int((datetime.now(UTC) - now).total_seconds() * 1000),
                input_snapshot={"symbol": symbol, "analyst_inputs": [analyst.parsed]},
                output_snapshot={"action": action, "confidence": confidence},
                lineage_id=None,
            )

            # B5: persist signals → dashboard AI confidence / signals panel.
            # Analyst output (direction dari recommendation) + IC decision.
            from lumine.data.models import Signal as SignalRow

            rec = str(analyst.parsed.get("recommendation", "hold")).lower()
            direction = (
                "bullish" if rec in ("buy", "long", "bullish")
                else "bearish" if rec in ("sell", "short", "bearish")
                else "neutral"
            )
            session.add(
                SignalRow(
                    run_id=result["run_id"],
                    symbol=symbol,
                    analyst="Technical Analyst",
                    direction=direction,
                    confidence=Decimal(str(float(analyst.parsed.get("confidence", 0.5)))),
                    rationale=str(analyst.parsed.get("reasoning", ""))[:500],
                    generated_at=now,
                )
            )
            ic_action = action.lower()
            ic_direction = (
                "bullish" if ic_action in ("buy", "long")
                else "bearish" if ic_action in ("sell", "short")
                else "neutral"
            )
            session.add(
                SignalRow(
                    run_id=result["run_id"],
                    symbol=symbol,
                    analyst="Investment Committee",
                    direction=ic_direction,
                    confidence=Decimal(str(confidence)),
                    rationale=str(ic.parsed.get("reasoning", ""))[:500],
                    generated_at=now,
                )
            )
            await session.commit()

            return {
                "status": "completed",
                "decision": action.lower(),
                "confidence": confidence,
                "analyst_recommendation": str(analyst.parsed.get("recommendation", "hold")),
                "finished_at": datetime.now(UTC).isoformat(),
            }

    try:
        result.update(await _run())
    except Exception as exc:  # RPC handler reports, never crashes worker
        logger.exception("decision cycle failed")
        result["error"] = str(exc)[:300]
        result["finished_at"] = datetime.now(UTC).isoformat()

    return result


async def _handle_halt_trading(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Arm the global kill switch (operational halt)."""
    r = await get_redis()
    await r.hset(
        settings.kill_switch_key,
        mapping={"armed": "1", "tier": "global", "reason": payload.get("reason", "rpc:halt-trading")},
    )
    return {"armed": True, "tier": "global"}


async def _handle_resume_trading(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Disarm the kill switch."""
    r = await get_redis()
    await r.hset(settings.kill_switch_key, mapping={"armed": "0", "reason": payload.get("reason", "rpc:resume-trading")})
    return {"armed": False}


async def _handle_cancel_order(payload: dict[str, Any], publisher: SSEPublisher) -> dict[str, Any]:
    """Demo cancel: mark the order cancelled and notify the orders channel."""
    order_id = payload.get("order_id", "unknown")
    result = {
        "order_id": order_id,
        "status": "cancelled",
        "cancelled_at": datetime.now(UTC).isoformat(),
    }
    await publisher.publish(
        SSEEvent(
            event_type="order_cancelled",
            channel="orders",
            data=result,
        )
    )
    return result


HANDLERS: dict[str, Any] = {
    "run_decision_cycle": _handle_run_decision_cycle,
    "halt_trading": _handle_halt_trading,
    "resume_trading": _handle_resume_trading,
    "cancel_order": _handle_cancel_order,
}


async def _process(
    command_id: str,
    command: str,
    payload: dict[str, Any],
    publisher: SSEPublisher,
    settings: Settings,
) -> None:
    existing = await get_result(command_id)
    if existing and existing.get("status") in {"completed", "failed"}:
        return  # idempotent redelivery
    try:
        handler = HANDLERS[command]
        if command in {"halt_trading", "resume_trading"}:
            result = await handler(payload, settings)  # type: ignore[arg-type]
        else:
            result = await handler(payload, publisher)  # type: ignore[arg-type]
        await set_result(command_id, "completed", result=result, command=command)
        logger.info("rpc %s %s completed", command, command_id)
    except Exception as exc:
        logger.exception("rpc %s %s failed", command, command_id)
        await set_result(command_id, "failed", error=str(exc), command=command)


def _decode_fields(fields: dict[bytes | str, bytes | str]) -> dict[str, str]:
    """redis-py returns raw stream entries as bytes — decode keys/values."""
    return {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in fields.items()
    }


async def run_worker(
    publisher: SSEPublisher,
    settings: Settings,
    *,
    consumer: str = "worker-1",
    block_ms: int = 2000,
) -> None:
    """Consume the rpc stream until cancelled (runs as a lifespan task)."""
    r = await get_redis()
    try:
        await r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except Exception:
        pass
    logger.info("rpc worker %s listening on %s", consumer, STREAM)
    while True:
        try:
            response = await r.xreadgroup(GROUP, consumer, {STREAM: ">"}, count=8, block=block_ms)
        except Exception:
            await asyncio.sleep(1)
            continue
        for _stream, messages in response or []:
            for message_id, fields in messages:
                decoded = _decode_fields(fields)
                # Hardening: satu message malformed tidak boleh crash worker loop.
                # Skip + XACK agar stream tidak tersumbat selamanya.
                if "command" not in decoded or "command_id" not in decoded:
                    logger.warning(
                        "rpc message %s malformed (missing command/command_id), skipping", message_id
                    )
                    await r.xack(STREAM, GROUP, message_id)
                    continue
                payload = json.loads(decoded.get("payload", "{}"))
                try:
                    await _process(decoded["command_id"], decoded["command"], payload, publisher, settings)
                except Exception:
                    logger.exception("rpc message %s processing failed", message_id)
                await r.xack(STREAM, GROUP, message_id)
