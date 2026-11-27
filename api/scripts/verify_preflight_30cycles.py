"""Bukti 30 siklus berturut-turut: gate pre-flight memblok TANPA memanggil LLM.

Kriteria selesai t_afd7fe4e #1: "log 30 siklus berturut-turut: tidak ada
pemanggilan LLM saat pasar tutup atau EA offline".

Cara membuktikan tanpa menunggu akhir pekan:
- Gate dihitung oleh kode PRODUKSI `preflight.evaluate` dengan baris
  `market_sessions` ASLI dari DB (bukan jam hardcode), memakai tiga skenario
  blok yang nyata: pasar tutup (Minggu), EA offline, spread terlalu lebar.
- Loop dijalankan dengan `llm_agent_loop.run_cycle` yang sama seperti daemon,
  tetapi HTTP-nya palsu: setiap permintaan ke LLM_BASE_URL DICATAT. Satu saja
  panggilan LLM pada siklus yang diblok = kegagalan skrip (exit 1).
- Tidak menulis apa pun ke DB dan tidak mengirim order: `_record_cycle_skipped`
  hidup di endpoint API, sedangkan skrip ini memanggil run_cycle langsung
  dengan transport palsu (POST /llm-agent/cycle dijawab 200 tanpa menyimpan).

Contoh:
    cd ~/fund2/api
    TELEGRAM_ALERTS_OFF=1 .venv/bin/python -m scripts.verify_preflight_30cycles \
        --cycles 30 --symbol XAUUSD --out /tmp/preflight_30cycles.jsonl
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
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(API_DIR / ".env")
os.environ.setdefault("TELEGRAM_ALERTS_OFF", "1")

from app import db, llm_agent_loop as loop, market_sessions, preflight  # noqa: E402


class _Resp:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)[:200]

    def json(self) -> dict:
        return self._body


class FakeHttp:
    """Transport palsu: menjawab preflight/cycle, MENCATAT setiap panggilan LLM."""

    def __init__(self, preflight_body: dict):
        self.preflight_body = preflight_body
        self.llm_calls: list[dict] = []
        self.calls: list[str] = []
        self.cookies: dict = {}

    async def post(self, url: str, json=None, headers=None, cookies=None, **kwargs):
        self.calls.append(url)
        if url.endswith("/llm-agent/preflight"):
            return _Resp(200, self.preflight_body)
        if url.endswith("/llm-agent/cycle") or url.endswith("/llm-agent/decisions") \
                or url.endswith("/llm-agent/evidence"):
            return _Resp(200, {"ok": True})
        if "/chat/completions" in url:
            self.llm_calls.append({"url": url, "body_keys": sorted((json or {}).keys())})
            return _Resp(500, {"error": "LLM tidak boleh dipanggil saat gate memblok"})
        return _Resp(404, {"error": f"tidak dikenal: {url}"})


def _tick(symbol: str, price: float, spread: float, age_s: float = 1.0) -> dict:
    """Bentuk tick seperti `market._latest`: `ts` = epoch detik (dipakai gate)."""
    return {"symbol": symbol, "bid": price - spread / 2, "ask": price + spread / 2,
            "price": price, "spread": spread, "ts": time.time() - age_s}


def _scenario(name: str, symbol: str, sessions: dict, settings: dict) -> tuple[dict, datetime]:
    """Hasil gate ASLI (preflight.evaluate) untuk satu skenario blok."""
    from app import risk

    ea_offline_s = float((settings.get("llm_risk") or {}).get("ea_offline_block_s") or 60.0)
    spec = risk.symbol_spec(symbol, settings) or {}
    max_spread = float(spec.get("spread_abs_max_usd")
                       or settings.get("max_spread") or 0.5)
    if name == "market_closed":
        # Minggu 12:00 WIB: bursa XAUUSD tutup menurut baris market_sessions.
        now = datetime(2026, 11, 29, 12, 0, tzinfo=market_sessions.WIB).astimezone(timezone.utc)
        result = preflight.evaluate(
            settings=settings, symbols=[symbol], sessions=sessions,
            ticks={symbol: _tick(symbol, 2000.0, 0.10)}, ea_age_s=2.0,
            drawdown_pct=0.0, now=now)
        return result, now
    if name == "ea_offline":
        now = datetime(2026, 11, 26, 9, 0, tzinfo=market_sessions.WIB).astimezone(timezone.utc)
        result = preflight.evaluate(
            settings=settings, symbols=[symbol], sessions=sessions,
            ticks={symbol: _tick(symbol, 2000.0, 0.10)}, ea_age_s=ea_offline_s + 120.0,
            drawdown_pct=0.0, now=now)
        return result, now
    # spread_too_wide
    now = datetime(2026, 11, 26, 9, 5, tzinfo=market_sessions.WIB).astimezone(timezone.utc)
    result = preflight.evaluate(
        settings=settings, symbols=[symbol], sessions=sessions,
        ticks={symbol: _tick(symbol, 2000.0, max_spread * 4)}, ea_age_s=2.0,
        drawdown_pct=0.0, now=now)
    return result, now


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cycles", type=int, default=30)
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    symbol = args.symbol.upper()
    await db.init_pool()
    failures: list[str] = []
    rows: list[dict] = []
    try:
        settings = await db.get_settings()
        async with db.pool().connection() as conn:
            sessions = await market_sessions.load_rows(conn, [symbol])
        if not sessions.get(symbol):
            print(f"FATAL: tidak ada baris market_sessions untuk {symbol}")
            return 2
        scenarios = ["market_closed", "ea_offline", "spread_too_wide"]
        for i in range(args.cycles):
            name = scenarios[i % len(scenarios)]
            gate, fake_now = _scenario(name, symbol, sessions, settings)
            if gate.get("ok"):
                failures.append(f"siklus {i + 1}: gate TIDAK memblok pada skenario {name}")
                break
            http = FakeHttp(gate)
            cycle_id = f"verify{name[:4]}{i:04d}"
            result = await loop.run_cycle(  # type: ignore[arg-type] - transport palsu
                http, {"csrf": "fake", "cookies": None}, cycle_id)
            skipped = isinstance(result, dict) and result.get("skipped")
            row = {
                "cycle": i + 1,
                "cycle_id": cycle_id,
                "scenario": name,
                "gate_ok": gate.get("ok"),
                "gate_reason": (gate.get("reason") or "")[:200],
                "blocked_codes": [b.get("code") for b in gate.get("blocked") or []],
                "loop_skipped": skipped or None,
                "llm_calls": len(http.llm_calls),
                "fake_now_utc": fake_now.isoformat(timespec="seconds"),
            }
            rows.append(row)
            print(f"[{i + 1:02d}/{args.cycles}] {name:16s} gate_block="
                  f"{row['blocked_codes']} loop_skip={bool(skipped)} "
                  f"llm_calls={len(http.llm_calls)}", flush=True)
            if http.llm_calls:
                failures.append(f"siklus {i + 1}: LLM dipanggil {len(http.llm_calls)}x "
                                f"saat gate memblok ({name})")
                break
            if not skipped:
                failures.append(f"siklus {i + 1}: run_cycle tidak melewati siklus "
                                f"({name}): {str(result)[:120]}")
                break
    finally:
        await db.close_pool()

    summary = {
        "cycles_requested": args.cycles,
        "cycles_run": len(rows),
        "llm_calls_total": sum(r["llm_calls"] for r in rows),
        "all_blocked": all(not r["gate_ok"] for r in rows),
        "all_skipped": all(bool(r["loop_skipped"]) for r in rows),
        "failures": failures,
        "verdict": "PASS" if not failures and len(rows) == args.cycles else "FAIL",
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
        print(f"log: {args.out}")
    return 0 if summary["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
