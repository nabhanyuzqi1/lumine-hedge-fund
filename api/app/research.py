"""Registry tool riset Hermes + CLI (PRD v2.2 §12, t_f2v22a7).

TOOL_ALLOWLIST adalah SATU-SATUNYA pintu eksekusi tool riset: nama tool
tidak dikenal -> ditolak; input/output divalidasi skema Pydantic; output
di-redact (key sensitif) sebelum keluar. Argumen yang mengandung pola
EKSEKUSI (perintah shell, aksi order, sabotase kill-switch) ditolak —
data tidak pernah dijalankan sebagai instruksi (PRD 12.4).

CLI (dipakai Hermes langsung, kredensial DB read-only per tool):
  cd ~/fund2/api
  .venv/bin/python -m app.research tools
  .venv/bin/python -m app.research run pnl-summary --args '{"days": 7}'
  .venv/bin/python -m app.research weekly-report --days 7

HTTP (role 'research' | 'admin'): POST /research/tools/{name} — lihat
app/research_routes.py. Role 'research' ditolak default-deny di semua
endpoint non-/research (middleware di app/main.py).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ValidationError

from . import db
from .research_sanitize import find_exec_injection
from .research_schemas import (
    CreateProposalArgs, CreateProposalOut, DataQualityArgs, DataQualityOut,
    EventLogArgs, EventLogOut, ListProposalsArgs, ListProposalsOut,
    ListReportsArgs, ListReportsOut, PatternScanArgs, PatternScanOut,
    PnlSummaryArgs, PnlSummaryOut, RunBacktestArgs, RunBacktestOut,
    WeeklyReportArgs, WeeklyReportOut, WriteReportArgs, WriteReportOut,
)
from .research_tools import (
    tool_data_quality, tool_event_log, tool_pattern_scan, tool_pnl_summary,
)
from .research_write import (
    tool_create_proposal, tool_list_proposals, tool_list_reports,
    tool_run_backtest, tool_weekly_report, tool_write_report,
)


class ResearchToolError(Exception):
    """Error domain tool riset -> HTTP 422 oleh routes."""


class UnknownToolError(ResearchToolError):
    """Tool tidak ada di allowlist -> HTTP 404 oleh routes."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    out_model: type[BaseModel]
    fn: Callable[..., Awaitable[dict]]
    writes: tuple[str, ...] = ()   # tabel yang ditulis; kosong = read-only


TOOL_ALLOWLIST: dict[str, ToolSpec] = {
    spec.name: spec for spec in [
        ToolSpec("data_quality",
                 "Validasi kelengkapan data candle & event (PRD 12.2 langkah 2)",
                 DataQualityArgs, DataQualityOut, tool_data_quality),
        ToolSpec("pnl_summary",
                 "Ringkasan P&L + biaya live & paper (PRD 12.1)",
                 PnlSummaryArgs, PnlSummaryOut, tool_pnl_summary),
        ToolSpec("event_log",
                 "Baca event log tersanitasi: order | kill_switch (PRD 12.1/12.4)",
                 EventLogArgs, EventLogOut, tool_event_log),
        ToolSpec("pattern_scan",
                 "Pengelompokan pola transaksi per jam/sesi/strategi (PRD 12.1)",
                 PatternScanArgs, PatternScanOut, tool_pattern_scan),
        ToolSpec("run_backtest",
                 "Backtest via sandbox subprocess, tercatat di backtest_runs (PRD 12.1)",
                 RunBacktestArgs, RunBacktestOut, tool_run_backtest,
                 writes=("backtest_runs",)),
        ToolSpec("write_report",
                 "Tulis laporan riset ke research_reports, status DRAFT (PRD 12.3)",
                 WriteReportArgs, WriteReportOut, tool_write_report,
                 writes=("research_reports",)),
        ToolSpec("create_proposal",
                 "Usulan untuk owner; deploy butuh approval owner (PRD 12.1/12.2)",
                 CreateProposalArgs, CreateProposalOut, tool_create_proposal,
                 writes=("research_proposals",)),
        ToolSpec("list_reports", "Daftar laporan riset",
                 ListReportsArgs, ListReportsOut, tool_list_reports),
        ToolSpec("list_proposals", "Daftar usulan + status keputusan owner",
                 ListProposalsArgs, ListProposalsOut, tool_list_proposals),
        ToolSpec("weekly_report",
                 "Laporan mingguan komposit: data_quality+pnl+pola -> research_reports (PRD 12.2-12.3)",
                 WeeklyReportArgs, WeeklyReportOut, tool_weekly_report,
                 writes=("research_reports",)),
    ]
}


def allowlist_public() -> list[dict]:
    """Deskripsi allowlist untuk GET /research/tools (transparansi)."""
    return [
        {
            "name": s.name,
            "description": s.description,
            "args_schema": s.args_model.model_json_schema(),
            "output_schema": s.out_model.model_json_schema(),
            "writes": list(s.writes),
        }
        for s in TOOL_ALLOWLIST.values()
    ]


async def run_tool(name: str, args: dict | None, actor: str = "hermes") -> dict:
    """Eksekusi satu tool allowlist: validasi in/out, redact, anti-eksekusi."""
    spec = TOOL_ALLOWLIST.get(name)
    if spec is None:
        raise UnknownToolError(f"tool '{name}' tidak ada di allowlist "
                               f"({sorted(TOOL_ALLOWLIST)})")
    try:
        parsed_args = spec.args_model(**(args or {}))
    except ValidationError as exc:
        raise ResearchToolError(f"args tidak valid: {exc}") from exc
    exec_hits = find_exec_injection(parsed_args.model_dump())
    if exec_hits:
        raise ResearchToolError(
            "args mengandung pola eksekusi (data bukan instruksi, PRD 12.4): "
            + json.dumps(exec_hits[:3]))
    try:
        result = await spec.fn(parsed_args, actor=actor)
    except ValueError as exc:
        raise ResearchToolError(str(exc)) from exc
    try:
        validated = spec.out_model(**result)
    except ValidationError as exc:
        raise ResearchToolError(f"output tool '{name}' tidak sesuai skema: {exc}") from exc
    return validated.model_dump(mode="json")


# ── CLI ---------------------------------------------------------------------
async def _cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="app.research",
                                     description="Tool riset Hermes (PRD v2.2 §12)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tools", help="daftar allowlist tool")
    p_run = sub.add_parser("run", help="jalankan tool allowlist")
    p_run.add_argument("tool")
    p_run.add_argument("--args", default="{}", help="JSON args")
    p_run.add_argument("--actor", default="hermes-cli")
    p_week = sub.add_parser("weekly-report", help="laporan mingguan komposit")
    p_week.add_argument("--days", type=int, default=7)
    p_week.add_argument("--title", default=None)
    p_week.add_argument("--actor", default="hermes-cli")
    ns = parser.parse_args(argv)

    await db.init_pool()
    try:
        if ns.cmd == "tools":
            print(json.dumps(allowlist_public(), indent=2, default=str))
        elif ns.cmd == "run":
            try:
                args = json.loads(ns.args)
            except json.JSONDecodeError as exc:
                print(json.dumps({"ok": False, "error": f"--args bukan JSON: {exc}"}))
                return 2
            result = await run_tool(ns.tool, args, actor=ns.actor)
            print(json.dumps(result, indent=2, default=str))
        elif ns.cmd == "weekly-report":
            result = await run_tool(
                "weekly_report", {"days": ns.days, **({"title": ns.title} if ns.title else {})},
                actor=ns.actor)
            print(json.dumps(result, indent=2, default=str))
        return 0
    finally:
        await db.close_pool()


def main() -> None:
    try:
        sys.exit(asyncio.run(_cli(sys.argv[1:])))
    except ResearchToolError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
