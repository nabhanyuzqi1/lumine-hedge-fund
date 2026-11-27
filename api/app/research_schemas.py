"""Skema input/output tool riset Hermes (PRD v2.2 §12.3-12.4).

Setiap tool di TOOL_ALLOWLIST punya satu args_model dan satu out_model;
input dan output divalidasi Pydantic sebelum dipakai/dikembalikan
(output schema PRD 12.4). Semua field JSON-safe (mode="json").
"""
from __future__ import annotations

from pydantic import BaseModel, Field

REPORT_TYPES = ("WEEKLY", "DIAGNOSIS", "EXPERIMENT", "REVIEW", "OTHER")
PROPOSAL_TYPES = ("STRATEGY_PARAM", "NEW_STRATEGY", "EXPERIMENT", "OTHER")


# ── data_quality ------------------------------------------------------------
class DataQualityArgs(BaseModel):
    days: int = Field(7, ge=1, le=90)


class SeriesQuality(BaseModel):
    symbol: str
    timeframe: str
    rows: int
    first_ts: str | None = None
    last_ts: str | None = None
    max_gap_minutes: float | None = None
    rows_last_24h: int = 0


class DataQualityOut(BaseModel):
    generated_at: str
    window_start: str
    series: list[SeriesQuality]
    order_events_total: int
    open_positions: int
    notes: list[str] = []


# ── pnl_summary -------------------------------------------------------------
class PnlSummaryArgs(BaseModel):
    days: int = Field(7, ge=1, le=365)


class PnlGroup(BaseModel):
    group: str
    trades: int
    net_usd: float
    wins: int
    winrate: float | None = None


class LivePnl(BaseModel):
    closed_positions: int
    net_usd: float
    wins: int
    losses: int
    winrate: float | None = None
    gross_profit_usd: float = 0.0
    gross_loss_usd: float = 0.0
    worst_single_loss_usd: float | None = None
    commission_usd: float = 0.0
    swap_usd: float = 0.0
    by_symbol: list[PnlGroup] = []
    by_strategy: list[PnlGroup] = []
    by_session: list[PnlGroup] = []


class PaperPnl(BaseModel):
    closed_orders: int
    net_usd: float
    wins: int
    losses: int
    winrate: float | None = None
    by_strategy: list[PnlGroup] = []
    by_symbol: list[PnlGroup] = []


class PnlSummaryOut(BaseModel):
    generated_at: str
    period_start: str
    period_end: str
    live: LivePnl
    paper: PaperPnl
    open_positions: int


# ── event_log ---------------------------------------------------------------
class EventLogArgs(BaseModel):
    kind: str = Field("order", description="order | kill_switch")
    limit: int = Field(50, ge=1, le=500)
    symbol: str | None = Field(None, max_length=20)


class SanitizedEvent(BaseModel):
    id: int
    created_at: str
    to_status: str | None = None
    order_id: str | None = None
    symbol: str | None = None
    payload: dict = {}
    decision: dict | None = None


class EventLogOut(BaseModel):
    generated_at: str
    kind: str
    count: int
    injection_findings: list[dict] = []
    events: list[SanitizedEvent]


# ── pattern_scan ------------------------------------------------------------
class PatternScanArgs(BaseModel):
    days: int = Field(30, ge=1, le=365)
    source: str = Field("paper", description="paper | live")


class PatternGroup(BaseModel):
    group: str
    trades: int
    net_usd: float
    wins: int
    winrate: float | None = None
    avg_win_usd: float | None = None
    avg_loss_usd: float | None = None
    expectancy_usd: float | None = None


class PatternScanOut(BaseModel):
    generated_at: str
    period_start: str
    period_end: str
    source: str
    total_trades: int
    by_hour_utc: list[PatternGroup] = []
    by_weekday: list[PatternGroup] = []
    by_session: list[PatternGroup] = []
    by_strategy: list[PatternGroup] = []
    by_symbol: list[PatternGroup] = []
    by_side: list[PatternGroup] = []
    notes: list[str] = []


# ── run_backtest ------------------------------------------------------------
class RunBacktestArgs(BaseModel):
    strategy_id: str = Field(min_length=2, max_length=64)
    symbol: str = Field(min_length=3, max_length=20)
    timeframe: str = Field("M5", description="M5 | M15 | H1")
    days: int = Field(30, ge=1, le=90)
    params: dict = Field(default_factory=dict)
    spread: float | None = Field(None, ge=0, le=1000)
    slippage: float | None = Field(None, ge=0, le=1000)
    regime_filter: bool = False


class RunBacktestOut(BaseModel):
    generated_at: str
    run_id: str
    backtest_run_id: int
    strategy_id: str
    strategy_version: str
    symbol: str
    timeframe: str
    window_start: str | None = None
    window_end: str | None = None
    candles: int
    sandbox: dict
    metrics: dict


# ── write_report ------------------------------------------------------------
class WriteReportArgs(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    report_type: str = Field("WEEKLY")
    period_start: str | None = None
    period_end: str | None = None
    summary: str = Field(min_length=1, max_length=8000)
    findings: list[dict] = Field(default_factory=list, max_length=100)
    hypotheses: list[dict] = Field(default_factory=list, max_length=50)
    recommendations: list[dict] = Field(default_factory=list, max_length=50)
    baseline_vs_candidate: dict = Field(default_factory=dict)
    risks: list[dict] = Field(default_factory=list, max_length=50)
    data_sources: dict = Field(default_factory=dict)
    supersedes_id: int | None = Field(None, ge=1)


class WriteReportOut(BaseModel):
    report_id: int
    title: str
    status: str
    injection_findings: list[dict] = []
    warnings: list[str] = []


# ── create_proposal ---------------------------------------------------------
class CreateProposalArgs(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    proposal_type: str = Field("EXPERIMENT")
    hypothesis: str = Field("", max_length=8000)
    change: dict = Field(default_factory=dict)
    report_id: int | None = Field(None, ge=1)
    backtest_run_ids: list[str] = Field(default_factory=list, max_length=50)
    risks: list[dict] = Field(default_factory=list, max_length=50)
    baseline_vs_candidate: dict = Field(default_factory=dict)


class CreateProposalOut(BaseModel):
    proposal_id: int
    title: str
    status: str
    note: str


# ── list_reports / list_proposals -------------------------------------------
class ListReportsArgs(BaseModel):
    limit: int = Field(20, ge=1, le=100)


class ListProposalsArgs(BaseModel):
    limit: int = Field(20, ge=1, le=100)


class ReportRow(BaseModel):
    id: int
    title: str
    report_type: str
    status: str
    period_start: str | None = None
    period_end: str | None = None
    author: str
    created_at: str


class ProposalRow(BaseModel):
    id: int
    title: str
    proposal_type: str
    status: str
    author: str
    decided_by: str | None = None
    decided_at: str | None = None
    strategy_version_id: int | None = None
    created_at: str


class ListReportsOut(BaseModel):
    count: int
    reports: list[ReportRow]


class ListProposalsOut(BaseModel):
    count: int
    proposals: list[ProposalRow]


# ── weekly_report (komposit) ------------------------------------------------
class WeeklyReportArgs(BaseModel):
    days: int = Field(7, ge=1, le=90)
    title: str | None = Field(None, max_length=200)
    summary_extra: str = Field("", max_length=4000)
    hypotheses: list[dict] = Field(default_factory=list, max_length=50)
    recommendations: list[dict] = Field(default_factory=list, max_length=50)
    risks: list[dict] = Field(default_factory=list, max_length=50)


class WeeklyReportOut(BaseModel):
    report_id: int
    title: str
    status: str
    period_start: str
    period_end: str
    summary: str
    findings: list[dict]
    injection_findings: list[dict] = []
    warnings: list[str] = []
