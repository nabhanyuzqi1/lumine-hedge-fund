#!/usr/bin/env python3
"""Susun laporan backtest P2 yang dibaca owner (PRD 5.4).

Input : JSON hasil paper.walkforward (satu atau beberapa TF).
Output: docs/LAPORAN_BACKTEST_P2.md + docs/backtest_p2_equity_<tf>.svg

Kriteria lolos (dideklarasikan sebelum run, anti-overfit):
  1. agregat window uji: net profit > 0, profit factor > 1, expectancy > 0
  2. max drawdown gabungan <= 10% (ambang auto-halt PRD 5.6)
  3. jumlah trade window uji >= 30
  4. tidak lebih dari 50% window uji dengan PF < 1

Run:
  .venv/bin/python ../scripts/report_backtest_p2.py \
      --json ../docs/walkforward_p2_m5.json --tf M5 [--json2 ... --tf2 H1]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DOCS = BASE / "docs"

PASS = {
    "profit": "net profit window uji > 0",
    "pf": "profit factor > 1.0",
    "expectancy": "expectancy per trade > 0",
    "dd": "max drawdown gabungan <= 10%",
    "trades": "jumlah trade window uji >= 30",
    "windows": "maks 50% window uji dengan PF < 1",
}


def evaluate(report: dict) -> dict:
    agg = report["aggregate"]
    wins = [w for w in report["windows"]
            if (w["test_metrics"].get("profit_factor") or 0) > 1]
    checks = {
        "profit": (agg["stitched_net_profit_usd"] or 0) > 0,
        "pf": (agg.get("stitched_profit_factor") or 0) > 1,
        "expectancy": (agg.get("stitched_expectancy_usd") or 0) > 0,
        "dd": (agg["stitched_max_drawdown_pct"] or 1) <= 0.10,
        "trades": agg.get("stitched_trades", 0) >= 30,
        "windows": len(wins) >= len(report["windows"]) / 2,
    }
    return checks


def agg_extras(report: dict) -> dict:
    """Metrik agregat lintas window uji yang tidak dihitung walkforward."""
    all_trades = []
    pf_w, exp_w = [], []
    for w in report["windows"]:
        m = w["test_metrics"]
        if m.get("profit_factor") is not None:
            pf_w.append(m["profit_factor"])
        if m.get("expectancy_usd") is not None:
            exp_w.append(m["expectancy_usd"])
        all_trades.extend(m.get("trades_detail") or [])
    wins = [t for t in all_trades if t["profit"] > 0]
    losses = [t for t in all_trades if t["profit"] <= 0]
    gw = sum(t["profit"] for t in wins)
    gl = abs(sum(t["profit"] for t in losses))
    sessions: dict[str, int] = {}
    for t in all_trades:
        sessions[t.get("session", "-")] = sessions.get(t.get("session", "-"), 0) + 1
    return {
        "stitched_trades": len(all_trades),
        "stitched_winrate": round(len(wins) / len(all_trades), 4) if all_trades else None,
        "stitched_profit_factor": round(gw / gl, 3) if gl else None,
        "stitched_expectancy_usd": round(sum(t["profit"] for t in all_trades) / len(all_trades), 2)
        if all_trades else None,
        "stitched_expectancy_r": round(sum(t["r_multiple"] for t in all_trades
                                           if t.get("r_multiple") is not None)
                                       / max(1, len([t for t in all_trades
                                                     if t.get("r_multiple") is not None])), 3),
        "median_pf_window": sorted(pf_w)[len(pf_w) // 2] if pf_w else None,
        "windows_pf_below_1": len([p for p in pf_w if p < 1]),
        "sessions": sessions,
        "commission_total_usd": round(sum(t.get("commission_usd") or 0 for t in all_trades), 2),
    }


def equity_svg(curve: list[float], path: Path, *, label: str) -> None:
    """Kurva ekuiti sederhana tanpa dependensi (SVG statis)."""
    w, h, pad = 900, 320, 44
    lo, hi = min(curve), max(curve)
    span = (hi - lo) or 1.0
    pts = []
    for i, v in enumerate(curve):
        x = pad + (w - 2 * pad) * i / max(1, len(curve) - 1)
        y = h - pad - (h - 2 * pad) * (v - lo) / span
        pts.append((round(x, 1), round(y, 1)))
    poly = " ".join(f"{x},{y}" for x, y in pts)
    area = f"M {pts[0][0]},{h - pad} L " + poly + f" L {pts[-1][0]},{h - pad} Z"
    start, end, peak = curve[0], curve[-1], max(curve)
    dd_i = max(range(len(curve)), key=lambda i: peak_at(curve, i) - curve[i])
    color = "#0a7d33" if end >= start else "#b3261e"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" font-family="Inter,Arial,sans-serif">
<rect width="{w}" height="{h}" fill="#ffffff"/>
<path d="{area}" fill="{color}" opacity="0.08"/>
<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2"/>
<line x1="{pad}" y1="{h - pad}" x2="{w - pad}" y2="{h - pad}" stroke="#d0d0d0"/>
<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{h - pad}" stroke="#d0d0d0"/>
<text x="{pad}" y="{pad - 12}" font-size="14" fill="#222">{label}</text>
<text x="{pad}" y="{h - pad + 18}" font-size="12" fill="#555">{curve[0]:.0f}</text>
<text x="{w - pad - 60}" y="{h - pad + 18}" font-size="12" fill="#555">{end:.0f} USD</text>
<text x="{w - pad - 170}" y="{pad - 12}" font-size="12" fill="{color}">puncak {peak:.0f} USD</text>
</svg>
"""
    path.write_text(svg)


def peak_at(curve: list[float], i: int) -> float:
    return max(curve[:i + 1])


def render(report: dict, tf: str) -> str:
    agg = report["aggregate"]
    ex = agg_extras(report)
    report["aggregate"].update(ex)
    checks = evaluate(report)
    verdict = "LOLOS" if all(checks.values()) else "GAGAL"
    cm = report["config"].get("cost_model") or {}
    data = report.get("data", {})
    failed = [w for w in report["windows"]
              if (w["test_metrics"].get("profit_factor") or 0) < 1
              or (w["test_metrics"].get("expectancy_usd") or 0) < 0
              or (w["test_metrics"].get("max_drawdown_pct") or 0) > 0.10]
    lines = [
        f"# Laporan Backtest P2: {report['strategy']} v{report['version']} "
        f"({report['symbol']} {tf})",
        "",
        f"**Verdict: {verdict}** (kriteria dideklarasikan sebelum run, lihat bawah)",
        "",
        f"- Run ID: `{report['run_id']}`; data {data.get('start', '')[:10]} .. "
        f"{data.get('end', '')[:10]} ({data.get('bars', 0)} bar {tf}, sumber "
        f"Dukascopy m1 via scripts/fetch_dukascopy_m1.py)",
        f"- Walk-forward: latih {report['config'].get('train_months', 6)} bulan, "
        f"uji {report['config'].get('test_months', 1)} bulan, geser 1 bulan; "
        f"{agg['n_windows']} window uji",
        f"- Parameter dipilih HANYA dari window latih; yang dilaporkan hanya "
        f"hasil window uji (anti-overfit PRD 5.4)",
        "",
        "## Ringkasan window uji (gabungan)",
        "",
        "| Metrik | Nilai |",
        "| --- | --- |",
        f"| Trades | {ex['stitched_trades']} |",
        f"| Winrate | {ex['stitched_winrate']} |",
        f"| Profit factor | {ex['stitched_profit_factor']} |",
        f"| Expectancy | {ex['stitched_expectancy_usd']} USD/trade "
        f"({ex['stitched_expectancy_r']} R) |",
        f"| Net profit (ekuiti berantai) | {agg['stitched_net_profit_usd']} USD |",
        f"| Max drawdown gabungan | {agg['stitched_max_drawdown_usd']} USD "
        f"({agg['stitched_max_drawdown_pct']}) |",
        f"| Komisi total | {ex['commission_total_usd']} USD |",
        f"| Distribusi entry per sesi | {ex['sessions']} |",
        "",
        "## Kriteria lolos",
        "",
        "| Kriteria | Status |",
        "| --- | --- |",
        f"| {PASS['profit']} | {'PASS' if checks['profit'] else 'FAIL'} "
        f"({agg['stitched_net_profit_usd']} USD) |",
        f"| {PASS['pf']} | {'PASS' if checks['pf'] else 'FAIL'} "
        f"({ex['stitched_profit_factor']}) |",
        f"| {PASS['expectancy']} | {'PASS' if checks['expectancy'] else 'FAIL'} "
        f"({ex['stitched_expectancy_usd']} USD) |",
        f"| {PASS['dd']} | {'PASS' if checks['dd'] else 'FAIL'} "
        f"({agg['stitched_max_drawdown_pct']}) |",
        f"| {PASS['trades']} | {'PASS' if checks['trades'] else 'FAIL'} "
        f"({ex['stitched_trades']} trade) |",
        f"| {PASS['windows']} | {'PASS' if checks['windows'] else 'FAIL'} "
        f"({ex['windows_pf_below_1']}/{agg['n_windows']} window PF<1) |",
        "",
        "## Biaya terkalibrasi (PRD 5.2)",
        "",
        "Spread biaya = median Dukascopy per sesi x faktor koreksi "
        "(median HFM / median Dukascopy per sesi) x 1.20 (haircut).",
        "",
        "| Sesi | Duka (USD) | HFM (USD) | Faktor | Filter (USD) | Biaya fill (USD) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for s in ("asia", "london", "london_newyork", "newyork"):
        d = cm.get("duka_spread_by_session", {}).get(s)
        h = cm.get("hfm_spread_by_session", {}).get(s)
        f = cm.get("factor_by_session", {}).get(s)
        fl = cm.get("filter_spread_by_session", {}).get(s)
        c = cm.get("spread_by_session", {}).get(s)
        lines.append(f"| {s} | {d} | {h} | {f} | {fl} | {c} |")
    lines += [
        "",
        f"Komisi {cm.get('commission_per_lot_round_usd')} USD/lot round-turn; "
        f"slippage {cm.get('slippage_usd_per_fill')} USD per fill. "
        f"Catatan kalibrasi: {'; '.join(cm.get('notes', []))}",
        "",
        "## Hasil per window uji",
        "",
        "| # | Window uji | Trades | Winrate | PF | Expectancy | Max DD | Net | Catatan |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for w in report["windows"]:
        m = w["test_metrics"]
        lines.append(
            f"| {w['window_index'] + 1} | {w['test']['start'][:10]}..{w['test']['end'][:10]} "
            f"| {m.get('trades', 0)} | {m.get('winrate')} | {m.get('profit_factor')} "
            f"| {m.get('expectancy_usd')} | {m.get('max_drawdown_usd')} "
            f"({m.get('max_drawdown_pct')}) | {m.get('net_profit_usd')} | {w['note']} |")
    lines += [
        "",
        "## Kurva ekuiti (window uji, ekuiti berantai)",
        "",
        f"![kurva ekuiti](backtest_p2_equity_{tf.lower()}.svg)",
        "",
        "## Kapan strategi gagal",
        "",
    ]
    if failed:
        lines.append("Window uji dengan PF < 1, expectancy negatif, atau DD > 10%:")
        lines.append("")
        for w in failed:
            m = w["test_metrics"]
            lines.append(
                f"- Window {w['window_index'] + 1} ({w['test']['start'][:10]}.."
                f"{w['test']['end'][:10]}): PF {m.get('profit_factor')}, "
                f"expectancy {m.get('expectancy_usd')} USD, "
                f"DD {m.get('max_drawdown_pct')}, {w['note']}")
    else:
        lines.append("Tidak ada window uji dengan PF < 1 / expectancy negatif / DD > 10%.")
    lines += [
        "",
        f"Median PF antar window: {ex['median_pf_window']}. "
        f"Window profit: {agg['windows_profitable']}/{agg['n_windows']}.",
        "",
        "## Audit anti-overfitting",
        "",
        f"- Grid: {len(report['config']['grid'])} parameter, "
        f"{len(report['config']['grid'].get('breakout_buffer_usd', [])) * len(report['config']['grid'].get('rr', [])) * len(report['config']['grid'].get('min_range_usd', []))} kombinasi",
        f"- Total percobaan tercatat di `backtest_runs`: {agg['total_attempts']} "
        f"({agg['n_windows']} window x kombinasi + 1 test per window)",
        "- Parameter dipilih dari window latih; hasil window uji tidak pernah "
        "dipakai memilih parameter.",
        "",
        "## Reproduksi",
        "",
        "```",
        "cd ~/fund2/api",
        ".venv/bin/python ../scripts/fetch_dukascopy_m1.py --start 2024-11-01 --end 2026-11-21",
        ".venv/bin/python ../scripts/load_dukascopy_history.py --tfs M5 M15 H1",
        f".venv/bin/python -m paper.walkforward --tf {tf} --cost-model dukascopy \\",
        f"    --out-json ../docs/walkforward_p2_{tf.lower()}.json",
        "```",
        "",
        "Catatan: hasil backtest bukan jaminan performa live (PRD 5.4). "
        "Faktor koreksi HFM/Dukascopy dihitung dari sampel HFM yang masih "
        "pendek dan wajib dikalibrasi ulang setiap data HFM bertambah.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--tf", required=True)
    args = ap.parse_args()
    report = json.loads(Path(args.json).read_text())
    md = render(report, args.tf.upper())
    out_md = DOCS / f"LAPORAN_BACKTEST_P2_{args.tf.upper()}.md"
    out_md.write_text(md)
    equity_svg(report["aggregate"]["stitched_curve"],
               DOCS / f"backtest_p2_equity_{args.tf.lower()}.svg",
               label=f"Equity window uji ({args.tf.upper()}) - {report['strategy']}")
    ex = agg_extras(report)
    report["aggregate"].update(ex)
    checks = evaluate(report)
    print(f"{out_md} ditulis; verdict={'LOLOS' if all(checks.values()) else 'GAGAL'}")
    print(json.dumps({k: v for k, v in checks.items()}, indent=1))


if __name__ == "__main__":
    main()
