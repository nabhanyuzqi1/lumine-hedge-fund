#!/usr/bin/env python3
"""Rotasi pin relay genomeprobe ke model terkuat saat cooldown terbuka.

Owner 25 Nov: semua profil hf-* pakai model paling strong (gp-gpt-6-astra,
pilihan teratas owner). Relay mengunci 1 model pin per key (ganti 1x/10 jam),
jadi script ini:
  1. Cek config profil hf-ceo — kalau primary sudah target, exit (tidak kerja).
  2. Probe 1 request ke model target.
  3. Kalau berhasil: terapkan ke semua profil (apply_model_chain.py --mode
     shared --primary <target>), kirim notifikasi Telegram ke owner, selesai.
  4. Kalau masih cooldown: exit diam-diam (timer coba lagi nanti).

Tanpa argumen. Jangan print nilai kredensial.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

HOME = Path.home()
FUND2 = HOME / "fund2"
TARGET = "gp-gpt-6-astra"
PROFILES = ["hf-ceo", "hf-backend", "hf-frontend", "hf-qa", "hf-uiux", "hf-devops"]
ENV_ALERTS = HOME / "fund2" / "api" / ".env.alerts"


def current_primary() -> str:
    cfg = yaml_safe((HOME / ".hermes" / "profiles" / "hf-ceo" / "config.yaml").read_text())
    return str(((cfg.get("model") or {}).get("default")) or "")


def yaml_safe(text: str) -> dict:
    import yaml
    return yaml.safe_load(text) or {}


def relay_key() -> str:
    env_path = HOME / ".hermes" / "profiles" / "hf-ceo" / ".env"
    for line in env_path.read_text().splitlines():
        if line.startswith("HERMES_CUSTOM_GENOMEPROBE_API_KEY="):
            return line.partition("=")[2].strip()
    return ""


def probe(model: str) -> bool:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "satu kata: ya"}],
        "max_tokens": 300,
    }).encode()
    req = urllib.request.Request(
        "https://api.genomeprobe.cloud/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {relay_key()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return "choices" in json.loads(resp.read())
    except Exception:
        return False


def notify(text: str) -> None:
    if not ENV_ALERTS.exists():
        return
    vals = {}
    for line in ENV_ALERTS.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, _, v = line.partition("=")
            vals[k.strip()] = v.strip()
    token, chat = vals.get("TELEGRAM_BOT_TOKEN", ""), vals.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat, "text": text}).encode(),
        headers={"Content-Type": "application/json"})
    with contextlib_suppress():
        urllib.request.urlopen(req, timeout=30)


class contextlib_suppress:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return True


def main() -> int:
    if current_primary() == TARGET:
        return 0  # sudah target
    if not probe(TARGET):
        return 0  # masih cooldown — coba lagi tick berikutnya
    subprocess.run(
        [sys.executable, str(FUND2 / "scripts" / "apply_model_chain.py"),
         "--mode", "shared", "--primary", TARGET], check=True)
    notify(f"🔄 Pin relay diganti ke {TARGET} (model terkuat) — 6 profil hf-* sudah memakainya. Chain tetap lucif → lucif-flash.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
