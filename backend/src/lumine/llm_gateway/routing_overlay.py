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
    # Circuit: skip model yang sedang down (bukan primary pertama).
    healthy = [primary]
    for m in fallbacks:
        if not is_circuit_open(m, overlay):
            healthy.append(m)
    return healthy, overlay


async def auto_select_best_model(redis: Any, gateway_url: str, gateway_key: str) -> dict[str, Any]:  # noqa: C901 — discovery heuristik bercabang
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
    def _score(mid: str) -> tuple[int, int]:
        low = mid.lower()
        if "free" in low:
            return (0, 0)
        if "flash" in low:
            return (1, 1)
        if "turbo" in low:
            return (2, 2)
        if "pro" in low:
            return (3, 3)
        if "mini" in low:
            return (1, 0)
        return (2, 1)  # default premium

    candidates = [m for m in models if not is_circuit_open(m, overlay)]
    if not candidates:
        candidates = models  # semua down → biarkan fallback chain menangani
    chosen = max(candidates, key=_score)

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
    if updates:
        await redis.hset(ROUTING_KEY, mapping=updates)
    return {
        "chosen": chosen if (auto_discovery and not manual_default) else prev_default,
        "models": models[:50],
        "error": None,
        "changed": auto_discovery and not manual_default and chosen != prev_default,
    }
