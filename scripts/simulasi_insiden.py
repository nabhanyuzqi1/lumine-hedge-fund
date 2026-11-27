#!/usr/bin/env python3
"""Simulasi insiden Fund2 — drill playbook (kartu t_f2v22a17, PRD §26/§27).

Mengikuti aturan isolasi conftest (api/tests/conftest.py):
- Hanya DB `fund2_test_*` (throwaway per-run, di-drop di akhir).
- Tanpa kredensial Telegram produksi (TELEGRAM_ALERTS_OFF=1).
- Tidak menyentuh DB live (:5433 fund2), tidak ada order ke broker.

Skenario: posisi ditutup broker tanpa CLOSE order (mismatch/orphan, T2 di
ROLLBACK_PLAN) → auto GLOBAL_HALT → snapshot → verifikasi rollback artifact
(backup manifest + restore drill) → reconcile → owner approve resume (2FA +
checklist) → incident report.

Pemakaian:
    ~/fund2/api/.venv/bin/python ~/fund2/scripts/simulasi_insiden.py

Output:
    docs/SIMULASI_INSIDEN_<ts>.md              (incident report drill)
    docs/simulasi_insiden_evidence_<ts>.json   (bukti tiap langkah)
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

FUND2_HOME = pathlib.Path("/home/tekka/fund2")
API_DIR = FUND2_HOME / "api"
DOCS = FUND2_HOME / "docs"
BACKUP_ROOT = pathlib.Path("/home/tekka/fund2-backups")
sys.path.insert(0, str(API_DIR))

TS = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
STAMP = datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_env_file(path: pathlib.Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _with_db(url: str, dbname: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, f"/{dbname}", p.query, p.fragment))


FILE_URL = (_load_env_file(API_DIR / ".env").get("DATABASE_URL") or "").strip()
if not FILE_URL:
    raise SystemExit("DATABASE_URL tidak ditemukan di api/.env")
DBNAME = f"fund2_test_sim_{TS}_{os.getpid()}"
URL = _with_db(_with_db(FILE_URL, "fund2_test"), DBNAME)

# Isolasi harus terpasang SEBELUM import app (config membaca env saat import).
os.environ["DATABASE_URL"] = URL
os.environ["TELEGRAM_ALERTS_OFF"] = "1"
os.environ.pop("TELEGRAM_BOT_TOKEN", None)
os.environ.pop("TELEGRAM_OWNER_ID", None)

import psycopg  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app import config, db  # noqa: E402
from app.auth import hash_password  # noqa: E402

config.DATABASE_URL = URL

STEPS: list[dict] = []


def step(n: str, name: str, ok: bool, detail: dict | str) -> None:
    STEPS.append({"step": n, "name": name, "status": "PASS" if ok else "FAIL",
                  "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {n} {name}")


async def main() -> int:
    # --- DB throwaway ------------------------------------------------------
    with psycopg.connect(_with_db(URL, "postgres"), autocommit=True) as c:
        c.execute(f'CREATE DATABASE "{DBNAME}"')
    await db.init_pool()
    await db.apply_schema()
    await db.seed_defaults()

    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'admin') "
            "RETURNING id",
            ("owner_sim", hash_password("sim-pass")),
        )

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://sim") as c:
        # --- Langkah 0: login admin ----------------------------------------
        r = await c.post("/auth/login", json={"username": "owner_sim", "password": "sim-pass"})
        assert r.status_code == 200, r.text
        csrf = r.json()["csrf_token"]
        c.headers["x-csrf-token"] = csrf
        step("0", "login admin (sesi + CSRF)", r.status_code == 200,
             {"http": r.status_code})

        # --- Langkah 1: trigger T2 — posisi ditutup tanpa CLOSE order -------
        bridge_token = (await db.get_settings())["bridge_token"]
        bh = {"Authorization": f"Bearer {bridge_token}"}
        r1 = await c.post("/bridge/positions", json={"positions": [
            {"ticket": 9001, "symbol": "XAUUSD", "side": "BUY", "volume": 0.01,
             "open_price": 2000.0, "profit": 1.5}]}, headers=bh)
        r2 = await c.post("/bridge/positions", json={"positions": []}, headers=bh)
        closed = r2.json().get("closed")
        from app import kill_switch
        state = await kill_switch.get_state()
        ok1 = r1.status_code == 200 and closed == [9001] and \
            state["active"] and state["mode"] == "GLOBAL_HALT" and \
            state["source"] == "auto:position_mismatch"
        step("1", "trigger T2 mismatch -> auto GLOBAL_HALT", ok1,
             {"closed": closed, "mode": state["mode"], "source": state["source"],
              "reason": state["reason"]})

        # --- Langkah 2: snapshot DB (audit) ---------------------------------
        async with db.pool().connection() as conn:
            pos = await conn.execute(
                "SELECT ticket, symbol, side, volume, status, raw FROM positions")
            pos_rows = [dict(r) for r in (await pos.fetchall())]
            ev = await conn.execute(
                "SELECT action, mode, source, actor, reason, created_at "
                "FROM kill_switch_events ORDER BY id DESC LIMIT 5")
            ev_rows = [str(dict(r)) for r in (await ev.fetchall())]
            orphans = await conn.execute(
                "SELECT count(*) AS n FROM positions WHERE status='OPEN'")
            open_n = (await orphans.fetchone())["n"]
        snap = {"positions": pos_rows, "kill_switch_events": ev_rows,
                "open_positions": open_n, "kill_switch_state": state}
        step("2", "snapshot DB (posisi + kill_switch_events)", open_n == 0 and state["active"],
             {"open_positions": open_n, "events": len(ev_rows)})

        # --- Langkah 3: verifikasi rollback artifact ------------------------
        verify = subprocess.run(
            [str(FUND2_HOME / "scripts" / "fund2_backup.sh"), "--verify-only"],
            capture_output=True, text=True, timeout=180)
        drills = sorted(BACKUP_ROOT.glob("drill/*/restore-drill-*.md"),
                        key=lambda p: p.stat().st_mtime)
        latest_drill = str(drills[-1]) if drills else None
        ok3 = verify.returncode == 0 and latest_drill is not None
        step("3", "rollback artifact: manifest backup sha256 + restore drill terakhir", ok3,
             {"verify_rc": verify.returncode, "verify_tail": verify.stdout.strip().splitlines()[-3:],
              "latest_restore_drill": latest_drill})

        # --- Langkah 4: reconcile (integritas ledger) -----------------------
        async with db.pool().connection() as conn:
            orphan_orders = await conn.execute(
                """SELECT count(*) AS n FROM orders o WHERE NOT EXISTS
                   (SELECT 1 FROM order_events e WHERE e.order_id = o.id)""")
            orphan_n = (await orphan_orders.fetchone())["n"]
            trig = await conn.execute(
                "SELECT tgname FROM pg_trigger WHERE tgname LIKE '%order_events%'")
            trig_n = len((await trig.fetchall()))
        ok4 = orphan_n == 0 and trig_n >= 1
        step("4", "reconcile: 0 order tanpa event + trigger append-only aktif", ok4,
             {"orders_without_events": orphan_n, "append_only_triggers": trig_n})

        # --- Langkah 5: owner approve resume (2FA + checklist) --------------
        from app import totp
        secret = (await c.post("/auth/2fa/setup")).json()["secret"]
        await c.post("/auth/2fa/enable", json={"code": totp.totp_at(secret)})
        rc = await c.post("/auth/2fa/challenge",
                          json={"code": totp.totp_at(secret, time.time() + 30)})
        rel = await c.post("/kill-switch/release", json={"checklist_ack": True})
        state2 = await kill_switch.get_state()
        ok5 = rc.status_code == 200 and rel.status_code == 200 and \
            state2["active"] is False
        step("5", "owner approve resume: 2FA challenge + checklist_ack -> release", ok5,
             {"challenge_http": rc.status_code, "release_http": rel.status_code,
              "active_after": state2["active"], "mode_after": state2["mode"]})

    # --- Tutup pool + drop DB ----------------------------------------------
    await db.close_pool()
    with psycopg.connect(_with_db(URL, "postgres"), autocommit=True) as c:
        c.execute(f'DROP DATABASE "{DBNAME}" WITH (FORCE)')

    # --- Evidence + incident report ----------------------------------------
    passed = all(s["status"] == "PASS" for s in STEPS)
    evidence = {"simulasi": "orphan-position-mismatch -> halt -> snapshot -> "
                            "artifact -> reconcile -> resume (t_f2v22a17)",
                "ts": STAMP, "db": DBNAME, "steps": STEPS, "verdict": "LULUS" if passed else "GAGAL"}
    DOCS.mkdir(exist_ok=True)
    ev_path = DOCS / f"simulasi_insiden_evidence_{TS}.json"
    ev_path.write_text(json.dumps(evidence, indent=2, default=str))

    report = f"""# Simulasi Insiden — Drill Incident Playbook (t_f2v22a17)

Tanggal: {STAMP} · Skenario: T2 mismatch posisi (orphan close) · Verdict: **{"LULUS" if passed else "GAGAL"}**

Lingkungan: DB test terisolasi `{DBNAME}` (drop setelah drill), Telegram dimatikan,
tanpa koneksi broker. Jalur kode yang dipakai = jalur produksi (`app.kill_switch`,
`app.bridge`, auth + 2FA, endpoint HTTP asli via ASGITransport).

## Ringkasan langkah

| # | Langkah playbook | Status | Bukti ringkas |
| --- | --- | --- | --- |
"""
    brief = {
        "0": "login admin, sesi + CSRF",
        "1": "orphan close -> auto GLOBAL_HALT (auto:position_mismatch)",
        "2": "snapshot posisi + kill_switch_events",
        "3": "manifest backup sha256 valid + restore drill terakhir ada",
        "4": "0 order tanpa event, trigger append-only aktif",
        "5": "2FA challenge + checklist_ack -> release, halt lepas",
    }
    for s in STEPS:
        d = s["detail"]
        d = json.dumps(d, default=str) if not isinstance(d, str) else d
        report += f"| {s['step']} | {brief.get(s['step'], s['name'])} | {s['status']} | `{d[:120]}` |\n"

    report += f"""
## Field incident report (template §3 playbook)

| Field | Isi |
| --- | --- |
| Severity | SEV-1 (drill) — mismatch posisi/orphan |
| Waktu mulai / selesai | {STAMP} / {datetime.now(timezone.utc).isoformat(timespec="seconds")} |
| Terdeteksi oleh | auto:position_mismatch (reconciler snapshot bridge) |
| Dampak posisi & order | 1 posisi uji XAUUSD 0.01 ditutup broker tanpa CLOSE order; tidak ada order baru |
| Timeline | trigger (langkah 1) -> snapshot (2) -> artifact (3) -> reconcile (4) -> resume (5) |
| Penyebab langsung | snapshot broker kehilangan ticket 9001 tanpa deal penutup tercatat |
| Akar masalah | (drill) skenario disuntik manual; di produksi: koneksi EA putus saat close |
| Tindakan otomatis | GLOBAL_HALT source auto:position_mismatch (idempotent, ter-audit) |
| Tindakan manual | snapshot, verifikasi artifact, verifikasi integritas ledger |
| Keputusan owner | resume disetujui (simulasi: 2FA + checklist_ack, 7 butir RECOVERY_CHECKLIST) |
| Bukti ledger | `{ev_path.name}` (positions, kill_switch_events, trigger append-only) |
| Bukti broker | snapshot `/bridge/positions` di langkah 1-2 (drill) |
| Corrective action | drill terjadwal rutin sebelum canary (ROLLBACK_PLAN §4) |
| Preventive action | pertahankan auto-trigger position_mismatch + alert SEV-1 |
| Status | CLOSED (drill) |

## Catatan

- Pengujian ini membuktikan jalur **playbook**, bukan performa broker live.
- Restore drill backup: lihat `DR_v2.2.md` (3x LULUS, 23 Nov) dan path di langkah 3.
"""
    rep_path = DOCS / f"SIMULASI_INSIDEN_{TS}.md"
    rep_path.write_text(report)

    print(f"\nVerdict: {'LULUS' if passed else 'GAGAL'}")
    print(f"Evidence: {ev_path}\nReport:   {rep_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
