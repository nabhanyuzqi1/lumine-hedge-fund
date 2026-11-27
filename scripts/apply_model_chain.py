#!/usr/bin/env python3
"""Terapkan model chain owner ke 6 profil hf-* (fund office).

Sumber spesifikasi: instruksi owner 24 Nov 2026 (lihat docs/MODEL_CHAIN.md).

Mode:
  shared  (default) semua profil: primary = 1 model relay yang sama + tail lucif.
          Ini satu-satunya mode yang bisa jalan di relay genomeprobe (1 key = 1
          model pin, ganti 1x/10 jam).
  full     urutan per-role persis seperti spesifikasi owner (primary berbeda
          tiap role + 20 model relay + lucif terakhir). HANYA dipakai kalau
          relay sudah membebaskan ganti model (atau relay/key lain).

Pakai: python3 scripts/apply_model_chain.py [--mode full] [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

PROFILES = ["hf-ceo", "hf-backend", "hf-frontend", "hf-qa", "hf-uiux", "hf-devops"]
HERMES = Path.home() / ".hermes" / "profiles"

RELAY_BASE_URL = "https://api.genomeprobe.cloud/v1"
RELAY_KEY_ENV = "HERMES_CUSTOM_GENOMEPROBE_API_KEY"
LUCIF_BASE_URL = "https://lucif.ai/v1"
LUCIF_KEY_ENV = "HERMES_CUSTOM_LUCIF_VPS_API_KEY"

TAIL = [
    {"provider": "lucif-vps", "model": "lucif", "base_url": LUCIF_BASE_URL, "key_env": LUCIF_KEY_ENV},
    {"provider": "lucif-vps", "model": "lucif-flash", "base_url": LUCIF_BASE_URL, "key_env": LUCIF_KEY_ENV},
]

# Urutan owner 24 Nov 2026 (tanpa Lucif/Lucif-Flash — otomatis ditambah di ekor).
FULL_CHAINS: dict[str, list[str]] = {
    "hf-ceo": [
        "gp-gpt-6-astra", "gp-claude-opus-5.5", "gp-gpt-6.1-sol", "gp-claude-sonnet-5.5",
        "gp-kimi-k3.1-pro", "gp-kimi-k3-ultra", "gp-glm-5.3", "gp-gpt-6-sol", "gp-gpt-6-luna",
        "gp-gpt-6.1-terra", "gp-kimi-k2.8", "gp-gemini-3.8-flash-high", "gp-deepseek-4-flash",
        "gp-deepseek-4.1-flash", "gp-glm-5.3-flash", "gp-claude-haiku-5.5", "gp-gemini-3.8-flash",
        "gp-kimi-k2.7-code", "gp-deepseek-4-flash-0731", "gp-gpt-6-astra-ultrafast",
    ],
    "hf-backend": [
        "gp-gpt-6-astra", "gp-claude-opus-5.5", "gp-kimi-k3.1-pro", "gp-gpt-6.1-sol",
        "gp-claude-sonnet-5.5", "gp-kimi-k2.7-code", "gp-glm-5.3", "gp-kimi-k3-ultra",
        "gp-gpt-6-sol", "gp-gpt-6-luna", "gp-deepseek-4-flash", "gp-deepseek-4.1-flash",
        "gp-gpt-6.1-terra", "gp-gemini-3.8-flash-high", "gp-kimi-k2.8", "gp-glm-5.3-flash",
        "gp-claude-haiku-5.5", "gp-deepseek-4-flash-0731", "gp-gemini-3.8-flash",
        "gp-gpt-6-astra-ultrafast",
    ],
    "hf-frontend": [
        "gp-gpt-6-astra", "gp-claude-sonnet-5.5", "gp-claude-opus-5.5", "gp-gemini-3.8-flash-high",
        "gp-gpt-6.1-sol", "gp-kimi-k3.1-pro", "gp-glm-5.3", "gp-gpt-6-sol", "gp-kimi-k2.8",
        "gp-gpt-6-luna", "gp-gemini-3.8-flash", "gp-kimi-k2.7-code", "gp-deepseek-4-flash",
        "gp-deepseek-4.1-flash", "gp-gpt-6.1-terra", "gp-glm-5.3-flash", "gp-claude-haiku-5.5",
        "gp-kimi-k3-ultra", "gp-deepseek-4-flash-0731", "gp-gpt-6-astra-ultrafast",
    ],
    "hf-qa": [
        "gp-claude-opus-5.5", "gp-gpt-6-astra", "gp-gpt-6.1-sol", "gp-kimi-k3.1-pro",
        "gp-glm-5.3", "gp-claude-sonnet-5.5", "gp-kimi-k3-ultra", "gp-gpt-6-sol", "gp-gpt-6-luna",
        "gp-deepseek-4.1-flash", "gp-deepseek-4-flash", "gp-gpt-6.1-terra",
        "gp-gemini-3.8-flash-high", "gp-kimi-k2.8", "gp-claude-haiku-5.5", "gp-glm-5.3-flash",
        "gp-kimi-k2.7-code", "gp-deepseek-4-flash-0731", "gp-gemini-3.8-flash",
        "gp-gpt-6-astra-ultrafast",
    ],
    "hf-uiux": [
        "gp-claude-sonnet-5.5", "gp-claude-opus-5.5", "gp-gemini-3.8-flash-high", "gp-gpt-6-astra",
        "gp-gpt-6.1-sol", "gp-gemini-3.8-flash", "gp-kimi-k3.1-pro", "gp-gpt-6-sol", "gp-glm-5.3",
        "gp-gpt-6-luna", "gp-kimi-k2.8", "gp-claude-haiku-5.5", "gp-gpt-6.1-terra",
        "gp-deepseek-4.1-flash", "gp-deepseek-4-flash", "gp-glm-5.3-flash", "gp-kimi-k3-ultra",
        "gp-kimi-k2.7-code", "gp-deepseek-4-flash-0731", "gp-gpt-6-astra-ultrafast",
    ],
    "hf-devops": [
        "gp-claude-opus-5.5", "gp-gpt-6-astra", "gp-gpt-6.1-sol", "gp-kimi-k3.1-pro",
        "gp-claude-sonnet-5.5", "gp-glm-5.3", "gp-gpt-6-sol", "gp-deepseek-4.1-flash",
        "gp-deepseek-4-flash", "gp-kimi-k3-ultra", "gp-gpt-6-luna", "gp-gpt-6.1-terra",
        "gp-kimi-k2.8", "gp-glm-5.3-flash", "gp-claude-haiku-5.5", "gp-kimi-k2.7-code",
        "gp-gemini-3.8-flash-high", "gp-deepseek-4-flash-0731", "gp-gemini-3.8-flash",
        "gp-gpt-6-astra-ultrafast",
    ],
}


def relay_entry(model: str) -> dict:
    return {"provider": "genomeprobe", "model": model, "base_url": RELAY_BASE_URL, "key_env": RELAY_KEY_ENV}


def apply_profile(profile: str, primary: str, chain: list[dict], dry_run: bool) -> None:
    cfg_path = HERMES / profile / "config.yaml"
    src = cfg_path.read_text()
    # Ganti model default apa pun yang sedang terpasang (gp-*, lucif, claude, dll)
    # dengan primary owner. Pola: di dalam blok model:, kunci default: "...".
    import re as _re
    src, n_sub = _re.subn(
        r'(?m)^(\s*default:\s*")[^"]*(")$',
        lambda m: m.group(1) + primary + m.group(2),
        src, count=1)
    if n_sub == 0:
        # fallback: blok model: tanpa indentasi khusus
        src, n_sub = _re.subn(
            r'(?m)^(\s*default:\s*")[^"]*(")',
            lambda m: m.group(1) + primary + m.group(2),
            src, count=1)
    for old, new in [
        ('  provider: "lucif-vps"', '  provider: "genomeprobe"'),
        ('  base_url: "https://lucif.ai/v1"', f'  base_url: "{RELAY_BASE_URL}"'),
        ('  base_url: "https://api.genomeprobe.cloud/v1"', f'  base_url: "{RELAY_BASE_URL}"'),
    ]:
        if old in src:
            src = src.replace(old, new, 1)
    # fallback_providers: ganti blok lama kalau ada, kalau tidak append di EOF.
    marker = "\nfallback_providers:\n"
    block = yaml.safe_dump({"fallback_providers": chain}, default_flow_style=False, sort_keys=False)
    if marker in src:
        head = src.split(marker, 1)[0].rstrip()
        src = head + "\n" + marker.lstrip("\n") + block
    else:
        src = src.rstrip() + "\n\n" + marker.lstrip("\n") + block
    if dry_run:
        print(f"[dry-run] {profile}: primary={primary}, chain={[e['model'] for e in chain]}")
        return
    cfg_path.write_text(src)
    yaml.safe_load(cfg_path.read_text())
    print(f"{profile}: primary={primary}, chain={len(chain)} entri")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["shared", "full"], default="shared")
    ap.add_argument("--primary", default="gp-gemini-3.8-flash", help="model pin relay untuk mode shared")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    for profile in PROFILES:
        if args.mode == "shared":
            apply_profile(profile, args.primary, TAIL, args.dry_run)
        else:
            chain = [relay_entry(m) for m in FULL_CHAINS[profile]] + TAIL
            apply_profile(profile, FULL_CHAINS[profile][0], chain, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
