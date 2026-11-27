"""Deteksi kode di disk vs proses yang sedang berjalan.

Insiden 26 Nov 2026: `fund2-api` tidak direstart setelah `PROMPT_VERSION`
dinaikkan, jadi UI menampilkan versi prompt lama (2.0.0) padahal kode di
disk sudah 2.3.0. Proses tidak bisa tahu commit terbaru sendirian, tetapi
ia BISA membandingkan konstanta yang di-import saat start dengan isi file
di disk sekarang. Selisih = proses basi, dan UI menampilkan banner.

`/health` memakai ini supaya drift terlihat tanpa harus menebak.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

from .llm_agent_loop import PROMPT_VERSION as _RUNNING_PROMPT_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_FILE = Path(__file__).with_name("llm_agent_loop.py")
_PROMPT_RE = re.compile(r'^PROMPT_VERSION\s*=\s*"([^"]+)"', re.MULTILINE)
_CACHE_TTL_S = 30.0
_cache: dict = {"at": 0.0, "commit": None}

STARTED_AT = time.time()


def disk_prompt_version() -> str | None:
    """PROMPT_VERSION yang tertulis di file sekarang (bukan yang di-import)."""
    try:
        match = _PROMPT_RE.search(AGENT_FILE.read_text(encoding="utf-8"))
    except OSError:
        return None
    return match.group(1) if match else None


def git_commit() -> str | None:
    """Commit HEAD repo, cache 30 s. Fallback env BUILD_COMMIT."""
    now = time.time()
    if now - float(_cache["at"] or 0.0) < _CACHE_TTL_S:
        return _cache["commit"]  # type: ignore[return-value]
    commit = os.environ.get("BUILD_COMMIT") or None
    if commit is None:
        try:
            out = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=2.0, check=True,
            )
            commit = out.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            commit = None
    _cache.update(at=now, commit=commit)
    return commit


def info() -> dict:
    """Ringkasan versi untuk /health dan banner UI."""
    disk = disk_prompt_version()
    return {
        "running_prompt_version": _RUNNING_PROMPT_VERSION,
        "disk_prompt_version": disk,
        "stale_code": bool(disk and disk != _RUNNING_PROMPT_VERSION),
        "commit": git_commit(),
        "started_at": STARTED_AT,
        "uptime_s": round(time.time() - STARTED_AT, 1),
    }
