"""Analisa mingguan + kriteria verdict + render laporan (PRD v2.1 §5.9, P4).

Dipakai app.self_improve (siklus penuh). Kriteria PASS dideklarasikan di
proposal SEBELUM backtest dijalankan (anti-overfit, pola gate P2).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from . import anomaly

# Kriteria lolos default (dideklarasikan sebelum run, sama dengan gate P2).
DEFAULT_CRITERIA = {
    "net_profit_usd_gt": 0.0,
    "profit_factor_gt": 1.0,
    "expectancy_usd_gt": 0.0,
    "max_drawdown_pct_lte": 0.10,
    "min_trades": 30,
    "max_windows_pf_below_1_ratio": 0.50,
}


async def collect_analysis(conn, days: int = 7) -> dict:
    """Analisa event log + hasil untuk satu siklus mingguan."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    out: dict = {"window_days": days, "since": since.isoformat()}

    rows = await (await conn.execute(
        "SELECT status, count(*) AS c FROM orders WHERE created_at >= %s "
        "GROUP BY status ORDER BY c DESC", (since,))).fetchall()
    out["orders_by_status"] = {r["status"]: r["c"] for r in rows}

    row = await (await conn.execute(
        "SELECT count(*) AS c FROM order_events WHERE created_at >= %s",
        (since,))).fetchone()
    out["order_events_7d"] = row["c"]

    rows = await (await conn.execute(
        "SELECT strategy, status, count(*) AS c FROM paper_orders "
        "WHERE created_at >= %s GROUP BY strategy, status ORDER BY c DESC",
        (since,))).fetchall()
    out["paper_orders_7d"] = [
        {"strategy": r["strategy"], "status": r["status"], "count": r["c"]} for r in rows]

    rows = await (await conn.execute("SELECT key, value FROM paper_state")).fetchall()
    out["paper_state"] = {
        r["key"]: {"balance": (r["value"] or {}).get("balance"),
                   "position": (r["value"] or {}).get("position")} for r in rows}

    rows = await (await conn.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (strategy_id, symbol, timeframe)
                   strategy_id, symbol, timeframe, run_id
            FROM backtest_runs
            WHERE role = 'test' AND selected
            ORDER BY strategy_id, symbol, timeframe, created_at DESC)
        SELECT b.strategy_id, b.symbol, b.timeframe, count(*) AS windows,
               sum((b.metrics->>'trades')::int) AS trades,
               round(sum((b.metrics->>'net_profit_usd')::numeric), 2) AS net_usd,
               round(avg(NULLIF(b.metrics->>'profit_factor', '')::numeric), 3) AS avg_pf
        FROM backtest_runs b
        JOIN latest l ON b.run_id = l.run_id
        WHERE b.role = 'test' AND b.selected
        GROUP BY b.strategy_id, b.symbol, b.timeframe
        ORDER BY net_usd ASC
        """)).fetchall()
    out["walkforward_summary"] = [dict(r) for r in rows]

    row = await (await conn.execute(
        "SELECT value FROM settings WHERE key = 'kill_switch'")).fetchone()
    out["kill_switch"] = (row["value"] if row else None) or {}

    out["anomalies_7d"] = await anomaly.collect_anomalies()
    return out


def _stitched_from_windows(windows: list[dict]) -> dict:
    """Hitung metrik gabungan dari trades_detail per window uji (pola gate P2)."""
    trades = []
    for w in windows:
        trades.extend((w.get("test_metrics") or {}).get("trades_detail") or [])
    if not trades:
        return {}
    wins = [t for t in trades if t.get("profit", 0) > 0]
    losses = [t for t in trades if t.get("profit", 0) <= 0]
    gw = sum(t.get("profit", 0) for t in wins)
    gl = abs(sum(t.get("profit", 0) for t in losses))
    exp = [t.get("r_multiple") for t in trades if t.get("r_multiple") is not None]
    return {
        "stitched_trades": len(trades),
        "stitched_profit_factor": round(gw / gl, 3) if gl else None,
        "stitched_expectancy_usd": round(
            sum(t.get("profit", 0) for t in trades) / len(trades), 2),
        "stitched_expectancy_r": round(sum(exp) / len(exp), 3) if exp else None,
    }


def evaluate_criteria(report: dict, criteria: dict | None = None) -> dict:
    """Nilai kriteria yang DIDEKLARASIKNAN sebelum run terhadap hasil walk-forward.

    Return {checks: {nama: bool}, verdict: 'LULUS'|'GAGAL', aggregate: {...}}.
    """
    crit = {**DEFAULT_CRITERIA, **(criteria or {})}
    agg = report.get("aggregate") or {}
    windows = report.get("windows") or []
    pf_values = [(w.get("test_metrics") or {}).get("profit_factor")
                 for w in windows]
    pf_below = [p for p in pf_values if p is not None and p < 1]
    pf_ratio = (len(pf_below) / len(pf_values)) if pf_values else 1.0
    agg_full = {
        "net_profit_usd": agg.get("stitched_net_profit_usd"),
        "profit_factor": agg.get("stitched_profit_factor"),
        "expectancy_usd": agg.get("stitched_expectancy_usd"),
        "max_drawdown_pct": agg.get("stitched_max_drawdown_pct"),
        "trades": agg.get("stitched_trades"),
        "n_windows": agg.get("n_windows"),
        "windows_pf_below_1_ratio": round(pf_ratio, 4),
    }
    agg_full.update(_stitched_from_windows(windows))
    # fallback: report tanpa agg_extras (mis. probe) -> pakai hasil stitching
    agg_full["profit_factor"] = agg_full.get("profit_factor") if agg_full.get("profit_factor") is not None else agg_full.get("stitched_profit_factor")
    agg_full["expectancy_usd"] = agg_full.get("expectancy_usd") if agg_full.get("expectancy_usd") is not None else agg_full.get("stitched_expectancy_usd")
    agg_full["trades"] = agg_full.get("trades") if agg_full.get("trades") is not None else agg_full.get("stitched_trades")
    checks = {
        "net_profit_usd_gt": (agg_full["net_profit_usd"] or 0) > crit["net_profit_usd_gt"],
        "profit_factor_gt": (agg_full["profit_factor"] or 0) > crit["profit_factor_gt"],
        "expectancy_usd_gt": (agg_full["expectancy_usd"] or 0) > crit["expectancy_usd_gt"],
        "max_drawdown_pct_lte": (agg_full["max_drawdown_pct"] or 1) <= crit["max_drawdown_pct_lte"],
        "min_trades": (agg_full["trades"] or 0) >= crit["min_trades"],
        "max_windows_pf_below_1_ratio": pf_ratio <= crit["max_windows_pf_below_1_ratio"],
    }
    return {"checks": checks, "verdict": "LULUS" if all(checks.values()) else "GAGAL",
            "aggregate": agg_full, "criteria": crit}


def _fmt(x) -> str:
    if x is None:
        return "-"
    if isinstance(x, float):
        return f"{x:.2f}"
    return str(x)


def _esc(s) -> str:
    """Escape karakter Markdown Telegram pada nilai dinamis.

    Temuan gerbang P4 (t_f2co_p4): laporan W48 memuat teks literal
    `t_f2p4a1` dan nama kriteria berunderscore, sehingga Telegram menolak
    pesan (can't parse entities) sementara pemanggil melaporkan sukses.
    """
    s = str(s)
    for ch in ("\\", "`", "*", "_", "["):
        s = s.replace(ch, f"\\{ch}")
    return s


def render_report(week: str, analysis: dict, entries: list[dict]) -> str:
    """Laporan mingguan untuk owner (Telegram, markdown)."""
    lines = [f"*LAPORAN MINGGUAN SELF-IMPROVE {_esc(week)}*", ""]
    ks = analysis.get("kill_switch") or {}
    lines.append(f"Kill-switch: {_esc(ks.get('mode') or 'AMAN')}")
    orders = analysis.get("orders_by_status") or {}
    lines.append(f"Order 7h: {sum(orders.values()) if orders else 0} "
                 f"({_esc(json.dumps(orders))}) | event: "
                 f"{_esc(analysis.get('order_events_7d'))}")
    for key, st in (analysis.get("paper_state") or {}).items():
        lines.append(f"Paper {_esc(key)}: balance {_fmt(st.get('balance'))}")
    if analysis.get("anomalies_7d"):
        lines.append("Anomali 7h: " + "; ".join(_esc(a) for a in analysis["anomalies_7d"][:3]))
    else:
        lines.append("Anomali 7h: tidak ada")

    lines += ["", "*Walk-forward terakhir (window uji terpilih)*"]
    for r in (analysis.get("walkforward_summary") or [])[:6]:
        lines.append(f"- {_esc(r['strategy_id'])} {_esc(r['symbol'])} "
                     f"{_esc(r['timeframe'])}: "
                     f"net {_fmt(r['net_usd'])} USD, {r['windows']} window, "
                     f"{r['trades']} trade, PF rata2 {r['avg_pf']}")

    lines += ["", "*Usulan perbaikan (backtest otomatis)*"]
    for e in entries:
        verdict = e.get("verdict", "PENDING")
        icon = "+" if verdict == "LULUS" else ("-" if verdict == "GAGAL" else "?")
        lines.append(f"[{icon}] {_esc(e['id'])}: {_esc(e['title'])}")
        lines.append(f"  verdict: {_esc(verdict)} | status: "
                     f"{_esc(e.get('status', 'PROPOSED'))}")
        agg = (e.get("criteria_result") or {}).get("aggregate") or {}
        if agg:
            lines.append(f"  net {_fmt(agg.get('net_profit_usd'))} USD, "
                         f"PF {_fmt(agg.get('profit_factor'))}, "
                         f"trade {_fmt(agg.get('trades'))}, "
                         f"DD {_fmt(agg.get('max_drawdown_pct'))}")
        checks = (e.get("criteria_result") or {}).get("checks") or {}
        failed = [k for k, ok in checks.items() if not ok]
        if failed:
            lines.append("  gagal kriteria: "
                         + ", ".join(f"`{_esc(k)}`" for k in failed))

    lines += ["", "Approve/reject: login UI (Strategy Lab) atau perintah "
                 "/proposals di bot Telegram fund2. Deploy hanya dengan "
                 "approve owner (PRD 5.9)."]
    return "\n".join(lines)


def split_telegram(text: str, limit: int = 3900) -> list[str]:
    """Pecah laporan jadi beberapa pesan Telegram (< 4096 char)."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.splitlines():
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks
