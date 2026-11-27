"""Anggaran latensi siklus LLM (t_afd7fe4e butir C).

Temuan kartu: `order_events.decision` 24 jam terakhir rata-rata 48,8 s (maks
119,7 s) dengan prompt konstan 87.256 token dan completion 3.217-6.804 token.
Throughput endpoint ±55-65 token/detik, jadi durasi DIDOMINASI panjang output,
bukan prefill. Karena itu anggaran di sini mengikat dua hal:

1. `max_tokens` per tahap (specialist / synthesizer / jalur satu-prompt).
   Jalur satu-prompt lama memakai 8000 token -> 3-6 ribu token reasoning yang
   tidak pernah dipakai gate mana pun (keputusan hanya butuh JSON pendek).
2. Aturan keluaran ringkas di prompt: reasoning <= 400 token, tanpa narasi.

Prompt caching: endpoint (vLLM) sudah melakukan automatic prefix caching dan
melaporkan `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`. Supaya
cache benar-benar HIT, prompt disusun statis-dulu: system prompt (aturan +
skema) lalu konteks paling stabil (H4 -> H1 -> M15) dan data volatil (M5, harga
sekarang, waktu) di belakang. Tanpa urutan ini, `now_utc` di awal prompt
membuat prefix berubah setiap siklus -> cache selalu miss.

Semua nilai bisa diubah owner lewat settings key `llm_latency_budget` (merge
parsial, pola yang sama dengan `llm_risk`), tanpa deploy.
"""
from __future__ import annotations

import json
from typing import Any

SETTING_KEY = "llm_latency_budget"

# Target p95 siklus penuh (kartu: <= 35 s), dari detik ke milidetik.
DEFAULT_BUDGET: dict = {
    "target_p95_s": 35.0,
    "max_tokens_specialist": 450,   # JSON pendek per peran (technical dll)
    "max_tokens_synth": 700,        # satu keputusan + reasoning <= 400 token
    "max_tokens_single": 1200,      # jalur satu-prompt (fallback parallel=off)
    "reasoning_max_tokens": 400,    # aturan prompt + plafon thinking provider
    "specialist_timeout_s": 45.0,
    "synth_timeout_s": 45.0,
    "single_timeout_s": 90.0,
    # `max_tokens` TIDAK membatasi token reasoning pada provider ini: terbukti
    # 26 Nov 2026, technical memakai max_tokens=450 tetap menghasilkan
    # completion 1.496-2.351 token (usage.completion_tokens_details
    # .reasoning_tokens), dan itulah 26-32 s dari satu siklus. Plafon thinking
    # harus dikirim sebagai parameter provider.
    #   specialist: "off"  -> reasoning 0, cukup membaca fakta terstruktur
    #               "budget" -> hormati reasoning_max_tokens
    #   synth/single: selalu "budget", keputusan akhir butuh berpikir terbatas
    "specialist_reasoning": "off",
    "synth_reasoning_tokens": 400,
}

_INT_KEYS = ("max_tokens_specialist", "max_tokens_synth", "max_tokens_single",
             "reasoning_max_tokens")
_FLOAT_KEYS = ("target_p95_s", "specialist_timeout_s", "synth_timeout_s",
               "single_timeout_s")

# Batas keras supaya salah ketik owner tidak mematikan gate/anggaran:
# max_tokens minimal 64 (JSON keputusan tidak mungkin lebih pendek) dan
# maksimal 2000 (di atas itu latensi kembali ke 30 s+).
_MAX_TOKENS_MIN = 64
_MAX_TOKENS_MAX = 2000


def resolve(settings: dict | None) -> dict:
    """Anggaran efektif: default <- settings `llm_latency_budget` (parsial)."""
    cfg = dict(DEFAULT_BUDGET)
    raw = (settings or {}).get(SETTING_KEY)
    if isinstance(raw, dict):
        for key in _INT_KEYS:
            value = raw.get(key)
            if value is None:
                continue
            try:
                cfg[key] = min(max(int(value), _MAX_TOKENS_MIN), _MAX_TOKENS_MAX)
            except (TypeError, ValueError):
                continue
        for key in _FLOAT_KEYS:
            value = raw.get(key)
            if value is None:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number > 0:
                cfg[key] = number
    # `synth_reasoning_tokens` punya batas sendiri (0 = thinking mati), jadi
    # TIDAK boleh lewat clamp max_tokens (64..2000): 0 akan berubah jadi 64 dan
    # thinking tetap hidup.
    raw_synth = raw.get("synth_reasoning_tokens") if isinstance(raw, dict) else None
    if raw_synth is not None:
        try:
            cfg["synth_reasoning_tokens"] = max(0, min(int(raw_synth), 4096))
        except (TypeError, ValueError):
            pass
    mode = raw.get("specialist_reasoning") if isinstance(raw, dict) else None
    if isinstance(mode, str) and mode.strip().lower() in ("off", "budget"):
        cfg["specialist_reasoning"] = mode.strip().lower()
    cfg["synth_reasoning_tokens"] = max(0, min(int(cfg["synth_reasoning_tokens"]), 4096))
    return cfg


# Cadangan waktu siklus untuk langkah non-LLM (submit keputusan, tulis audit).
# Anggaran 35 s => tahap LLM wajib selesai dalam 30 s sejak siklus mulai.
DEADLINE_RESERVE_S = 5.0


def llm_deadline(budget: dict | None, started_mono: float) -> float:
    """Batas time.monotonic() untuk seluruh tahap LLM satu siklus."""
    budget = budget or DEFAULT_BUDGET
    span = max(float(budget.get("target_p95_s") or 35.0) - DEADLINE_RESERVE_S, 10.0)
    return float(started_mono) + span


def thinking_param(budget: dict, stage: str) -> dict:
    """Parameter plafon thinking untuk satu tahap (kosong = perilaku default).

    `max_tokens` hanya membatasi token JAWABAN; token reasoning tetap
    dihasilkan penuh dan dibayar dengan waktu. Stage specialist default tanpa
    thinking (`specialist_reasoning="off"`) karena tugasnya membaca fakta
    terstruktur, sedangkan synth (keputusan akhir) memakai plafon
    `synth_reasoning_tokens`.
    """
    budget = budget or DEFAULT_BUDGET
    if stage == "specialist":
        if str(budget.get("specialist_reasoning", "off")) == "off":
            return {"thinking": {"type": "disabled"}}
        limit = int(budget.get("reasoning_max_tokens") or 0)
        return {"thinking": {"type": "enabled", "budget_tokens": limit}} if limit > 0 else {}
    limit = int(budget.get("synth_reasoning_tokens") or 0)
    return {"thinking": {"type": "enabled", "budget_tokens": limit}} if limit > 0 else \
        {"thinking": {"type": "disabled"}}


def reasoning_rule(budget: dict) -> str:
    """Satu baris aturan output ringkas yang ditempel ke prompt."""
    return (f"reasoning maksimal {int(budget['reasoning_max_tokens'])} token "
            "(1-3 kalimat), tanpa narasi langkah demi langkah; jawab JSON saja.")


# ── Prompt caching: susun konteks dengan prefix paling stabil di depan ──────
# Urutan timeframe: paling lambat berubah lebih dulu (H4 14 hari, H1 5 hari,
# M15 2 hari, M5 24 jam). M5 berubah tiap siklus, jadi diletakkan paling
# belakang supaya 3 timeframe lain tetap kena prefix cache.
CACHE_TF_ORDER = ("H4", "H1", "M15", "M5")

# Kunci top-level yang berubah setiap siklus (waktu, status, posisi, likuiditas,
# makro) -> diletakkan SETELAH blok simbol (yang berisi candle historis).
VOLATILE_TOP_KEYS = ("now_utc", "session", "kill_switch", "halted",
                     "risk_limits", "facts")

# Di dalam satu simbol, urutan stabil: candle dulu, sisanya belakangan.
_STABLE_SYMBOL_KEYS = ("candles",)

# Fakta simbol (llm_facts.symbol_facts): blok besar yang hampir tidak berubah
# antar siklus diletakkan lebih dulu supaya jadi prefix cache; nilai yang
# berubah tiap siklus (harga, umur candle, posisi) paling belakang.
SYMBOL_FACT_STABLE_KEYS = ("timeframes", "structure", "liquidity", "fib_zones")
SYMBOL_FACT_VOLATILE_KEYS = ("status", "price", "candle_age_min", "open_positions",
                             "llm_positions")


def _ordered_facts(block: Any) -> Any:
    """Urutkan satu blok fakta simbol: stabil dulu, volatil belakang."""
    if not isinstance(block, dict):
        return block
    out: dict = {}
    for key in SYMBOL_FACT_STABLE_KEYS:
        if key in block:
            out[key] = block[key]
    for key, value in block.items():
        if key not in out and key not in SYMBOL_FACT_VOLATILE_KEYS:
            out[key] = value
    for key in SYMBOL_FACT_VOLATILE_KEYS:
        if key in block:
            out[key] = block[key]
    return out


def reorder_for_cache(payload: Any) -> Any:
    """Payload prompt dengan prefix paling stabil di depan (cache-friendly).

    Hanya mengubah URUTAN kunci, tidak isi: prefix caching endpoint (vLLM/
    provider) memotong di token pertama yang berbeda, jadi satu `price` di
    posisi kedua membatalkan cache seluruh blok candle di belakangnya.
    """
    if not isinstance(payload, dict):
        return payload
    out: dict = {}
    for key, value in payload.items():
        if key == "symbols" and isinstance(value, dict):
            out[key] = {sym: _ordered_facts(block) for sym, block in value.items()}
        else:
            out[key] = value
    return out


def _ordered_symbol(block: Any) -> Any:
    if not isinstance(block, dict):
        return block
    out: dict = {}
    for key in _STABLE_SYMBOL_KEYS:
        if key in block:
            value = block[key]
            if key == "candles" and isinstance(value, dict):
                ordered_tf = {tf: value[tf] for tf in CACHE_TF_ORDER if tf in value}
                ordered_tf.update({k: v for k, v in value.items() if k not in ordered_tf})
                value = ordered_tf
            out[key] = value
    for key, value in block.items():
        if key not in out:
            out[key] = value
    return out


def stable_context(ctx: dict) -> dict:
    """Konteks untuk prompt: prefix stabil dulu, data volatil di belakang.

    Tidak mengubah isi/angka apa pun, hanya urutan kunci. JSON hasilnya tetap
    dibaca LLM persis sama (objek tanpa semantik urutan), tetapi prefix cache
    vLLM bisa hit karena awal prompt tidak lagi diawali `now_utc`.
    """
    if not isinstance(ctx, dict):
        return ctx
    out: dict = {}
    symbols = ctx.get("symbols")
    if isinstance(symbols, dict):
        out["symbols"] = {sym: _ordered_symbol(block)
                          for sym, block in symbols.items()}
    for key, value in ctx.items():
        if key in out or key in VOLATILE_TOP_KEYS:
            continue
        out[key] = value
    for key in VOLATILE_TOP_KEYS:
        if key in ctx:
            out[key] = ctx[key]
    return out


def dumps_stable(value: Any) -> str:
    """JSON deterministik untuk prompt (tanpa spasi acak, UTF-8 apa adanya)."""
    return json.dumps(value, default=str, ensure_ascii=False, separators=(",", ":"))


# ── Statistik cache dari response usage (banyak bentuk, semua ditoleransi) ──
def cache_stats(usage: dict | None) -> dict:
    """Normalisasi statistik prompt cache dari berbagai bentuk `usage`.

    - vLLM/DeepSeek: prompt_cache_hit_tokens / prompt_cache_miss_tokens
    - OpenAI:        prompt_tokens_details.cached_tokens
    - Anthropic:     cache_read_input_tokens / cache_creation_input_tokens
    Return {"hit": int|None, "miss": int|None, "rate": float|None}.
    """
    usage = usage if isinstance(usage, dict) else {}
    hit = None
    miss = None
    for key in ("prompt_cache_hit_tokens", "cache_read_input_tokens"):
        value = usage.get(key)
        if isinstance(value, (int, float)):
            hit = int(value)
            break
    for key in ("prompt_cache_miss_tokens",):
        value = usage.get(key)
        if isinstance(value, (int, float)):
            miss = int(value)
            break
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict) and isinstance(details.get("cached_tokens"), (int, float)):
        hit = int(details["cached_tokens"])
    total = usage.get("prompt_tokens")
    if miss is None and isinstance(total, (int, float)) and hit is not None:
        miss = max(int(total) - hit, 0)
    rate = None
    if hit is not None and isinstance(total, (int, float)) and total:
        rate = round(hit / float(total), 4)
    elif hit is not None and miss is not None and (hit + miss):
        rate = round(hit / float(hit + miss), 4)
    return {"hit": hit, "miss": miss, "rate": rate}


def summarise_latency(samples: list[float], target_s: float) -> dict:
    """Statistik latensi untuk dashboard/gate: p50/p95/max + status vs target."""
    values = sorted(float(s) for s in samples if s is not None)

    def pct(p: float) -> float | None:
        if not values:
            return None
        if len(values) == 1:
            return round(values[0], 3)
        pos = (len(values) - 1) * (p / 100.0)
        low = int(pos)
        high = min(low + 1, len(values) - 1)
        frac = pos - low
        return round(values[low] + (values[high] - values[low]) * frac, 3)

    p95 = pct(95)
    return {
        "n": len(values),
        "p50_s": pct(50),
        "p95_s": p95,
        "max_s": round(values[-1], 3) if values else None,
        "target_p95_s": float(target_s),
        "within_budget": bool(p95 is not None and p95 <= float(target_s)),
    }
