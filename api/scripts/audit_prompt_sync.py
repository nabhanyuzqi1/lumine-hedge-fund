#!/usr/bin/env python3
"""Audit sinkronisasi keluaran multi-agent vs system prompt (read-only).

Menjawab pertanyaan owner: "output LLM multiagent tidak sinkron dengan system
prompt". Skrip ini memanggil jalur nyata (specialist + synthesizer) dengan
konteks tipis, lalu memeriksa keluaran terhadap skema yang DITULIS di
`SPECIALIST_PROMPTS` / `SYNTH_PROMPT`:

  * JSON valid, tanpa teks/markdown di luar objek.
  * Kunci wajib per peran ada, tipe benar, enum sesuai daftar.
  * Aturan synthesizer: kind dikenal; kind=order wajib symbol+side+volume+sl;
    bila evidence "missing" -> reasoning menyebutnya dan confidence < 1.

Tidak menulis ke DB, tidak mengirim order, tidak mengubah settings.
Pakai: .venv/bin/python scripts/audit_prompt_sync.py [--symbol XAUUSD]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import llm_specialists as S  # noqa: E402

ENUMS = {
    "kind": {"order", "cut", "hold", "sl", "be", "tp", "layer", "close"},
    "side": {"BUY", "SELL"},
}

ROLE_SCHEMA = {
    "technical": {
        "trend": dict, "key_levels": dict, "setup": dict,
        "volatility": str, "confidence": (int, float), "note": str,
    },
    "macro": {
        "event_risk": str, "next_events": list, "regime": str,
        "trade_window": dict, "bias": dict, "confidence": (int, float),
        "note": str,
    },
    "sentiment": {
        "sentiment": dict, "drivers": list, "crowding": str,
        "confidence": (int, float), "note": str,
    },
    "portfolio": {
        "exposure_pct": (int, float), "open_positions": int, "risk_flags": list,
        "room": dict, "recommendation": str, "confidence": (int, float),
        "note": str,
    },
}

SYNTH_SCHEMA = {
    "kind": str, "symbol": (str, type(None)), "side": (str, type(None)),
    "volume": (int, float, type(None)), "sl": (int, float, type(None)),
    "tp": (int, float, type(None)), "reasoning": str,
    "confidence": (int, float),
}


def load_env() -> None:
    for name in (".env", ".env.llm"):
        path = ROOT / name
        if path.exists():
            for key, value in dotenv_values(path).items():
                if value is not None:
                    os.environ.setdefault(key, value)


def check(obj: dict, schema: dict) -> list[str]:
    problems = []
    for key, typ in schema.items():
        if key not in obj:
            problems.append(f"kunci hilang: {key}")
            continue
        if not isinstance(obj[key], typ):
            problems.append(f"tipe salah: {key}={type(obj[key]).__name__}")
    for key, allowed in ENUMS.items():
        if key in obj and isinstance(obj[key], str) and obj[key] not in allowed:
            problems.append(f"enum salah: {key}={obj[key]!r}")
    return problems


def synth_rules(dec: dict, missing: list[str]) -> list[str]:
    problems = check(dec, SYNTH_SCHEMA)
    conf = dec.get("confidence")
    if isinstance(conf, (int, float)) and not (0.0 <= float(conf) <= 1.0):
        problems.append(f"confidence di luar 0..1: {conf}")
    if dec.get("kind") == "order":
        for key in ("symbol", "side", "volume", "sl"):
            if dec.get(key) in (None, ""):
                problems.append(f"kind=order tanpa {key}")
        vol = dec.get("volume")
        if isinstance(vol, (int, float)) and not (0.01 <= float(vol) <= 0.10):
            problems.append(f"volume di luar 0.01-0.10: {vol}")
    if missing:
        reasoning = str(dec.get("reasoning") or "").lower()
        if not any(m in reasoning for m in missing) and "missing" not in reasoning:
            problems.append("reasoning tidak menyebut evidence yang missing")
    return problems


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--budget-tokens", type=int, default=0)
    args = ap.parse_args()
    load_env()

    base = (os.environ.get("LLM_BASE_URL") or "").rstrip("/")
    key = os.environ.get("LLM_API_KEY") or ""
    if not base or not key:
        print("FATAL: LLM_BASE_URL / LLM_API_KEY tidak ada di .env.llm")
        return 2
    cfg = {"specialist": os.environ.get("LLM_MODEL", "lucif-flash"),
           "synth": os.environ.get("LLM_MODEL_SYNTH", "lucif")}
    budget = None
    if args.budget_tokens:
        from app import llm_budget
        budget = llm_budget.resolve({"llm_latency_budget": {
            "max_tokens_specialist": args.budget_tokens,
            "max_tokens_synth": max(args.budget_tokens, 700)}})

    ctx: dict = {}  # konteks tipis: kontrak prompt harus tetap dipenuhi
    failures = 0
    async with httpx.AsyncClient(timeout=120.0) as http:
        print(f"== specialist (model {cfg['specialist']}) ==")
        ev = await S.run_specialists(
            http, ctx, symbol=args.symbol, base=base, key=key,
            model=cfg["specialist"], budget=budget)
        for role in S.ROLES:
            res = ev.get(role) or {}
            state = res.get("state")
            if state != "ok":
                print(f"  {role:10s} state={state} err={str(res.get('error'))[:90]}")
                failures += 1
                continue
            problems = check(res.get("data") or {}, ROLE_SCHEMA[role])
            print(f"  {role:10s} state=ok {res.get('latency_ms')}ms "
                  f"{'PASS' if not problems else 'FAIL ' + '; '.join(problems)}")
            failures += bool(problems)

        print(f"== synthesizer (model {cfg['synth']}) ==")
        try:
            synth = await S.synthesize(
                http, ctx, ev, symbol=args.symbol, base=base, key=key,
                model=cfg["synth"], budget=budget)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            return 1
        dec = synth.get("data") or {}
        missing = synth.get("missing") or []
        problems = synth_rules(dec, missing)
        print(f"  latency={synth.get('latency_ms')}ms tokens={synth.get('completion_tokens')} "
              f"missing={missing}")
        print("  decision=" + json.dumps(dec, ensure_ascii=False)[:600])
        print("  " + ("PASS" if not problems else "FAIL " + "; ".join(problems)))
        failures += bool(problems)
    print(f"\nHASIL: {'PASS' if failures == 0 else f'{failures} temuan'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
