"""Self-improvement loop mingguan (PRD v2.1 §5.9 & P4).

Siklus: analisa event log + hasil -> usulan perbaikan -> backtest otomatis
(bounded, tercatat di backtest_runs) -> laporan owner via Telegram ->
keputusan owner -> deploy (flag enabled, hanya lewat approve owner).

Garis merah PRD §5.9 (di-enforce di modul ini):
- Cron/agent TIDAK punya kredensial endpoint order dan TIDAK mengubah
  parameter risiko; yang diusulkan hanya parameter strategi.
- Deploy = commit ke repo + flag `enabled` yang hanya bisa diubah owner:
  keputusan owner dicatat append-only di strategy_approvals, perubahan
  settings ter-audit otomatis (trigger settings_audit b002), dan
  deployment dicatat di deployment_records.

Usulan per minggu: docs/selfimprove_proposals.json (di-commit ke repo).
Pemakaian:
  cd api && .venv/bin/python -m app.self_improve run      # siklus penuh
  .venv/bin/python -m app.self_improve status             # baca state
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import db
from .selfimprove_analysis import (
    evaluate_criteria,
    collect_analysis,
    render_report,
    split_telegram,
)
from .telegram_bot import notify_owner

BASE = Path(__file__).resolve().parent.parent
PROPOSALS_FILE = BASE.parent / "docs" / "selfimprove_proposals.json"
OUT_DIR = BASE.parent / "docs" / "selfimprove"


def iso_week_now() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"


def load_proposals(path: Path | None = None) -> list[dict]:
    source = path or PROPOSALS_FILE
    if not source.exists():
        return []
    return json.loads(source.read_text())


async def _ensure_pool() -> None:
    try:
        db.pool()
    except RuntimeError:
        await db.init_pool()


async def _candles(symbol: str, tf: str) -> tuple[list[dict], dict]:
    from paper.backtest import to_utc_candles
    from paper.runner import db_timezone_offset_h

    await _ensure_pool()
    async with db.pool().connection() as conn:
        db_tz = await db_timezone_offset_h(conn)
        async with conn.transaction():
            cur = await conn.execute(
                "SELECT min(ts) AS mn, max(ts) AS mx, count(*) AS n FROM candles "
                "WHERE symbol = %s AND timeframe = %s", (symbol, tf.upper()))
            stats = await cur.fetchone()
            cur = await conn.execute(
                "SELECT ts, open, high, low, close FROM candles "
                "WHERE symbol = %s AND timeframe = %s ORDER BY ts ASC",
                (symbol, tf.upper()))
            rows = await cur.fetchall()
    if not stats or stats["n"] == 0:
        raise RuntimeError(f"tidak ada candle {symbol} {tf} di DB")
    candles = to_utc_candles(rows, db_tz)
    meta = {"start": stats["mn"], "end": stats["mx"], "bars": stats["n"]}
    return candles, meta


# ---------------------------------------------------------------- backtest


def _attach_report_evidence(proposal: dict) -> dict:
    """Pakai report walk-forward yang sudah ada (JSON) sebagai bukti."""
    spec = proposal["backtest"]
    path = BASE.parent / spec["path"]
    data = json.loads(path.read_text())
    report = data[spec["side"]] if "side" in spec else data
    baseline = data.get(spec["baseline_side"]) if spec.get("baseline_side") else None
    return {"report": report, "baseline": baseline, "run_ids": [report["run_id"]],
            "source": f"existing:{spec['path']}"}


async def _run_fresh_backtest(proposal: dict) -> dict:
    """Jalankan walk-forward bounded untuk proposal (tercatat di backtest_runs)."""
    from paper import walkforward as wf
    from paper.dukascopy import build_dukascopy_cost_model

    spec = proposal["backtest"]
    symbol = proposal["change"]["symbol"]
    tf = proposal["change"]["tf"]
    strategy_id = proposal["change"]["strategy_id"]
    candles, meta = await _candles(symbol, tf)
    windows = wf.plan_windows(meta["start"], meta["end"],
                              train_months=spec.get("train_months", 6),
                              test_months=spec.get("test_months", 1),
                              step_months=spec.get("step_months", 1))
    last_n = spec.get("last_n_windows") or len(windows)
    windows = windows[-last_n:] if last_n < len(windows) else windows
    if not windows:
        raise RuntimeError("data terlalu pendek untuk window walk-forward")

    grid = dict(wf.PARAM_GRIDS.get(strategy_id, {}))
    grid.update(spec.get("grid") or {})
    strategy = wf.STRATEGIES[strategy_id]

    await _ensure_pool()
    async with db.pool().connection() as conn:
        cost_model = await build_dukascopy_cost_model(conn)
        report = wf.run_walkforward(
            candles, tf=tf, symbol=symbol, windows=windows, equity0=10000.0,
            cost_model=cost_model, strategy=strategy, data_end=meta["end"])
        report["config"]["train_months"] = spec.get("train_months", 6)
        report["config"]["test_months"] = spec.get("test_months", 1)
        report["config"]["grid"] = grid
        report["data"] = {"start": meta["start"].isoformat(),
                          "end": meta["end"].isoformat(), "bars": meta["bars"]}
        written = await wf.write_report_rows(conn, report)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{proposal['id']}.json"
    out.write_text(json.dumps(report, indent=1, default=str))
    return {"report": report, "baseline": None, "run_ids": [report["run_id"]],
            "source": f"fresh:{out.name}", "rows_written": written}


async def _report_from_registry(conn, run_id: str) -> dict:
    """Rekonstruksi report walk-forward dari registry backtest_runs."""
    rows = await (await conn.execute(
        "SELECT window_index, metrics FROM backtest_runs "
        "WHERE run_id = %s AND role = 'test' AND selected ORDER BY window_index",
        (run_id,))).fetchall()
    if not rows:
        raise RuntimeError(f"tidak ada baris test terpilih untuk run {run_id}")
    windows = [{"test_metrics": dict(r["metrics"])} for r in rows]
    net = sum((w["test_metrics"].get("net_profit_usd") or 0.0) for w in windows)
    dd = max((w["test_metrics"].get("max_drawdown_pct") or 0.0) for w in windows)
    return {"run_id": run_id,
            "aggregate": {"n_windows": len(windows),
                          "stitched_net_profit_usd": round(net, 2),
                          "stitched_max_drawdown_pct": dd},
            "windows": windows}


async def _backtest_for(proposal: dict) -> dict:
    spec = proposal["backtest"]
    if spec.get("source") == "report":
        return _attach_report_evidence(proposal)
    if spec.get("source") == "registry":
        await _ensure_pool()
        async with db.pool().connection() as conn:
            report = await _report_from_registry(conn, spec["run_id"])
        return {"report": report, "baseline": None, "run_ids": [spec["run_id"]],
                "source": f"registry:{spec['run_id'][:8]}"}
    return await _run_fresh_backtest(proposal)


# ---------------------------------------------------------------- siklus


async def record_proposal(conn, week: str, proposal: dict, evidence: dict,
                          verdict_info: dict) -> None:
    await conn.execute(
        """
        INSERT INTO improvement_proposals
            (id, week, title, hypothesis, change, analysis, backtest_run_ids,
             evidence, verdict, criteria_result, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'PROPOSED')
        ON CONFLICT (id) DO UPDATE SET
            week = EXCLUDED.week, evidence = EXCLUDED.evidence,
            backtest_run_ids = EXCLUDED.backtest_run_ids,
            verdict = EXCLUDED.verdict, criteria_result = EXCLUDED.criteria_result
        """,
        (proposal["id"], week, proposal["title"], proposal["hypothesis"],
         json.dumps(proposal["change"]), json.dumps(evidence.get("analysis") or {}),
         json.dumps(evidence.get("run_ids") or []),
         json.dumps({"source": evidence.get("source"),
                     "baseline_net": (evidence.get("baseline") or {}).get(
                         "aggregate", {}).get("stitched_net_profit_usd")}),
         verdict_info["verdict"], json.dumps(verdict_info)))


async def run_cycle(send: bool = True, proposals_path: Path | None = None) -> dict:
    """Satu siklus mingguan penuh. Return ringkasan untuk pemanggil."""
    week = iso_week_now()
    proposals = load_proposals(proposals_path)
    if not proposals:
        raise RuntimeError(f"tidak ada usulan di {PROPOSALS_FILE}")

    await _ensure_pool()
    entries: list[dict] = []
    async with db.pool().connection() as conn:
        analysis = await collect_analysis(conn)
        known = {r["id"] for r in await (await conn.execute(
            "SELECT id FROM improvement_proposals")).fetchall()}
        for proposal in proposals:
            if proposal["id"] in known:
                row = await (await conn.execute(
                    "SELECT id, title, verdict, status, criteria_result "
                    "FROM improvement_proposals WHERE id = %s",
                    (proposal["id"],))).fetchone()
                entries.append(dict(row))
                continue
            evidence = await _backtest_for(proposal)
            verdict_info = evaluate_criteria(
                evidence["report"], proposal.get("criteria"))
            evidence["analysis"] = {
                k: analysis[k] for k in ("orders_by_status", "order_events_7d",
                                         "anomalies_7d") if k in analysis}
            await record_proposal(conn, week, proposal, evidence, verdict_info)
            entries.append({
                "id": proposal["id"], "title": proposal["title"],
                "verdict": verdict_info["verdict"], "status": "PROPOSED",
                "criteria_result": verdict_info})

    report = render_report(week, analysis, entries)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"laporan_{week}.md").write_text(report)
    sent = False
    if send:
        for chunk in split_telegram(report):
            sent = await notify_owner(chunk)
            if not sent:
                break
    return {"week": week, "entries": entries, "report": report, "sent": sent}


# ---------------------------------------------------------------- approve/deploy


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(BASE.parent),
            text=True, stderr=subprocess.DEVNULL).strip()[:12]
    except Exception:
        return None


async def _get_proposal(conn, proposal_id: str) -> dict:
    row = await (await conn.execute(
        "SELECT * FROM improvement_proposals WHERE id = %s",
        (proposal_id,))).fetchone()
    if row is None:
        raise KeyError(f"usulan {proposal_id} tidak ditemukan")
    return dict(row)


async def decide(proposal_id: str, decision: str, reviewer: str,
                 rationale: str | None = None) -> dict:
    """Rekam keputusan owner (APPROVED/REJECTED) + langsung deploy bila APPROVED.

    Pemanggil WAJIB sudah memverifikasi reviewer = owner (endpoint:
    admin + CSRF + 2FA + username == settings.owner_username). Keputusan
    dicatat append-only di strategy_approvals.
    """
    decision = decision.upper()
    if decision not in ("APPROVED", "REJECTED"):
        raise ValueError("decision harus APPROVED atau REJECTED")
    await _ensure_pool()
    async with db.pool().connection() as conn:
        async with conn.transaction():
            row = await (await conn.execute(
                "SELECT status FROM improvement_proposals WHERE id = %s "
                "FOR UPDATE", (proposal_id,))).fetchone()
            if row is None:
                raise KeyError(f"usulan {proposal_id} tidak ditemukan")
            if row["status"] != "PROPOSED":
                raise ValueError(f"usulan sudah diputuskan (status {row['status']})")
            version_id = None
            if decision == "APPROVED":
                version_id = await _approve_version(conn, proposal_id, reviewer,
                                                    rationale)
            await conn.execute(
                """
                UPDATE improvement_proposals
                SET status = %s, reviewer = %s, rationale = %s,
                    decided_at = now(), strategy_version_id = COALESCE(%s, strategy_version_id)
                WHERE id = %s
                """,
                (decision, reviewer, rationale, version_id, proposal_id))
    if decision == "APPROVED":
        return await deploy(proposal_id, reviewer, rationale)
    return {"proposal_id": proposal_id, "status": "REJECTED"}


async def _approve_version(conn, proposal_id: str, reviewer: str,
                           rationale: str | None) -> int:
    """Daftarkan strategi + versi APPROVED + approval append-only. Return version id."""
    prop = await _get_proposal(conn, proposal_id)
    change = prop["change"]
    sid = change["strategy_id"]
    version = change["version"]
    from strategies import mean_reversion, london_breakout, btc_range_breakout
    names = {m.STRATEGY_ID: m.STRATEGY_NAME for m in
             (mean_reversion, london_breakout, btc_range_breakout)}
    await conn.execute(
        """
        INSERT INTO strategies (strategy_id, name, description, status,
                                environment, config, current_version, enabled)
        VALUES (%s, %s, %s, 'PAPER', 'dev', %s, %s, false)
        ON CONFLICT (strategy_id) DO UPDATE SET
            current_version = EXCLUDED.current_version, updated_at = now()
        """,
        (sid, names.get(sid, sid), prop["hypothesis"],
         json.dumps({"mode": change.get("mode", "paper"),
                     "params": change.get("params") or {}}), version))
    row = await (await conn.execute(
        """
        INSERT INTO strategy_versions (strategy_id, version, code_commit_hash,
                                       code_path, params, walkforward_report,
                                       status, change_reason, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, 'APPROVED', %s, %s)
        RETURNING id
        """,
        (sid, version, _git_head(),
         f"strategies/{sid}.py",
         json.dumps(change.get("params") or {}),
         json.dumps(prop["evidence"] or {}), rationale or prop["title"],
         f"owner:{reviewer}"))).fetchone()
    version_id = row["id"]
    await conn.execute(
        """
        INSERT INTO strategy_approvals (strategy_version_id, stage, decision,
                                        reviewer, rationale, evidence)
        VALUES (%s, 'OWNER_APPROVE', 'APPROVED', %s, %s, %s)
        """,
        (version_id, reviewer, rationale,
         json.dumps({"proposal_id": proposal_id, "week": prop["week"],
                     "verdict": prop["verdict"]})))
    return version_id


async def deploy(proposal_id: str, reviewer: str,
                 rationale: str | None = None) -> dict:
    """Deploy usulan ter-approve: flag enabled + settings param (ter-audit).

    Hanya boleh dipanggil setelah keputusan owner tercatat; fungsi ini
    menegakkan status APPROVED.
    """
    await _ensure_pool()
    async with db.pool().connection() as conn:
        async with conn.transaction():
            prop = await _get_proposal(conn, proposal_id)
            if prop["status"] != "APPROVED":
                raise ValueError(
                    f"deploy butuh status APPROVED (sekarang {prop['status']})")
            change = prop["change"]
            sid, version = change["strategy_id"], change["version"]
            params = change.get("params") or {}
            mode = change.get("mode", "paper")
            await conn.execute(
                """
                UPDATE strategies SET enabled = true, status = 'PAPER',
                    current_version = %s, updated_at = now()
                WHERE strategy_id = %s
                """,
                (version, sid))
            await conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
                """,
                (f"strategy_params_{sid}", json.dumps(params)))
            await conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
                """,
                (f"strategy_mode_{sid}", json.dumps(mode)))
            await conn.execute(
                """
                INSERT INTO deployment_records (service, version, environment,
                                                deploy_type, deployed_by, details)
                VALUES (%s, %s, 'staging', 'CONFIG', %s, %s)
                """,
                (f"fund2-strategy-{sid}", version, reviewer,
                 json.dumps({"proposal_id": proposal_id, "mode": mode,
                             "params": params, "via": "self_improve"})))
            if prop["strategy_version_id"]:
                await conn.execute(
                    """
                    INSERT INTO strategy_approvals (strategy_version_id, stage,
                                                    decision, reviewer, rationale, evidence)
                    VALUES (%s, 'DEPLOY', 'APPROVED', %s, %s, %s)
                    """,
                    (prop["strategy_version_id"], reviewer, rationale,
                     json.dumps({"proposal_id": proposal_id,
                                 "settings": [f"strategy_params_{sid}",
                                              f"strategy_mode_{sid}"]})))
            await conn.execute(
                "UPDATE improvement_proposals SET status = 'DEPLOYED', "
                "deployed_at = now() WHERE id = %s", (proposal_id,))
    return {"proposal_id": proposal_id, "status": "DEPLOYED", "strategy": sid,
            "version": version, "mode": mode, "params": params}


async def status() -> dict:
    await _ensure_pool()
    async with db.pool().connection() as conn:
        rows = await (await conn.execute(
            "SELECT id, week, title, verdict, status, reviewer, decided_at, "
            "deployed_at FROM improvement_proposals ORDER BY created_at DESC"
        )).fetchall()
    return {"proposals": [dict(r) for r in rows]}


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Self-improvement loop mingguan")
    parser.add_argument("action", choices=["run", "status"])
    parser.add_argument("--no-send", action="store_true", help="jangan kirim Telegram")
    args = parser.parse_args()
    if args.action == "run":
        result = asyncio_run_cycle(send=not args.no_send)
        print(json.dumps({"week": result["week"], "sent": result["sent"],
                          "entries": [{k: e.get(k) for k in ("id", "verdict", "status")}
                                      for e in result["entries"]]}, indent=1, default=str))
    else:
        print(json.dumps(asyncio_run_status(), indent=1, default=str))


def asyncio_run_cycle(send: bool) -> dict:
    import asyncio
    return asyncio.run(run_cycle(send=send))


def asyncio_run_status() -> dict:
    import asyncio
    return asyncio.run(status())


if __name__ == "__main__":
    main()
