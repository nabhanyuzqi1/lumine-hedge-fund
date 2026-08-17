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
    except Exception:
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
