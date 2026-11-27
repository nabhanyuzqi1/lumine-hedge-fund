"""Tool riset Hermes dengan efek tulis TERBATAS (PRD v2.2 §12.1-12.3).

Yang boleh ditulis HANYA:
- research_reports  (laporan Hermes, PRD 12.3)
- research_proposals (usulan untuk owner; deploy tetap butuh approval owner)
- backtest_runs     (registry semua percobaan backtest, PRD 5.4)

Tidak ada endpoint/modul di file ini yang menyentuh orders, positions,
settings, kill-switch, atau audit log. Backtest dijalankan lewat subprocess
sandbox (app/research_sandbox.py): env kosong, tanpa jaringan, rlimits.

Anti-klaim sampel kecil (PRD 12.1 "menyatakan strategi profitable hanya
dari sampel kecil" dilarang): write_report memperingatkan bila teks
mengklaim profitabilitas dengan sampel < MIN_TRADES_FOR_PROFIT_CLAIM.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from . import db
from .research_sanitize import scan_injection
from .research_schemas import (
    CreateProposalArgs, CreateProposalOut, DataQualityArgs, ListProposalsArgs,
    ListProposalsOut, ListReportsArgs, ListReportsOut, PatternScanArgs,
    ProposalRow, ReportRow, RunBacktestArgs, RunBacktestOut, PnlSummaryArgs,
    WeeklyReportArgs, WeeklyReportOut, WriteReportArgs, WriteReportOut,
)
from .research_tools import tool_data_quality, tool_pattern_scan, tool_pnl_summary
from .state_machine import fetchone

MIN_TRADES_FOR_PROFIT_CLAIM = 30

STRATEGY_MODULES = {
    "london_breakout": "strategies.london_breakout",
    "mean_reversion": "strategies.mean_reversion",
    "btc_range_breakout": "strategies.btc_range_breakout",
}
STRATEGY_SYMBOLS = {
    "london_breakout": {"XAUUSD"},
    "mean_reversion": {"XAUUSD"},
    "btc_range_breakout": {"BTCUSD"},
}
STRATEGY_CONTEXT_BARS = {"btc_range_breakout": 24}
TF_SECONDS = {"M5": 300, "M15": 900, "H1": 3600}
CONTRACT_SIZE = {"XAUUSD": 100.0, "BTCUSD": 1.0}
MAX_BACKTEST_CANDLES = 20000
_PROFIT_CLAIM_RE = re.compile(r"profitab", re.I)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ── run_backtest (tool riset terbatas, sandbox) -----------------------------
async def tool_run_backtest(args: RunBacktestArgs, actor: str = "hermes") -> dict:
    from .research_sandbox import run_sandbox_backtest

    if args.strategy_id not in STRATEGY_MODULES:
        raise ValueError(f"strategy_id harus salah satu dari {sorted(STRATEGY_MODULES)}")
    if args.symbol not in STRATEGY_SYMBOLS[args.strategy_id]:
        raise ValueError(
            f"strategi {args.strategy_id} hanya untuk {sorted(STRATEGY_SYMBOLS[args.strategy_id])}")
    if args.timeframe not in TF_SECONDS:
        raise ValueError(f"timeframe harus salah satu dari {sorted(TF_SECONDS)}")

    now = datetime.now(timezone.utc)
    window_end = now
    window_start = now - timedelta(days=args.days)
    from .research_candles import load_candles
    candles = await load_candles(args.symbol, args.timeframe, window_start,
                                 window_end, MAX_BACKTEST_CANDLES)
    if len(candles) < 50:
        raise ValueError(
            f"candle tersedia {len(candles)} (< 50) untuk "
            f"{args.symbol} {args.timeframe} {args.days}h — window tidak layak backtest")

    request = {
        "strategy_module": STRATEGY_MODULES[args.strategy_id],
        "module_dir": str(db_module_dir()),
        "symbol": args.symbol,
        "tf_seconds": TF_SECONDS[args.timeframe],
        "candles": candles,
        "params": args.params,
        "spread": args.spread,
        "slippage": args.slippage,
        "equity0": 10000.0,
        "context_bars": STRATEGY_CONTEXT_BARS.get(args.strategy_id, 0),
        "regime_filter": args.regime_filter,
        "contract_size": CONTRACT_SIZE[args.symbol],
    }
    sandbox_result = await run_sandbox_backtest(request)
    if not sandbox_result.get("ok"):
        raise ValueError(f"sandbox backtest gagal: {sandbox_result.get('error')}")
    metrics = sandbox_result["metrics"]

    run_id = str(uuid.uuid4())
    version_row = await _strategy_version(args.strategy_id)
    async with db.pool().connection() as conn:
        row = await fetchone(
            conn,
            """
            INSERT INTO backtest_runs (run_id, strategy_id, strategy_version,
                                       symbol, timeframe, role, window_index,
                                       train_start, train_end, test_start,
                                       test_end, params, config, metrics,
                                       selected, note)
            VALUES (%s, %s, %s, %s, %s, 'test', 0, %s, %s, %s, %s, %s, %s,
                    %s, FALSE, %s)
            RETURNING id
            """,
            (
                run_id, args.strategy_id, version_row, args.symbol,
                args.timeframe, window_start, window_end, window_start,
                window_end, json.dumps(args.params),
                json.dumps({"source": "hermes_research", "sandbox": sandbox_result.get("sandbox", {})}),
                json.dumps(metrics, default=str),
                f"hermes research backtest by {actor}",
            ),
        )
    return RunBacktestOut(
        generated_at=now.isoformat(),
        run_id=run_id, backtest_run_id=int(row["id"]),
        strategy_id=args.strategy_id, strategy_version=version_row,
        symbol=args.symbol, timeframe=args.timeframe,
        window_start=window_start.isoformat(),
        window_end=window_end.isoformat(),
        candles=len(candles),
        sandbox=sandbox_result.get("sandbox", {}),
        metrics=metrics,
    ).model_dump(mode="json")


def db_module_dir() -> object:
    from pathlib import Path
    return Path(__file__).resolve().parent.parent


async def _strategy_version(strategy_id: str) -> str:
    """Versi strategi terakhir dari strategy_versions; fallback modul."""
    async with db.pool().connection() as conn:
        row = await fetchone(
            conn,
            """
            SELECT version FROM strategy_versions WHERE strategy_id = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (strategy_id,),
        )
    if row:
        return str(row["version"])
    from importlib import import_module
    mod = import_module(STRATEGY_MODULES[strategy_id])
    return str(getattr(mod, "STRATEGY_VERSION", "unknown"))


# ── write_report (PRD 12.3) --------------------------------------------------
async def tool_write_report(args: WriteReportArgs, actor: str = "hermes") -> dict:
    now = datetime.now(timezone.utc)
    if args.report_type not in (
            "WEEKLY", "DIAGNOSIS", "EXPERIMENT", "REVIEW", "OTHER"):
        raise ValueError("report_type tidak dikenal")
    if args.supersedes_id is not None:
        async with db.pool().connection() as conn:
            prev = await fetchone(
                conn, "SELECT id FROM research_reports WHERE id = %s",
                (args.supersedes_id,))
        if prev is None:
            raise ValueError(f"supersedes_id {args.supersedes_id} tidak ada")

    text_blobs = [args.summary]
    text_blobs += [str(f) for f in args.findings]
    text_blobs += [str(h) for h in args.hypotheses]
    text_blobs += [str(r) for r in args.recommendations]
    injection_findings = scan_injection(text_blobs)

    warnings: list[str] = []
    candidate = (args.baseline_vs_candidate or {}).get("candidate") or {}
    trades_n = candidate.get("trades")
    claim_text = " ".join(text_blobs)
    if _PROFIT_CLAIM_RE.search(claim_text):
        if not args.baseline_vs_candidate:
            warnings.append(
                "Klausa profitabilitas tanpa baseline_vs_candidate: klaim "
                "tidak didukung perbandingan terukur (PRD 12.3).")
        if trades_n is None or (isinstance(trades_n, (int, float))
                                and trades_n < MIN_TRADES_FOR_PROFIT_CLAIM):
            warnings.append(
                f"Klausa profitabilitas dengan sampel "
                f"{trades_n if trades_n is not None else 'tidak disebutkan'} "
                f"(< {MIN_TRADES_FOR_PROFIT_CLAIM} trade) dilarang PRD 12.1; "
                "turunkan menjadi hipotesis yang perlu diuji.")

    period_start = _parse_dt(args.period_start)
    period_end = _parse_dt(args.period_end)
    data_quality = {
        "injection_findings": injection_findings[:20],
        "warnings": warnings,
        "small_sample_note": (
            f"Klaim profitabilitas butuh >= {MIN_TRADES_FOR_PROFIT_CLAIM} "
            "trade out-of-sample; backtest bukan bukti profit live.")
        if warnings else None,
    }
    async with db.pool().connection() as conn:
        row = await fetchone(
            conn,
            """
            INSERT INTO research_reports (title, report_type, period_start,
                period_end, data_sources, data_quality, summary, findings,
                hypotheses, recommendations, baseline_vs_candidate, risks,
                author, supersedes_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                args.title, args.report_type, period_start, period_end,
                json.dumps(args.data_sources), json.dumps(data_quality),
                args.summary, json.dumps(args.findings),
                json.dumps(args.hypotheses), json.dumps(args.recommendations),
                json.dumps(args.baseline_vs_candidate), json.dumps(args.risks),
                actor, args.supersedes_id,
            ),
        )
    return WriteReportOut(
        report_id=int(row["id"]), title=args.title, status="DRAFT",
        injection_findings=injection_findings[:20], warnings=warnings,
    ).model_dump(mode="json")


# ── create_proposal (usulan untuk owner; deploy owner-only) -----------------
async def tool_create_proposal(args: CreateProposalArgs, actor: str = "hermes") -> dict:
    now = datetime.now(timezone.utc)
    if args.proposal_type not in ("STRATEGY_PARAM", "NEW_STRATEGY",
                                  "EXPERIMENT", "OTHER"):
        raise ValueError("proposal_type tidak dikenal")
    if args.report_id is not None:
        async with db.pool().connection() as conn:
            rep = await fetchone(
                conn, "SELECT id FROM research_reports WHERE id = %s",
                (args.report_id,))
        if rep is None:
            raise ValueError(f"report_id {args.report_id} tidak ada")
    if args.backtest_run_ids:
        async with db.pool().connection() as conn:
            rows = await conn.execute(
                "SELECT DISTINCT run_id::text FROM backtest_runs WHERE run_id = ANY(%s)",
                (args.backtest_run_ids,),
            )
            found = {r["run_id"] for r in await rows.fetchall()}
        missing = [r for r in args.backtest_run_ids if r not in found]
        if missing:
            raise ValueError(f"backtest run_id tidak ditemukan: {missing}")
    scan_injection([args.title, args.hypothesis, str(args.change)])
    async with db.pool().connection() as conn:
        row = await fetchone(
            conn,
            """
            INSERT INTO research_proposals (proposal_type, title, hypothesis,
                report_id, change, baseline_vs_candidate, backtest_run_ids,
                risks, author)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                args.proposal_type, args.title, args.hypothesis,
                args.report_id, json.dumps(args.change),
                json.dumps(args.baseline_vs_candidate),
                json.dumps(args.backtest_run_ids), json.dumps(args.risks),
                actor,
            ),
        )
    return CreateProposalOut(
        proposal_id=int(row["id"]), title=args.title, status="PROPOSED",
        note="Proposal PROPOSED: tidak bisa deploy tanpa keputusan owner "
             "(admin+CSRF+2FA+owner_username) dan release workflow terpisah.",
    ).model_dump(mode="json")


# ── list_reports / list_proposals -------------------------------------------
async def tool_list_reports(args: ListReportsArgs, actor: str = "hermes") -> dict:
    async with db.pool().connection() as conn:
        rows = await conn.execute(
            """
            SELECT id, title, report_type, status, period_start, period_end,
                   author, created_at
            FROM research_reports ORDER BY id DESC LIMIT %s
            """,
            (args.limit,),
        )
        data = [dict(r) for r in await rows.fetchall()]
    reports = [ReportRow(
        id=int(r["id"]), title=r["title"], report_type=r["report_type"],
        status=r["status"], period_start=_iso(r["period_start"]),
        period_end=_iso(r["period_end"]), author=r["author"],
        created_at=_iso(r["created_at"]) or "",
    ) for r in data]
    return ListReportsOut(count=len(reports), reports=reports).model_dump(mode="json")


async def tool_list_proposals(args: ListProposalsArgs, actor: str = "hermes") -> dict:
    async with db.pool().connection() as conn:
        rows = await conn.execute(
            """
            SELECT id, title, proposal_type, status, author, decided_by,
                   decided_at, strategy_version_id, created_at
            FROM research_proposals ORDER BY id DESC LIMIT %s
            """,
            (args.limit,),
        )
        data = [dict(r) for r in await rows.fetchall()]
    proposals = [ProposalRow(
        id=int(r["id"]), title=r["title"], proposal_type=r["proposal_type"],
        status=r["status"], author=r["author"], decided_by=r["decided_by"],
        decided_at=_iso(r["decided_at"]),
        strategy_version_id=r["strategy_version_id"],
        created_at=_iso(r["created_at"]) or "",
    ) for r in data]
    return ListProposalsOut(count=len(proposals), proposals=proposals).model_dump(mode="json")


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


# ── weekly_report (komposit PRD 12.2-12.3) ----------------------------------
async def tool_weekly_report(args: WeeklyReportArgs, actor: str = "hermes") -> dict:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=args.days)
    dq = await tool_data_quality(DataQualityArgs(days=args.days), actor)
    pnl = await tool_pnl_summary(PnlSummaryArgs(days=args.days), actor)
    patterns = await tool_pattern_scan(PatternScanArgs(days=args.days, source="paper"), actor)

    live, paper = pnl["live"], pnl["paper"]
    findings: list[dict] = [
        {"metric": "live_net_usd", "value": live["net_usd"],
         "evidence": f"{live['closed_positions']} posisi closed dalam {args.days} hari"},
        {"metric": "live_winrate", "value": live["winrate"],
         "evidence": f"{live['wins']}W/{live['losses']}L"},
        {"metric": "live_cost_usd",
         "value": round(live["commission_usd"] + live["swap_usd"], 2),
         "evidence": "commission+swap dari positions.raw"},
        {"metric": "paper_net_usd", "value": paper["net_usd"],
         "evidence": f"{paper['closed_orders']} order paper closed"},
        {"metric": "paper_winrate", "value": paper["winrate"],
         "evidence": f"{paper['wins']}W/{paper['losses']}L (paper, sampel terbatas)"},
        {"metric": "open_positions", "value": pnl["open_positions"],
         "evidence": "posisi OPEN saat laporan dibuat"},
    ]
    top_session = (patterns["by_session"] or [{}])[0]
    if top_session.get("group"):
        findings.append({
            "metric": "paper_session_terbanyak", "value": top_session["group"],
            "evidence": f"{top_session['trades']} trade; net {top_session['net_usd']} USD "
                        f"(paper, {args.days} hari)",
        })
    for note in dq.get("notes", []) + patterns.get("notes", []):
        findings.append({"metric": "data_quality", "value": note, "evidence": "validator data"})

    summary = (
        f"Periode {start.date()} .. {now.date()} (UTC). "
        f"Live: {live['closed_positions']} posisi closed, net {live['net_usd']} USD, "
        f"biaya commission+swap {round(live['commission_usd'] + live['swap_usd'], 2)} USD. "
        f"Paper: {paper['closed_orders']} order closed, net {paper['net_usd']} USD. "
        + (f"Catatan data: {'; '.join(dq.get('notes', [])[:2])}" if dq.get("notes") else "Data lengkap sesuai validator.")
        + (f" | {args.summary_extra}" if args.summary_extra else "")
    )
    title = args.title or f"Laporan riset mingguan Hermes ({args.days}h)"
    report_args = WriteReportArgs(
        title=title, report_type="WEEKLY",
        period_start=start.isoformat(), period_end=now.isoformat(),
        summary=summary,
        findings=findings,
        hypotheses=args.hypotheses,
        recommendations=args.recommendations,
        risks=args.risks or [{"risk": "Sampel kecil: angka winrate/expectancy "
                                       "belum stabil; butuh >= 30 trade out-of-sample "
                                       "sebelum klaim apa pun.",
                              "severity": "medium"}],
        data_sources={"database": "fund2 (read-only)",
                      "tables": ["positions", "orders", "order_events",
                                 "paper_orders", "candles", "kill_switch_events"],
                      "tools": ["data_quality", "pnl_summary", "pattern_scan"]},
    )
    written = await tool_write_report(report_args, actor)
    return WeeklyReportOut(
        report_id=written["report_id"], title=title, status=written["status"],
        period_start=start.isoformat(), period_end=now.isoformat(),
        summary=summary, findings=findings,
        injection_findings=written["injection_findings"],
        warnings=written["warnings"],
    ).model_dump(mode="json")
