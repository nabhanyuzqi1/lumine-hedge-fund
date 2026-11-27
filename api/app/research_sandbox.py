"""Sandbox subprocess untuk backtest riset Hermes (PRD v2.2 §12.4).

Parent (app/research_write.py) mengirim candle + parameter via stdin ke
child `python -I -E -B app/research_sandbox_child.py`. Isolasi
(defence in depth, tanpa root — pola app/sandbox_child.py):

1. `python -I -E -B` + env kosong: tidak ada DATABASE_URL/secret yang
   mewaris; child tidak bisa menyambung DB.
2. closerange fd 3..N di preexec: tidak ada fd warisan (koneksi DB).
3. rlimits: RLIMIT_AS (memori), RLIMIT_CPU, RLIMIT_FSIZE=0 (anti tulis
   file), RLIMIT_CORE=0.
4. cwd direktori kosong sementara; stdout HANYA satu baris hasil.
5. Socket dinetralkan sebelum import modul strategi/backtest.
6. Landlock (deny-all FS + TCP) di-enforce setelah import, sebelum
   komputasi. Best-effort: bila kernel tidak mendukung, lapisan 1-5
   tetap aktif.
7. Wall-clock killpg oleh parent.

Child murni komputasi: run_backtest(candles, ...) dari paper.backtest
(fungsi murni, tanpa I/O). Tidak ada keputusan, tidak ada order — hasilnya
hanya metrik JSON yang dicatat parent ke backtest_runs.
"""
from __future__ import annotations

import asyncio
import json
import os
import resource
import signal
import sys
import tempfile
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent
CHILD_SCRIPT = Path(__file__).resolve().parent / "research_sandbox_child.py"

MAX_REQUEST_BYTES = 8 * 1024 * 1024    # candle 20k bar ~ 2 MB JSON
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MEM_LIMIT_MB = 512
CPU_LIMIT_S = 120
WALL_LIMIT_S = 150


def _preexec_limits() -> None:
    """preexec_fn: rlimits + tutup fd warisan (async-signal-safe)."""
    os.closerange(3, 4096)
    mem = MEM_LIMIT_MB * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT_S, CPU_LIMIT_S))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _kill_group(proc: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass


async def run_sandbox_backtest(request: dict) -> dict:
    """Jalankan satu backtest di sandbox; return {ok, metrics|error, sandbox}."""
    body = json.dumps(request, default=str).encode("utf-8")
    if len(body) > MAX_REQUEST_BYTES:
        return {"ok": False, "error": "request too large", "sandbox": {}}
    with tempfile.TemporaryDirectory(prefix="fund2-research-") as empty_cwd:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-I", "-E", "-B", str(CHILD_SCRIPT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=empty_cwd,
            env={},                       # tidak ada secret yang mewaris
            preexec_fn=_preexec_limits,
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(body), timeout=WALL_LIMIT_S)
        except asyncio.TimeoutError:
            _kill_group(proc)
            await proc.wait()
            return {"ok": False, "error": f"sandbox wall-clock {WALL_LIMIT_S}s",
                    "sandbox": {"killed": True}}
        except Exception:
            _kill_group(proc)
            await proc.wait()
            raise

    sandbox_info = {"returncode": proc.returncode,
                    "stderr_tail": (stderr or b"").decode("utf-8", "replace")[-400:]}
    if proc.returncode != 0:
        return {"ok": False,
                "error": f"sandbox exit {proc.returncode}: {sandbox_info['stderr_tail'][:200]}",
                "sandbox": sandbox_info}
    raw = (stdout or b"").strip()
    if len(raw) > MAX_RESPONSE_BYTES:
        return {"ok": False, "error": "response too large", "sandbox": sandbox_info}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"output sandbox tidak valid: {exc}",
                "sandbox": sandbox_info}
    parsed.setdefault("sandbox", {})
    parsed["sandbox"].update(sandbox_info)
    return parsed
