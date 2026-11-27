"""Data & code provenance untuk backtest reproducible (PRD v2.2 §8.2).

Setiap run walk-forward mencatat:
- data provenance: sumber, periode, simbol, timezone, versi, checksum
  (sha256 kanonik series), tanggal unduh (mtime file raw Dukascopy);
- code provenance: commit hash, branch, status dirty + daftar file kotor,
  hash konten modul yang dieksekusi (paper/, strategies/, app inti) sehingga
  reproducible bahkan saat tree dirty, versi Python + dependency, hash
  uv.lock;
- config hash: sha256 JSON kanonik seluruh konfigurasi run (grid, window,
  cost model, execution model, seed, dsb.).

Semua fungsi deterministik: input sama -> output sama.
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.data_quality import series_checksum

REPO_DIR = Path(__file__).resolve().parents[2]  # ~/fund2
API_DIR = REPO_DIR / "api"

# Modul yang dieksekusi backtest (hash konten = identitas kode yang jalan,
# independen dari git state). Relatif terhadap api/.
CODE_MODULES = [
    "paper/backtest.py", "paper/broker.py", "paper/costs.py",
    "paper/execution.py", "paper/provenance.py", "paper/preflight.py",
    "paper/baseline.py", "paper/walkforward.py", "paper/store.py",
    "paper/runner.py", "paper/feed.py",
    "strategies/london_breakout.py", "strategies/mean_reversion.py",
    "strategies/btc_range_breakout.py", "strategies/broker_time.py",
    "app/data_quality.py", "app/ingest.py", "app/regime.py", "app/risk.py",
    "app/db.py", "app/config.py",
]

# Dependency yang dipakai jalur backtest; yang tidak terpasang dilewati.
DEPS_TO_RECORD = [
    "psycopg", "psycopg-binary", "psycopg-pool", "pydantic", "fastapi",
    "uvicorn", "numpy", "pandas", "pyarrow", "hypothesis", "pytest",
    "pytest-asyncio", "alembic", "greenlet",
]

DATA_VERSION = "v1"  # versi skema provenance ini sendiri


def canonical_json(obj) -> str:
    """JSON kanonik: sort_keys, pemisah rapat, default=str untuk datetime."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def config_hash(config: dict) -> str:
    """sha256 dari JSON kanonik config (PRD §8.2: config hash)."""
    return "sha256:" + hashlib.sha256(canonical_json(config).encode()).hexdigest()


def _git(args: list[str], repo_dir: Path) -> str | None:
    try:
        out = subprocess.run(["git"] + args, cwd=repo_dir, capture_output=True,
                             text=True, timeout=15)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def module_file_hashes(api_dir: Path | None = None) -> dict[str, str]:
    """sha256 konten tiap modul yang dieksekusi backtest (relpath -> hash)."""
    api_dir = api_dir or API_DIR
    out: dict[str, str] = {}
    for rel in CODE_MODULES:
        p = api_dir / rel
        if p.exists():
            out[rel] = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def code_hash(api_dir: Path | None = None) -> str:
    """Hash agregat seluruh modul yang dieksekusi (identitas kode run)."""
    return config_hash(module_file_hashes(api_dir))


def code_provenance(repo_dir: Path | None = None) -> dict:
    """Commit hash, branch, dirty state, hash modul, Python, dependency."""
    repo_dir = repo_dir or REPO_DIR
    commit = _git(["rev-parse", "HEAD"], repo_dir)
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], repo_dir)
    porcelain = _git(["status", "--porcelain"], repo_dir) or ""
    dirty_files = sorted(line[3:].strip() for line in porcelain.splitlines() if line.strip())
    deps: dict[str, str] = {}
    from importlib.metadata import PackageNotFoundError, version
    for name in DEPS_TO_RECORD:
        try:
            deps[name] = version(name)
        except PackageNotFoundError:
            continue
    uv_lock = API_DIR / "uv.lock"
    uv_lock_hash = None
    if uv_lock.exists():
        uv_lock_hash = "sha256:" + hashlib.sha256(uv_lock.read_bytes()).hexdigest()
    return {
        "git_commit": commit,
        "git_branch": branch,
        "git_dirty": bool(dirty_files),
        "git_dirty_files": dirty_files[:30],
        "git_dirty_file_count": len(dirty_files),
        "code_hash": code_hash(),               # identitas modul yang dieksekusi
        "module_hashes": module_file_hashes(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "dependencies": deps,
        "uv_lock_sha256": uv_lock_hash,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def download_dates(raw_dir: Path | None) -> dict | None:
    """Tanggal unduh data (min/max mtime file raw .bi5 Dukascopy, UTC)."""
    if raw_dir is None or not Path(raw_dir).exists():
        return None
    mtimes = []
    for p in Path(raw_dir).rglob("*.bi5"):
        mtimes.append(datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc))
    if not mtimes:
        return None
    return {"downloaded_at_min": min(mtimes).isoformat(),
            "downloaded_at_max": max(mtimes).isoformat(),
            "files": len(mtimes)}


def data_provenance(candles: list[dict], *, symbol: str, tf: str,
                    source: str = "db:candles",
                    upstream: str = "dukascopy_m1 + ea_feed (live A1)",
                    raw_dir: str | Path | None = "~/fund2/data/dukascopy/m1/raw",
                    notes: list[str] | None = None) -> dict:
    """Provenance data candle yang dipakai backtest (PRD §8.2).

    - checksum: series_checksum (sha256 kanonik symbol|tf|ts|o|h|l|c|v)
    - tanggal unduh: mtime file raw Dukascopy (history); candle live EA
      tidak menyimpan ingest timestamp di schema candles (keterbatasan
      dicatat jujur di notes).
    """
    notes = list(notes or [])
    if not candles:
        raise ValueError("tidak ada candle untuk provenance")
    rows = []
    for c in candles:
        rows.append({
            "symbol": symbol, "timeframe": tf, "ts": c["ts"],
            "open": c.get("open", 0), "high": c.get("high", 0),
            "low": c.get("low", 0), "close": c.get("close", 0),
            "volume": c.get("volume", 0),
        })
    checksum = series_checksum(rows)
    ts_list = [c["ts"] for c in candles if c.get("ts") is not None]
    first, last = min(ts_list), max(ts_list)
    dl = download_dates(Path(raw_dir).expanduser()) if raw_dir else None
    if dl is None:
        notes.append("tanggal unduh raw tidak tersedia untuk window ini")
    if not any(c.get("volume") for c in candles):
        notes.append("tick volume 0/nol: partial fill tidak terkalibrasi")
    return {
        "data_version": DATA_VERSION,
        "source": source,
        "upstream": upstream,
        "symbol": symbol,
        "timeframe": tf,
        "period_start": first.astimezone(timezone.utc).isoformat(),
        "period_end": last.astimezone(timezone.utc).isoformat(),
        "bars": len(candles),
        "timezone": "UTC",
        "ts_semantics": "ts = awal bar; bar dianggap close pada ts+timeframe "
                        "(konvensi pipeline fund2; jam server A1 = UTC+7, "
                        "lihat strategies/broker_time.py)",
        "checksum": checksum,
        "download": dl,
        "notes": notes,
    }
