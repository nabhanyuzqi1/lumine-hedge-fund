"""Tool riset Hermes read-only (PRD v2.2 §12.1-12.2).

Semua fungsi di modul ini HANYA membaca tabel produksi (positions, orders,
order_events, kill_switch_events, paper_orders, candles, liquidity_samples)
dan tidak pernah menulis, tidak pernah membaca tabel settings (bridge_token
dkk tidak boleh keluar). Output melewati redact() + scan_injection() di
app.research (registry) sebelum divalidasi skema.

Data yang keluar dari event_log adalah data tersanitasi: field dibatasi,
string di-scan pola instruksinya, dan temuan dilaporkan sebagai temuan
(bukan dieksekusi).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from . import db
from .ingest import session_of
from .research_sanitize import redact, scan_injection
from .research_schemas import (
    DataQualityArgs, DataQualityOut, EventLogArgs, EventLogOut, LivePnl,
    PaperPnl, PatternGroup, PatternScanArgs, PatternScanOut, PnlGroup,
    PnlSummaryArgs, PnlSummaryOut, SanitizedEvent, SeriesQuality,
)

SERIES = (("XAUUSD", "M5"), ("XAUUSD", "M15"), ("XAUUSD", "H1"),
          ("BTCUSD", "M5"), ("BTCUSD", "M15"), ("BTCUSD", "H1"))
TF_MINUTES = {"M5": 5, "M15": 15, "H1": 60}


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


# ── data_quality (PRD 12.2 langkah 2: validasi kelengkapan data) ------------
async def tool_data_quality(args: DataQualityArgs, actor: str = "hermes") -> dict:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=args.days)
    series: list[SeriesQuality] = []
    notes: list[str] = []
    async with db.pool().connection() as conn:
        for symbol, tf in SERIES:
            row = await conn.execute(
                """
                SELECT count(*) AS n, min(ts) AS first_ts, max(ts) AS last_ts
                FROM candles WHERE symbol = %s AND timeframe = %s
                  AND ts >= %s
                """,
                (symbol, tf, window_start),
            )
            stat = await row.fetchone()
            gap_row = await conn.execute(
                """
                SELECT max(gap) AS max_gap FROM (
                    SELECT extract(epoch FROM (ts - lag(ts) OVER
                           (ORDER BY ts))) / 60 AS gap
                    FROM candles WHERE symbol = %s AND timeframe = %s
                      AND ts >= %s
                ) g
                """,
                (symbol, tf, window_start),
            )
            gap = await gap_row.fetchone()
            recent = await conn.execute(
                """
                SELECT count(*) AS n FROM candles
                WHERE symbol = %s AND timeframe = %s AND ts >= %s
                """,
                (symbol, tf, now - timedelta(hours=24)),
            )
            recent_stat = await recent.fetchone()
            series.append(SeriesQuality(
                symbol=symbol, timeframe=tf,
                rows=int(stat["n"] or 0),
                first_ts=_iso(stat["first_ts"]), last_ts=_iso(stat["last_ts"]),
                max_gap_minutes=round(float(gap["max_gap"]), 2) if gap and gap["max_gap"] is not None else None,
                rows_last_24h=int(recent_stat["n"] or 0),
            ))
            expected_min = args.days * 24 * 60 // TF_MINUTES[tf]
            if stat["n"] and (stat["n"] or 0) < expected_min * 0.5:
                notes.append(
                    f"{symbol} {tf}: {stat['n']} bar dalam {args.days} hari "
                    f"(expektasi >= {expected_min * 0.5}) — data tidak lengkap "
                    f"untuk backtest full-window; batasi window")
        ev = await conn.execute("SELECT count(*) AS n FROM order_events")
        ev_stat = await ev.fetchone()
        pos = await conn.execute(
            "SELECT count(*) AS n FROM positions WHERE status = 'OPEN'")
        pos_stat = await pos.fetchone()
    return DataQualityOut(
        generated_at=now.isoformat(),
        window_start=window_start.isoformat(),
        series=series,
        order_events_total=int(ev_stat["n"]),
        open_positions=int(pos_stat["n"]),
        notes=notes,
    ).model_dump(mode="json")


# ── helper P&L ---------------------------------------------------------------
def _costs_from_raw(raw) -> tuple[float, float]:
    """Jumlahkan commission/swap dari positions.raw JSONB (recursive)."""
    commission = 0.0
    swap = 0.0

    def walk(node):
        nonlocal commission, swap
        if isinstance(node, dict):
            for key, value in node.items():
                k = str(key).lower()
                if isinstance(value, (int, float)):
                    if "commission" in k:
                        commission += float(value)
                    elif "swap" in k:
                        swap += float(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(raw)
    return round(commission, 2), round(swap, 2)


def _groups(rows: list[dict], key: str) -> list[PnlGroup]:
    agg: dict[str, dict] = {}
    for r in rows:
        g = str(r.get(key) or "-")
        d = agg.setdefault(g, {"trades": 0, "net": 0.0, "wins": 0})
        d["trades"] += 1
        d["net"] += float(r.get("profit") or 0)
        d["wins"] += 1 if float(r.get("profit") or 0) > 0 else 0
    return [
        PnlGroup(group=g, trades=d["trades"], net_usd=round(d["net"], 2),
                 wins=d["wins"],
                 winrate=round(d["wins"] / d["trades"], 4) if d["trades"] else None)
        for g, d in sorted(agg.items(), key=lambda kv: -kv[1]["net"])
    ]


# ── pnl_summary (PRD 12.1: ringkasan profit/loss dan biaya) -----------------
async def tool_pnl_summary(args: PnlSummaryArgs, actor: str = "hermes") -> dict:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=args.days)
    async with db.pool().connection() as conn:
        rows = await conn.execute(
            """
            SELECT p.ticket, p.symbol, p.side, p.volume, p.profit, p.raw,
                   o.strategy, p.open_time, p.close_time
            FROM positions p LEFT JOIN orders o ON o.id = p.order_id
            WHERE p.status = 'CLOSED' AND p.close_time >= %s
            ORDER BY p.close_time
            """,
            (start,),
        )
        live_rows = [dict(r) for r in await rows.fetchall()]
        open_pos = await conn.execute(
            "SELECT count(*) AS n FROM positions WHERE status = 'OPEN'")
        open_stat = await open_pos.fetchone()
        paper = await conn.execute(
            """
            SELECT strategy, symbol, side, volume, profit, opened_at, closed_at
            FROM paper_orders
            WHERE status = 'CLOSED' AND closed_at >= %s AND mode = 'PAPER'
            ORDER BY closed_at
            """,
            (start,),
        )
        paper_rows = [dict(r) for r in await paper.fetchall()]

    profits = [float(r["profit"] or 0) for r in live_rows]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p <= 0]
    commission_total = 0.0
    swap_total = 0.0
    for r in live_rows:
        c, s = _costs_from_raw(r.get("raw"))
        commission_total += c
        swap_total += s
    for r in live_rows:
        r["session"] = session_of(r["open_time"]) if r["open_time"] else "-"
    worst = min(profits) if profits else None
    live = LivePnl(
        closed_positions=len(live_rows),
        net_usd=round(sum(profits), 2),
        wins=len(wins), losses=len(losses),
        winrate=round(len(wins) / len(profits), 4) if profits else None,
        gross_profit_usd=round(sum(wins), 2),
        gross_loss_usd=round(sum(losses), 2),
        worst_single_loss_usd=round(worst, 2) if worst is not None else None,
        commission_usd=round(commission_total, 2),
        swap_usd=round(swap_total, 2),
        by_symbol=_groups(live_rows, "symbol"),
        by_strategy=_groups(live_rows, "strategy"),
        by_session=_groups(live_rows, "session"),
    )
    pp = [float(r["profit"] or 0) for r in paper_rows]
    pw = [p for p in pp if p > 0]
    paper = PaperPnl(
        closed_orders=len(paper_rows),
        net_usd=round(sum(pp), 2),
        wins=len(pw), losses=len(pp) - len(pw),
        winrate=round(len(pw) / len(pp), 4) if pp else None,
        by_strategy=_groups(paper_rows, "strategy"),
        by_symbol=_groups(paper_rows, "symbol"),
    )
    return PnlSummaryOut(
        generated_at=now.isoformat(),
        period_start=start.isoformat(), period_end=now.isoformat(),
        live=live, paper=paper,
        open_positions=int(open_stat["n"]),
    ).model_dump(mode="json")


# ── event_log (PRD 12.1: membaca event log tersanitasi) ---------------------
async def tool_event_log(args: EventLogArgs, actor: str = "hermes") -> dict:
    now = datetime.now(timezone.utc)
    findings: list[dict] = []
    events: list[SanitizedEvent] = []
    async with db.pool().connection() as conn:
        if args.kind == "order":
            rows = await conn.execute(
                """
                SELECT e.id, e.created_at, e.to_status, e.order_id,
                       e.payload, e.decision, o.symbol
                FROM order_events e LEFT JOIN orders o ON o.id = e.order_id
                WHERE (%s::text IS NULL OR o.symbol = %s)
                ORDER BY e.id DESC LIMIT %s
                """,
                (args.symbol, args.symbol, args.limit),
            )
            for r in await rows.fetchall():
                payload = redact(r["payload"] or {})
                decision = redact(r["decision"]) if r["decision"] else None
                findings.extend(scan_injection(payload))
                if decision:
                    findings.extend(scan_injection(decision))
                events.append(SanitizedEvent(
                    id=int(r["id"]), created_at=r["created_at"].isoformat(),
                    to_status=r["to_status"],
                    order_id=str(r["order_id"]) if r["order_id"] else None,
                    symbol=r["symbol"],
                    payload=payload if isinstance(payload, dict) else {},
                    decision=decision if isinstance(decision, dict) else None,
                ))
        elif args.kind == "kill_switch":
            rows = await conn.execute(
                """
                SELECT id, created_at, action, mode, strategy, source, actor,
                       reason, details
                FROM kill_switch_events
                ORDER BY id DESC LIMIT %s
                """,
                (args.limit,),
            )
            for r in await rows.fetchall():
                details = redact(r["details"] or {})
                findings.extend(scan_injection(details))
                events.append(SanitizedEvent(
                    id=int(r["id"]), created_at=r["created_at"].isoformat(),
                    to_status=r["action"],
                    payload={
                        "mode": r["mode"], "strategy": r["strategy"],
                        "source": r["source"], "actor": r["actor"],
                        "reason": r["reason"], **({"details": details} if details else {}),
                    },
                ))
        else:
            raise ValueError("kind harus order | kill_switch")
    return EventLogOut(
        generated_at=now.isoformat(), kind=args.kind, count=len(events),
        injection_findings=findings[:20], events=events,
    ).model_dump(mode="json")


# ── pattern_scan (PRD 12.1: mengelompokkan pola transaksi) -------------------
async def tool_pattern_scan(args: PatternScanArgs, actor: str = "hermes") -> dict:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=args.days)
    if args.source not in ("paper", "live"):
        raise ValueError("source harus paper | live")
    notes: list[str] = []
    async with db.pool().connection() as conn:
        if args.source == "paper":
            rows = await conn.execute(
                """
                SELECT strategy, symbol, side, profit, opened_at, closed_at
                FROM paper_orders
                WHERE status = 'CLOSED' AND closed_at >= %s AND mode = 'PAPER'
                """,
                (start,),
            )
        else:
            rows = await conn.execute(
                """
                SELECT COALESCE(o.strategy, 'manual') AS strategy, p.symbol,
                       p.side, p.profit, p.open_time AS opened_at,
                       p.close_time AS closed_at
                FROM positions p LEFT JOIN orders o ON o.id = p.order_id
                WHERE p.status = 'CLOSED' AND p.close_time >= %s
                """,
                (start,),
            )
        data = [dict(r) for r in await rows.fetchall()]

    if len(data) < 30:
        notes.append(
            f"Sampel kecil ({len(data)} trade < 30): pola winrate/expectancy "
            "TIDAK boleh disimpulkan sebagai fakta stabil (PRD 12.1)")
    enriched = []
    for r in data:
        opened = r["opened_at"]
        r = dict(r)
        r["hour"] = f"{opened.hour:02d}" if opened else "-"
        r["weekday"] = opened.strftime("%a") if opened else "-"
        r["session"] = session_of(opened) if opened else "-"
        enriched.append(r)

    def groups(key: str) -> list[PatternGroup]:
        agg: dict[str, dict] = {}
        for r in enriched:
            g = str(r.get(key) or "-")
            d = agg.setdefault(g, {"n": 0, "net": 0.0, "wins": 0,
                                   "win_sum": 0.0, "loss_sum": 0.0})
            p = float(r["profit"] or 0)
            d["n"] += 1
            d["net"] += p
            d["wins"] += 1 if p > 0 else 0
            if p > 0:
                d["win_sum"] += p
            else:
                d["loss_sum"] += p
        out = []
        for g, d in sorted(agg.items(), key=lambda kv: -kv[1]["n"]):
            n = d["n"]
            out.append(PatternGroup(
                group=g, trades=n, net_usd=round(d["net"], 2),
                wins=d["wins"], winrate=round(d["wins"] / n, 4) if n else None,
                avg_win_usd=round(d["win_sum"] / d["wins"], 2) if d["wins"] else None,
                avg_loss_usd=round(d["loss_sum"] / (n - d["wins"]), 2) if n > d["wins"] else None,
                expectancy_usd=round(d["net"] / n, 2) if n else None,
            ))
        return out

    return PatternScanOut(
        generated_at=now.isoformat(),
        period_start=start.isoformat(), period_end=now.isoformat(),
        source=args.source, total_trades=len(data),
        by_hour_utc=groups("hour"), by_weekday=groups("weekday"),
        by_session=groups("session"), by_strategy=groups("strategy"),
        by_symbol=groups("symbol"), by_side=groups("side"),
        notes=notes,
    ).model_dump(mode="json")
