"""Ukur latensi siklus LLM multi-agent tanpa mengirim order (t_afd7fe4e butir C).

Dipakai untuk membuktikan anggaran p95 <= 35 s dengan ANGKA NYATA, bukan
perkiraan: jalur yang diukur sama dengan `llm_agent_loop.run_cycle` (konteks
DB + fakta Layer 0 + 4 specialist paralel + synthesizer), hanya langkah
`_submit_decision` yang TIDAK dijalankan, sehingga tidak ada order/posisi
yang berubah.

Contoh:
    cd ~/fund2/api
    TELEGRAM_ALERTS_OFF=1 .venv/bin/python -m scripts.measure_cycle_latency \
        --runs 5 --symbol XAUUSD --out /tmp/latency.json

Keluaran: JSON per siklus (latensi per peran, token prompt/completion, cache
hit/miss) + ringkasan p50/p95/max memakai `llm_budget.summarise_latency`
(implementasi yang sama dengan endpoint GET /llm-agent/latency), supaya angka
CLI dan dashboard tidak mungkin berbeda rumus.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


def _load_env_file(path: Path) -> None:
    """Muat KEY=VALUE ke env bila belum ada (tanpa menimpa env proses)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(API_DIR / ".env")
_load_env_file(API_DIR / ".env.llm")
os.environ.setdefault("TELEGRAM_ALERTS_OFF", "1")

from app import db, llm_budget, llm_facts, llm_models, llm_specialists  # noqa: E402
from app import llm_agent_loop as loop  # noqa: E402


def _role_row(res: dict) -> dict:
    return {
        "state": res.get("state"),
        "model": res.get("model"),
        "latency_ms": res.get("latency_ms"),
        "prompt_tokens": res.get("prompt_tokens"),
        "completion_tokens": res.get("completion_tokens"),
        "prompt_cache_hit_tokens": res.get("prompt_cache_hit_tokens"),
        "prompt_cache_miss_tokens": res.get("prompt_cache_miss_tokens"),
    }


async def measure_one(symbol: str, budget: dict, cfg: dict, http) -> dict:
    """Satu siklus penuh TANPA submit order."""
    started = time.monotonic()
    now = datetime.now(timezone.utc)
    extras = await loop._collect_extras_safe(now)
    async with db.pool().connection() as conn:
        ctx = await loop._collect_context(conn, extras=extras, now=now,
                                          symbols=(symbol,))
        settings = await db.settings_snapshot(conn)
        portfolio = await loop._collect_portfolio(conn, settings, ctx)
    ctx["facts"] = llm_facts.build_facts(ctx, portfolio, now)
    context_ms = int((time.monotonic() - started) * 1000)

    base = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    key = os.environ.get("LLM_API_KEY", "")
    if not base or not key:
        raise RuntimeError("LLM_BASE_URL / LLM_API_KEY tidak ada di env/.env.llm")

    deadline = llm_budget.llm_deadline(budget, started)
    evidence = await llm_specialists.run_specialists(
        http, ctx, symbol=symbol, base=base, key=key,
        model=cfg["specialist"], role_models=cfg.get("roles"), budget=budget,
        deadline=deadline,
    )
    try:
        synth = await llm_specialists.synthesize(
            http, ctx, evidence, symbol=symbol, base=base, key=key,
            model=cfg["synth"], budget=budget, deadline=deadline,
        )
    except Exception as exc:  # noqa: BLE001 - fallback sama seperti produksi
        synth = await llm_specialists.synthesize(
            http, ctx, evidence, symbol=symbol, base=base, key=key,
            model=cfg["fallback"], budget=budget, deadline=deadline,
        )
        synth["fallback_reason"] = f"{type(exc).__name__}: {exc}"[:200]
    total_ms = int((time.monotonic() - started) * 1000)
    return {
        "symbol": symbol,
        "started_at": now.isoformat(timespec="seconds"),
        "context_ms": context_ms,
        "total_ms": total_ms,
        "roles": {role: _role_row(res) for role, res in evidence.items()},
        "synth": {**_role_row(synth), "missing": synth.get("missing")},
        "decision": (synth.get("data") or {}).get("action"),
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    import httpx

    await db.init_pool()
    try:
        settings = await db.get_settings()
        budget = llm_budget.resolve(settings)
        cfg = llm_models.resolve(settings)
        rows = []
        async with httpx.AsyncClient(timeout=180.0) as http:
            for i in range(max(args.runs, 1)):
                row = await measure_one(args.symbol, budget, cfg, http)
                rows.append(row)
                roles = " ".join(
                    f"{role}={r['latency_ms']}ms/{r['completion_tokens']}tok"
                    for role, r in row["roles"].items())
                print(f"[run {i + 1}/{args.runs}] total={row['total_ms']}ms "
                      f"ctx={row['context_ms']}ms synth={row['synth']['latency_ms']}ms "
                      f"{roles}", flush=True)
        samples = [row["total_ms"] / 1000.0 for row in rows]
        summary = llm_budget.summarise_latency(samples, float(budget["target_p95_s"]))
        summary["context_ms_median"] = sorted(r["context_ms"] for r in rows)[len(rows) // 2]
        summary["budget_used"] = budget
        out = {"summary": summary, "runs": rows}
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        if args.out:
            Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False))
            print(f"tersimpan: {args.out}")
    finally:
        await db.close_pool()
    return 0 if summary.get("within_budget") or len(rows) < 2 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
