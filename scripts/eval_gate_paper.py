#!/usr/bin/env python3
"""Evaluasi gerbang paper (B2/G1, PRD v2.2 §8.4) untuk satu strategi.

Sumber data: tabel paper_orders (paper runner). Profit paper sudah net
spread+slippage pada fill; komisi round-turn didiskon terpisah di sini
(default 7.0 USD/lot, kalibrasi P2) agar "setelah biaya" konsisten dengan
model biaya backtest terkalibrasi (docs/LAPORAN_DOD_P2.md).

Rasio keputusan valid vs hold dibaca dari file JSONL audit keputusan agent
(satu JSON per baris: {"ts": ISO-8601, "decision": "order|close|hold|invalid",
"symbol": "...", "confidence": 0.0-1.0, "reason": "..."}). Jika file tidak
diberikan, metrik dilaporkan N/A — tidak pernah dipalsukan.

Pemakaian (dari repo root):
  api/.venv/bin/python scripts/eval_gate_paper.py --strategy llm_agent \
      [--decisions-json audit.jsonl] [--start 2026-11-24] [--end 2026-12-23]
      [--out docs/QA_F2LLM4_eval_gerbang]

Sumber trade:
  - default (auto): strategy llm/llm_agent -> tabel `orders` (ledger eksekusi
    demo MT5 via bridge; agent LLM tidak lewat paper runner). Strategi lain ->
    tabel `paper_orders`.
  - Pada sumber `orders`, bila payload close lapor profit 0.0 padahal
    entry/close price lengkap (bug EA BuildResultJson hardcode 0), profit
    dihitung ulang dari harga: (close-entry)*contract_size*volume*dir —
    rumus terverifikasi match dengan DEAL_PROFIT broker. Trade semacam itu
    ditandai profit_source="computed" dan dihitung terpisah di laporan;
    yang profit-nya tetap 0 (harga tak lengkap) ditandai "unknown".

Rasio keputusan valid vs hold:
  - --decisions-json (JSONL audit) bila diberikan; selain itu, pada sumber
    `orders`, dibaca dari kolom decision order_events (event AGENT_*); pada
    sumber paper -> N/A. Tidak pernah dipalsukan.

Output: <out>.json (metrik) + <out>.md (laporan owner-readable).
Exit code: 0 lulus / 2 gagal gerbang / 3 data belum cukup.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1] / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.ingest import session_of  # noqa: E402

SESSIONS = ("asia", "london", "london_newyork", "newyork")
CLOSED_STATUSES = ("CLOSED", "FILLED_THEN_CLOSED")

# Ambang gerbang B2/G1 (KEPUTUSAN_OWNER.md B2; PRD v2.2 §8.4).
GATE_DEFAULTS = {
    "min_working_days": 20,
    "min_trades": 100,
    "min_profit_factor": 1.3,
    "max_drawdown_pct": 5.0,
}
COMMISSION_PER_LOT_DEFAULT = 7.0  # USD/lot round-turn, kalibrasi P2


# ---------------------------------------------------------------- metrik murni

def profit_factor(profits: list[float]) -> float | None:
    """PF = gross profit / |gross loss| setelah biaya. None jika tak terdefinisi."""
    if not profits:
        return None
    gross_win = sum(p for p in profits if p > 0)
    gross_loss = sum(-p for p in profits if p < 0)
    if gross_loss == 0:
        return float("inf") if gross_win > 0 else None
    return gross_win / gross_loss


def max_drawdown(equity: list[float]) -> tuple[float, float]:
    """Kurva ekuitas berurutan (termasuk titik awal) -> (dd_usd, dd_pct dari peak)."""
    if not equity:
        return 0.0, 0.0
    peak = equity[0]
    max_dd = 0.0
    dd_pct = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
            dd_pct = (dd / peak * 100.0) if peak > 0 else 0.0
    return round(max_dd, 2), round(dd_pct, 2)


def working_days(dates: list[date]) -> list[date]:
    """Hari Senin-Jumat, unik, terurut."""
    return sorted({d for d in dates if d.weekday() < 5})


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def session_distribution(trades: list[dict]) -> dict:
    """Distribusi trade per sesi (app.ingest.session_of, UTC)."""
    dist = {s: {"trades": 0, "net": 0.0, "wins": 0} for s in SESSIONS}
    for t in trades:
        opened = t.get("opened_at")
        if opened is None:
            continue
        s = session_of(_to_utc(opened))
        if s not in dist:
            dist[s] = {"trades": 0, "net": 0.0, "wins": 0}
        pnl = float(t.get("net_profit", t["profit"]))
        dist[s]["trades"] += 1
        dist[s]["net"] = round(dist[s]["net"] + pnl, 2)
        if pnl > 0:
            dist[s]["wins"] += 1
    for s in dist:
        n = dist[s]["trades"]
        dist[s]["winrate"] = round(dist[s]["wins"] / n, 4) if n else None
        dist[s]["pf"] = profit_factor(
            [float(t.get("net_profit", t["profit"])) for t in trades
             if t.get("opened_at") is not None
             and session_of(_to_utc(t["opened_at"])) == s]
        )
    return dist


def decision_ratio(decisions: list[dict]) -> dict | None:
    """Rasio keputusan valid (order/close) vs hold vs invalid dari audit JSONL."""
    if not decisions:
        return None
    counts = defaultdict(int)
    for d in decisions:
        counts[str(d.get("decision", "invalid")).lower()] += 1
    valid = counts["order"] + counts["close"]
    total = sum(counts.values())
    return {
        "total": total,
        "valid": valid,
        "hold": counts["hold"],
        "invalid": counts["invalid"],
        "valid_ratio": round(valid / total, 4) if total else None,
    }


# ---------------------------------------------------------------- evaluasi

def net_profit(t: dict, commission_per_lot: float) -> float:
    """Profit paper (net spread+slippage) dikurangi komisi round-turn."""
    return round(float(t["profit"]) - commission_per_lot * float(t["volume"]), 2)


def evaluate(
    trades: list[dict],
    decisions: list[dict] | None,
    starting_balance: float,
    commission_per_lot: float = COMMISSION_PER_LOT_DEFAULT,
    thresholds: dict | None = None,
) -> dict:
    th = {**GATE_DEFAULTS, **(thresholds or {})}
    closed = [t for t in trades if t.get("status") in CLOSED_STATUSES and t.get("profit") is not None]
    for t in closed:
        t["net_profit"] = net_profit(t, commission_per_lot)

    equity = [starting_balance] + [starting_balance + sum(float(x["net_profit"]) for x in closed[: i + 1]) for i in range(len(closed))]
    dd_usd, dd_pct = max_drawdown(equity)
    profits = [float(t["net_profit"]) for t in closed]
    pf = profit_factor(profits)

    trade_days = [t["closed_at"].date() if isinstance(t.get("closed_at"), datetime) else t.get("closed_at") for t in closed]
    decision_days = []
    for d in decisions or []:
        ts = d.get("ts")
        if isinstance(ts, datetime):
            decision_days.append(_to_utc(ts).date())
        elif isinstance(ts, date):
            decision_days.append(ts)
    days = working_days([d for d in trade_days + decision_days if isinstance(d, date)])

    by_symbol: dict[str, dict] = {}
    for t in closed:
        sym = t.get("symbol", "?")
        b = by_symbol.setdefault(sym, {"trades": 0, "net": 0.0, "profits": []})
        b["trades"] += 1
        b["net"] = round(b["net"] + float(t["net_profit"]), 2)
        b["profits"].append(float(t["net_profit"]))
    for sym, b in by_symbol.items():
        b["pf"] = profit_factor(b.pop("profits"))

    result = {
        "strategy": None,  # diisi pemanggil
        "period": None,  # diisi pemanggil
        "starting_balance": starting_balance,
        "commission_per_lot": commission_per_lot,
        "thresholds": th,
        "metrics": {
            "working_days": len(days),
            "working_day_list": [str(d) for d in days],
            "trades": len(closed),
            "net_profit": round(sum(profits), 2),
            "profit_factor": pf,
            "winrate": round(sum(1 for p in profits if p > 0) / len(profits), 4) if profits else None,
            "max_drawdown_usd": dd_usd,
            "max_drawdown_pct": dd_pct,
            "ending_equity": round(equity[-1], 2) if equity else starting_balance,
            "by_symbol": by_symbol,
            "by_session": session_distribution(closed),
            "decisions": decision_ratio(decisions or []),
            "profit_source_counts": {
                s: sum(1 for t in closed if t.get("profit_source") == s)
                for s in {t.get("profit_source") for t in closed} if s
            },
        },
    }
    m = result["metrics"]
    result["gate"] = {
        "duration": {"pass": m["working_days"] >= th["min_working_days"],
                     "detail": f"{m['working_days']} hari kerja (min {th['min_working_days']})"},
        "volume": {"pass": m["trades"] >= th["min_trades"],
                   "detail": f"{m['trades']} trade closed (min {th['min_trades']})"},
        "profit_factor": {"pass": pf is not None and pf >= th["min_profit_factor"],
                          "detail": f"PF {pf} (min {th['min_profit_factor']}) setelah biaya"},
        "max_drawdown": {"pass": m["max_drawdown_pct"] <= th["max_drawdown_pct"],
                         "detail": f"max DD {m['max_drawdown_pct']}% (maks {th['max_drawdown_pct']}%)"},
    }
    preconditions_ok = m["working_days"] >= th["min_working_days"] and m["trades"] >= th["min_trades"]
    if not closed or not preconditions_ok:
        # Durasi/volume belum terpenuhi: gerbang belum bisa dinilai, bukan gagal.
        result["verdict"] = "DATA_BELUM_CUKUP"
    elif all(c["pass"] for c in result["gate"].values()):
        result["verdict"] = "LULUS"
    else:
        result["verdict"] = "GAGAL"
    return result


# ---------------------------------------------------------------- render

def render_markdown(r: dict) -> str:
    m = r["metrics"]
    lines = [
        f"# Evaluasi Gerbang Paper — {r['strategy']}",
        "",
        f"Periode: {r['period']}",
        f"Ekuitas awal: {r['starting_balance']}; komisi {r['commission_per_lot']} USD/lot round-turn.",
        "",
        "## Verdict gerbang",
        "",
        f"**{r['verdict']}**",
        "",
        "| Kriteria | Status | Detail |",
        "| --- | --- | --- |",
    ]
    label = {"duration": "Hari kerja >= 20", "volume": "Trade >= 100",
             "profit_factor": "PF >= 1.3 setelah biaya", "max_drawdown": "Max DD <= 5%"}
    for k, c in r["gate"].items():
        lines.append(f"| {label[k]} | {'PASS' if c['pass'] else 'FAIL'} | {c['detail']} |")
    lines += [
        "",
        "## Metrik",
        "",
        f"- Trades: {m['trades']}; net profit: {m['net_profit']}; ekuitas akhir: {m['ending_equity']}",
        f"- Winrate: {m['winrate']}; profit factor: {m['profit_factor']}",
        f"- Max drawdown: {m['max_drawdown_usd']} USD ({m['max_drawdown_pct']}%)",
        f"- Hari kerja teramati: {m['working_days']}",
        "",
        "## Per simbol",
        "",
        "| Simbol | Trades | Net | PF |",
        "| --- | --- | --- | --- |",
    ]
    for sym, b in sorted(m["by_symbol"].items()):
        lines.append(f"| {sym} | {b['trades']} | {b['net']} | {b['pf']} |")
    lines += ["", "## Per sesi (UTC)", "",
              "| Sesi | Trades | Net | Winrate | PF |", "| --- | --- | --- | --- | --- |"]
    for s in SESSIONS:
        d = m["by_session"].get(s, {})
        lines.append(f"| {s} | {d.get('trades', 0)} | {d.get('net', 0.0)} | {d.get('winrate')} | {d.get('pf')} |")
    dec = m["decisions"]
    lines += ["", "## Keputusan valid vs hold", ""]
    if dec:
        lines.append(
            f"- Total {dec['total']}: valid {dec['valid']} (ratio {dec['valid_ratio']}), "
            f"hold {dec['hold']}, invalid {dec['invalid']}"
        )
    else:
        lines.append("- N/A (audit keputusan belum tersedia — tidak dipalsukan)")
    psc = m.get("profit_source_counts")
    if psc:
        lines += ["", "## Sumber profit (data quality)", ""]
        lines.append(
            f"- reported: {psc.get('reported', 0)}; computed: {psc.get('computed', 0)} "
            f"(EA lapor 0, dihitung dari harga); unknown: {psc.get('unknown', 0)}"
        )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- DB + CLI

def fetch_trades(conn, strategy: str, start: date | None, end: date | None) -> list[dict]:
    import psycopg  # noqa: F401  (dipakai via conn)

    q = ("select symbol, side, volume, sl, tp, status, profit, reason, "
         "opened_at, closed_at from paper_orders where strategy = %s")
    params: list = [strategy]
    if start:
        q += " and closed_at >= %s"
        params.append(start)
    if end:
        q += " and closed_at < %s"
        params.append(end + timedelta_days(1))
    q += " order by closed_at"
    cur = conn.execute(q, tuple(params))
    rows = cur.fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------- sumber orders (ledger demo)

def close_profit_from_prices(symbol: str, side: str, volume: float,
                             entry_price: float | None,
                             close_price: float | None,
                             contract_size: float) -> float | None:
    """Profit close dari harga (rumus = DEAL_PROFIT broker, terverifikasi).

    None bila harga entry/close tidak lengkap — pemanggil menandai unknown.
    """
    if entry_price is None or close_price is None or not volume:
        return None
    direction = 1.0 if side == "BUY" else -1.0
    return round((close_price - entry_price) * contract_size * volume * direction, 2)


def orders_row_to_trade(row: dict, contract_size: float) -> dict:
    """Baris orders (+payload close) -> dict trade ala paper_orders.

    profit_source: 'reported' (broker/reconciler), 'computed' (dihitung dari
    harga karena EA lapor 0), 'unknown' (profit 0 tanpa harga lengkap).
    """
    payload = row.get("close_payload") or {}
    profit = payload.get("profit")
    source = "reported"
    if profit is None or profit == 0:
        # EA BuildResultJson hardcode 0.0 utk CLOSE: laporan 0 tak tepercaya.
        # Coba hitung dari harga; bila tak lengkap -> unknown (jangan karang).
        computed = close_profit_from_prices(
            row["symbol"], row["side"], float(row["volume"]),
            float(row["price_filled"]) if row.get("price_filled") is not None else None,
            float(payload["close_price"]) if payload.get("close_price") is not None else None,
            contract_size,
        )
        if computed is not None:
            profit, source = computed, "computed"
        else:
            profit, source = 0.0, "unknown"
    status = row["status"]
    return {
        "symbol": row["symbol"],
        "side": row["side"],
        "volume": float(row["volume"]),
        "sl": row.get("sl"),
        "tp": row.get("tp"),
        "status": "CLOSED" if status == "FILLED_THEN_CLOSED" else status,
        "profit": float(profit),
        "profit_source": source,
        "reason": payload.get("reason", ""),
        "opened_at": row.get("created_at"),
        "closed_at": row.get("resolved_at"),
    }


def fetch_trades_orders(conn, strategy: str, start: date | None,
                        end: date | None) -> list[dict]:
    """Trade strategi llm dari tabel orders (eksekusi demo MT5 via bridge)."""
    cur = conn.execute(
        "select value from settings where key = 'symbol_specs'")
    specs_row = cur.fetchone()
    specs = (specs_row[0] if isinstance(specs_row, tuple) else
             (specs_row or {}).get("value")) or {}
    default_cs = float((specs.get("XAUUSD") or {}).get("contract_size", 100.0))

    q = """
        select o.symbol, o.side, o.volume, o.sl, o.tp, o.status,
               o.price_filled, o.created_at, o.resolved_at,
               cp.payload as close_payload
        from orders o
        left join lateral (
            select e.payload from order_events e
            where e.order_id = o.id and e.to_status = 'FILLED_THEN_CLOSED'
            order by e.id desc limit 1
        ) cp on true
        where o.strategy = %s
    """
    params: list = [strategy]
    if start:
        q += " and o.created_at >= %s"
        params.append(start)
    if end:
        q += " and o.created_at < %s"
        params.append(end + timedelta_days(1))
    q += " order by o.created_at"
    cur = conn.execute(q, tuple(params))
    rows = [dict(r) for r in cur.fetchall()]
    # contract_size per simbol (XAUUSD 100, BTCUSD 1 — spec_verified).
    out = []
    for r in rows:
        cs = float((specs.get(r["symbol"]) or {}).get(
            "contract_size", default_cs))
        out.append(orders_row_to_trade(r, cs))
    return out


def fetch_decisions_db(conn, start: date | None, end: date | None) -> list[dict]:
    """Audit keputusan agent dari kolom decision order_events (event AGENT_*)."""
    q = ("select decision, created_at from order_events "
         "where decision is not null")
    params: list = []
    if start:
        q += " and created_at >= %s"
        params.append(start)
    if end:
        q += " and created_at < %s"
        params.append(end + timedelta_days(1))
    q += " order by created_at"
    out = []
    for r in conn.execute(q, tuple(params)).fetchall():
        d = r[0] if isinstance(r, tuple) else dict(r)["decision"]
        ts = r[1] if isinstance(r, tuple) else dict(r)["created_at"]
        if isinstance(d, str):
            d = json.loads(d)
        # kolom decision menyimpan {"kind": "order|close|hold|invalid", ...};
        # decision_ratio membaca key "decision".
        out.append({"ts": ts, "decision": d.get("kind"), **d})
    return out


def timedelta_days(n: int):
    from datetime import timedelta
    return timedelta(days=n)


def load_decisions(path: str | None) -> list[dict]:
    if not path:
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            ts = d.get("ts")
            if isinstance(ts, str):
                d["ts"] = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            out.append(d)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--source", choices=("auto", "paper", "orders"), default="auto",
                    help="sumber trade: auto = orders utk llm/llm_agent, "
                         "paper_orders untuk strategi lain")
    ap.add_argument("--db-url", default=None, help="default: DATABASE_URL dari api/.env")
    ap.add_argument("--decisions-json", default=None, help="JSONL audit keputusan agent")
    ap.add_argument("--start", default=None, help="YYYY-MM-DD (inclusive, pada closed_at)")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (exclusive)")
    ap.add_argument("--starting-balance", type=float, default=10000.0)
    ap.add_argument("--commission-per-lot", type=float, default=COMMISSION_PER_LOT_DEFAULT)
    ap.add_argument("--min-working-days", type=int, default=GATE_DEFAULTS["min_working_days"])
    ap.add_argument("--min-trades", type=int, default=GATE_DEFAULTS["min_trades"])
    ap.add_argument("--min-profit-factor", type=float, default=GATE_DEFAULTS["min_profit_factor"])
    ap.add_argument("--max-drawdown-pct", type=float, default=GATE_DEFAULTS["max_drawdown_pct"])
    ap.add_argument("--out", default=None, help="path dasar output (default: docs/QA_eval_gerbang_<strategy>)")
    args = ap.parse_args()

    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None

    if args.db_url:
        db_url = args.db_url
    else:
        from dotenv import load_dotenv
        load_dotenv(API_DIR / ".env")
        db_url = os_environ_get("DATABASE_URL")
    import psycopg
    from psycopg.rows import dict_row
    source = args.source
    if source == "auto":
        source = "orders" if args.strategy in ("llm", "llm_agent") else "paper"
    with psycopg.connect(db_url, autocommit=True, row_factory=dict_row) as conn:
        if source == "orders":
            trades = fetch_trades_orders(conn, args.strategy, start, end)
            decisions = (load_decisions(args.decisions_json)
                         if args.decisions_json
                         else fetch_decisions_db(conn, start, end))
        else:
            trades = fetch_trades(conn, args.strategy, start, end)
            decisions = load_decisions(args.decisions_json)

    result = evaluate(
        trades, decisions, args.starting_balance, args.commission_per_lot,
        thresholds={"min_working_days": args.min_working_days, "min_trades": args.min_trades,
                    "min_profit_factor": args.min_profit_factor, "max_drawdown_pct": args.max_drawdown_pct},
    )
    result["strategy"] = args.strategy
    result["period"] = f"{start or 'awal'} .. {end or 'sekarang'}"
    result["source"] = source
    result["trade_count_in_source"] = len(trades)

    out_base = args.out or str(API_DIR.parent / "docs" / f"QA_eval_gerbang_{args.strategy}")
    Path(out_base).parent.mkdir(parents=True, exist_ok=True)
    with open(out_base + ".json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(out_base + ".md", "w", encoding="utf-8") as f:
        f.write(render_markdown(result))

    print(render_markdown(result))
    if result["verdict"] == "LULUS":
        return 0
    if result["verdict"] == "GAGAL":
        return 2
    return 3


def os_environ_get(key: str) -> str:
    import os
    return os.environ[key]


if __name__ == "__main__":
    sys.exit(main())
