#!/usr/bin/env python3
"""check_guardrail_runtime.py - pengawas harian drift guardrail runtime.

Kartu t_097ef2bb (tindak lanjut §8 `docs/BUKTI_GUARDRAIL_PARITY_t_bf4b85f9.md`).
Dijalankan `fund2-guardrail-watch.timer` (systemd user, harian). Tugasnya SATU:
menjalankan gate guardrail yang sudah ada, `check_db()` dari
`scripts/validate_release_packet.py` (koneksi `read_only = True`), lalu:

  * menulis hasil ke `~/fund2-backups/logs/guardrail-<YYYY-MM-DD>.json`
    (tren harian bisa diaudit),
  * mengirim SATU alert Telegram ke owner lewat jalur yang sudah dipakai
    (`app.alerts` / `app.telegram_bot.notify_owner`) bila `guardrail_drift`
    atau `guardrail_open` tidak kosong,
  * keluar dengan exit code != 0 saat drift/open terdeteksi (0 = bersih,
    2 = drift/open, 1 = gate tidak bisa dijalankan).

READ-ONLY terhadap `settings`: skrip ini tidak pernah menulis, tidak pernah
"memperbaiki" nilai. Perubahan guardrail hanya lewat kanal §I.3
(`PUT /admin/risk-settings` atau `PUT /kill-switch/triggers`, sesi 2FA).

Pemakaian:
    cd ~/fund2
    api/.venv/bin/python scripts/check_guardrail_runtime.py            # live
    api/.venv/bin/python scripts/check_guardrail_runtime.py --no-alert # tanpa kirim
    api/.venv/bin/python scripts/check_guardrail_runtime.py \
        --db-url postgresql://.../fund2_test_x --label DRILL           # uji drift

`TELEGRAM_ALERTS_OFF=1` (dibaca `notify_owner`) tetap mematikan pengiriman;
dipakai saat uji supaya owner tidak dibanjiri pesan.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
API_DIR = ROOT / "api"
SCRIPTS_DIR = ROOT / "scripts"
DEFAULT_OUT_DIR = pathlib.Path.home() / "fund2-backups" / "logs"

# Rujukan policy (satu sumber kebenaran, jangan ulangi angka di sini).
KEPUTUSAN_REF = "KEPUTUSAN_OWNER.md §I.1 (angka final) + §I.4 (paritas dev/staging)"

# ID guardrail per key, hanya untuk label pada pesan alert (§I.1).
KEY_ID = {
    "max_volume": "A3",
    "max_orders_per_min": "A8",
    "daily_drawdown_pct": "A6 auto-halt",
    "max_daily_drawdown": "A6 absolut",
    "total_drawdown_pct": "A7",
    "consecutive_failed_orders": "desain runbook",
    "ea_offline_seconds": "A12",
    "ea_offline_halt_seconds": "lampiran v2.1 §5.7",
    "max_tick_age_s": "A10",
    "max_total_volume_lot": "A4",
    "max_risk_per_trade_pct": "A5",
    "max_spread": "A9",
    "max_feed_age_s": "bukan A10",
    "daily_start_balance": "dasar A6 absolut",
}

# Exit code.
RC_OK = 0
RC_ERROR = 1
RC_DRIFT = 2


def _ensure_imports() -> None:
    """Buat `scripts/` dan `api/` bisa diimpor dari cwd mana pun."""
    for p in (str(SCRIPTS_DIR), str(API_DIR)):
        if p not in sys.path:
            sys.path.insert(0, p)


_ensure_imports()

import validate_release_packet as vrp  # noqa: E402  (gate tunggal, tidak diduplikasi)
from app.alerts import _md_escape  # noqa: E402  (escape Markdown Telegram)
from app.telegram_bot import notify_owner  # noqa: E402


# ------------------------------------------------------------------ formatting

def fmt_val(value) -> str:
    """Angka untuk pesan: 0.1 -> '0.1', 6.0 -> '6', 292.02 -> '292.02'."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return f"{float(value):g}"
    if value is None:
        return "tidak ada"
    return str(value)


def masked_db(url: str) -> str:
    """Nama database + host:port tanpa kredensial (aman masuk log/alert)."""
    try:
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        name = (parts.path or "/").lstrip("/") or "?"
        return f"{name}@{parts.hostname or '?'}:{parts.port or '?'}"
    except Exception:  # noqa: BLE001 - label saja, jangan gagalkan gate
        return "?"


def build_alert_message(report: dict, *, db_label: str, now: datetime,
                        label: str | None = None) -> str:
    """Teks alert Markdown Telegram untuk drift/open.

    Semua teks dinamis lewat `_md_escape` dan DI LUAR backtick: underscore di
    nama key (mis. `ea_offline_seconds`) membuat parser Markdown Telegram
    menolak pesan dengan 400 "can't parse entities" (pelajaran 23 Nov 2026).
    """
    drift = report.get("guardrail_drift") or []
    open_items = report.get("guardrail_open") or []
    lines: list[str] = []

    head = "GUARDRAIL DRIFT (runtime tidak sama dengan §I)"
    if label:
        head = f"{label} - {head}"
    lines.append(f"🚨 {_md_escape(head)}")
    lines.append("")
    lines.append(f"Sumber kebenaran: {_md_escape(KEPUTUSAN_REF)}")
    lines.append(f"Cek: {now.strftime('%Y-%m-%dT%H:%M:%SZ')} | DB: {_md_escape(db_label)}")

    if drift:
        lines.append("")
        lines.append(f"Nilai menyimpang ({len(drift)}):")
        for i, item in enumerate(drift, 1):
            key = item.get("key")
            gid = KEY_ID.get(key)
            suffix = f" ({gid})" if gid else ""
            lines.append(
                f"{i}. {_md_escape(key)}: aktif {_md_escape(fmt_val(item.get('actual')))}, "
                f"§I {_md_escape(fmt_val(item.get('expected')))}{_md_escape(suffix)}")

    if open_items:
        lines.append("")
        lines.append(f"Perlu ditinjau (open, bukan pelonggaran) ({len(open_items)}):")
        for i, item in enumerate(open_items, 1):
            lines.append(f"{i}. {_md_escape(item)}")

    lines.append("")
    lines.append("Perbaikan hanya lewat kanal §I.3: PUT /admin/risk-settings "
                 "(guardrail inti) atau PUT /kill-switch/triggers (auto-trigger), "
                 "sesi 2FA. psql langsung bukan kanal sah.")
    return "\n".join(lines)


def build_error_message(error: str, *, db_label: str, now: datetime,
                        label: str | None = None) -> str:
    head = "GUARDRAIL WATCH GAGAL DIJALANKAN"
    if label:
        head = f"{label} - {head}"
    return "\n".join([
        f"⚠️ {_md_escape(head)}",
        "",
        f"Cek: {now.strftime('%Y-%m-%dT%H:%M:%SZ')} | DB: {_md_escape(db_label)}",
        f"Error: {_md_escape(error)}",
        f"Rujukan: {_md_escape(KEPUTUSAN_REF)}",
        "Gate tidak berjalan = drift tidak terpantau. Periksa "
        "`journalctl --user -u fund2-guardrail-watch.service`.",
    ])


# --------------------------------------------------------------------- payload

def build_log(report: dict | None, *, db_label: str, now: datetime,
              label: str | None, alert: dict, error: str | None,
              rc: int) -> dict:
    """Payload log JSON harian (audit tren)."""
    report = report or {}
    return {
        "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ts_wib": now.astimezone().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "date": now.strftime("%Y-%m-%d"),
        "mode": "drill" if label else "live",
        "label": label,
        "db": db_label,
        "gate": "scripts/validate_release_packet.py:check_db",
        "keputusan_ref": KEPUTUSAN_REF,
        "ok": bool(report.get("guardrails_pass")) and not error,
        "exit_code": rc,
        "error": error,
        "drift_count": len(report.get("guardrail_drift") or []),
        "open_count": len(report.get("guardrail_open") or []),
        "guardrail_drift": report.get("guardrail_drift") or [],
        "guardrail_open": report.get("guardrail_open") or [],
        "settings_actual": report.get("settings_actual") or {},
        "kill_switch_active": report.get("kill_switch_active"),
        "halted": report.get("halted"),
        "alert": alert,
    }


def write_log(payload: dict, out_dir: pathlib.Path) -> pathlib.Path:
    """Tulis `guardrail-<YYYY-MM-DD>.json` atomik (tmp + replace)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"guardrail-{payload['date']}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    return path


# ------------------------------------------------------------------------ main

def run(db_url: str | None, *, alert_enabled: bool, label: str | None,
        out_dir: pathlib.Path) -> int:
    if db_url:
        os.environ["DATABASE_URL"] = db_url
    # Backstop anti-hang: connect + statement timeout libpq/Postgres.
    os.environ.setdefault("PGCONNECT_TIMEOUT", "10")
    os.environ.setdefault("PGOPTIONS", "-c statement_timeout=60000")

    url = vrp.read_env_db_url()
    db_label = masked_db(url)
    now = datetime.now(timezone.utc)
    alert: dict = {"attempted": False, "sent": False, "error": None}

    try:
        report = vrp.check_db()
        error = None
    except Exception as exc:  # noqa: BLE001 - semua kegagalan gate jadi alert
        report = None
        error = f"{type(exc).__name__}: {exc}"

    ok = bool(report and report.get("guardrails_pass")) and not error
    rc = RC_OK if ok else (RC_ERROR if error else RC_DRIFT)
    message = (build_error_message(error, db_label=db_label, now=now, label=label)
               if error else
               build_alert_message(report or {}, db_label=db_label, now=now, label=label))

    if not ok and alert_enabled:
        alert["attempted"] = True
        try:
            sent = asyncio.run(notify_owner(message))
            alert["sent"] = bool(sent)
        except Exception as exc:  # noqa: BLE001 - alert gagal tidak boleh hapus log
            alert["error"] = f"{type(exc).__name__}: {exc}"

    payload = build_log(report, db_label=db_label, now=now, label=label,
                        alert=alert, error=error, rc=rc)
    path = write_log(payload, out_dir)

    status = "OK (sesuai §I)" if ok else ("ERROR" if error else "DRIFT")
    print(f"{payload['ts']} guardrail_watch status={status} rc={rc} "
          f"drift={payload['drift_count']} open={payload['open_count']} "
          f"alert_sent={alert['sent']} log={path}")
    if not ok:
        print(message)
    return rc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pengawas harian drift guardrail §I")
    ap.add_argument("--db-url", default=None,
                    help="override DATABASE_URL (uji drift di DB test, bukan live)")
    ap.add_argument("--no-alert", action="store_true",
                    help="jangan kirim alert Telegram (log tetap ditulis)")
    ap.add_argument("--label", default=None,
                    help="penanda pesan, mis. DRILL (untuk uji di DB test)")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR),
                    help=f"direktori log JSON (default {DEFAULT_OUT_DIR})")
    ap.add_argument("--print-message", action="store_true",
                    help="cetak pesan alert walau gate bersih (debug format)")
    args = ap.parse_args(argv)
    rc = run(args.db_url, alert_enabled=not args.no_alert, label=args.label,
             out_dir=pathlib.Path(args.out_dir))
    return rc


if __name__ == "__main__":
    sys.exit(main())
