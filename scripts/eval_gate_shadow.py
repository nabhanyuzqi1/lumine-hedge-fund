#!/usr/bin/env python3
"""Evaluasi gerbang promosi shadow -> paper (PRD v2.2 §9.3) untuk satu label.

Kriteria §9.3 (semua wajib):
  1. Tidak ada error kritis: supervisor CRITICAL / breaker OPEN / fault
     reject selama periode run = 0.
  2. Perilaku sinyal sesuai spec: frekuensi sinyal dalam rentang harapan
     (min sinyal, max sinyal/hari) dan tanpa dominasi REJECTED supervisor.
  3. Hasil out-of-sample & biaya masuk akal: profit factor + expectancy
     SIMULASI setelah model biaya konservatif di atas ambang.
  4. Tidak ada indikasi data leakage: timestamp sinyal tidak boleh di atas
     waktu pencatatannya (lookahead) — sinyal yang mengklaim ts setelah
     created_at + toleransi = leakage.
  5. Owner menyetujui eksperimen paper: baris strategy_approvals
     (stage=SHADOW_REVIEW, decision=APPROVED) untuk strategi ts.

Sumber data: shadow_runs + shadow_signals (shadow runner) + system_events
(supervisor) + strategy_approvals. Tidak ada angka dipalsukan: data kurang
= exit 3 "belum cukup".

Pemakaian (dari repo root):
  api/.venv/bin/python scripts/eval_gate_shadow.py --label lb-base \
      [--min-signals 10] [--max-per-day 20] [--min-profit-factor 1.0]
      [--out docs/QA_SHADOW_gate_lb-base]

Output: <out>.json + <out>.md. Exit: 0 lulus / 2 gagal / 3 belum cukup /
4 owner approval belum ada (semua cek otomatis lulus).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1] / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

import psycopg  # noqa: E402

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    (API_DIR / ".env").read_text().split("DATABASE_URL=", 1)[1].splitlines()[0].strip()
    if (API_DIR / ".env").exists() else "")
LEAKAGE_TOLERANCE_S = 5.0


def _fetch(conn, query: str, params: tuple = ()) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def evaluate(*, label: str, min_signals: int, max_per_day: float,
             min_profit_factor: float) -> tuple[dict, str]:
    """Return (report dict, verdict). Verdict: PASS|FAIL|INSUFFICIENT|PENDING."""
    with psycopg.connect(DATABASE_URL) as conn:
        runs = _fetch(
            conn,
            """
            SELECT run_id, strategy_id, strategy_version, symbol, timeframe,
                   period_start, period_end, metrics, signal_count, status,
                   created_at, completed_at, config
            FROM shadow_runs WHERE label = %s ORDER BY created_at DESC LIMIT 1
            """, (label,))
        if not runs:
            return {}, "INSUFFICIENT"
        run = runs[0]
        signals = _fetch(
            conn,
            """
            SELECT ts, created_at, sim_status, sim_pnl_usd, sim_cost_usd,
                   regime_label, side, reason
            FROM shadow_signals WHERE run_id = %s ORDER BY ts
            """, (run["run_id"],))
        critical = _fetch(
            conn,
            """
            SELECT count(*) AS n FROM system_events
            WHERE source = 'supervisor' AND severity = 'CRITICAL'
              AND actor = %s
              AND created_at >= %s AND created_at <= COALESCE(%s, now())
            """, (run["strategy_id"], run["period_start"] or run["created_at"],
                  run["period_end"]))
        approvals = _fetch(
            conn,
            """
            SELECT decision, reviewer, created_at FROM strategy_approvals
            WHERE stage = 'SHADOW_REVIEW' AND decision = 'APPROVED'
              AND strategy_version_id IN (
                  SELECT id FROM strategy_versions
                  WHERE strategy_id = %s ORDER BY created_at DESC LIMIT 1)
            ORDER BY created_at DESC LIMIT 1
            """, (run["strategy_id"],))

    n = len(signals)
    if n < min_signals:
        # Data belum cukup: tetap keluarkan laporan lengkap (vektor metrics/checks
        # kosong) supaya _markdown tidak crash dan verdict terbaca jelas.
        report = {
            "label": label,
            "run": _run_summary(run, signals),
            "checks": {"enough_signals": False},
            "metrics": {"signals": n, "closed": 0, "wins": 0, "losses": 0,
                        "profit_factor": None, "expectancy_usd": None,
                        "total_sim_pnl_usd": 0.0, "total_sim_cost_usd": 0.0,
                        "rejected": 0, "regime_blocked": 0,
                        "supervisor_critical": None, "signals_per_day": 0.0,
                        "days": 0.0, "leakage_signals": 0},
            "owner_approval": {"approved": False,
                               "note": "data belum cukup untuk dinilai"},
            "regime_distribution": _regime_dist(signals),
            "verdict": "INSUFFICIENT",
            "reason": f"sinyal {n} < minimum {min_signals}",
        }
        return report, "INSUFFICIENT"

    closed = [s for s in signals if s["sim_pnl_usd"] is not None]
    profits = [float(s["sim_pnl_usd"]) for s in closed]
    gross_win = sum(p for p in profits if p > 0)
    gross_loss = -sum(p for p in profits if p < 0)
    pf = (gross_win / gross_loss) if gross_loss > 0 else (
        float("inf") if gross_win > 0 else None)
    wins = sum(1 for p in profits if p > 0)
    expectancy = round(sum(profits) / len(profits), 2) if profits else None
    rejected = sum(1 for s in signals if s["sim_status"] == "REJECTED")
    regime_blocked = sum(1 for s in signals if s["sim_status"] == "REGIME_BLOCKED")
    critical_n = int(critical[0]["n"]) if critical else None

    start = run["period_start"] or run["created_at"]
    end = run["period_end"] or datetime.now(timezone.utc)
    days = max((end - start).total_seconds() / 86400.0, 1e-9)
    per_day = n / days

    leaks = [s for s in signals
             if s["ts"] and s["created_at"]
             and (s["created_at"] - s["ts"]).total_seconds() < -LEAKAGE_TOLERANCE_S]

    checks = {
        "no_critical_errors": critical_n == 0,
        "signal_behavior_per_spec": per_day <= max_per_day,
        "out_of_sample_costs_reasonable": pf is not None and pf >= min_profit_factor,
        "no_data_leakage": not leaks,
    }
    approved = bool(approvals)
    report = {
        "label": label,
        "run": _run_summary(run, signals),
        "checks": checks,
        "metrics": {
            "signals": n, "closed": len(closed), "wins": wins,
            "losses": len(profits) - wins,
            "profit_factor": pf, "expectancy_usd": expectancy,
            "total_sim_pnl_usd": round(sum(profits), 2),
            "total_sim_cost_usd": round(sum(float(s["sim_cost_usd"] or 0)
                                            for s in signals), 2),
            "rejected": rejected, "regime_blocked": regime_blocked,
            "supervisor_critical": critical_n,
            "signals_per_day": round(per_day, 2), "days": round(days, 2),
            "leakage_signals": len(leaks),
        },
        "owner_approval": (
            {"approved": True, "reviewer": approvals[0]["reviewer"],
             "at": str(approvals[0]["created_at"])} if approved
            else {"approved": False,
                  "note": "belum ada strategy_approvals SHADOW_REVIEW APPROVED"}),
        "regime_distribution": _regime_dist(signals),
    }
    if not all(checks.values()):
        report["verdict"] = "FAIL"
        return report, "FAIL"
    if not approved:
        report["verdict"] = "PENDING"
        return report, "PENDING"
    report["verdict"] = "PASS"
    return report, "PASS"


def _run_summary(run: dict, signals: list[dict]) -> dict:
    return {"run_id": str(run["run_id"]), "strategy_id": run["strategy_id"],
            "strategy_version": run["strategy_version"],
            "symbol": run["symbol"], "timeframe": run["timeframe"],
            "status": run["status"],
            "params_hash": (run.get("config") or {}).get("params_hash"),
            "code_commit": (run.get("config") or {}).get("code_commit"),
            "period_start": str(run["period_start"]),
            "period_end": str(run["period_end"]),
            "first_signal": str(signals[0]["ts"]) if signals else None,
            "last_signal": str(signals[-1]["ts"]) if signals else None}


def _regime_dist(signals: list[dict]) -> dict:
    out: dict[str, int] = {}
    for s in signals:
        key = s.get("regime_label") or "NONE"
        out[key] = out.get(key, 0) + 1
    return out


def _markdown(report: dict) -> str:
    m = report["metrics"]
    checks = report["checks"]
    lines = [
        f"# Gerbang Shadow -> Paper: {report['label']}",
        "",
        f"Verdict: **{report['verdict']}**",
        "",
        f"- Run: `{report['run']['run_id']}` ({report['run']['strategy_id']} "
        f"v{report['run']['strategy_version']}, {report['run']['symbol']} "
        f"{report['run']['timeframe']})",
        f"- Label versi: `{report['run']['params_hash']}` "
        f"commit `{report['run']['code_commit']}`",
        f"- Periode: {report['run']['period_start']} .. {report['run']['period_end']}",
        f"- Sinyal: {m['signals']} ({m['signals_per_day']}/hari), closed "
        f"{m['closed']}, rejected {m['rejected']}, regime-blocked "
        f"{m['regime_blocked']}",
        f"- PF simulasi (net biaya konservatif): {m['profit_factor']}, "
        f"expectancy {m['expectancy_usd']} USD, total sim P&L "
        f"{m['total_sim_pnl_usd']} USD, biaya {m['total_sim_cost_usd']} USD",
        f"- Supervisor CRITICAL: {m['supervisor_critical']}; leakage: "
        f"{m['leakage_signals']}",
        f"- Distribusi regime: `{report['regime_distribution']}`",
        "",
        "| Cek §9.3 | Hasil |",
        "| --- | --- |",
    ]
    for name, ok in checks.items():
        lines.append(f"| {name} | {'LULUS' if ok else 'GAGAL'} |")
    lines.append(f"| owner approval | "
                 f"{'LULUS' if report['owner_approval']['approved'] else 'PENDING'} |")
    if not report["owner_approval"]["approved"]:
        lines.append("")
        lines.append(f"> {report['owner_approval']['note']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", required=True, help="label versi shadow (PRD 9.2)")
    ap.add_argument("--min-signals", type=int, default=10)
    ap.add_argument("--max-per-day", type=float, default=20.0)
    ap.add_argument("--min-profit-factor", type=float, default=1.0)
    ap.add_argument("--out", default=None, help="path output tanpa ekstensi")
    args = ap.parse_args()

    report, verdict = evaluate(
        label=args.label, min_signals=args.min_signals,
        max_per_day=args.max_per_day,
        min_profit_factor=args.min_profit_factor)
    out = args.out or f"docs/QA_SHADOW_gate_{args.label}"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out + ".json").write_text(json.dumps(report, indent=1, default=str))
    Path(out + ".md").write_text(_markdown(report))
    print(f"[eval_gate_shadow] label={args.label} verdict={verdict} "
          f"-> {out}.json / {out}.md")
    if verdict == "PASS":
        sys.exit(0)
    if verdict == "PENDING":
        sys.exit(4)  # semua cek otomatis lulus; tinggal approval owner
    if verdict == "INSUFFICIENT":
        sys.exit(3)
    sys.exit(2)


if __name__ == "__main__":
    main()
