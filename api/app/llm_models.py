"""Pemilihan model LLM per peran + katalog model endpoint (t_2a1fbf01).

Keputusan owner: biaya token bukan batasan; yang dipilih adalah model tercepat
per peran, dan model terkuat untuk keputusan akhir.

Hasil benchmark 26 Nov 2026 (prompt 12k token, output <=400 token target):
  lucif        total 13,84 s  ttft 12,42 s  72 tok/s
  lucif-claude total 10,68 s  ttft  8,85 s  64 tok/s   (paling ringkas)
  lucif-flash  total 13,34 s  ttft 12,24 s  75 tok/s   (token/detik tertinggi)
Karena waktu total ditentukan panjang output, specialist memakai model dengan
throughput tertinggi (lucif-flash) dan synthesizer memakai lucif.
"""
from __future__ import annotations

import re
import time

DEFAULT_MODELS: dict[str, str] = {
    "specialist": "lucif-flash",
    "synth": "lucif",
    "fallback": "lucif-claude",
}

SETTING_KEY = "llm_models"

# Peran specialist yang modelnya boleh di-override owner dari UI
# (AgentModelPicker). Urutan ini yang ditampilkan di UI.
ROLE_KEYS: tuple[str, ...] = ("technical", "macro", "sentiment", "portfolio")

_NAME_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_CATALOG: dict[str, object] = {"models": None, "at": 0.0}


def is_valid_name(value: object) -> bool:
    """True bila `value` berbentuk nama model yang aman dikirim ke provider."""
    return isinstance(value, str) and bool(_NAME_RE.match(value.strip()))


def _valid_name(value: object, default: str) -> str:
    if isinstance(value, str) and _NAME_RE.match(value.strip()):
        return value.strip()
    return default


# Override per peran. Dasar: benchmark 26 Nov menunjukkan `lucif-claude` punya
# TTFT terendah (8,85 s pada prompt 12k) sementara `lucif-flash` unggul di
# throughput output. Specialist teknikal adalah yang terberat (prompt terpanjang),
# jadi prefill-nya yang menentukan wall-clock -> pakai model TTFT terendah.
DEFAULT_ROLE_MODELS: dict[str, str] = {"technical": "lucif-claude"}


def resolve(settings: dict | None) -> dict:
    """Konfigurasi efektif: {parallel, specialist, synth, fallback}.

    Dibaca dari settings key `llm_models` (bisa diubah owner dari UI), dengan
    fallback env/konstanta. Nilai tidak valid diabaikan, bukan membuat error:
    siklus trading tidak boleh mati karena salah ketik nama model.
    """
    raw = (settings or {}).get(SETTING_KEY)
    cfg = dict(DEFAULT_MODELS)
    parallel = True
    if isinstance(raw, dict):
        for key in ("specialist", "synth", "fallback"):
            cfg[key] = _valid_name(raw.get(key), cfg[key])
        if isinstance(raw.get("parallel"), bool):
            parallel = raw["parallel"]
    roles = dict(DEFAULT_ROLE_MODELS)
    if isinstance(raw, dict) and isinstance(raw.get("roles"), dict):
        for role, model in raw["roles"].items():
            if isinstance(role, str) and _NAME_RE.match(role):
                roles[role] = _valid_name(model, DEFAULT_MODELS["specialist"])
    return {"parallel": parallel, "roles": roles, **cfg}


async def fetch_catalog(http, *, base: str, key: str, ttl_s: float = 300.0) -> list[str]:
    """Daftar model dari endpoint OpenAI-compatible `/models` (cache 5 menit).

    Gagal fetch -> daftar kosong (UI menampilkan model efektif saja, tidak
    pernah mengarang model yang tidak ada).
    """
    now = time.monotonic()
    cached = _CATALOG.get("models")
    cached_at = _CATALOG.get("at")
    cached_at = float(cached_at) if isinstance(cached_at, (int, float)) else 0.0
    if isinstance(cached, list) and now - cached_at < ttl_s:
        return [str(m) for m in cached]
    try:
        resp = await http.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"}, timeout=10.0)
        if resp.status_code != 200:
            return []
        data = resp.json().get("data") or []
        models = sorted({str(m["id"]) for m in data if isinstance(m, dict) and m.get("id")})
        _CATALOG["models"] = models
        _CATALOG["at"] = now
        return list(models)
    except Exception:  # noqa: BLE001 - katalog bersifat informatif
        return []
