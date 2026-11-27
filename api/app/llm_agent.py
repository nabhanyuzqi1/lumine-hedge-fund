"""LLM agent audit endpoint (t_f2llm1, KEPUTUSAN_OWNER G1).

Service fund2-llm-agent (loop terpisah, pola fund2-alerts) memanggil LLM lalu
mengirim keputusannya ke sini. Yang disimpan di endpoint ini HANYA audit
(G1 butir 3): setiap keputusan -- termasuk hold -- tercatat di order_events
dengan reasoning + confidence + model + prompt_version + token usage.

Eksekusi order TIDAK lewat sini: loop memakai POST /orders (routes.py) yang
tetap melewati risk gate penuh, sehingga lapisan eksekusi tetap satu-satunya.
Auth: login+CSRF dengan kredensial role 'agent' (bukan admin) -- role agent
ditolak 403 di semua endpoint kontrol (kill-switch/triggers/strategy mode).
"""
from __future__ import annotations

import os

import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db, llm_budget, llm_models, llm_risk, market, preflight
from .auth import require_csrf, require_2fa
from .guardrail_ranges import (
    GuardrailRangeError,
    LLM_INTERVAL_RANGE_S,
    effective_interval,
    validate_interval_s,
)
from .kill_switch import transition_close
from .portfolio_risk import PORTFOLIO_LOCK_KEY
from .sse import broadcaster
from .state_machine import fetchall, fetchone

router = APIRouter(prefix="/llm-agent")


class AgentDecisionBody(BaseModel):
    """Audit keputusan agent LLM per siklus (G1 butir 3)."""

    symbol: Optional[str] = Field(default=None, min_length=3, max_length=20)
    # v2.0.0 (FUND2-LLM-B1): order | cut | hold | sl | be | tp | layer |
    # invalid; `close` tetap diterima sebagai alias `cut` (v1.2.0).
    kind: str
    reasoning: str = Field(min_length=1, max_length=8000)
    confidence: float = Field(ge=0.0, le=1.0)
    model: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=50)
    cycle_id: str = Field(min_length=8, max_length=64)
    prompt_tokens: Optional[int] = Field(default=None, ge=0)
    completion_tokens: Optional[int] = Field(default=None, ge=0)
    latency_ms: Optional[int] = Field(default=None, ge=0)
    error: Optional[str] = Field(default=None, max_length=2000)
    order_id: Optional[str] = Field(default=None, max_length=64)  # UUID order bila kind=order/close/cut/layer
    # t_afd7fe4e butir C: anggaran latensi + bukti prompt caching.
    cycle_latency_ms: Optional[int] = Field(default=None, ge=0)   # durasi siklus penuh
    prompt_cache_hit_tokens: Optional[int] = Field(default=None, ge=0)
    prompt_cache_miss_tokens: Optional[int] = Field(default=None, ge=0)
    # t_2a1fbf01 kriteria 3: jejak specialist yang mendukung keputusan ini
    # (state/model/latensi per peran) + peran yang gagal/timeout. Tanpa field
    # ini Pydantic membuangnya diam-diam dan audit tidak bisa membuktikan
    # keputusan mana yang berjalan terdegradasi.
    evidence: Optional[dict] = None
    evidence_missing: Optional[list[str]] = None


# kind -> to_status order_events (v2.0.0). kind lama TIDAK berubah perilaku;
# `close` = alias `cut`; sl/be/tp = AGENT_MODIFY; layer = AGENT_LAYER.
AGENT_KIND_TO_STATUS: dict = {
    "order": "AGENT_ORDER",
    "close": "AGENT_CLOSE",
    "cut": "AGENT_CLOSE",
    "hold": "AGENT_HOLD",
    "invalid": "AGENT_INVALID",
    "sl": "AGENT_MODIFY",
    "be": "AGENT_MODIFY",
    "tp": "AGENT_MODIFY",
    "layer": "AGENT_LAYER",
}
# kind yang wajib membawa order_id (keputusan yang melahirkan/menutup order).
_AGENT_KINDS_NEED_ORDER_ID = ("order", "close", "cut", "layer")
# kind tanpa order_id (audit murni / modify di-audit lewat AGENT_MODIFY-nya
# sendiri oleh POST /llm-agent/modify).
_AGENT_KINDS_NO_ORDER_ID = ("hold", "invalid", "sl", "be", "tp")


@router.post("/decisions")
async def create_agent_decision(body: AgentDecisionBody, user: dict = Depends(require_csrf)):
    """Catat satu keputusan agent LLM ke order_events (G1 butir 3).

    Keputusan hold/close/cut tanpa order baru: order_id NULL + to_status
    AGENT_HOLD / AGENT_CLOSE. Keputusan order/layer: order_id diisi
    body.order_id (order yang baru dibuat via POST /orders oleh agent)
    sehingga reasoning menempel pada rantai order. Keputusan sl/be/tp:
    dieksekusi + ter-audit AGENT_MODIFY oleh POST /llm-agent/modify; audit
    di sini hanya keputusan (order_id NULL). Append-only; tidak mengubah
    status order.
    """
    if body.kind not in AGENT_KIND_TO_STATUS:
        raise HTTPException(
            422, "kind harus order | cut | close | hold | sl | be | tp | layer | invalid")
    to_status = AGENT_KIND_TO_STATUS[body.kind]
    if body.kind in _AGENT_KINDS_NEED_ORDER_ID and not body.order_id:
        raise HTTPException(422, f"kind={body.kind} membutuhkan order_id")
    if body.kind in _AGENT_KINDS_NO_ORDER_ID and body.order_id:
        raise HTTPException(422, f"kind={body.kind} tidak boleh membawa order_id")

    decision = {
        "kind": body.kind,
        "symbol": body.symbol,
        "reasoning": body.reasoning,
        "confidence": body.confidence,
        "model": body.model,
        "prompt_version": body.prompt_version,
        "cycle_id": body.cycle_id,
        # Tanpa ini baris keputusan tidak bisa diatribusikan ke simbolnya:
        # QA "hanya simbol sesi aktif" gagal karena 22 baris symbol=null.
        "symbol": body.symbol,
        "prompt_tokens": body.prompt_tokens,
        "completion_tokens": body.completion_tokens,
        "latency_ms": body.latency_ms,
        "error": body.error,
        "cycle_latency_ms": body.cycle_latency_ms,
        "prompt_cache_hit_tokens": body.prompt_cache_hit_tokens,
        "prompt_cache_miss_tokens": body.prompt_cache_miss_tokens,
        "username": user["username"],
    }
    if body.evidence:
        decision["evidence"] = body.evidence
        decision["evidence_missing"] = list(body.evidence_missing or [])
    async with db.pool().connection() as conn:
        if body.order_id:
            row = await fetchone(conn, "SELECT id, status FROM orders WHERE id = %s", (body.order_id,))
            if row is None:
                raise HTTPException(404, "order_id not found")
            order_id = row["id"]
            from_status = row["status"]
        else:
            order_id = None
            from_status = None
        await conn.execute(
            """
            INSERT INTO order_events (order_id, from_status, to_status, payload, decision)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                order_id,
                from_status,
                to_status,
                json.dumps({"source": "llm_agent", "username": user["username"]}),
                json.dumps(decision),
            ),
        )
    broadcaster.publish(
        {"type": "agent_decision", "kind": body.kind, "symbol": body.symbol, "cycle_id": body.cycle_id}
    )
    return {"ok": True, "to_status": to_status}


class AgentCloseBody(BaseModel):
    """Keputusan close LLM untuk satu simbol (G1)."""

    symbol: str = Field(min_length=3, max_length=20)


@router.post("/close")
async def close_symbol_positions(body: AgentCloseBody, user: dict = Depends(require_csrf)):
    """Tutup posisi OPEN strategy 'llm' untuk `symbol` (keputusan close agent).

    Order CLOSE tidak melewati risk gate (penutupan selalu diizinkan, pola
    kill-switch flatten_positions). Hanya posisi milik strategy 'llm' yang
    boleh ditutup oleh agent -- posisi strategy lain tidak disentuh.
    """
    symbol = body.symbol.upper()
    async with db.pool().connection() as conn:
        async with conn.transaction():
            positions = await fetchall(
                conn,
                """
                SELECT p.* FROM positions p JOIN orders o ON o.id = p.order_id
                WHERE p.status = 'OPEN' AND p.symbol = %s AND o.strategy = 'llm'
                """,
                (symbol,),
            )
            if not positions:
                raise HTTPException(404, f"tidak ada posisi llm OPEN untuk {symbol}")
            created: list[str] = []
            for p in positions:
                row = await fetchone(
                    conn,
                    """
                    INSERT INTO orders (user_id, symbol, side, volume, sl, tp, strategy,
                                        ticket, action, status)
                    VALUES (%s, %s, %s, %s, NULL, NULL, 'llm', %s, 'CLOSE', 'RECEIVED')
                    RETURNING id
                    """,
                    (
                        user["user_id"], p["symbol"],
                        "SELL" if p["side"] == "BUY" else "BUY",
                        float(p["volume"]), p["ticket"],
                    ),
                )
                await conn.execute(
                    """
                    INSERT INTO order_events (order_id, from_status, to_status, payload)
                    VALUES (%s, NULL, 'RECEIVED', %s)
                    """,
                    (row["id"], json.dumps({"source": "llm_agent", "action": "CLOSE",
                                            "position_ticket": p["ticket"]})),
                )
                await transition_close(conn, row["id"])
                created.append(str(row["id"]))
    broadcaster.publish({"type": "agent_close", "symbol": symbol, "n": len(created)})
    return {"ok": True, "symbol": symbol, "close_order_ids": created}


class AgentCycleBody(BaseModel):
    """Siklus agent LLM: broadcast SSE saja (FUND2-LLM-B1 D2 butir 1).

    Tidak menyimpan apa pun ke DB; detail keputusan tetap teraudit via
    POST /llm-agent/decisions. phase: started | error.
    """

    cycle_id: str = Field(min_length=8, max_length=64)
    phase: str
    detail: Optional[str] = Field(default=None, max_length=2000)


@router.post("/cycle")
async def agent_cycle(body: AgentCycleBody, user: dict = Depends(require_csrf)):
    """Broadcast event SSE `agent_cycle` per siklus loop agent (broadcast-only).

    Kegagalan siklus trading TIDAK pernah dipicu endpoint ini maupun
    broadcaster (publish in-memory, tanpa consumer lambat yang blocking).
    """
    if body.phase not in ("started", "error", "skipped"):
        raise HTTPException(422, "phase harus started | error | skipped")
    broadcaster.publish({
        "type": "agent_cycle",
        "cycle_id": body.cycle_id,
        "phase": body.phase,
        "detail": body.detail,
    })
    return {"ok": True, "phase": body.phase}


# ── Pre-flight gate sebelum LLM (t_afd7fe4e butir A) ───────────────────────

class AgentPreflightBody(BaseModel):
    """Kandidat simbol satu siklus; gate memutuskan boleh-tidak memanggil LLM.

    `symbols` = kandidat dari loop (sudah difilter policy allowed_symbols dan
    jadwal hari). Endpoint TIDAK menambah simbol apa pun: simbol di luar
    `allowed_symbols` dibuang, bukan dianalisa.
    """

    cycle_id: str = Field(min_length=8, max_length=64)
    symbols: list[str] = Field(default_factory=list, max_length=8)


def _preflight_candidates(settings: dict, symbols: list[str]) -> list[str]:
    allowed = settings.get("allowed_symbols")
    allowed_set = {str(s).upper() for s in allowed} if isinstance(allowed, list) else None
    out: list[str] = []
    for raw in symbols:
        sym = str(raw).strip().upper()
        if not sym or sym in out:
            continue
        if allowed_set is not None and sym not in allowed_set:
            continue
        out.append(sym)
    return out


async def _record_cycle_skipped(result: dict, cycle_id: str, username: str) -> None:
    """Catat siklus yang dilewati gate (append-only, tanpa order).

    Inilah bukti DoD "tidak ada pemanggilan LLM saat pasar tutup / EA offline":
    satu baris order_events per siklus yang diblok, berisi kode + stage + pesan
    per simbol. Kegagalan pencatatan tidak boleh menggagalkan respons gate.
    """
    decision = {
        "kind": "cycle_skipped",
        "reasoning": (result.get("reason") or "preflight_blocked")[:2000],
        "confidence": 1.0,
        "model": "deterministic-preflight",
        "prompt_version": "preflight-1.0.0",
        "cycle_id": cycle_id,
        "allowed": result.get("allowed") or [],
        "blocked": result.get("blocked") or [],
        "latency_ms": result.get("latency_ms"),
        "username": username,
    }
    try:
        async with db.pool().connection() as conn:
            await conn.execute(
                """
                INSERT INTO order_events (order_id, from_status, to_status, payload, decision)
                VALUES (NULL, NULL, 'CYCLE_SKIPPED', %s, %s)
                """,
                (json.dumps({"cycle_id": cycle_id,
                             "reason": result.get("reason"),
                             "symbols": result.get("allowed") or []}),
                 json.dumps(decision, default=str)),
            )
    except Exception as exc:  # noqa: BLE001 - audit tidak boleh menggagalkan gate
        print(f"[preflight] gagal mencatat cycle_skipped {cycle_id}: {exc!r}", flush=True)


@router.post("/preflight")
async def agent_preflight(body: AgentPreflightBody, user: dict = Depends(require_csrf)):
    """Rantai pre-flight deterministik sebelum LLM (tanpa LLM).

    Mengembalikan `allowed` (simbol yang lolos semua lapisan) + `blocked`
    (kode/stage/pesan alasan). Bila tidak ada yang lolos, satu event
    CYCLE_SKIPPED dicatat supaya siklus tetap terlihat di audit/History.
    """
    settings = await db.get_settings()
    candidates = _preflight_candidates(settings, list(body.symbols))
    async with db.pool().connection() as conn:
        result = await preflight.run_preflight(conn, settings, candidates)
    result["cycle_id"] = body.cycle_id
    if not result["ok"]:
        await _record_cycle_skipped(result, body.cycle_id, user["username"])
    broadcaster.publish({
        "type": "agent_preflight",
        "cycle_id": body.cycle_id,
        "allowed": result.get("allowed") or [],
        "blocked": result.get("blocked") or [],
        "reason": result.get("reason"),
        "latency_ms": result.get("latency_ms"),
    })
    return result


@router.get("/latency")
async def agent_latency(window: int = 30, user: dict = Depends(require_csrf)):
    """p50/p95/max latensi siklus dari audit `order_events.decision`.

    Dasar angka: `cycle_latency_ms` (durasi siklus penuh, diukur loop) dengan
    fallback `latency_ms` (durasi panggilan LLM) untuk data lama. `window`
    = jumlah siklus terakhir yang dihitung (default 30, maks 200).
    Target p95 dari settings `llm_latency_budget.target_p95_s` (default 35 s).
    """
    window = max(1, min(int(window), 200))
    settings = await db.get_settings()
    budget = llm_budget.resolve(settings)
    async with db.pool().connection() as conn:
        rows = await fetchall(
            conn,
            """
            SELECT decision->>'cycle_latency_ms' AS cycle_ms,
                   decision->>'latency_ms' AS llm_ms,
                   decision->>'prompt_tokens' AS prompt_tokens,
                   decision->>'completion_tokens' AS completion_tokens,
                   created_at
            FROM order_events
            WHERE decision IS NOT NULL
              AND decision->>'kind' <> 'evidence'
              AND (decision ? 'cycle_latency_ms' OR decision ? 'latency_ms')
            ORDER BY id DESC LIMIT %s
            """,
            (window,),
        )
    samples: list[float] = []
    for row in rows:
        raw = row["cycle_ms"] or row["llm_ms"]
        try:
            samples.append(float(raw) / 1000.0)
        except (TypeError, ValueError):
            continue
    stats = llm_budget.summarise_latency(samples, float(budget["target_p95_s"]))
    stats["budget"] = budget
    stats["source"] = "order_events.decision"
    return stats


class AgentModifyBody(BaseModel):
    """Modify posisi llm aktif: kind sl | be | tp (FUND2-LLM-B1 D2 butir 2).

    kind sl/be wajib membawa `sl` baru (be = breakeven: entry +- buffer kecil,
    dihitung agent dari konteks); kind tp wajib membawa `tp` baru. Field yang
    tidak relevan untuk kind tsb DITOLAK (kontrak ketik, pola OrderIntent).
    """

    symbol: str = Field(min_length=3, max_length=20)
    kind: str
    sl: Optional[float] = None
    tp: Optional[float] = None
    reasoning: str = Field(min_length=1, max_length=8000)
    confidence: float = Field(ge=0.0, le=1.0)
    model: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=50)
    cycle_id: str = Field(min_length=8, max_length=64)


@router.post("/modify")
async def modify_position(body: AgentModifyBody, user: dict = Depends(require_csrf)):
    """Geser SL (sl/be) atau ubah TP (tp) posisi llm OPEN di `symbol`.

    Validasi gate deterministik (llm_risk.modify_gate_reason): SL hanya boleh
    memperketat (long: SL naik, short: SL turun) atau BE; TP tidak melintasi
    harga sekarang; SL tetap stop yang sah di sisi yang benar dari harga.
    Efek: UPDATE positions.sl/tp + antre bridge_commands MODIFY_SL
    {ticket, sl, tp, reason} (EA sudah support, LumineEA.mq5 ~line 1533) +
    audit event AGENT_MODIFY ke order_events dengan decision JSONB.
    """
    symbol = body.symbol.upper()
    if body.kind not in ("sl", "be", "tp"):
        raise HTTPException(422, "kind harus sl | be | tp")
    if body.kind in ("sl", "be"):
        if body.sl is None:
            raise HTTPException(422, f"kind={body.kind} membutuhkan sl")
        if body.tp is not None:
            raise HTTPException(422, f"kind={body.kind} tidak boleh membawa tp")
    if body.kind == "tp":
        if body.tp is None:
            raise HTTPException(422, "kind=tp membutuhkan tp")
        if body.sl is not None:
            raise HTTPException(422, "kind=tp tidak boleh membawa sl")

    settings = await db.get_settings()
    tick = market.latest(symbol)
    bid = float(tick["bid"]) if tick else None
    ask = float(tick["ask"]) if tick else None

    async with db.pool().connection() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(%s)", (PORTFOLIO_LOCK_KEY,))
            pos = await fetchone(
                conn,
                """
                SELECT p.* FROM positions p JOIN orders o ON o.id = p.order_id
                WHERE p.status = 'OPEN' AND p.symbol = %s AND o.strategy = 'llm'
                ORDER BY p.id LIMIT 1
                """,
                (symbol,),
            )
            if pos is None:
                raise HTTPException(404, f"tidak ada posisi llm OPEN untuk {symbol}")
            cfg = llm_risk.get_llm_agent_v2(settings)
            reason = llm_risk.modify_gate_reason(
                pos, body.kind, body.sl, body.tp, bid=bid, ask=ask, cfg=cfg,
            )
            if reason:
                raise HTTPException(422, reason)
            new_sl = body.sl if body.kind in ("sl", "be") else (
                float(pos["sl"]) if pos["sl"] is not None else None)
            new_tp = body.tp if body.kind == "tp" else (
                float(pos["tp"]) if pos["tp"] is not None else None)
            await conn.execute(
                "UPDATE positions SET sl = %s, tp = %s, updated_at = now() WHERE ticket = %s",
                (new_sl, new_tp, pos["ticket"]),
            )
            await conn.execute(
                """
                INSERT INTO bridge_commands (order_id, action, payload)
                VALUES (%s, 'MODIFY_SL', %s)
                """,
                (pos["order_id"], json.dumps({
                    "ticket": pos["ticket"], "sl": new_sl, "tp": new_tp,
                    "reason": f"llm_agent_{body.kind}",
                })),
            )
            decision = {
                "kind": body.kind,
                "symbol": symbol,
                "ticket": pos["ticket"],
                "sl": new_sl,
                "tp": new_tp,
                "reasoning": body.reasoning,
                "confidence": body.confidence,
                "model": body.model,
                "prompt_version": body.prompt_version,
                "cycle_id": body.cycle_id,
                "username": user["username"],
            }
            await conn.execute(
                """
                INSERT INTO order_events (order_id, from_status, to_status, payload, decision)
                VALUES (%s, NULL, 'AGENT_MODIFY', %s, %s)
                """,
                (
                    pos["order_id"],
                    json.dumps({"source": "llm_agent", "action": "AGENT_MODIFY",
                                "position_ticket": pos["ticket"]}),
                    json.dumps(decision),
                ),
            )
    broadcaster.publish({
        "type": "agent_modify", "symbol": symbol, "kind": body.kind,
        "ticket": pos["ticket"], "cycle_id": body.cycle_id,
    })
    return {"ok": True, "symbol": symbol, "kind": body.kind,
            "ticket": pos["ticket"], "sl": new_sl, "tp": new_tp}


@router.post("/resume")
async def resume_agent(user: dict = Depends(require_2fa)):
    """Resume agent LLM setelah breaker pause (t_f2v22a13/t_3e5853ea).

    Owner-only dengan step-up 2FA (require_2fa = admin + CSRF + TOTP):
    role agent/user ditolak 403, admin tanpa 2FA terdaftar/terverifikasi
    juga 403. Memanggil llm_risk.resume_agent yang me-nonaktifkan pause,
    me-set marker llm_breaker_ack.failed_streak_after (streak FAILED lama
    tidak langsung memicu pause ulang), dan mencatat event AGENT_RESUME.
    """
    pause = await llm_risk.resume_agent(actor=user["username"])
    return {"pause": pause}


@router.get("/status")
async def agent_status(user: dict = Depends(require_csrf)):
    """Status agent LLM untuk dashboard (user mana pun ter-login).

    Melaporkan: pause circuit breaker, batas llm_risk efektif, counter
    order (last_minute/today/failed_streak), dan drawdown hari ini.
    Read-only; tidak mengubah state apa pun.
    """
    settings = await db.get_settings()
    interval_s, interval_source = effective_interval(settings)
    async with db.pool().connection() as conn:
        stats = await llm_risk.llm_order_stats(conn, settings)
        drawdown_pct = await llm_risk.daily_drawdown_pct(conn, settings)
    return {
        "pause": llm_risk.normalize_pause(settings.get("llm_agent_pause")),
        "llm_risk": llm_risk.get_llm_risk(settings),
        "stats": stats,
        "daily_drawdown_pct": drawdown_pct,
        # AUDIT-E (t_bb927ec7): angka yang BENAR-BENAR dipakai loop siklus
        # berikutnya + dari mana angka itu datang (`settings|env|default`).
        # Tanpa `source`, operator tidak bisa membedakan nilai pilihan owner
        # dari env yang tertinggal di unit file.
        "interval_s": interval_s,
        "source": interval_source,
        "interval_range_s": {
            "min": LLM_INTERVAL_RANGE_S[0], "max": LLM_INTERVAL_RANGE_S[1],
        },
    }


class AgentIntervalBody(BaseModel):
    """Interval siklus agent LLM dalam detik (AUDIT-E t_bb927ec7)."""

    interval_s: int


@router.put("/interval")
async def set_agent_interval(body: AgentIntervalBody, user: dict = Depends(require_2fa)):
    """Owner mengatur interval siklus agent LLM tanpa restart service.

    Ditulis ke settings `llm_agent_interval_s` (dibaca ulang loop TIAP siklus
    -> hot-reload) dan dicerminkan ke key lama `llm_interval_s` supaya panel
    lama (PUT /admin/risk-settings) tidak menampilkan angka basi. Validasi
    memakai validator guardrail bersama: 30..86400 detik, di luar itu 422.
    Setiap perubahan tercatat dua lapis: `audit_log` (CONFIG_CHANGED
    `llm_agent_interval`) dan trigger `settings_audit`.
    """
    try:
        value = validate_interval_s(body.interval_s)
    except GuardrailRangeError as exc:
        raise HTTPException(422, str(exc)) from exc
    new_interval = int(value)
    settings = await db.get_settings()
    previous, _ = effective_interval(settings)
    actor = user["username"]
    await db.set_setting("llm_agent_interval_s", new_interval, actor=actor)
    await db.set_setting("llm_interval_s", float(new_interval), actor=actor)
    # Impor lokal: routes mengimpor banyak modul; impor di dalam handler
    # menghindari siklus impor saat startup dan tetap memakai satu helper
    # audit (bentuk audit_log identik dengan perubahan guardrail lain).
    from .routes import _audit

    async with db.pool().connection() as conn:
        await _audit(
            conn, actor, user.get("role"), "CONFIG_CHANGED",
            object="llm_agent_interval",
            details={"old": previous, "new": new_interval},
        )
    return {
        "ok": True,
        "interval_s": new_interval,
        "previous": previous,
        "source": "settings",
    }


# ── t_2a1fbf01: evidence specialist + katalog/pilihan model ────────────────

class AgentEvidenceBody(BaseModel):
    """Hasil satu specialist (technical/macro/sentiment/portfolio) per siklus.

    Disimpan ke order_events sebagai to_status AGENT_EVIDENCE dan langsung
    di-broadcast sebagai event SSE `agent_evidence` supaya visualisasi agent
    menampilkan progres nyata, bukan animasi karangan.
    """

    cycle_id: str = Field(min_length=8, max_length=64)
    symbol: str = Field(min_length=3, max_length=20)
    role: Literal["technical", "macro", "sentiment", "portfolio", "synth"]
    state: Literal["ok", "error", "timeout"]
    model: Optional[str] = Field(default=None, max_length=100)
    latency_ms: Optional[int] = None
    # Bukti anggaran: tanpa ini latency tidak bisa dipecah prefill vs output.
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    summary: Optional[str] = Field(default=None, max_length=800)
    data: Optional[dict] = None
    error: Optional[str] = Field(default=None, max_length=800)
    # t_afd7fe4e: bukti prompt caching efektif per peran (dari usage endpoint).
    prompt_cache_hit_tokens: Optional[int] = Field(default=None, ge=0)
    prompt_cache_miss_tokens: Optional[int] = Field(default=None, ge=0)
    # t_afd7fe4e butir C: angka token per peran, supaya biang latensi
    # (prompt besar vs output panjang) bisa dibuktikan dari audit, bukan ditebak.
    prompt_tokens: Optional[int] = Field(default=None, ge=0)
    completion_tokens: Optional[int] = Field(default=None, ge=0)


def _llm_env(name: str) -> str:
    """Env LLM: process env dulu, lalu .env.llm (service api tidak memuatnya).

    Service `fund2-api` hanya EnvironmentFile=.env, sedangkan kredensial LLM ada
    di .env.llm yang dipakai `fund2-llm-agent`. Tanpa fallback ini endpoint
    katalog model selalu kosong padahal agent loop bisa memanggil LLM.
    """
    value = os.environ.get(name)
    if value:
        return value.strip()
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env.llm")
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith(f"{name}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return ""
    return ""


# Validasi utama ada di skema (Literal) supaya payload salah ditolak sebelum
# handler; tuple ini dipertahankan sebagai jaring kedua untuk pemanggil internal.
_EVIDENCE_ROLES = ("technical", "macro", "sentiment", "portfolio", "synth")
_EVIDENCE_STATES = ("ok", "error", "timeout")


@router.post("/evidence")
async def create_evidence(body: AgentEvidenceBody, user: dict = Depends(require_csrf)):
    """Catat evidence satu specialist + broadcast SSE (append-only)."""
    if body.role not in _EVIDENCE_ROLES:
        raise HTTPException(422, "role harus technical | macro | sentiment | portfolio | synth")
    if body.state not in _EVIDENCE_STATES:
        raise HTTPException(422, "state harus ok | error | timeout")
    conf = 0.0
    if isinstance(body.data, dict):
        try:
            conf = max(0.0, min(1.0, float(body.data.get("confidence") or 0.0)))
        except (TypeError, ValueError):
            conf = 0.0
    decision = {
        "kind": "evidence",
        # Kolom shape-check order_events mewajibkan kelima field ini ada.
        "reasoning": (body.summary or body.error or "evidence kosong")[:2000],
        "confidence": conf,
        "prompt_version": "2.4.0-facts-quality",
        "role": body.role,
        "symbol": body.symbol,
        "state": body.state,
        "model": body.model,
        "latency_ms": body.latency_ms,
        "prompt_tokens": body.prompt_tokens,
        "completion_tokens": body.completion_tokens,
        "summary": body.summary,
        "data": body.data,
        "error": body.error,
        "prompt_cache_hit_tokens": body.prompt_cache_hit_tokens,
        "prompt_cache_miss_tokens": body.prompt_cache_miss_tokens,
        "prompt_tokens": body.prompt_tokens,
        "completion_tokens": body.completion_tokens,
        "cycle_id": body.cycle_id,
        "username": user["username"],
    }
    async with db.pool().connection() as conn:
        await conn.execute(
            """
            INSERT INTO order_events (order_id, from_status, to_status, payload, decision)
            VALUES (NULL, NULL, 'AGENT_EVIDENCE', %s, %s)
            """,
            (json.dumps({"cycle_id": body.cycle_id, "role": body.role}), json.dumps(decision, default=str)),
        )
    broadcaster.publish({
        "type": "agent_evidence",
        "cycle_id": body.cycle_id,
        "symbol": body.symbol,
        "role": body.role,
        "state": body.state,
        "model": body.model,
        "latency_ms": body.latency_ms,
        "summary": body.summary,
    })
    return {"ok": True}


def _saved_roles(settings: dict | None) -> dict[str, str]:
    """Override per peran yang benar-benar tersimpan di settings.

    Berbeda dari `effective.roles` (yang sudah dicampur DEFAULT_ROLE_MODELS):
    di sini hanya nilai eksplisit owner, supaya UI bisa membedakan "owner
    memilih model ini" dari "memakai bawaan sistem".
    """
    raw = (settings or {}).get(llm_models.SETTING_KEY)
    saved = raw.get("roles") if isinstance(raw, dict) else None
    if not isinstance(saved, dict):
        return {}
    return {
        role: model.strip()
        for role, model in saved.items()
        if isinstance(role, str) and isinstance(model, str) and model.strip()
    }


def _latency_ms(value: object) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


async def _last_role_cycle() -> dict | None:
    """Model yang BENAR-BENAR dipakai tiap peran pada siklus terakhir.

    Sumbernya evidence specialist (order_events.to_status='AGENT_EVIDENCE',
    decision->>'role' + decision->>'model'), bukan pilihan tersimpan. Ini yang
    membuat UI tidak berbohong: kalau siklus terakhir gagal atau peran jatuh ke
    model global, angka di layar tetap mencerminkan kenyataan.
    """
    async with db.pool().connection() as conn:
        head = await fetchone(
            conn,
            """
            SELECT payload->>'cycle_id' AS cycle_id
            FROM order_events
            WHERE to_status = 'AGENT_EVIDENCE'
              AND payload->>'cycle_id' IS NOT NULL
            ORDER BY id DESC
            LIMIT 1
            """,
        )
        cycle_id = head["cycle_id"] if head else None
        if not cycle_id:
            return None
        rows = await fetchall(
            conn,
            """
            SELECT decision->>'role'   AS role,
                   decision->>'model'  AS model,
                   decision->>'state'  AS state,
                   decision->>'symbol' AS symbol,
                   decision->>'latency_ms' AS latency_ms,
                   created_at
            FROM order_events
            WHERE to_status = 'AGENT_EVIDENCE'
              AND payload->>'cycle_id' = %s
            ORDER BY id
            """,
            (cycle_id,),
        )
    roles: dict[str, dict] = {}
    at = None
    symbol = None
    for row in rows:
        role = row["role"]
        if not role:
            continue
        roles[role] = {
            "model": row["model"],
            "state": row["state"],
            "latency_ms": _latency_ms(row["latency_ms"]),
        }
        created = row["created_at"]
        if created is not None and (at is None or created > at):
            at = created
        symbol = symbol or row["symbol"]
    return {"cycle_id": cycle_id, "at": at, "symbol": symbol, "roles": roles}


@router.get("/conclusions")
async def agent_conclusions(limit: int = 12, user: dict = Depends(require_csrf)):
    """Kesimpulan siklus agent untuk panel stream read-only di Terminal.

    Hanya keputusan akhir (order/hold/close/cut/sl/be/tp) yang dikirim, bukan
    evidence specialist: panel ini untuk dipantau, bukan untuk dibaca teknis.
    """
    limit = max(1, min(int(limit), 50))
    async with db.pool().connection() as conn:
        rows = await fetchall(
            conn,
            """
            SELECT e.created_at,
                   e.decision->>'symbol'     AS symbol,
                   e.decision->>'kind'       AS kind,
                   e.decision->>'action'     AS action,
                   e.decision->>'confidence' AS confidence,
                   e.decision->>'reasoning'  AS reasoning,
                   e.decision->>'model'      AS model,
                   e.payload->>'cycle_id'    AS cycle_id
            FROM order_events e
            WHERE e.decision IS NOT NULL
              AND e.decision->>'kind' IN ('order','hold','close','cut','sl','be','tp')
            ORDER BY e.id DESC
            LIMIT %s
            """,
            (limit,),
        )
        settings = await db.get_settings()
    interval_s, interval_source = effective_interval(settings)
    items = []
    for row in rows:
        text = (row["reasoning"] or "").strip().replace("\n", " ")
        # Kesimpulan saja: potong ke dua kalimat / 240 karakter.
        parts = [p.strip() for p in text.split(". ") if p.strip()]
        short = ". ".join(parts[:2])
        if len(short) > 240:
            cut = short[:240]
            space = cut.rfind(" ")
            short = (cut[:space] if space > 160 else cut).rstrip(" ,;:.") + "…"
        conf = row["confidence"]
        try:
            conf = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            conf = None
        items.append({
            "at": row["created_at"].isoformat() if row["created_at"] else None,
            "symbol": row["symbol"],
            "kind": row["kind"],
            "action": row["action"],
            "confidence": conf,
            "summary": short or None,
            "model": row["model"],
            "cycle_id": row["cycle_id"],
        })
    return {
        "items": items,
        "last_at": items[0]["at"] if items else None,
        "pause": llm_risk.normalize_pause(settings.get("llm_agent_pause")),
        "interval_s": interval_s,
        "source": interval_source,
    }


@router.get("/models")
async def list_llm_models(user: dict = Depends(require_csrf)):
    """Katalog model + pilihan efektif per peran + evidence siklus terakhir.

    `roles_saved`  : yang dipilih owner (kosong = tidak di-override).
    `role_defaults`: bawaan sistem (dipakai saat peran tidak di-override).
    `effective`    : konfigurasi efektif hasil resolve() (global + peran).
    `last_cycle`   : model yang benar-benar dipakai per peran pada siklus
                     terakhir, dari evidence AGENT_EVIDENCE.
    """
    settings = await db.get_settings()
    base, key = _llm_env("LLM_BASE_URL"), _llm_env("LLM_API_KEY")
    catalog: list[str] = []
    if base and key:
        import httpx

        from .llm_models import fetch_catalog

        async with httpx.AsyncClient(timeout=12.0) as http:
            catalog = await fetch_catalog(http, base=base, key=key)
    return {
        "catalog": catalog,
        "effective": llm_models.resolve(settings),
        "roles_saved": _saved_roles(settings),
        "role_keys": list(llm_models.ROLE_KEYS),
        "role_defaults": dict(llm_models.DEFAULT_ROLE_MODELS),
        "last_cycle": await _last_role_cycle(),
        "env_model": _llm_env("LLM_MODEL") or "lucif",
    }


class LlmModelsBody(BaseModel):
    specialist: Optional[str] = Field(default=None, max_length=64)
    synth: Optional[str] = Field(default=None, max_length=64)
    fallback: Optional[str] = Field(default=None, max_length=64)
    parallel: Optional[bool] = None
    # Override model per peran: {technical|macro|sentiment|portfolio: model}.
    # String kosong = hapus override (kembali ke role_defaults / global).
    # Peran di luar ROLE_KEYS ditolak 422 supaya typo tidak diabaikan diam-diam.
    roles: Optional[dict[str, str]] = None


@router.put("/models")
async def set_llm_models(body: LlmModelsBody, user: dict = Depends(require_2fa)):
    """Owner memilih model global + per peran (butuh 2FA, ter-audit)."""
    settings = await db.get_settings()
    current = llm_models.resolve(settings)
    roles = _saved_roles(settings)
    if body.roles is not None:
        unknown = sorted(role for role in body.roles if role not in llm_models.ROLE_KEYS)
        if unknown:
            raise HTTPException(422, f"peran tidak dikenal: {', '.join(unknown)}")
        for role, model in body.roles.items():
            name = (model or "").strip()
            if not name:
                roles.pop(role, None)
                continue
            if role not in llm_models.ROLE_KEYS or not llm_models.is_valid_name(name):
                raise HTTPException(422, f"model untuk peran {role} tidak valid")
            roles[role] = name
    payload = {
        "specialist": body.specialist or current["specialist"],
        "synth": body.synth or current["synth"],
        "fallback": body.fallback or current["fallback"],
        "parallel": current["parallel"] if body.parallel is None else body.parallel,
        "roles": roles,
    }
    for name in ("specialist", "synth", "fallback"):
        if not isinstance(payload[name], str) or not payload[name]:
            raise HTTPException(422, f"{name} tidak valid")
    await db.set_setting(llm_models.SETTING_KEY, payload, actor=user["username"])
    return {
        "ok": True,
        "effective": llm_models.resolve({llm_models.SETTING_KEY: payload}),
        "roles_saved": roles,
    }
