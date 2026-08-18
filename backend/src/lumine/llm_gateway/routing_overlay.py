# Copyright (c) 2026 Lumine. All rights reserved.
"""Realtime LLM routing overlay (18 Aug 2026).

Masalah: `update_system_config` menulis Redis tapi gateway tetap pakai
env/policy DB sampai restart → user ubah default/fallback model tidak
berfungsi. Solusi: overlay Redis `lumine:llm_routing` dibaca SETIAP call
di `_routes_for` — perubahan realtime tanpa restart.

Struktur hash `lumine:llm_routing`:
  default_model: str          # nama model primary (mis. "deepseek-v4-pro")
  fallback_models: str        # JSON list (mis. ["deepseek-v4-flash","glm-5"])
  auto_discovery: "1"|"0"     # fetch /v1/models 9router, pilih best aktif
  last_models_json: str       # cache hasil discovery (untuk UI)
  last_discovery_ts: str      # epoch detik
  circuit_open: str           # JSON dict model → epoch (sementara down)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger("lumine.llm_gateway.overlay")

ROUTING_KEY = "lumine:llm_routing"
# Circuit breaker: model yang gagal auth (401/403) dibuka N detik.
_CIRCUIT_SECONDS = 120


async def get_overlay(redis: Any) -> dict[str, Any]:
    """Read the routing overlay (empty dict kalau belum di-set)."""
    try:
        raw = await redis.hgetall(ROUTING_KEY)
        if not raw:
            return {}
        return {k.decode() if isinstance(k, bytes) else str(k): (v.decode() if isinstance(v, bytes) else str(v)) for k, v in raw.items()}
    except Exception:
        return {}


async def set_overlay(redis: Any, *, default_model: str | None = None,
                      fallback_models: list[str] | None = None,
                      auto_discovery: bool | None = None) -> dict[str, str]:
    """Update overlay — hanya field yang diberikan (None = skip)."""
    updates: dict[str, str] = {}
    if default_model is not None:
        updates["default_model"] = default_model
    if fallback_models is not None:
        updates["fallback_models"] = json.dumps(fallback_models)
    if auto_discovery is not None:
        updates["auto_discovery"] = "1" if auto_discovery else "0"
    if updates:
        await redis.hset(ROUTING_KEY, mapping=updates)
    return updates


def parse_fallbacks(raw: str | None) -> list[str]:
    try:
        val = json.loads(raw or "[]")
        return [str(m) for m in val] if isinstance(val, list) else []
    except Exception:
        return []


def is_circuit_open(model: str, overlay: dict[str, Any]) -> bool:
    """True kalau model sedang di-circuit (gagal auth <120s lalu)."""
    try:
        raw = overlay.get("circuit_open", "{}")
        circuits = json.loads(raw)
        opened = float(circuits.get(model, 0))
        return time.time() - opened < _CIRCUIT_SECONDS
    except Exception:
        return False


async def open_circuit(redis: Any, model: str) -> None:
    """Tandai model circuit-open (dipakai setelah 401/403)."""
    try:
        overlay = await get_overlay(redis)
        circuits = json.loads(overlay.get("circuit_open", "{}"))
        circuits[model] = time.time()
        await redis.hset(ROUTING_KEY, mapping={"circuit_open": json.dumps(circuits)})
        logger.warning("llm routing: circuit open for %s (120s)", model)
    except Exception:  # nosec B110 — Redis down → circuit tetap closed
        pass


async def resolve_route_models(
    redis: Any,
    *,
    env_default: str,
    policy_fallbacks: list[str],
) -> tuple[list[str], dict[str, Any]]:
    """Return (model chain primary→fallbacks, overlay) dengan overlay menang.

    Priority (tertinggi dulu):
      1. Redis overlay default_model (realtime user config)
      2. Env llm_default_model
      3. Policy DB fallbacks
    Fallbacks: overlay > policy. Circuit-open model di-skip dari chain.
    """
    overlay = await get_overlay(redis)
    primary = str(overlay.get("default_model") or env_default)
    fb_raw = overlay.get("fallback_models")
    fallbacks = parse_fallbacks(fb_raw) if fb_raw else list(policy_fallbacks)
    # Availability (18 Aug 2026): model yang gagal probe (quota habis/
    # tidak available) di-skip dari chain — discovery menandai via
    # `available_models` + circuit_open. Jangan pakai model yang
    # diketahui 429 "Budget has been exceeded".
    import json as _json

    avail: list[str] = []
    try:
        avail_raw = overlay.get("available_models")
        if avail_raw:
            _v = _json.loads(avail_raw)
            avail = [str(m) for m in _v] if isinstance(_v, list) else []
    except Exception:
        avail = []
    known_bad = {m for m in fallbacks if is_circuit_open(m, overlay)}
    if avail:
        known_bad |= {m for m in fallbacks if m not in avail}
    healthy = [primary]
    for m in fallbacks:
        if m not in known_bad:
            healthy.append(m)
    return healthy, overlay


async def auto_select_best_model(redis: Any, gateway_url: str, gateway_key: str) -> dict[str, Any]:  # noqa: C901, PLR0915 — discovery heuristik bercabang
    """Auto-discovery: fetch 9router /v1/models → pilih model TERBAIK aktif.

    Agent utama (18 Aug 2026) — user minta program yang fetch semua model
    9router, pilih yang terbaik, dan auto-switch saat rate-limit/down:

    1. GET {gateway_url}/v1/models (Bearer key) → daftar model aktif.
    2. Skor: prefer model non-free (flash/free = rate-limit cepat); rank
       by heuristic (pro > turbo > flash > free; context-rich menang).
    3. Skip model yang circuit-open (sedang down).
    4. Update overlay `default_model` + `last_models_json` + `last_discovery_ts`.
    5. Return dict {chosen, models, error} untuk UI/log.

    Dipanggil worker `_model_discovery_worker` tiap 60s + saat startup.
    """
    import asyncio
    import json
    import time as _time
    import urllib.request

    def _fetch() -> dict:
        url = str(gateway_url).rstrip("/") + "/v1/models"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {gateway_key}"})  # noqa: S310  # nosec B310 — url dari env
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310  # nosec B310 — url dari env
            return json.loads(resp.read())

    try:
        payload = await asyncio.to_thread(_fetch)
    except Exception as exc:
        return {"chosen": None, "models": [], "error": str(exc)[:150]}

    models = [str(m.get("id", "")) for m in payload.get("data", []) if m.get("id")]
    if not models:
        return {"chosen": None, "models": [], "error": "no models returned"}

    overlay = await get_overlay(redis)
    # Skor: pro > turbo > flash > free; premium tanpa "free" menang.
    def _score(mid: str) -> tuple[int, float, int]:  # noqa: C901, PLR0912 — heuristik bercabang
        low = mid.lower()
        # Free selalu terakhir (rate-limit cepat).
        if "free" in low:
            return (0, 0.0, 0)
        # Tier utama: opus > sonnet > pro > flash > mini/oss > default.
        tier = 2
        if "opus" in low:
            tier = 6
        elif "sonnet" in low:
            tier = 5
        elif "pro" in low:
            tier = 4
        elif "flash" in low:
            tier = 3
        elif "gpt-oss" in low or "oss" in low:
            tier = 2
        elif "mini" in low:
            tier = 1
        # Version-aware tiebreak: gemini-3.7 > 3.6 > 3.5 > 3.1 > 3
        # (18 Aug 2026: daftar 9router baru — ag/gemini-3.7-flash-high dll).
        ver = 0.0
        for marker in ("3.7", "3.6", "3.5", "3.1", "3.0", "4.6", "4.5", "120b"):
            if marker in low:
                ver = float(marker.replace("b", "")) if marker != "120b" else 3.5
                break
        if "3-flash-agent" in low:
            ver = 3.5
        # Sub-tier: high > medium > low > extra-low (sama model).
        sub = 0
        if "high" in low:
            sub = 3
        elif "medium" in low:
            sub = 2
        elif "extra-low" in low:
            sub = 0
        elif "low" in low:
            sub = 1
        else:
            sub = 2  # tanpa suffix → anggap default (medium)
        return (tier, ver, sub)

    candidates = [m for m in models if not is_circuit_open(m, overlay)]
    if not candidates:
        candidates = models  # semua down → biarkan fallback chain menangani

    # ── Availability probe (18 Aug 2026) ─────────────────────────────
    # Masalah: service memilih model yang quota habis / tidak available —
    # ranking heuristic tidak tahu budget/availability sebenarnya (semua
    # ss/* kena 429 "Budget has been exceeded"). Solusi: TEST-CALL top-8
    # model (paralel, max_tokens=1) → hanya yang respond 200 dianggap
    # available → chosen dari available saja. Model 429 → circuit open
    # (skip 120s) → discovery berikutnya tidak probe lagi.
    ranked = sorted(candidates, key=_score, reverse=True)
    probe_pool = ranked[:8]

    async def _probe(mid: str) -> tuple[str, bool]:
        """Minimal chat call — 200 = available, 429/4xx/5xx = skip.
        urllib blocking → jalankan di thread (async-safe).
        """

        def _probe_sync() -> tuple[str, bool]:
            import urllib.request

            body = json.dumps(
                {
                    "model": mid,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                }
            ).encode()
            url = str(gateway_url).rstrip("/") + "/v1/chat/completions"
            req = urllib.request.Request(  # noqa: S310  # nosec B310 — url dari env
                url,
                data=body,
                headers={
                    "Authorization": f"Bearer {gateway_key}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=12) as resp:  # noqa: S310  # nosec B310 — url dari env
                    resp.read()
                    return mid, True
            except urllib.error.HTTPError as exc:
                # 429 budget exceeded / quota habis → circuit open (skip 120s).
                if exc.code == 429 or exc.code >= 500:
                    # circuit di-lakukan dari luar (async) — tandai saja.
                    pass
                return mid, False
            except Exception:
                return mid, False

        ok = await asyncio.to_thread(_probe_sync)
        if not ok[1]:
            await open_circuit(redis, mid)
        return ok

    available: list[str] = []
    if probe_pool:
        try:
            results = await asyncio.gather(*(_probe(m) for m in probe_pool))
            available = [m for m, ok in results if ok]
        except Exception:
            available = []
    # Kalau probe gagal total (network), fallback ke ranking (jangan
    # kosongkan chain — worker circuit breaker tetap melindungi).
    if not available:
        available = ranked
    chosen = max(available, key=_score)

    # Update overlay — default_model HANYA jika auto_discovery aktif DAN
    # user belum set default manual (Bug fix 18 Aug 2026: sebelumnya
    # SELALU timpa pilihan manual via superadmin — auto-select menang
    # karena skor 'pro' > model lain → "pengaturan tidak tersimpan").
    auto_discovery = overlay.get("auto_discovery") == "1"
    manual_default = overlay.get("manual_default") == "1"
    prev_default = overlay.get("default_model", "")
    updates: dict[str, str] = {}
    if auto_discovery and not manual_default and chosen != prev_default:
        updates["default_model"] = chosen
    # last_models_json SELALU di-update (cache untuk dropdown UI) —
    # ini bukan keputusan routing, hanya daftar model yang tersedia.
    updates["last_models_json"] = json.dumps(models[:50])
    updates["last_discovery_ts"] = str(int(_time.time()))
    updates["available_models"] = json.dumps(available[:20])
    if updates:
        await redis.hset(ROUTING_KEY, mapping=updates)
    return {
        "chosen": chosen if (auto_discovery and not manual_default) else prev_default,
        "models": models[:50],
        "available": available[:20],
        "error": None,
        "changed": auto_discovery and not manual_default and chosen != prev_default,
    }
