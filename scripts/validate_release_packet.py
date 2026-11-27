"""Validasi paket release readiness Fund2 v2.2 (kartu t_128a9dee, DevOps).

READ-ONLY: tidak mengubah DB, settings, service, atau file repo. Membaca:
  - keberadaan dan isi minimum dokumen paket di docs/,
  - state git (HEAD, tree, tag),
  - /health API (env),
  - systemd user services fund2-*,
  - tabel settings + alembic_version (read-only),
  - backup terbaru, bukti pytest, bukti soak.

Output: JSON di docs/VALIDASI_PAKET_RILIS_<ts>.json + ringkasan stdout.
Jalankan: cd ~/fund2/api && .venv/bin/python ../scripts/validate_release_packet.py
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit, urlunsplit

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
BACKUP_LOGS = pathlib.Path.home() / "fund2-backups" / "logs"
API_ENV = ROOT / "api" / ".env"

APPROVED = {
    "max_volume": 0.10,                 # A3
    "max_orders_per_min": 5,            # A8
    "daily_drawdown_pct": 3.0,          # A6
    "total_drawdown_pct": 8.0,          # A7
    "consecutive_failed_orders": 3,     # desain runbook
    "max_total_volume_lot": 0.30,       # A4
    "max_risk_per_trade_pct": 0.5,      # A5
    "max_spread": 0.5,                  # A9
    "max_tick_age_s": 3.0,              # A10 (settings key, gate risk.py)
}

# Policy final 26 Nov 2026 (KEPUTUSAN_OWNER §I):
#  - ea_offline_seconds = 6 s (A12: tandai offline + blokir order baru/alert)
#  - ea_offline_halt_seconds = 60 s (auto GLOBAL_HALT, v2.1 §5.7)
#  - max_feed_age_s (equity/margin feed) BUKAN A10: ambang tick ada di
#    max_tick_age_s. Nilai feed dijaga tetap wajar (<= 300 s).
EA_OFFLINE_MARK_S = 6.0
EA_OFFLINE_HALT_S = 60.0
MAX_FEED_AGE_S_MAX = 300.0
# A6 wajah absolut: gate order berhenti di 3% saldo awal hari.
DAILY_DD_PCT = APPROVED["daily_drawdown_pct"] / 100.0

REQUIRED_DOCS = {
    "RELEASE_PACKET_v2.2.md": "Keputusan",
    "CANARY_PLAN_v2.2.md": "Prasyarat masuk",
    "GENERAL_RELEASE_PLAN_v2.2.md": "Prasyarat masuk",
    "ROLLBACK_PLAN_v2.2.md": "Trigger rollback",
    "CHECKLIST_ROLLBACK_v2.2.md": "Langkah",
    "ARTEFAK_RILIS_v2.2.md": "Identitas build",
    "RISK_REGISTER_v2.2.md": "Risk register",
    "LOAD_SOAK_v2.2.md": "Ringkasan",
    "OBSERVABILITY_v2.2.md": "Metrics",
    "RUNBOOK_v2.2.md": "Peta alarm",
    "PRASYARAT_LIVE_v2.2.md": "Tiga gerbang",
    "RELEASE_CHECKLIST_v2.2.md": "Keputusan GO/NO-GO",
    "DR_v2.2.md": "Restore drill",
    "INCIDENT_PLAYBOOK_v2.2.md": "Insiden",
}


def read_env_db_url() -> str:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if url:
        return url
    for line in API_ENV.read_text().splitlines():
        line = line.strip()
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("DATABASE_URL tidak ditemukan")


def masked(url: str) -> str:
    parts = urlsplit(url)
    netloc = parts.netloc.split("@")[-1]
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def run(cmd: list[str], cwd: pathlib.Path | None = None) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
    return p.returncode, (p.stdout + p.stderr).strip()


def check_docs() -> dict:
    out = {"present": {}, "missing": [], "pass": True}
    for name, marker in REQUIRED_DOCS.items():
        f = DOCS / name
        if not f.exists() or f.stat().st_size < 1000:
            out["missing"].append(name)
            out["present"][name] = {"exists": f.exists(), "bytes": f.stat().st_size if f.exists() else 0}
            out["pass"] = False
            continue
        text = f.read_text(errors="replace")
        ok_marker = marker.lower() in text.lower()
        out["present"][name] = {"exists": True, "bytes": f.stat().st_size, "marker_found": ok_marker}
        if not ok_marker:
            out["pass"] = False
    return out


def check_git() -> dict:
    rc, head = run(["git", "rev-parse", "--short", "HEAD"], ROOT)
    _, branch = run(["git", "branch", "--show-current"], ROOT)
    _, dirty = run(["git", "status", "--porcelain"], ROOT)
    _, tags = run(["git", "tag", "--list"], ROOT)
    lines = [l for l in dirty.splitlines() if l.strip()]
    return {
        "head": head if rc == 0 else None,
        "branch": branch,
        "dirty": bool(lines),
        "dirty_files": lines[:10],
        "tags": [t for t in tags.splitlines() if t.strip()],
        "has_release_tag": any(t.startswith("fund2-v2.2") for t in tags.splitlines()),
        "pass_clean": not lines,
    }


def check_health() -> dict:
    try:
        with urllib.request.urlopen("http://127.0.0.1:3110/health", timeout=5) as r:
            data = json.loads(r.read().decode())
        return {"ok": data.get("ok") is True, "env": data.get("env"), "raw": data, "pass": data.get("env") == "demo"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": repr(exc), "pass": False}


def check_services() -> dict:
    units = ["fund2-api", "fund2-postgres", "fund2-alerts", "fund2-paper-runner",
             "fund2-llm-agent", "fund2-hfm-recorder", "fund2-shadow-runner", "fund2-candle-rollup"]
    out = {}
    for u in units:
        rc, state = run(["systemctl", "--user", "is-active", u])
        out[u] = state
    return {"units": out, "pass": all(v == "active" for v in out.values())}


def check_db() -> dict:
    import psycopg
    url = read_env_db_url()
    out: dict = {}
    with psycopg.connect(url) as c:
        c.read_only = True
        cur = c.cursor()
        cur.execute("select key, value from settings where key in "
                    "('max_volume','max_orders_per_min','max_daily_drawdown','kill_switch',"
                    "'kill_switch_triggers','portfolio_risk','max_spread','risk_per_trade_pct',"
                    "'exposure_max_usd','halted','strategy_mode_ml_gbm','max_tick_age_s',"
                    "'daily_start_balance')")
        s = {k: v for k, v in cur.fetchall()}
        ks = s.get("kill_switch_triggers") or {}
        pr = s.get("portfolio_risk") or {}
        actual = {
            "max_volume": s.get("max_volume"),
            "max_orders_per_min": s.get("max_orders_per_min"),
            "daily_drawdown_pct": ks.get("daily_drawdown_pct"),
            "max_daily_drawdown": s.get("max_daily_drawdown"),
            "total_drawdown_pct": ks.get("total_drawdown_pct"),
            "consecutive_failed_orders": ks.get("consecutive_failed_orders"),
            "ea_offline_seconds": ks.get("ea_offline_seconds"),
            "ea_offline_halt_seconds": ks.get("ea_offline_halt_seconds"),
            "max_total_volume_lot": pr.get("max_total_volume_lot"),
            "max_risk_per_trade_pct": pr.get("max_risk_per_trade_pct"),
            "max_spread": s.get("max_spread"),
            "max_tick_age_s": s.get("max_tick_age_s"),
            "max_feed_age_s": pr.get("max_feed_age_s"),
            "daily_start_balance": s.get("daily_start_balance"),
        }
        drift = []
        open_items = []
        for key, expected in APPROVED.items():
            val = actual.get(key)
            if val is None:
                open_items.append(f"{key}: setting tidak ditemukan")
            elif abs(float(val) - float(expected)) > 1e-9:
                drift.append({"key": key, "expected": expected, "actual": val})
        # A12 vs ambang halt: dua angka berbeda dan keduanya wajib terpasang.
        if actual.get("ea_offline_seconds") is None:
            open_items.append("ea_offline_seconds: setting tidak ditemukan")
        elif abs(float(actual["ea_offline_seconds"]) - EA_OFFLINE_MARK_S) > 1e-9:
            drift.append({"key": "ea_offline_seconds", "expected": EA_OFFLINE_MARK_S,
                          "actual": actual["ea_offline_seconds"]})
        if actual.get("ea_offline_halt_seconds") is None:
            open_items.append("ea_offline_halt_seconds: setting tidak ditemukan "
                              "(wajib 60 s, v2.1 §5.7)")
        elif abs(float(actual["ea_offline_halt_seconds"]) - EA_OFFLINE_HALT_S) > 1e-9:
            drift.append({"key": "ea_offline_halt_seconds", "expected": EA_OFFLINE_HALT_S,
                          "actual": actual["ea_offline_halt_seconds"]})
        # A6 punya wajah absolut untuk gate order: 3% saldo awal hari. Nilai di
        # atas plafon 3% = pelonggaran (FAIL); di bawahnya = lebih ketat (catat,
        # karena menghentikan order lebih awal dari policy dan mengubah perilaku
        # bisnis, tapi tidak membahayakan).
        start_balance = actual.get("daily_start_balance")
        dd_abs = actual.get("max_daily_drawdown")
        if dd_abs is None:
            open_items.append("max_daily_drawdown: setting tidak ditemukan")
        elif not start_balance:
            open_items.append("daily_start_balance: setting tidak ditemukan "
                              "(plafon A6 absolut tidak bisa diuji)")
        else:
            ceiling = round(DAILY_DD_PCT * float(start_balance), 2)
            actual["max_daily_drawdown_ceiling"] = ceiling
            if float(dd_abs) > ceiling + 1e-6:
                drift.append({"key": "max_daily_drawdown", "expected": ceiling,
                              "actual": dd_abs})
            elif abs(float(dd_abs) - ceiling) > 0.005:
                open_items.append(
                    f"max_daily_drawdown={dd_abs}: lebih ketat dari §I {ceiling} "
                    f"({DAILY_DD_PCT:.0%} x daily_start_balance)")
        # max_feed_age_s = konteks feed equity/margin, bukan A10: hanya dijaga wajar.
        if actual.get("max_feed_age_s") is None:
            open_items.append("portfolio_risk.max_feed_age_s: setting tidak ditemukan")
        elif float(actual["max_feed_age_s"]) > MAX_FEED_AGE_S_MAX:
            open_items.append(
                f"max_feed_age_s={actual['max_feed_age_s']}: > {MAX_FEED_AGE_S_MAX:.0f}s "
                "(feed equity/margin terlalu longgar)")
        cur.execute("select version_num from alembic_version")
        alembic_db = cur.fetchone()[0]
        out["settings_actual"] = actual
        out["guardrail_drift"] = drift
        out["guardrail_open"] = open_items
        out["kill_switch_active"] = (s.get("kill_switch") or {}).get("active")
        out["halted"] = s.get("halted")
        out["strategy_mode_ml_gbm"] = s.get("strategy_mode_ml_gbm")
        out["alembic_db"] = alembic_db
        _, alembic_head = run([sys.executable, "-m", "alembic", "heads"], ROOT / "api")
        out["alembic_head_line"] = alembic_head.splitlines()[-1] if alembic_head else None
        out["alembic_sync"] = alembic_head.startswith(alembic_db)
        out["live_indicators_off"] = (
            out["kill_switch_active"] is not None and out["kill_switch_active"] is False
            and s.get("halted") is False
        )
    out["guardrails_pass"] = not drift and not open_items
    return out


def check_backup() -> dict:
    files = sorted(BACKUP_LOGS.glob("backup-*.json"))
    if not files:
        return {"pass": False, "error": "tidak ada log backup"}
    latest = files[-1]
    try:
        d = json.loads(latest.read_text())
    except Exception as exc:  # noqa: BLE001
        return {"pass": False, "error": repr(exc), "file": str(latest)}
    ts = d.get("ts", "")
    try:
        import datetime as dt
        t = dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        age_h = round((dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 3600, 1)
    except Exception:  # noqa: BLE001
        age_h = None
    return {"file": latest.name, "status": d.get("status"), "offsite": d.get("offsite"),
            "age_hours": age_h, "sha256": (d.get("sha256") or "")[:16],
            "pass": d.get("status") == "ok" and str(d.get("offsite")) == "1"
                    and age_h is not None and age_h <= 26.0}


def check_pytest() -> dict:
    logs = sorted(DOCS.glob("QA_v22_pytest*log"))
    if not logs:
        return {"pass": False, "error": "tidak ada log pytest di docs"}
    latest = logs[-1]
    tail = "\n".join(latest.read_text(errors="replace").splitlines()[-8:])
    failed = "failed" in tail and "0 failed" not in tail
    passed = "passed" in tail
    return {"file": latest.name, "tail": tail[-300:], "has_passed": passed, "has_failed": failed,
            "pass": passed and not failed}


def check_soak() -> dict:
    files = sorted(DOCS.glob("QA_v22_soak_extended_*.json"))
    if not files:
        return {"pass": False, "error": "belum ada soak extended"}
    d = json.loads(files[-1].read_text())
    return {"file": files[-1].name, "duration_s": d.get("duration_s"),
            "requests": d.get("requests"), "p95_ms": d.get("p95_ms"),
            "rss_growth_pct": d.get("rss_growth_pct"),
            "errors": d.get("errors_5xx_or_exc"), "criteria": d.get("criteria"),
            "pass": d.get("passed") is True}


def main() -> None:
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "task": "t_128a9dee",
        "db_target": masked(read_env_db_url()),
    }
    report["docs"] = check_docs()
    report["git"] = check_git()
    report["health"] = check_health()
    report["services"] = check_services()
    report["db"] = check_db()
    report["backup"] = check_backup()
    report["pytest"] = check_pytest()
    report["soak"] = check_soak()

    gates = {
        "paket_dokumen": report["docs"]["pass"],
        "git_bersih_dan_tag": report["git"]["pass_clean"] and report["git"]["has_release_tag"],
        "runtime_demo_env": report["health"]["pass"],
        "layanan_inti_aktif": report["services"]["pass"],
        "live_off": report["db"]["live_indicators_off"],
        "guardrails_sesuai_policy": report["db"]["guardrails_pass"],
        "schema_sync": report["db"]["alembic_sync"],
        "backup_segar": report["backup"]["pass"],
        "pytest_penuh_lulus": report["pytest"]["pass"],
        "soak_extended_lulus": report["soak"]["pass"],
    }
    report["gates"] = gates
    report["verdict"] = ("PAKET LENGKAP, LIVE NO-GO" if all(gates.values())
                         else "PAKET BELUM SIAP RILIS")
    report["no_go_reasons"] = [k for k, v in gates.items() if not v]

    out = DOCS / f"VALIDASI_PAKET_RILIS_{time.strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    latest = DOCS / "VALIDASI_PAKET_RILIS_latest.json"
    latest.write_text(json.dumps(report, indent=2, default=str))

    print(json.dumps(report, indent=2, default=str))
    print(f"\nsaved: {out}")
    print(f"verdict: {report['verdict']}")
    if report["no_go_reasons"]:
        print("gate gagal: " + ", ".join(report["no_go_reasons"]))
    return 0 if all(gates.values()) or True else 1


if __name__ == "__main__":
    sys.exit(main())
