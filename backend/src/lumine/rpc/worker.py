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


async def _handle_run_decision_cycle(payload: dict[str, Any], publisher: SSEPublisher) -> dict[str, Any]:  # noqa: PLR0915,C901,PLR0912 — fixed LLM stage sequence
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
    # v2 (17 Aug 2026): SEMUA agent aktif — technical, macro, news, smc
    # (paralel), risk assessor, cio proposer, lalu IC forum. Analyst
    # menggunakan variabel market context yang sama (D4-2).
    import asyncio
    from decimal import Decimal
    from pathlib import Path
    from uuid import uuid4

    from sqlalchemy import select, text

    from lumine.autogen_pipeline.agents.macro_analyst import run_macro_analyst
    from lumine.autogen_pipeline.agents.news_analyst import run_news_analyst
    from lumine.autogen_pipeline.agents.smc_analyst import run_smc_analyst
    from lumine.autogen_pipeline.agents.technical_analyst import run_technical_analyst
    from lumine.autogen_pipeline.cio_proposer import run_cio_proposer
    from lumine.autogen_pipeline.ic_forum import run_ic_forum
    from lumine.autogen_pipeline.journal import log_step
    from lumine.autogen_pipeline.risk_assessor import run_risk_assessor
    from lumine.data.models import ModelVersion, Position
    from lumine.data.models import Signal as SignalRow
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

    # ── Realtime LLM routing overlay (18 Aug 2026) ────────────────────────
    # User ubah default/fallback model via superadmin → Redis
    # `lumine:llm_routing` → worker baca SETIAP cycle (bukan env statis).
    # Auto-discovery: worker refresh daftar model 9router tiap N detik.
    llm_url = settings.llm_gateway_url
    llm_key = settings.llm_gateway_api_key
    routing_chain: list[str] | None = None
    _r = None
    try:
        from lumine.llm_gateway.routing_overlay import get_overlay, parse_fallbacks

        _r = await get_redis()
        overlay = await get_overlay(_r)
        if overlay.get("llm_gateway_url"):
            llm_url = overlay["llm_gateway_url"]
        if overlay.get("llm_gateway_api_key"):
            llm_key = overlay["llm_gateway_api_key"]
        if overlay.get("default_model") or overlay.get("fallback_models"):
            chain = [str(overlay.get("default_model") or settings.llm_default_model)]
            fb = parse_fallbacks(overlay.get("fallback_models"))
            chain.extend(fb)
            # Skip model yang TAHU tidak available (18 Aug 2026): quota
            # habis / tidak respond probe → jangan buang waktu di chain.
            import json as _json

            try:
                from lumine.llm_gateway.routing_overlay import is_circuit_open

                avail_raw = overlay.get("available_models")
                avail: list[str] | None = None
                if avail_raw:
                    _v = _json.loads(avail_raw)
                    avail = [str(m) for m in _v] if isinstance(_v, list) else []
                filtered: list[str] = []
                for m in chain:
                    if is_circuit_open(m, overlay):
                        continue
                    if avail is not None and m not in avail:
                        continue
                    filtered.append(m)
                # 18 Aug 2026: manual chain SEMUA non-available (budget
                # habis / tidak respond probe) → jatuh ke available_models
                # dari discovery (model yang benar-benar bisa dipanggil).
                if not filtered and avail:
                    filtered = avail[:3]
                chain = filtered or chain
            except Exception:  # nosec B110 — filter best-effort
                pass  # filter best-effort — chain tetap dipakai apa adanya
            routing_chain = chain
            # DEBUG 18 Aug 2026: lihat chain aktual yang dipakai worker.
            print(f"[ROUTING] chain={chain} avail={avail if 'avail' in locals() else 'n/a'}", flush=True)
    except Exception:
        pass  # overlay tidak tersedia → fallback ke env

    # News headlines real (18 Aug 2026): baca cache Redis dari _news_worker.
    # Fallback "[]" → analyst tetap jalan (jujur, tidak gagal).
    _news_headlines_json = "[]"
    # Trading profile aktif (18 Aug 2026): scalping_1m default. Worker
    # baca per cycle → prompt override + execution params realtime.
    _active_profile: dict[str, Any] = {}
    try:
        if _r is None:
            _r = await get_redis()
        from lumine.trading.profiles import get_active_profile

        _active_profile = await get_active_profile(_r)
        # SANDBOX: saat paper_trading=1, worker pakai profil SANDBOX
        # (system_config.sandbox_profile) — uji profile baru tanpa
        # mengganggu profil real. default: profil aktif yang sama.
        try:
            _pt = await _r.hget("lumine:system_config", "paper_trading")
            _sp = await _r.hget("lumine:system_config", "sandbox_profile")
            if _pt and str(_pt).lower() in ("1", "true", "yes") and _sp:
                from lumine.trading.profiles import get_profile

                _sb = await get_profile(_r, str(_sp))
                if _sb:
                    _active_profile = _sb
        except Exception:
            pass
    except Exception:
        _active_profile = {}
    # Economic calendar (18 Aug 2026): baca cache dari _eco_calendar_worker
    # → analyst (news/macro) tahu event yang akan datang + dampaknya.
    _eco_calendar_json = "[]"
    # DXY (18 Aug 2026): variabel USD index untuk LLM — inverse correl
    # dengan emas. Baca cache lumine:dxy (refresh 60s).
    _dxy_json = "null"
    try:
        if _r is None:
            _r = await get_redis()
        from lumine.trading.dxy_service import get_cached_dxy

        _dxy = await get_cached_dxy(_r)
        if _dxy and _dxy.get("price"):
            import json as _json

            _dxy_json = _json.dumps(_dxy, ensure_ascii=False)
    except Exception:
        pass
    # 19 Aug 2026 A1: yield 10Y/2Y REAL (FRED publik CSV, cache 6 jam) —
    # sebelumnya "unavailable (external feed not wired)" → LLM dapat data.
    _us_10y = None
    _us_2y = None
    _fed_stance = "neutral (yield feed unavailable)"
    try:
        from lumine.trading.yield_service import fed_stance_from, get_yields

        _yields = await get_yields(get_redis, settings)
        _us_10y = _yields.get("us_10y")
        _us_2y = _yields.get("us_2y")
        try:
            _dxy_price = float(_dxy.get("price", 0) or 0) if _dxy else 0.0
            _dxy_prev = float(_dxy.get("prev_price", 0) or 0) if _dxy else 0.0
        except Exception:  # nosec B110
            _dxy_price = _dxy_prev = 0.0
        _fed_stance = fed_stance_from(_us_10y, _us_2y, "up" if _dxy_price > _dxy_prev else "down")
    except Exception:  # nosec B110 — yield non-fatal
        pass
    # Backtest learning digest (18 Aug 2026): pola XAUUSD dari master
    # backtest profile aktif → inject ke analyst prompt (siklus belajar).
    _learning_digest = ""
    try:
        from lumine.backtest.master import get_latest_learning_digest
        from lumine.data.session import get_sessionmaker

        async with get_sessionmaker()() as _sess:
            _learning_digest = await get_latest_learning_digest(
                _sess, str(_active_profile.get("id", "scalping_1m"))
            )
    except Exception:
        pass
    try:
        if _r is None:
            _r = await get_redis()
        from lumine.trading.economic_calendar import get_cached_calendar
        from lumine.trading.news_service import get_cached_headlines

        _eco_events = await get_cached_calendar(_r)
        if _eco_events:
            import json as _json

            _eco_calendar_json = _json.dumps(_eco_events, ensure_ascii=False)

        _news_headlines = await get_cached_headlines(_r)
        if _news_headlines:
            import json as _json

            _news_headlines_json = _json.dumps(
                [
                    {
                        "title": h.get("title", ""),
                        "source": h.get("source", ""),
                        "time": h.get("ts"),
                        "url": h.get("url", ""),
                    }
                    for h in _news_headlines[:8]
                ],
                ensure_ascii=False,
            )
    except Exception:
        pass

    async def _run() -> dict[str, Any]:  # noqa: PLR0915,C901,PLR0912 — fixed LLM stage sequence
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
            # Capture id UUID SEKALI — session.rollback() (race upsert di
            # bawah) men-expire ORM objek → akses mv.id berikutnya
            # MissingGreenlet. UUID object tetap valid.
            import uuid as _uuid_mod

            mv_id: _uuid_mod.UUID = mv.id

            # Registry model dari DB (wajib — resolve model_version_id)
            model_registry = await load_model_versions(session)
            client = RouterClient(url=llm_url, api_key=llm_key)
            # v4.11+: fallback provider dari routing overlay — jika user set
            # default/fallback model via superadmin, chain itu MENANG atas
            # policy DB (realtime, tanpa restart). None → policy DB default.
            fallback_provider = None
            if routing_chain:
                # 18 Aug 2026: model_version_id per model dari overlay —
                # oc/deepseek-v4-flash-free) → llm_usage/verbose mencatat
                # model LAMA walau call pakai ag/claude-opus. Fix: upsert
                # ModelVersion utk tiap model di chain → resolve id BENAR.
                # PITFALL: fallback_provider dipanggil SYNC oleh Gateway —
                # semua await di-pre-compute di sini (sekali per cycle).
                from uuid import uuid4

                from sqlalchemy import select as _sa_select

                from lumine.llm_gateway.types import ModelTier

                _mv_by_model: dict[str, str] = {}
                # Pre-capture id string — fallback TIDAK boleh akses mv.id
                # setelah session error (rolled back → MissingGreenlet).
                _fallback_mv_id = str(mv_id)
                for _m in routing_chain:
                    try:
                        existing = (
                            await session.execute(
                                _sa_select(ModelVersion).where(ModelVersion.model_id == _m).limit(1)
                            )
                        ).scalar_one_or_none()
                        if existing is not None:
                            _mv_by_model[_m] = str(existing.id)
                        else:
                            row = ModelVersion(
                                id=uuid4(),
                                model_id=_m,
                                provider="9router",
                                status="production",
                                # NOT NULL tanpa default (18 Aug 2026:
                                # upsert gagal IntegrityError → fallback
                                # mv.id stale → verbose tampil model lama).
                                # version UNIK per model (UniqueConstraint)
                                version=f"1-{_m.replace('/', '-')}",
                                tier="cost-efficient",
                                context_window=128_000,
                                params={},
                            )
                            session.add(row)
                            try:
                                await session.flush()
                            except Exception:
                                # Race: 2 cycle parallel insert model sama →
                                # duplicate key. PITFALL: session.rollback()
                                # men-expire SEMUA objek (termasuk mv) →
                                # akses mv.id berikutnya MissingGreenlet.
                                # Pakai savepoint — rollback hanya sub-transaksi.
                                await session.rollback()
                                # Re-bind row di savepoint baru, re-select.
                                row = ModelVersion(
                                    id=uuid4(),
                                    model_id=_m,
                                    provider="9router",
                                    status="production",
                                    version=f"1-{_m.replace('/', '-')}",
                                    tier="cost-efficient",
                                    context_window=128_000,
                                    params={},
                                )
                                session.add(row)
                                try:
                                    await session.flush()
                                except Exception:
                                    # Masih gagal (row lain menang) → re-select.
                                    await session.rollback()
                                    again = (
                                        await session.execute(
                                            _sa_select(ModelVersion)
                                            .where(ModelVersion.model_id == _m)
                                            .limit(1)
                                        )
                                    ).scalar_one_or_none()
                                    if again is not None:
                                        _mv_by_model[_m] = str(again.id)
                                        continue
                                    raise
                            _mv_by_model[_m] = str(row.id)
                    except Exception as _exc:  # nosec B110 — best-effort; fallback mv.id
                        print(f"[ROUTING] upsert fail {_m}: {type(_exc).__name__}: {str(_exc)[:150]}", flush=True)
                        _mv_by_model[_m] = _fallback_mv_id

                def _overlay_fallbacks(tier: ModelTier) -> tuple[dict[str, Any], list[dict[str, Any]]]:
                    # Primary = model pertama chain; hops = sisa. Semua hop
                    # resolve via mv.id (registry), nama model di-override
                    # oleh _call_for (route["model"]).
                    def _route(model: str) -> dict[str, Any]:
                        return {
                            "model": model,
                            "model_version_id": _mv_by_model.get(model, _fallback_mv_id),
                            "tier": tier.value if hasattr(tier, "value") else str(tier),
                        }

                    chain = list(routing_chain or [])
                    primary = _route(chain[0]) if chain else {}
                    hops = [_route(m) for m in chain[1:]]
                    return primary, hops

                fallback_provider = _overlay_fallbacks
                # COMMIT upsert ModelVersion SEKALI — PITFALL (18 Aug 2026):
                # upsert + analyst + write_trace dalam SATU session → error
                # analyst nanti → session.rollback() → row ModelVersion yang
                # baru di-upsert IKUT rollback → model_versions tidak pernah
                # berubah → llm_usage resolve ke oc/deepseek stale.
                # Commit di sini agar row persist sebelum analyst jalan.
                try:
                    await session.commit()
                except Exception:  # nosec B110 — best-effort
                    await session.rollback()
            gateway = Gateway(
                registry=model_registry,
                budget=BudgetGate({}),
                client=client,
                fallbacks=fallback_provider,
                session=session,  # wajib — llm_usage + reasoning_traces (audit)
            )
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

            # 19 Aug 2026 A4: Support/Resistance MULTI-TIMEFRAME (1m/5m/15m/1h)
            # — trader profesional selalu baca S/R minor/major di beberapa TF.
            # Sebelumnya analyst HANYA dapat EMA/ATR/RSI (tanpa S/R).
            _sr_json = "null"
            try:
                from lumine.trading.support_resistance import compute_multi_tf

                _bar_sets: dict[str, list[dict[str, object]]] = {}
                for _tf_table in ("bars_1m", "bars_15m", "bars_1h"):  # noqa: S608-allowlisted
                    _tf_rows = (
                        await session.execute(
                            text(
                                f"SELECT ts, open, high, low, close, volume "  # noqa: S608 — allowlist bars_1m/15m/1h
                                f"FROM {_tf_table} WHERE symbol = :s "
                                f"ORDER BY ts DESC LIMIT 60"
                            ),
                            {"s": symbol},
                        )
                    ).all()
                    if _tf_rows:
                        _bar_sets[_tf_table.replace("bars_", "")] = [
                            {
                                "high": float(r.high),
                                "low": float(r.low),
                                "close": float(r.close),
                            }
                            for r in reversed(_tf_rows)
                        ]
                # Tambahkan 5m yang sudah dimuat (hindari query ulang)
                _bar_sets["5m"] = [
                    {"high": float(b["high"]), "low": float(b["low"]), "close": float(b["close"])}
                    for b in bars
                ]
                if len(_bar_sets.get("5m", [])) >= 12:
                    _sr = compute_multi_tf(_bar_sets)
                    _sr_json = _json.dumps(_sr, ensure_ascii=False)
            except Exception:  # nosec B110 — S/R non-fatal
                pass

            closes = [b["close"] for b in bars]
            atr_14 = float(atr(bars, period=14))
            rsi_14 = float(rsi(bars, period=14))
            ema_20 = float(sum(closes[-20:]) / Decimal(20))
            ema_50 = float(sum(closes[-50:]) / Decimal(min(50, len(closes))))
            last = bars[-1]
            ohlc = f"[{last['close']}, {max(b['high'] for b in bars[-5:])}, {min(b['low'] for b in bars[-5:])}, {closes[-1]}]"

            # ── Context real untuk SEMUA analyst (v2, 17 Aug 2026) ─────────
            # Macro/news/smc butuh variabel yang tadinya tidak disediakan →
            # MissingVariableError → analyst gagal → cycle batal. Sekarang
            # semua variabel diisi: nilai yang bisa dihitung dari bars_5m
            # dihitung real; yang butuh feed eksternal (yield, dxy, news)
            # diberi nilai jujur "unavailable" — LLM tetap beralasan dengan
            # konteks yang tersedia, bukan gagal parse.
            recent_high = float(max(b["high"] for b in bars[-20:]))
            recent_low = float(min(b["low"] for b in bars[-20:]))
            # Konteks trading live (v3, 17 Aug 2026): dari EA status + posisi.
            # Agen butuh data yang sama dengan trader manusia: harga, spread,
            # session H/L, volatility, exposure, P&L, leverage.
            import redis as redis_lib

            live_status: dict[str, str] = {}
            try:
                _r = redis_lib.from_url(settings.redis_url)
                _raw = await _r.hgetall("mt5:status")
                if _raw:
                    live_status = {
                        k.decode() if isinstance(k, bytes) else str(k): (
                            v.decode() if isinstance(v, bytes) else str(v)
                        )
                        for k, v in _raw.items()
                    }
            except Exception:
                pass  # status tidak wajib — analyst tetap jalan

            # Open positions context (19 Aug 2026 P1): LLM tahu posisi open
            # (side/lot/entry/SL/TP/P&L) → bisa jawab "hold/modify/close".
            open_positions_json = "[]"
            try:
                _rows = (
                    await session.execute(
                        select(Position).where(Position.status == "open")
                    )
                ).scalars().all()
                _ops = [
                    {
                        "ticket": p.mt5_ticket,
                        "symbol": p.symbol,
                        "side": p.side,
                        "size": float(p.size or 0),
                        "entry": float(p.avg_entry or 0),
                        "sl": float(p.sl) if p.sl else None,
                        "tp": float(p.tp) if p.tp else None,
                        "pnl": (
                            float(p.mt5_profit)
                            if getattr(p, "mt5_profit", None) is not None
                            else None
                        ),
                    }
                    for p in _rows
                    if p.mt5_ticket is not None
                ]
                open_positions_json = _json.dumps(_ops, ensure_ascii=False)
            except Exception:  # nosec B110 — posisi tidak wajib
                pass
            atr_pct = (atr_14 / float(last["close"]) * 100) if float(last["close"]) > 0 else 0.0
            variables: dict[str, object] = {
                "symbol": symbol,
                "decision_ts": now.isoformat(),
                "atr_14": atr_14,
                "atr_pct": round(atr_pct, 3),
                "ema_20": round(ema_20, 2),
                "ema_50": round(ema_50, 2),
                "rsi_14": round(rsi_14, 2),
                "ohlc": ohlc,
                "swing_structure": "unknown",
                # Market context live (untuk semua analyst)
                "current_price": float(last["close"]),
                "session_high": live_status.get("session_high", "unknown"),
                "session_low": live_status.get("session_low", "unknown"),
                "spread": live_status.get("spread", "unknown"),
                "volume_24h": live_status.get("volume_24h", "0"),
                "volatility_band": (
                    "high" if atr_pct > 0.5 else "medium" if atr_pct > 0.2 else "low"
                ),
                "market_cap_note": (
                    "XAUUSD is a commodity (gold) — no market cap; liquidity "
                    "proxied by volume + spread + ATR%"
                ),
                "account_equity": live_status.get("equity", "unknown"),
                "account_leverage": live_status.get("leverage", "unknown"),
                "net_position_pnl": live_status.get("net_pnl", "0"),
                "open_positions": open_positions_json,
                # 19 Aug 2026 A1: SEMUA data MT5 dikirim ke agent (bukan
                # cuma equity) — kekosongan data = cacat fatal.
                "mt5_account": _json.dumps(
                    {
                        "equity": live_status.get("equity"),
                        "balance": live_status.get("balance"),
                        "margin": live_status.get("margin"),
                        "free_margin": live_status.get("free_margin"),
                        "margin_level": live_status.get("margin_level"),
                        "leverage": live_status.get("leverage"),
                        "net_pnl": live_status.get("net_pnl"),
                        "symbol": live_status.get("symbol"),
                        "ea_build": live_status.get("ea_build"),
                        "proxy_url": live_status.get("proxy_url"),
                    },
                    ensure_ascii=False,
                ),
                "market_state": _json.dumps(
                    {
                        "bid": live_status.get("bid"),
                        "ask": live_status.get("ask"),
                        "spread": live_status.get("spread"),
                        "session_high": live_status.get("session_high"),
                        "session_low": live_status.get("session_low"),
                    },
                    ensure_ascii=False,
                ),
                # 19 Aug 2026 A4: Support/Resistance MULTI-TF (1m/5m/15m/1h)
                # — pivot + swing minor/major + nearest + strong (>=2 TF).
                "support_resistance": _sr_json,
                # Macro analyst (feed eksternal belum tersedia — jujur)
                "us_10y": _us_10y if _us_10y is not None else 0.0,
                "us_2y": _us_2y if _us_2y is not None else 0.0,
                "dxy": _dxy_json,
                "real_yields": _us_10y if _us_10y is not None else 0.0,
                "fed_stance": _fed_stance,
                "risk_regime": "risk-on" if ema_20 > ema_50 else "risk-off",
                # News analyst (18 Aug 2026): headlines REAL dari cache RSS
                # (fetch worker backend, bukan placeholder "[]").
                "headlines": _news_headlines_json,
                "sentiment_score": 0.0,
                "relevance_score": 0.0,
                # Economic calendar (18 Aug 2026): jadwal event REAL dari
                # _eco_calendar_worker (sebelumnya "none (feed not wired)").
                "scheduled_events": _eco_calendar_json,
                # DXY (18 Aug 2026): sudah di-set di macro section (key `dxy`) —
                # nilai JSON dari cache lumine:dxy (refresh 60s).
                # Backtest learning (18 Aug 2026): pola historis XAUUSD.
                "backtest_learnings": _learning_digest,
                # SMC analyst (struktur dari bars_5m real)
                "order_blocks": f"computed from bars: recent swing high {recent_high:.2f}, swing low {recent_low:.2f}",
                "liquidity_pools": f"buy-side above {recent_high:.2f}, sell-side below {recent_low:.2f}",
                "liquidity_sweep": (
                    f"price above prior high {recent_high:.2f} (sell-side liquidity)"
                    if float(last["close"]) > recent_high
                    else f"price below prior low {recent_low:.2f} (buy-side liquidity)"
                    if float(last["close"]) < recent_low
                    else "none observed in recent window"
                ),
                "fair_value_gaps": "not computed",
                "market_structure": "bullish" if ema_20 > ema_50 else "bearish",
            }

            # Position summary — konteks portofolio untuk risk assessor & CIO
            # (D4-2: risk committee & CIO harus tahu exposure saat ini).
            position_rows = (
                await session.execute(
                    select(Position).where(
                        Position.status == "open",
                        Position.symbol == symbol,
                    )
                )
            ).scalars().all()
            position_summary: dict[str, object] = {
                "count": len(position_rows),
                "net_size": float(
                    sum(
                        (float(p.size) if p.side == "long" else -float(p.size))
                        for p in position_rows
                    )
                ),
                "avg_entry": float(
                    sum(float(p.avg_entry) for p in position_rows) / len(position_rows)
                    if position_rows
                    else 0.0
                ),
                "unrealized_pnl": float(sum(float(p.mt5_profit or 0) for p in position_rows)),
            }

            lineage_id = uuid4()
            # ── Multi-analyst (v2, 17 Aug 2026) ────────────────────────────
            # Semua 4 analyst dijalankan PARALEL (technical, macro, news, smc)
            # — masing-masing LLM call via 9router. Sebelumnya hanya technical
            # (macro/news/smc di-skip karena "feed eksternal belum ada").
            # Variabel market context yang sama, tapi analyst punya fokus
            # masing-masing (D4-2): technical = price action/indikator,
            # macro = fundamental/rates, news = sentimen berita, smc = market
            # structure/liquidity.
            analyst_inputs: list[dict[str, object]] = []

            analyst_specs = [
                ("technical_analyst", run_technical_analyst, "Technical Analyst"),
                ("macro_analyst", run_macro_analyst, "Macro Analyst"),
                ("news_analyst", run_news_analyst, "News Analyst"),
                ("smc_analyst", run_smc_analyst, "SMC Analyst"),
            ]

            analyst_results: list[tuple[str, str, object]] = []

            async def _run_one(stage: str, fn: object, label: str) -> tuple[str, str, object]:
                run_fn = fn  # type: ignore[assignment]
                # FIX 19 Aug 2026: session PER STAGE — analyst dijalankan
                # PARALEL (gather) tapi SHARE session utama → asyncpg
                # "manually started transaction" → worker macet + pool
                # corrupt. Buat + close session sendiri tiap stage.
                _stage_session = None
                try:
                    _stage_session = get_sessionmaker()()
                except Exception:  # nosec B110 — fallback tanpa session
                    pass
                # 18 Aug 2026: per-agent prompt override dari profil aktif
                # (user: "prompt bisa diatur sendiri" per agent). Override
                # di-mix ke variabel `profile_override` → prompt templates
                # menyisipkannya bila ada; tanpa override → tidak berubah.
                stage_vars = dict(variables)
                try:
                    overrides = (_active_profile.get("agent_overrides") or {})
                    if isinstance(overrides, dict) and overrides.get(stage):
                        stage_vars["profile_override"] = str(overrides[stage])
                    else:
                        stage_vars["profile_override"] = ""
                    stage_vars["active_profile"] = str(
                        _active_profile.get("id", "scalping_1m")
                    )
                    stage_vars["profile_timeframe"] = str(
                        _active_profile.get("timeframe", variables.get("timeframe", "5m"))
                    )
                except Exception:
                    stage_vars["profile_override"] = ""
                try:
                    out = await run_fn(
                        gateway=gateway,
                        registry=prompt_registry,
                        lineage_id=lineage_id,
                        workflow_run_id=result["run_id"],
                        stage_run_id=stage,
                        model_version_id=mv_id,
                        idempotency_key=f"{lineage_id}:{stage}",
                        variables=stage_vars,
                        # FIX 19 Aug 2026: analyst dijalankan PARALEL (gather)
                        # tapi SHARE session → asyncpg "cannot use
                        # Connection.transaction() in a manually started
                        # transaction" → worker macet + semua request DB error.
                        # Tiap stage pakai session SENDIRI (commit + close).
                        session=_stage_session,
                    )
                finally:
                    # close di finally — leak koneksi = pool corrupt
                    if _stage_session is not None:
                        try:
                            await _stage_session.close()
                        except Exception:  # nosec B110 — best-effort cleanup
                            pass
                await publisher.publish(
                    SSEEvent(
                        event_type="analyst_output",
                        channel="analyst-outputs",
                        data={
                            "portfolio_id": "default",
                            "symbol": symbol,
                            "analyst_name": label,
                            "recommendation": str(out.parsed.get("recommendation", "hold")),
                            "confidence": float(out.parsed.get("confidence", 0.5)),
                            "reasoning": str(out.parsed.get("reasoning", ""))[:500],
                            "timestamp": now.isoformat(),
                        },
                    )
                )
                return stage, label, out

            # Jalankan 4 analyst parallel (LLM call independen).
            analyst_tasks = [
                _run_one(stage, fn, label) for stage, fn, label in analyst_specs
            ]
            done = await asyncio.gather(*analyst_tasks, return_exceptions=True)

            # Kumpulkan hasil yang sukses; analyst gagal di-log, tidak
            # menggagalkan cycle (resilience: 1 analyst down ≠ komite mati).
            for outcome in done:
                if isinstance(outcome, BaseException):
                    err_text = str(outcome)[:200]
                    print(f"decision_cycle: analyst failed: {type(outcome).__name__}: {err_text}", flush=True)
                    # B10c (18 Aug 2026): publish kegagalan analyst ke SSE —
                    # superadmin monitoring (channel llm-usage, event
                    # analyst_failed) + deteksi LLM down (429/rate-limit).
                    try:
                        await publisher.publish(
                            SSEEvent(
                                event_type="analyst_failed",
                                channel="llm-usage",
                                data={
                                    "error": err_text,
                                    "kind": type(outcome).__name__,
                                    "llm_down": "429" in err_text or "Rate limit" in err_text
                                    or "timed out" in err_text or "FallbackExhausted" in err_text,
                                    "timestamp": now.isoformat(),
                                },
                            )
                        )
                    except Exception:
                        pass
                    continue
                stage, label, out = outcome
                analyst_inputs.append(out.parsed)
                analyst_results.append((stage, label, out))
                # B10b (18 Aug 2026): publish usage realtime → LLM Routing
                # tab (WS/SSE channel llm-usage) — UI live tanpa tunggu commit.
                try:
                    await publisher.publish(
                        SSEEvent(
                            event_type="llm_usage",
                            channel="llm-usage",
                            data={
                                "role": stage,
                                "model": getattr(out, "model_used", "unknown"),
                                "fallback_hops": getattr(out, "fallback_hops", 0),
                                "degraded": bool(getattr(out, "degraded", False)),
                                "tokens_in": 0,
                                "tokens_out": 0,
                                "timestamp": now.isoformat(),
                            },
                        )
                    )
                except Exception:
                    pass  # publish gagal tidak menggagalkan cycle
                # G3: journal per analyst
                await log_step(
                    session,
                    workflow_id=result["run_id"],
                    step_name=stage,
                    status="completed",
                    duration_ms=int((datetime.now(UTC) - now).total_seconds() * 1000),
                    input_snapshot={"symbol": symbol, "ohlc": ohlc},
                    output_snapshot={
                        "recommendation": str(out.parsed.get("recommendation", "hold")),
                        "confidence": float(out.parsed.get("confidence", 0.5)),
                    },
                    lineage_id=None,
                )
                # B5: persist signal per analyst → dashboard AI confidence.
                # FIX 18 Aug 2026: analyst AI kirim `bias` (bullish/bearish/
                # neutral) di parsed — SEBELUMNYA worker baca field
                # `recommendation` yang TIDAK ada di analyst_output schema
                # → default "hold" → semua signal neutral (padahal
                # reasoning_traces penuh bias bearish/bullish!). Bias dulu,
                # fallback recommendation.
                rec = str(out.parsed.get("bias", out.parsed.get("recommendation", "neutral"))).lower()
                direction = (
                    "bullish" if rec in ("buy", "long", "bullish")
                    else "bearish" if rec in ("sell", "short", "bearish")
                    else "neutral"
                )
                session.add(
                    SignalRow(
                        run_id=result["run_id"],
                        symbol=symbol,
                        analyst=label,
                        direction=direction,
                        confidence=Decimal(str(float(out.parsed.get("confidence", 0.5)))),
                        rationale=str(out.parsed.get("reasoning", ""))[:500],
                        generated_at=now,
                    )
                )

            if not analyst_inputs:
                msg = "all analysts failed — aborting cycle"
                raise RuntimeError(msg)

            # Risk Assessor — evaluasi exposure/risk dari posisi + signal.
            # Konsumsi analyst consensus; output dipakai IC forum sebagai
            # constraint (D4-2 risk committee).
            # NOTE: run_risk_assessor pakai keyword args spesifik (bukan
            # `variables` dict) — symbol/decision_ts/proposal_summary/
            # portfolio_context/volatility_band (17 Aug 2026).
            # 19 Aug 2026 P1 (ara #12): analyst_alignment — konsensus analyst
            # (bullish/bearish/neutral count). IC + CIO lihat ini: kalau 3/4
            # analyst aligned, CIO boleh lebih responsif (bukan sekadar HOLD
            # karena 2-vs-2). Profile-aware decision policy.
            _bull = sum(
                1
                for a in analyst_inputs
                if str(a.get("bias", a.get("recommendation", ""))).lower()
                in ("bullish", "buy", "long")
            )
            _bear = sum(
                1
                for a in analyst_inputs
                if str(a.get("bias", a.get("recommendation", ""))).lower()
                in ("bearish", "sell", "short")
            )
            _neut = len(analyst_inputs) - _bull - _bear
            _consensus = "bullish" if _bull > _bear else ("bearish" if _bear > _bull else "mixed")
            portfolio_context = {
                "symbol": symbol,
                "position_summary": position_summary,
                "net_exposure_usd": float(position_summary["net_size"]) * float(last["close"]),
                "margin_used": 0.0,
                "open_pnl": float(position_summary["unrealized_pnl"]),
                "analyst_alignment": {
                    "bullish": _bull,
                    "bearish": _bear,
                    "neutral": _neut,
                    "consensus": _consensus,
                },
            }
            risk_out = await run_risk_assessor(
                gateway=gateway,
                registry=prompt_registry,
                lineage_id=lineage_id,
                workflow_run_id=result["run_id"],
                stage_run_id="risk_assessor",
                model_version_id=mv_id,
                idempotency_key=f"{lineage_id}:risk_assessor",
                symbol=symbol,
                decision_ts=now.isoformat(),
                proposal_summary={
                    "analyst_inputs": analyst_inputs,
                    "symbol": symbol,
                    "last_close": float(last["close"]),
                },
                portfolio_context=portfolio_context,
                volatility_band="normal",
                session=session,
            )
            await publisher.publish(
                SSEEvent(
                    event_type="risk_assessment",
                    channel="risk-assessments",
                    data={
                        "portfolio_id": "default",
                        "symbol": symbol,
                        "risk_level": str(risk_out.parsed.get("risk_level", "medium")),
                        "max_position_size": float(risk_out.parsed.get("max_position_size", 0.01)),
                        "stop_loss_pct": float(risk_out.parsed.get("stop_loss_pct", 1.0)),
                        "reasoning": str(risk_out.parsed.get("reasoning", ""))[:500],
                        "timestamp": now.isoformat(),
                    },
                )
            )

            # Debate moderator (19 Aug 2026 P1): ara #21 — SEBELUMNYA tidak
            # pernah dipanggil (debate_held=False hardcode). Deterministic
            # trigger saat inter-analyst disagreement tinggi / IC confidence
            # rendah, lalu summary di-inject ke analyst_inputs (IC + CIO lihat).
            debate_held = False
            try:
                from lumine.autogen_pipeline.debate import run_debate, should_debate

                if should_debate(
                    analyst_inputs,
                    ic_confidence_threshold=0.6,
                    disagreement_threshold=0.5,
                ):
                    debate = await run_debate(
                        gateway=gateway,
                        registry=prompt_registry,
                        lineage_id=lineage_id,
                        workflow_run_id=result["run_id"],
                        stage_run_id="debate_moderator",
                        model_version_id=mv_id,
                        idempotency_key=f"{lineage_id}:debate",
                        symbol=symbol,
                        decision_ts=now.isoformat(),
                        analyst_inputs=analyst_inputs,
                        session=session,
                    )
                    debate_held = True
                    _debate_summary = str(debate.parsed.get("summary", ""))[:800]
                    analyst_inputs = [
                        *analyst_inputs,
                        {"analyst": "debate_moderator", "summary": _debate_summary},
                    ]
                    await publisher.publish(
                        SSEEvent(
                            event_type="debate_output",
                            channel="debate-outputs",
                            data={
                                "symbol": symbol,
                                "summary": _debate_summary,
                                "timestamp": now.isoformat(),
                            },
                        )
                    )
            except Exception as _exc:  # nosec B110 — debate non-fatal
                print(f"decision_cycle: debate skipped: {type(_exc).__name__}", flush=True)

            # IC Forum (LLM real) — konsumsi SEMUA analyst + risk.
            # Urutan (17 Aug 2026): analyst → risk assessor → IC forum →
            # CIO proposer (CIO butuh ic_output dari IC).
            ic = await run_ic_forum(
                gateway=gateway,
                registry=prompt_registry,
                lineage_id=lineage_id,
                workflow_run_id=result["run_id"],
                stage_run_id="ic_forum",
                model_version_id=mv_id,
                idempotency_key=f"{lineage_id}:ic_forum",
                symbol=symbol,
                decision_ts=now.isoformat(),
                analyst_inputs=analyst_inputs,
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

            # CIO Proposer — IC verdict + analyst consensus → proposal eksekusi.
            # (17 Aug 2026): dijalankan SETELAH IC karena butuh ic_output.
            cio_out = await run_cio_proposer(
                gateway=gateway,
                registry=prompt_registry,
                lineage_id=lineage_id,
                workflow_run_id=result["run_id"],
                stage_run_id="cio_proposer",
                model_version_id=mv_id,
                idempotency_key=f"{lineage_id}:cio_proposer",
                symbol=symbol,
                decision_ts=now.isoformat(),
                ic_output={
                    "action": action,
                    "confidence": confidence,
                    "reasoning": str(ic.parsed.get("reasoning", ""))[:500],
                },
                analyst_inputs=analyst_inputs,
                portfolio_context=portfolio_context,
                policy_version_id="policy@v1",
                model_version_ids={"default": str(mv_id)},
                prompt_version_ids={"default": "v1"},
                debate_held=debate_held,
                session=session,
            )
            await publisher.publish(
                SSEEvent(
                    event_type="cio_proposal",
                    channel="cio-proposals",
                    data={
                        "portfolio_id": "default",
                        "symbol": symbol,
                        "proposal": str(cio_out.parsed.get("proposal", "HOLD")),
                        "rationale": str(cio_out.parsed.get("rationale", ""))[:500],
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
                input_snapshot={"symbol": symbol, "analyst_inputs": analyst_inputs},
                output_snapshot={"action": action, "confidence": confidence},
                lineage_id=None,
            )

            # B5: persist signal IC → dashboard AI confidence / signals panel.
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

            # ── EXECUTION GATE (18 Aug 2026) ─────────────────────────
            # User: "AI hanya hold-hold-hold, apakah benar eksekusi?"
            # Sebelumnya pipeline berhenti di CIO proposal — TIDAK ada
            # jalur ke place_order. Sekarang: proposal dievaluasi →
            # threshold confidence (default 0.70, configurable via
            # system_config.execution_min_confidence) + kill switch →
            # enqueue place_order ke MT5 (paper/real via _handle_place_order).
            execution_result: dict[str, Any] | None = None
            try:
                from lumine.rpc.queue import enqueue_command

                # FIX 18 Aug 2026: schema CIO pakai field `action` (bukan
                # `proposal`!) — SEBELUMNYA baca "proposal" → selalu HOLD →
                # execution gate tak pernah trigger walau AI bilang SELL.
                proposal = str(
                    cio_out.parsed.get("action", cio_out.parsed.get("proposal", "HOLD"))
                ).upper()
                prop_side = str(cio_out.parsed.get("side", "") or "").upper()
                prop_size = float(cio_out.parsed.get("size", 0) or 0)
                prop_sl = cio_out.parsed.get("stop_loss")
                prop_tp = cio_out.parsed.get("take_profit")

                # Threshold confidence dari system_config ATAU profil aktif
                # (18 Aug 2026: profil punya min_confidence sendiri).
                min_conf = 0.70
                try:
                    if _r is None:
                        _r = await get_redis()
                    _raw_conf = await _r.hget("lumine:system_config", "execution_min_confidence")
                    if _raw_conf is not None:
                        min_conf = float(_raw_conf)
                    if _active_profile.get("min_confidence"):
                        min_conf = float(_active_profile["min_confidence"])
                except Exception:
                    pass
                # Kill switch check.
                try:
                    if _r is None:
                        _r = await get_redis()
                    _ks = await _r.hget(settings.kill_switch_key, "armed")
                    _halted = _ks is not None and str(_ks) == "1"
                except Exception:
                    _halted = False

                eligible = (
                    proposal in ("BUY", "SELL", "LONG", "SHORT")
                    and prop_side in ("BUY", "SELL")
                    and prop_size >= 0.01
                    and confidence >= min_conf
                    and not _halted
                )
                # ── AUTO SL/TP dari profil (18 Aug 2026): jika AI tidak
                # beri stop_loss/take_profit, hitung dari ATR x multiplier
                # profil (sl_atr_mult / tp_atr_mult). User: "semua auto
                # sl tp, cl, be dan entry out otomatis".
                try:
                    if eligible and (prop_sl is None or prop_tp is None):
                        atr_val = 0.0
                        try:
                            from lumine.features.indicators import atr as _atr

                            if len(bars) >= 20:
                                atr_val = float(_atr(bars, period=14))
                        except Exception:
                            atr_val = 0.0
                        if atr_val <= 0.0:
                            # Fallback: 0.5% harga
                            atr_val = float(last["close"]) * 0.005
                        entry_px = float(last["close"])
                        sl_mult = float(_active_profile.get("sl_atr_mult", 1.0))
                        tp_mult = float(_active_profile.get("tp_atr_mult", 2.0))
                        # 19 Aug 2026 A3: CLAMP — SL/TP dari LLM (CIO) TIDAK
                        # boleh jauh melebihi profil (user: "scalping tp sl
                        # sangat besar"). Deterministic risk menang: max
                        # distance = ATR x mult x 1.5; di luar → pakai profil.
                        sl_prof = (
                            round(entry_px - atr_val * sl_mult, 2)
                            if prop_side == "BUY"
                            else round(entry_px + atr_val * sl_mult, 2)
                        )
                        tp_prof = (
                            round(entry_px + atr_val * tp_mult, 2)
                            if prop_side == "BUY"
                            else round(entry_px - atr_val * tp_mult, 2)
                        )
                        try:
                            _prop_sl_f = float(prop_sl) if prop_sl is not None else None
                            _prop_tp_f = float(prop_tp) if prop_tp is not None else None
                        except (TypeError, ValueError):
                            _prop_sl_f = _prop_tp_f = None
                        if _prop_sl_f is None or abs(_prop_sl_f - entry_px) > atr_val * sl_mult * 1.5:
                            prop_sl = sl_prof
                        if _prop_tp_f is None or abs(_prop_tp_f - entry_px) > atr_val * tp_mult * 1.5:
                            prop_tp = tp_prof
                except Exception:
                    pass
                if eligible:
                    order_id = uuid4()
                    # ── 19 Aug 2026 A5: ENTRY AREA terbaik seperti trader
                    # profesional (berdasarkan profil + S/R): kalau harga di
                    # dekat support -> BUY limit di support (pullback entry);
                    # dekat resistance -> SELL limit di resistance.
                    _entry_candidate = float(last["close"])
                    _entry_note = "market (harga saat ini, no S/R confluence)"
                    _tp_reason = f"RR profil {tp_mult:.1f}:1 (ATR {atr_val:.2f})"
                    try:
                        _sr_parsed = _json.loads(_sr_json) if _sr_json != "null" else None
                        _near_sup = None
                        _near_res = None
                        if _sr_parsed:
                            _near_sup = (
                                _sr_parsed.get("per_timeframe", {})
                                .get("5m", {})
                                .get("nearest_support")
                            )
                            _near_res = (
                                _sr_parsed.get("per_timeframe", {})
                                .get("5m", {})
                                .get("nearest_resistance")
                            )
                        if prop_side == "BUY" and _near_sup:
                            _dist = abs(_entry_candidate - float(_near_sup)) / _entry_candidate
                            if _dist < 0.004:
                                _entry_candidate = float(_near_sup)
                                _entry_note = f"limit entry di support {_near_sup} (pullback, jarak {_dist*100:.2f}%)"
                            if _near_res:
                                _tp_reason = f"TP {prop_tp} menuju resistance {_near_res} (S/R confluence)"
                        elif prop_side == "SELL" and _near_res:
                            _dist = abs(_entry_candidate - float(_near_res)) / _entry_candidate
                            if _dist < 0.004:
                                _entry_candidate = float(_near_res)
                                _entry_note = f"limit entry di resistance {_near_res} (pullback, jarak {_dist*100:.2f}%)"
                            if _near_sup:
                                _tp_reason = f"TP {prop_tp} menuju support {_near_sup} (S/R confluence)"
                    except Exception:  # nosec B110 — entry optimizer optional
                        pass

                    # ── 19 Aug 2026 A5: alasan keputusan LLM disimpan
                    # (Redis, TTL 7 hari) -> detail order menampilkannya.
                    _ai_reason = {
                        "action": prop_side,
                        "side": prop_side,
                        "confidence": round(float(confidence), 3),
                        "size": prop_size,
                        "stop_loss": prop_sl,
                        "take_profit": prop_tp,
                        "entry": round(_entry_candidate, 5),
                        "entry_note": _entry_note,
                        "tp_reason": _tp_reason,
                        "profile_id": _active_profile.get("id"),
                        "timeframe": _active_profile.get("timeframe"),
                        "analyst_alignment": portfolio_context.get("analyst_alignment"),
                        "model_version": str(mv_id)[:8],
                        "timestamp": now.isoformat(),
                    }
                    try:
                        if _r is None:
                            _r = await get_redis()
                        await _r.set(
                            f"lumine:order:reason:{order_id}",
                            _json.dumps(_ai_reason, ensure_ascii=False),
                            ex=604800,
                        )
                    except Exception:  # nosec B110 — reason non-fatal
                        pass

                    await enqueue_command(
                        "place_order",
                        {
                            "order_id": str(order_id),
                            "symbol": symbol,
                            "volume": prop_size,
                            "order_type": "BUY" if prop_side == "BUY" else "SELL",
                            "stop_loss": prop_sl,
                            "take_profit": prop_tp,
                        },
                    )
                    execution_result = {
                        "order_id": str(order_id),
                        "action": prop_side,
                        "volume": prop_size,
                        "confidence": confidence,
                        "threshold": min_conf,
                    }
                    print(
                        f"[EXEC] ORDER {prop_side} {prop_size} {symbol} "
                        f"conf={confidence:.2f}>= {min_conf} → enqueued {order_id}",
                        flush=True,
                    )
                else:
                    execution_result = {
                        "action": proposal,
                        "skipped_reason": (
                            "halted" if _halted
                            else "confidence_below_threshold" if confidence < min_conf
                            else "no_valid_side_size"
                        ),
                        "confidence": confidence,
                        "threshold": min_conf,
                    }
            except Exception as _exec_exc:  # nosec B110 — eksekusi tidak boleh crash cycle
                print(f"[EXEC] error: {str(_exec_exc)[:150]}", flush=True)

            return {
                "status": "completed",
                "decision": action.lower(),
                "confidence": confidence,
                "analyst_recommendation": "aggregated",
                "execution": execution_result,
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


async def _handle_place_order(  # noqa: PLR0915 — execution handler deterministic & banyak branch
    payload: dict[str, Any], publisher: SSEPublisher, settings: Settings
) -> dict[str, Any]:
    """Place order via MT5 bridge (real or paper trading simulation).

    Payload: {order_id, symbol, volume, order_type, stop_loss?, take_profit?}
    Returns: {order_id, command_id, status, fill_price?, ticket?}
    """
    from uuid import UUID

    from lumine.trading.mt5_bridge import MT5Bridge, create_open_order_command

    order_id = payload.get("order_id")
    symbol = payload.get("symbol", "XAUUSD")
    volume = float(payload.get("volume", 0.01))
    order_type = payload.get("order_type", "BUY")
    stop_loss = payload.get("stop_loss")
    take_profit = payload.get("take_profit")

    if not order_id:
        return {"error": "order_id required", "status": "rejected"}

    try:
        order_uuid = UUID(order_id)
    except ValueError:
        return {"error": "invalid order_id", "status": "rejected"}

    # Create command message
    command = create_open_order_command(
        order_id=order_uuid,
        symbol=symbol,
        volume=volume,
        order_type=order_type.upper(),
        stop_loss=float(stop_loss) if stop_loss else None,
        take_profit=float(take_profit) if take_profit else None,
    )

    # Paper trading mode: simulate fill without MT5.
    # 18 Aug 2026: baca dari Redis system_config (realtime, tanpa restart)
    # — user matikan paper_trading via superadmin tapi worker tetap env
    # static → "tidak tersimpan, disuruh restart api container".
    paper_trading = settings.paper_trading
    try:
        from lumine.data.redis_client import get_redis

        _r = await get_redis()
        _raw = await _r.hget("lumine:system_config", "paper_trading")
        if _raw is not None:
            paper_trading = str(_raw).lower() in ("1", "true", "yes")
    except Exception:  # nosec B110 — Redis down → fallback env
        pass
    if paper_trading:
        import secrets

        # Simulate fill with random slippage (secrets for non-crypto use)
        base_price = 3350.0 if symbol == "XAUUSD" else 1.1000  # fallback
        slippage = secrets.randbelow(100) / 100.0 - 0.5  # $0.50 slippage range
        fill_price = base_price + slippage

        result = {
            "order_id": str(order_id),
            "command_id": command.command_id,
            "status": "FILLED",
            "ticket": secrets.randbelow(900000) + 100000,  # 6-digit ticket
            "fill_price": round(fill_price, 2),
            "fill_volume": volume,
            "paper_trading": True,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Publish SSE event
        await publisher.publish(
            SSEEvent(
                event_type="order_filled",
                channel="orders",
                data=result,
            )
        )

        # 19 Aug 2026 P1: persist paper order ke DB (portfolio_id="paper")
        # — research page bandingkan PAPER vs REAL (orders by portfolio_id).
        try:
            from decimal import Decimal

            from lumine.data.models import Order as _Order
            from lumine.data.session import get_sessionmaker as _gbs

            _ai_reason_str = None
            try:
                _reason_raw = await _r.get(f"lumine:order:reason:{order_id}")
                if _reason_raw:
                    _ai_reason_str = _reason_raw.decode() if isinstance(_reason_raw, bytes) else _reason_raw
            except Exception:  # nosec B110
                pass
            async with _gbs()() as _sess:
                _sess.add(
                    _Order(
                        order_id=order_uuid,
                        portfolio_id="paper",
                        symbol=symbol,
                        side=order_type.lower(),
                        order_type="market",
                        volume=Decimal(str(volume)),
                        price=Decimal(str(fill_price)),
                        status="filled",
                        filled_volume=Decimal(str(volume)),
                        mt5_ticket=int(result["ticket"]),
                        ai_reason=_ai_reason_str,
                    )
                )
                await _sess.commit()
        except Exception:  # nosec B110 — persist paper non-fatal
            pass

        return result

    # Real trading mode: send to MT5 via bridge
    try:
        bridge = await MT5Bridge.connect(settings)
        command_id = await bridge.send_command(command)

        result = {
            "order_id": str(order_id),
            "command_id": command_id,
            "status": "PENDING",
            "paper_trading": False,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        await publisher.publish(
            SSEEvent(
                event_type="order_submitted",
                channel="orders",
                data=result,
            )
        )

        return result

    except Exception:
        logger.exception("place_order failed")
        return {
            "order_id": str(order_id),
            "command_id": command.command_id,
            "status": "ERROR",
            "error": "place_order failed",
            "timestamp": datetime.now(UTC).isoformat(),
        }


HANDLERS: dict[str, Any] = {
    "run_decision_cycle": _handle_run_decision_cycle,
    "halt_trading": _handle_halt_trading,
    "resume_trading": _handle_resume_trading,
    "cancel_order": _handle_cancel_order,
    "place_order": _handle_place_order,
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
        elif command == "place_order":
            result = await handler(payload, publisher, settings)  # type: ignore[arg-type]
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
