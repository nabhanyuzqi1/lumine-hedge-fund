#!/usr/bin/env python3
"""Laporan mingguan agent LLM ke owner (Telegram), t_f2llm4.

Menjalankan evaluasi gerbang paper untuk strategi 'llm' (sumber tabel orders),
mengirim ringkasan ke Telegram owner (env TELEGRAM_BOT_TOKEN/TELEGRAM_OWNER_ID
dari api/.env), dan menyimpan laporan .md/.json di docs/.

Pemakaian (dari repo root):
  api/.venv/bin/python scripts/llm_weekly_report.py [--start 2026-11-24] \
      [--end 2026-12-01] [--out docs/QA_F2LLM4_eval_gerbang_minggu2]

Tanpa --start: otomatis 7 hari kalender terakhir (end = kemarin UTC).
Exit 0 bila pesan terkirim (verdict apapun), 1 bila gagal kirim.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import eval_gate_paper as eg  # noqa: E402

STRATEGY = "llm"


def load_env() -> dict:
    env = {}
    for line in (BASE / "api" / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v
    return env


def tg_send(token: str, chat_id: str, text: str) -> None:
    import urllib.request

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({
        "chat_id": chat_id, "text": text,
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        out = json.loads(resp.read())
        if not out.get("ok"):
            raise RuntimeError(f"telegram ok=false: {out}")


def notable_decisions(decisions: list[dict], limit: int = 5) -> list[str]:
    """Keputusan penting minggu ini: order/close/invalid terakhir + reasoning."""
    important = [d for d in decisions if d.get("decision") in ("order", "close", "invalid")]
    lines = []
    for d in important[-limit:]:
        reason = str(d.get("reasoning") or "").replace("\n", " ")[:220]
        lines.append(f"- {d.get('decision')} {d.get('symbol') or '-'} "
                     f"(conf {d.get('confidence')}): {reason}")
    return lines


def build_message(result: dict, decisions: list[dict]) -> str:
    m = result["metrics"]
    g = result["gate"]
    lines = [
        f"📊 Laporan mingguan agent LLM (paper, t_f2llm4)",
        f"Periode: {result['period']} | Verdict: {result['verdict']}",
        "",
        f"• Hari kerja: {m['working_days']}/20 | Trade closed: {m['trades']}/100",
        f"• PF setelah biaya: {m['profit_factor']:.2f} (min 1.3)",
        f"• Max DD: {m['max_drawdown_pct']:.2f}% (maks 5%) | Net: {m['net_profit']:+.2f} USD",
        f"• Winrate: {m['winrate']}",
        f"• Keputusan: valid {m['decisions']['valid']}/{m['decisions']['total']} "
        f"(hold {m['decisions']['hold']}, invalid {m['decisions']['invalid']})",
        f"• Simbol: " + ", ".join(
            f"{s}: {b['trades']} trade, net {b['net']:+.2f}"
            for s, b in sorted(m["by_symbol"].items())) or "-",
        f"• Durasi {'PASS' if g['duration']['pass'] else 'FAIL'}; "
        f"volume {'PASS' if g['volume']['pass'] else 'FAIL'}; "
        f"PF {'PASS' if g['profit_factor']['pass'] else 'FAIL'}; "
        f"DD {'PASS' if g['max_drawdown']['pass'] else 'FAIL'}",
    ]
    psc = m.get("profit_source_counts")
    if psc:
        lines.append(f"• Profit: reported {psc.get('reported', 0)}, "
                     f"computed {psc.get('computed', 0)}, unknown {psc.get('unknown', 0)}")
    lines.append("")
    lines.append("Keputusan penting terakhir:")
    nd = notable_decisions(decisions)
    lines.extend(nd if nd else ["- (tidak ada keputusan order/close minggu ini)"])
    lines.append("")
    lines.append("Live tetap OFF sampai D1 + approval owner terpisah.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default=None, help="YYYY-MM-DD inclusive (created_at)")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD exclusive")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    end = date.fromisoformat(args.end) if args.end else datetime.now(timezone.utc).date()
    start = date.fromisoformat(args.start) if args.start else end - timedelta(days=7)

    from dotenv import load_dotenv
    load_dotenv(BASE / "api" / ".env")
    import os
    db_url = os.environ["DATABASE_URL"]
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(db_url, autocommit=True, row_factory=dict_row) as conn:
        trades = eg.fetch_trades_orders(conn, STRATEGY, start, end)
        decisions = eg.fetch_decisions_db(conn, start, end)

    result = eg.evaluate(trades, decisions, 10000.0,
                         thresholds=dict(eg.GATE_DEFAULTS))
    result["strategy"] = STRATEGY
    result["period"] = f"{start} .. {end}"
    result["source"] = "orders"
    result["trade_count_in_source"] = len(trades)

    out_base = args.out or str(BASE / "docs" / f"QA_F2LLM4_eval_gerbang_minggu_{end}")
    Path(out_base).parent.mkdir(parents=True, exist_ok=True)
    Path(out_base + ".json").write_text(
        json.dumps(result, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    Path(out_base + ".md").write_text(eg.render_markdown(result), encoding="utf-8")

    msg = build_message(result, decisions)
    env = load_env()
    token, chat = env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_OWNER_ID", "")
    if not token or not chat:
        print("TELEGRAM_BOT_TOKEN/TELEGRAM_OWNER_ID kosong — laporan disimpan, TIDAK terkirim")
        print(msg)
        return 1
    tg_send(token, chat, msg)
    print(f"laporan terkirim: {out_base}.md/.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
