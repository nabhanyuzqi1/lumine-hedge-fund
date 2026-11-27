"""Walk-forward runner + backtest_runs registry (PRD 5.4, fase P2).

Skema window [USULAN]: latih 6 bulan / uji 1 bulan, geser 1 bulan, uji pada
batas bulan kalender. Aturan anti-overfitting PRD 5.4:

  1. Parameter DIPILIH hanya dari hasil window latih (grid kecil, deterministik).
  2. Yang dilaporkan hanya hasil window uji (parameter tidak pernah melihat uji).
  3. SEMUA percobaan parameter (latih + uji) dicatat ke tabel ``backtest_runs``
     dengan ``run_id`` yang sama, sehingga jumlah percobaan terlihat/teraudit.

Aturan pemilihan parameter di window latih (deterministik, tanpa RNG):
  - Kandidat dengan trades >= MIN_TRADES_TRAIN dinilai lebih dulu.
  - Urutan: expectancy_r tertinggi, lalu profit_factor tertinggi, lalu trades
    terbanyak; seri dipecah oleh urutan grid (kombinasi pertama menang).

Realitas data (22 Nov 2026): XAUUSD H1 tersedia 19 Jan-20 Nov 2026 (~10 bulan),
M5 baru sejak 27 Okt, M15 sejak 7 Sep. Walk-forward 6+1 bulan saat ini hanya
bisa dijalankan di H1; jalankan ulang di M5/M15 begitu crawler P2 mengirim
sejarah panjang (DoD P2: backtest 2 tahun data).

Run:
  .venv/bin/python -m paper.walkforward --symbol XAUUSD --tf H1
  .venv/bin/python -m paper.walkforward --tf M15 --train-months 2 --test-months 1
  .venv/bin/python -m paper.walkforward --tf H1 --dry-run   # tanpa tulis DB
  .venv/bin/python -m paper.walkforward --verify <run_id>   # reproducibility

PRD v2.2 §8.2 (t_f2v22a19): setiap run mencatat preflight data quality
(gap/duplicate/missing/bad tick/survivorship), provenance (sumber, periode,
timezone, checksum data, tgl unduh, commit hash, hash modul, dependency,
config hash, random seed), execution model (swap/latency/rejection/partial
fill/market closure), dan baseline pembanding (buy&hold + random entry
ber-seed). --verify memuat ulang run dari backtest_runs dan menghitung ulang
seluruh metrik dari config/data hash untuk membuktikan reproducibility.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from app import db
from paper.backtest import (
    SPREAD_DEFAULT,
    SLIPPAGE_DEFAULT,
    canonical_tf,
    run_backtest,
    to_utc_candles,
)
from paper.baseline import buy_and_hold, random_entry
from paper.costs import CostModel
from paper.execution import ExecutionModel, default_execution_model
from paper.preflight import run_preflight
from paper.provenance import code_provenance, config_hash, data_provenance
from paper.runner import db_timezone_offset_h
from strategies import btc_range_breakout, london_breakout, mean_reversion

DEFAULT_SEED = 20261124  # seed default; dicatat di config (PRD §8.2)


async def _ensure_pool() -> None:
    """init_pool hanya bila pool belum terbentuk (aman dipanggil berulang,
    tidak menutup pool yang sudah dipakai pemanggil/conftest)."""
    try:
        db.pool()
    except RuntimeError:
        await db.init_pool()



STRATEGIES = {
    london_breakout.STRATEGY_ID: london_breakout,
    mean_reversion.STRATEGY_ID: mean_reversion,
    btc_range_breakout.STRATEGY_ID: btc_range_breakout,
}

# Contract size per simbol (multipair P2): XAUUSD 100 oz/lot, BTCUSD 1 BTC/lot
# (t_fmp1 verifikasi deal live). Simbol lain fallback 100.0.
CONTRACT_SIZE_BY_SYMBOL = {"BTCUSD": 1.0}


def contract_size_for(symbol: str) -> float:
    return CONTRACT_SIZE_BY_SYMBOL.get(symbol, 100.0)

TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}

# Grid parameter kecil dan berprinsip (12 kombinasi per strategi): tiap
# kombinasi adalah satu percobaan yang dicatat di backtest_runs. Grid besar =
# jumlah percobaan besar = flag overfitting di laporan.
PARAM_GRIDS: dict[str, dict[str, list]] = {
    "london_breakout": {
        "breakout_buffer_usd": [0.10, 0.30],
        "rr": [1.0, 1.5, 2.0],
        "min_range_usd": [0.50, 1.00],
    },
    "mean_reversion": {
        "num_std": [2.0, 2.5, 3.0],
        "min_rr": [0.6, 1.0],
        "reentry_buffer_usd": [0.10, 0.30],
    },
    "btc_range_breakout": {
        "atr_sl_mult": [1.0, 2.0],
        "rr": [1.0, 1.5, 2.0],
        "range_lookback": [24, 48],
    },
}
PARAM_GRID = PARAM_GRIDS["london_breakout"]  # kompatibilitas impor lama

MIN_TRADES_TRAIN = 5  # kandidat di bawah ini dianggap sampel terlalu kecil


@dataclass(frozen=True)
class Window:
    train_start: datetime
    train_end: datetime  # == test_start
    test_start: datetime
    test_end: datetime


# ---------------------------------------------------------------- kalender


def month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def add_months(dt: datetime, months: int) -> datetime:
    index = dt.year * 12 + (dt.month - 1) + months
    return dt.replace(year=index // 12, month=index % 12 + 1)


def plan_windows(data_start: datetime, data_end: datetime, *,
                 train_months: int = 6, test_months: int = 1,
                 step_months: int = 1) -> list[Window]:
    """Window uji di batas bulan; latih = n bulan kalender sebelum uji.

    Window dilewati bila window latih tidak sepenuhnya berada di dalam data
    (train_start >= data_start) dan dipotong bila data berakhir di tengah
    window uji (ditandai 'partial' di laporan).
    """
    if data_start is None or data_end is None or data_end <= data_start:
        return []
    windows: list[Window] = []
    first_test = add_months(month_start(data_start), train_months)
    while first_test < data_end:
        train_start = add_months(first_test, -train_months)
        if train_start >= data_start:
            windows.append(Window(
                train_start=train_start, train_end=first_test,
                test_start=first_test, test_end=add_months(first_test, test_months)))
        first_test = add_months(first_test, step_months)
    return windows


def expand_grid(grid: dict[str, list] | None = None) -> list[dict]:
    """Kartesian grid dalam urutan deterministik (urutan deklarasi dict)."""
    grid = PARAM_GRID if grid is None else grid
    combos = [{}]
    for key, values in grid.items():
        combos = [{**combo, key: value} for combo in combos for value in values]
    return combos


# ---------------------------------------------------------------- pemilihan


def _rank(result: dict) -> tuple:
    pf = result.get("profit_factor")
    pf = 0.0 if pf is None else float(pf)
    er = result.get("expectancy_r")
    er = float("-inf") if er is None else float(er)
    return (er, pf, result.get("trades", 0))


def select_best(train_rows: list[dict]) -> dict:
    """Pilih parameter terbaik dari hasil window latih (lihat docstring modul)."""
    if not train_rows:
        raise ValueError("tidak ada hasil latih untuk dipilih")
    full = [r for r in train_rows if r["metrics"].get("trades", 0) >= MIN_TRADES_TRAIN]
    pool = full or train_rows
    best = pool[0]
    for row in pool[1:]:
        if _rank(row["metrics"]) > _rank(best["metrics"]):
            best = row
    return best


def _failure_note(metrics: dict) -> str:
    """Catatan kapan strategi gagal (PRD 5.4: laporan menyebut kegagalan)."""
    if metrics.get("trades", 0) == 0:
        return "GAGAL: tidak ada trade di window uji"
    pf = metrics.get("profit_factor")
    if pf is not None and pf < 1.0:
        return f"GAGAL: profit factor {pf} < 1 setelah biaya"
    if (metrics.get("expectancy_usd") or 0) < 0:
        return f"GAGAL: expectancy {metrics['expectancy_usd']} USD per trade"
    if (metrics.get("max_drawdown_pct") or 0) > 0.10:
        return f"awas: max drawdown {metrics['max_drawdown_pct']:.1%} > 10%"
    return "OK"


# ---------------------------------------------------------------- registry


def _metrics_json(result: dict, *, keep_trades: bool) -> dict:
    metrics = {k: v for k, v in result.items() if k not in ("meta",)}
    if not keep_trades:
        metrics.pop("trades_detail", None)
    return metrics


async def record_run(conn, *, run_id: str, window_index: int, role: str, window: Window,
                     symbol: str, tf: str, params: dict, config: dict, metrics: dict,
                     selected: bool, note: str | None,
                     strategy_id: str, strategy_version: str) -> None:
    await conn.execute(
        """
        INSERT INTO backtest_runs (run_id, strategy_id, strategy_version, symbol,
                                   timeframe, role, window_index, train_start, train_end,
                                   test_start, test_end, params, config, metrics,
                                   selected, note)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (run_id, strategy_id, strategy_version, symbol, canonical_tf(tf), role,
         window_index, window.train_start, window.train_end,
         window.test_start, window.test_end,
         json.dumps(params), json.dumps(config), json.dumps(metrics, default=str),
         selected, note),
    )


# ---------------------------------------------------------------- runner


def _slice(candles: list[dict], start: datetime, end: datetime) -> list[dict]:
    return [c for c in candles if start <= c["ts"] < end]


def run_walkforward(candles: list[dict], *, tf: str, symbol: str = "XAUUSD",
                    windows: list[Window], grid: dict[str, list] | None = None,
                    equity0: float = 10000.0, spread: float = SPREAD_DEFAULT,
                    slippage: float = SLIPPAGE_DEFAULT,
                    cost_model: CostModel | None = None,
                    strategy=london_breakout,
                    data_end: datetime | None = None,
                    contract_size: float | None = None,
                    execution: ExecutionModel | None = None,
                    seed: int | None = None) -> dict:
    """Jalankan walk-forward murni (tanpa I/O). Tulis DB dilakukan pemanggil.

    cost_model: biaya terkalibrasi PRD 5.2 (paper/costs.py); bila None pakai
    biaya konstan spread/slippage. strategy: modul strategi dari
    paper.walkforward.STRATEGIES. contract_size: unit per lot simbol
    (default: peta CONTRACT_SIZE_BY_SYMBOL). execution: ExecutionModel PRD
    v2.2 §8.2 (swap/latency/rejection/partial fill/closure); None = legacy.
    seed: random seed run (dicatat di config; jalur inti deterministik tanpa
    RNG - seed dipakai baseline random entry).
    """
    tf_seconds = TF_SECONDS[canonical_tf(tf)]
    if contract_size is None:
        contract_size = contract_size_for(symbol)
    grid = grid if grid is not None else PARAM_GRIDS[strategy.STRATEGY_ID]
    combos = expand_grid(grid)
    config = {
        "symbol": symbol, "tf": canonical_tf(tf), "tf_seconds": tf_seconds,
        "contract_size": contract_size,
        "train_months_test": None,  # diisi per window dari bounds
        "equity0": equity0, "spread_usd": spread,
        "slippage_usd_per_fill": slippage,
        "cost_model": cost_model.as_dict() if cost_model else None,
        "grid": grid,
        "min_trades_train": MIN_TRADES_TRAIN,
        "selection": "expectancy_r > profit_factor > trades (kandidat trades >= "
                     f"{MIN_TRADES_TRAIN} diprioritaskan)",
        "execution": execution.as_dict() if execution else None,
        "seed": seed,
    }
    report: dict = {
        "run_id": str(uuid.uuid4()), "strategy": strategy.STRATEGY_ID,
        "version": strategy.STRATEGY_VERSION, "symbol": symbol, "tf": canonical_tf(tf),
        "config": config, "windows": [], "attempts_total": 0,
    }
    balance = equity0
    for index, window in enumerate(windows):
        train = _slice(candles, window.train_start, window.train_end)
        test = _slice(candles, window.test_start, window.test_end)
        train_rows = []
        ctx_bars = getattr(strategy, "CONTEXT_BARS", 0)
        for combo in combos:
            params = strategy.StrategyParams(tf_seconds=tf_seconds, **combo)
            result = run_backtest(train, tf_seconds=tf_seconds, equity0=equity0,
                                  spread=spread, slippage=slippage, params=params,
                                  cost_model=cost_model, strategy=strategy,
                                  symbol=symbol, contract_size=contract_size,
                                  context_bars=ctx_bars, execution=execution)
            train_rows.append({
                "params": {**asdict(params)},
                "metrics": _metrics_json(result, keep_trades=False),
                "combo": combo,
            })
        chosen = select_best(train_rows)
        chosen_params = strategy.StrategyParams(tf_seconds=tf_seconds, **chosen["combo"])

        # Window uji dijalankan dengan ekuiti berantai (compound) agar kurva
        # ekuiti gabungan realistis; metrik per window tetap dilaporkan sendiri.
        test_result = run_backtest(test, tf_seconds=tf_seconds, equity0=balance,
                                   spread=spread, slippage=slippage, params=chosen_params,
                                   cost_model=cost_model, strategy=strategy,
                                   symbol=symbol, contract_size=contract_size,
                                   context_bars=ctx_bars, execution=execution)
        balance = test_result["final_balance"]
        partial = data_end is not None and window.test_end > data_end
        entry = {
            "window_index": index,
            "train": {"start": window.train_start.isoformat(),
                      "end": window.train_end.isoformat(), "bars": len(train)},
            "test": {"start": window.test_start.isoformat(),
                     "end": window.test_end.isoformat(), "bars": len(test),
                     "partial": partial},
            "n_attempts": len(combos),
            "selected_params": chosen["params"],
            "train_metrics": chosen["metrics"],
            "test_metrics": _metrics_json(test_result, keep_trades=True),
            "note": _failure_note(test_result),
            "_train_rows": train_rows,  # untuk penulisan registry (tidak dilaporkan)
        }
        report["windows"].append(entry)
        report["attempts_total"] += len(combos) + 1

    closed = [w for w in report["windows"] if w["test_metrics"].get("trades")]
    curve = [equity0]
    for w in report["windows"]:
        curve.append(w["test_metrics"]["final_balance"])
    peak = equity0
    max_dd = 0.0
    for value in curve:
        peak = max(peak, value)
        max_dd = max(max_dd, peak - value)
    report["aggregate"] = {
        "n_windows": len(report["windows"]),
        "windows_with_trades": len(closed),
        "windows_profitable": sum(1 for w in report["windows"]
                                  if (w["test_metrics"].get("net_profit_usd") or 0) > 0),
        "total_attempts": report["attempts_total"],
        "stitched_final_balance": balance,
        "stitched_net_profit_usd": round(balance - equity0, 2),
        "stitched_max_drawdown_usd": round(max_dd, 2),
        "stitched_max_drawdown_pct": round(max_dd / peak, 4) if peak else None,
        "stitched_curve": curve,
    }
    return report


async def write_report_rows(conn, report: dict) -> int:
    """Tulis semua percobaan (train + test) dari satu run ke backtest_runs."""
    run_id = report["run_id"]
    written = 0
    for entry in report["windows"]:
        window = Window(
            train_start=datetime.fromisoformat(entry["train"]["start"]),
            train_end=datetime.fromisoformat(entry["train"]["end"]),
            test_start=datetime.fromisoformat(entry["test"]["start"]),
            test_end=datetime.fromisoformat(entry["test"]["end"]))
        # Semua percobaan latih: selected hanya pada parameter terpilih.
        selected_params = entry["selected_params"]
        sid, sver = report["strategy"], report["version"]
        for row in entry["_train_rows"]:
            is_selected = row["params"] == selected_params
            await record_run(
                conn, run_id=run_id, window_index=entry["window_index"], role="train",
                window=window, symbol=report["symbol"], tf=report["tf"],
                params=row["params"], config=report["config"],
                metrics=row["metrics"], selected=is_selected,
                note="parameter dipilih dari window latih" if is_selected else None,
                strategy_id=sid, strategy_version=sver)
            written += 1
        await record_run(
            conn, run_id=run_id, window_index=entry["window_index"], role="test",
            window=window, symbol=report["symbol"], tf=report["tf"],
            params=selected_params, config=report["config"],
            metrics=entry["test_metrics"], selected=True, note=entry["note"],
            strategy_id=sid, strategy_version=sver)
        written += 1
    return written


# ---------------------------------------------------------------- laporan


def render_report(report: dict) -> str:
    agg = report["aggregate"]
    cfg = report["config"]
    cm = cfg.get("cost_model")
    prov = report.get("provenance") or {}
    prov_data = prov.get("data") or {}
    prov_code = prov.get("code") or {}
    dq = report.get("data_quality") or {}
    base = report.get("baseline") or {}
    lines = [
        f"# Walk-forward {report['strategy']} v{report['version']} "
        f"({report['symbol']} {report['tf']})",
        "",
        f"Run ID: `{report['run_id']}`",
        f"Window: latih {cfg.get('train_months', 6)} bulan / uji "
        f"{cfg.get('test_months', 1)} bulan, geser 1 bulan [USULAN PRD 5.4]",
        f"Data: {report.get('data', {}).get('start')} .. "
        f"{report.get('data', {}).get('end')} "
        f"({report.get('data', {}).get('bars')} bar, UTC)",
        f"Config hash: `{cfg.get('config_hash')}`",
        f"Seed: {cfg.get('seed')} (jalur inti deterministik; dipakai baseline acak)",
    ]
    if prov_data:
        lines.append(
            f"Data provenance: {prov_data.get('source')} ({prov_data.get('upstream')}); "
            f"checksum `{prov_data.get('checksum')}`")
    if prov_code:
        lines.append(
            f"Kode: commit `{prov_code.get('git_commit')}` "
            f"(dirty={prov_code.get('git_dirty')}, "
            f"{prov_code.get('git_dirty_file_count')} file); "
            f"code hash `{prov_code.get('code_hash')}`")
    if dq:
        lines.append(
            f"Preflight data: {dq.get('overall_status')} "
            f"({', '.join(f'{k}={v.get('status')}' for k, v in dq.get('checks', {}).items())})")
    if cm:
        lines += [
            "Biaya terkalibrasi (PRD 5.2): spread per sesi = Dukascopy x faktor "
            f"HFM/Duka + haircut {int(round(cm['haircut'] * 100))}%; komisi "
            f"{cm['commission_per_lot_round_usd']} USD/lot round-turn; slippage "
            f"{cm['slippage_usd_per_fill']} USD per fill.",
            f"Spread akhir per sesi (USD): {cm['spread_by_session']}",
        ]
        if cm.get("notes"):
            lines.append(f"Catatan kalibrasi: {'; '.join(cm['notes'])}")
    else:
        lines.append(
            f"Biaya: spread {cfg['spread_usd']} USD, slippage "
            f"{cfg['slippage_usd_per_fill']} USD per fill")
    ex = cfg.get("execution")
    if ex:
        lines.append(
            f"Execution model: fill delay {ex.get('fill_delay_bars')} bar, "
            f"swap long/short {ex.get('swap_long_usd_per_lot_night')}/"
            f"{ex.get('swap_short_usd_per_lot_night')} USD/lot/malam "
            f"(triple Rabu server), rejection spread>{ex.get('max_spread_fill')} / "
            f"gap>{ex.get('max_gap_usd')} USD, partial fill "
            f"{'aktif' if ex.get('partial_fill_enabled') else 'nonaktif (butuh depth data)'}, "
            f"market closure {'aktif' if ex.get('block_entry_closed_market') else 'nonaktif'}")
    if base:
        bh = base.get("buy_and_hold") or {}
        re_ = base.get("random_entry") or {}
        # detail dari segmen terakhir (agregat: net gabungan berantai)
        bh_last = (bh.get("segments") or [{}])[-1].get("result", {})
        re_last = (re_.get("segments") or [{}])[-1].get("result", {})
        re_trades = sum((s.get("result", {}).get("trades") or 0)
                        for s in (re_.get("segments") or []))
        lines.append(
            f"Baseline: buy&hold net {bh.get('net_profit_usd')} USD "
            f"(max DD {bh_last.get('max_drawdown_usd')}); random entry "
            f"(seed {re_last.get('seed')}) net {re_.get('net_profit_usd')} USD, "
            f"{re_trades} trade, PF {re_last.get('profit_factor')}")
    lines += [
        f"equity awal {cfg['equity0']} USD; risiko 0.5% per trade",
        f"Grid parameter: {len(expand_grid(cfg['grid']))} kombinasi; "
        f"total percobaan tercatat di backtest_runs: {agg['total_attempts']}",
        "",
        "## Hasil per window uji",
        "",
        "| # | Window uji (UTC) | Bar | Trades | Winrate | PF | Expectancy | Max DD | Durasi DD | Net (USD) | Catatan |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for w in report["windows"]:
        m = w["test_metrics"]
        lines.append(
            f"| {w['window_index'] + 1} | {w['test']['start'][:10]} .. {w['test']['end'][:10]}"
            f"{' (parsial)' if w['test']['partial'] else ''} | {w['test']['bars']} "
            f"| {m.get('trades', 0)} | {m.get('winrate') if m.get('winrate') is not None else '-'} "
            f"| {m.get('profit_factor') if m.get('profit_factor') is not None else '-'} "
            f"| {m.get('expectancy_usd')} USD / {m.get('expectancy_r')} R "
            f"| {m.get('max_drawdown_usd')} ({m.get('max_drawdown_pct')}) "
            f"| {m.get('max_drawdown_duration_min')} mnt "
            f"| {m.get('net_profit_usd')} | {w['note']} |")
    lines += [
        "",
        "## Ringkasan gabungan (ekuiti berantai antar window uji)",
        "",
        f"- Window uji: {agg['n_windows']} (dengan trade: {agg['windows_with_trades']}, "
        f"profit: {agg['windows_profitable']})",
        f"- Total percobaan parameter: {agg['total_attempts']} "
        f"(semua tercatat di backtest_runs)",
        f"- Net profit gabungan: {agg['stitched_net_profit_usd']} USD "
        f"(saldo akhir {agg['stitched_final_balance']} USD)",
        f"- Max drawdown gabungan: {agg['stitched_max_drawdown_usd']} USD "
        f"({agg['stitched_max_drawdown_pct']})",
        "",
        "## Metrik wajib PRD §8.3 (agregat window uji, setelah biaya)",
        "",
    ]
    ms = [w["test_metrics"] for w in report["windows"] if w["test_metrics"].get("trades")]
    if ms:
        def _agg_sum(key):
            return round(sum((m.get(key) or 0) for m in ms), 2)
        total_trades = sum(m.get("trades", 0) for m in ms)
        gw = sum((m.get("avg_win_usd") or 0) * sum(1 for _ in [0]) for m in ms)
        wins = sum(m.get("wins", 0) for m in ms)
        lines += [
            f"- Jumlah trade: {total_trades}; win rate gabungan: "
            f"{round(wins / total_trades, 4) if total_trades else '-'}",
            f"- Net P&L setelah biaya: {_agg_sum('net_profit_usd')} USD "
            f"(komisi {_agg_sum('commission_total_usd')}, swap {_agg_sum('swap_total_usd')})",
            f"- Expectancy: "
            f"{[m.get('expectancy_usd') for m in ms]} USD/trade per window; "
            f"CI95 {[m.get('expectancy_ci95') for m in ms]}",
            f"- Profit factor per window: {[m.get('profit_factor') for m in ms]}",
            f"- Max DD + durasi per window: "
            f"{[(m.get('max_drawdown_usd'), m.get('max_drawdown_duration_min')) for m in ms]}",
            f"- Sharpe harian: {[m.get('sharpe_daily_annualized') for m in ms]}; "
            f"Sortino harian: {[m.get('sortino_daily_annualized') for m in ms]}",
            f"- Exposure: {[m.get('exposure_pct') for m in ms]}%; "
            f"avg holding (mnt): {[m.get('avg_holding_min') for m in ms]}",
            f"- Tail loss CVaR95: {[m.get('tail_loss_cvar95_usd') for m in ms]} USD; "
            f"worst day: {[m.get('worst_day_usd') for m in ms]} USD",
            f"- Distribusi spread: {[m.get('spread_distribution') for m in ms]}",
            f"- Distribusi slippage: {[m.get('slippage_distribution') for m in ms]}",
            f"- Rejections: {[m.get('rejections') for m in ms]}",
        ]
        # agregat per sesi & regime (di-stitch dari semua window uji)
        ses: dict[str, dict] = {}
        reg: dict[str, dict] = {}
        for m in ms:
            for k, v in (m.get("by_session") or {}).items():
                d = ses.setdefault(k, {"trades": 0, "net_usd": 0.0})
                d["trades"] += v.get("trades", 0)
                d["net_usd"] = round(d["net_usd"] + v.get("net_usd", 0), 2)
            for k, v in ((m.get("regime") or {}).get("breakdown") or {}).items():
                d = reg.setdefault(k, {"trades": 0, "net_usd": 0.0})
                d["trades"] += v.get("trades", 0)
                d["net_usd"] = round(d["net_usd"] + v.get("net_usd", 0), 2)
        lines += [
            f"- Per sesi: {ses}",
            f"- Per regime: {reg}",
            f"- Per hari (worst): {[{k: v for k, v in (m.get('by_day') or {}).items()} for m in ms]}",
        ]
        # Per bucket spread (kuartil spread entry yang teramati, PRD 8.3)
        spr: dict[str, dict] = {}
        for m in ms:
            for k, v in (m.get("by_spread_bucket") or {}).items():
                d = spr.setdefault(k, {"trades": 0, "net_usd": 0.0})
                d["trades"] += v.get("trades", 0)
                d["net_usd"] = round(d["net_usd"] + v.get("net_usd", 0), 2)
                d.setdefault("range", v.get("range"))
        if spr:
            lines.append(f"- Per bucket spread (kuartil entry): {spr}")

        # Per jam UTC (entry per jam, PRD 8.3: per sesi/hari/ kondisi
        # spread; entries_by_hour_utc adalah dict hour->count)
        spr2: dict[str, dict] = {}
        for m in ms:
            for k, v in (m.get("entries_by_hour_utc") or {}).items():
                d = spr2.setdefault(k, {"trades": 0})
                d["trades"] += v if isinstance(v, int) else v.get("trades", 0)
        if spr2:
            lines.append(f"- Entry per jam UTC: {spr2}")
    else:
        lines.append("- Tidak ada trade pada window uji mana pun.")
    lines += [
        "",
        "## Parameter terpilih per window (dari window latih)",
        "",
        "| # | Window latih | Parameter terpilih | Expectancy latih (R) | PF latih | Trades latih |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for w in report["windows"]:
        p = w["selected_params"]
        t = w["train_metrics"]
        params_short = ", ".join(f"{k}={v}" for k, v in p.items()
                                 if k not in ("tf_seconds",))
        lines.append(
            f"| {w['window_index'] + 1} | {w['train']['start'][:10]} .. {w['train']['end'][:10]} "
            f"| {params_short} | {t.get('expectancy_r')} | {t.get('profit_factor')} "
            f"| {t.get('trades', 0)} |")
    lines += [
        "",
        "Catatan: hasil window uji bukan jaminan performa live. Jumlah percobaan "
        "yang besar relatif terhadap jumlah window uji adalah indikasi overfitting "
        "(PRD 5.4). Data H1 terbatas ~10 bulan; ulangi dengan sejarah 2 tahun "
        "(DoD P2) begitu crawler mengirimnya.",
        "Metodologi metrik: lihat kunci ``methodology`` di JSON run (Sharpe/Sortino, "
        "drawdown, exposure, CVaR, CI 95%).",
        "",
    ]
    return "\n".join(lines) + "\n"


async def _load_data(symbol: str, tf: str) -> tuple[list[dict], dict]:
    await _ensure_pool()
    async with db.pool().connection() as conn:
        db_tz = await db_timezone_offset_h(conn)
        stats = await conn.execute(
            "SELECT min(ts) AS mn, max(ts) AS mx, count(*) AS n FROM candles "
            "WHERE symbol = %s AND timeframe = %s",
            (symbol, canonical_tf(tf)))
        row = await stats.fetchone()
        if row is None or row["n"] == 0:
            await db.close_pool()
            raise SystemExit(f"tidak ada candle {symbol} {canonical_tf(tf)} di DB")
        rows = await (await conn.execute(
            "SELECT ts, open, high, low, close, volume FROM candles "
            "WHERE symbol = %s AND timeframe = %s ORDER BY ts ASC",
            (symbol, canonical_tf(tf)))).fetchall()
    candles = to_utc_candles(rows, db_tz)
    # Hanya bar CLOSED yang boleh dipakai backtest (PRD §8.2 look-ahead
    # guard): bar in-progress berubah-ubah saat feed berjalan sehingga
    # run yang sama di waktu berbeda menghasilkan metrik berbeda.
    tf_seconds = TF_SECONDS[canonical_tf(tf)]
    now_utc = datetime.now(timezone.utc)
    dropped = 0
    while candles and (candles[-1]["ts"].timestamp() + tf_seconds
                       > now_utc.timestamp()):
        candles.pop()
        dropped += 1
    if candles:
        meta = {"start": candles[0]["ts"], "end": candles[-1]["ts"],
                "bars": len(candles)}
        if dropped:
            meta["note"] = (f"{dropped} bar in-progress dibuang; "
                            "backtest hanya memakai bar closed")
    else:
        meta = {"start": row["mn"], "end": row["mx"], "bars": 0}
    return candles, meta


async def _cost_model_from_settings(conn, symbol: str) -> CostModel:
    """CostModel terkalibrasi dari settings `backtest_cost_calibration_<SYMBOL>`.

    Dipakai untuk simbol yang kalibrasinya disimpan worker data (mis. BTCUSD,
    t_f2mp4) — JSON-nya punya field yang sama dengan CostModel.as_dict().
    """
    row = await conn.execute(
        "SELECT value FROM settings WHERE key = %s",
        (f"backtest_cost_calibration_{symbol}",))
    found = await row.fetchone()
    if not found or not found["value"]:
        raise SystemExit(
            f"tidak ada kalibrasi biaya backtest_cost_calibration_{symbol} di settings")
    data = dict(found["value"] or {})
    known = set(CostModel.__dataclass_fields__)
    return CostModel(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------- baseline

def _stitched_baseline(candles: list[dict], windows: list[Window], *, kind: str,
                       symbol: str, seed: int, contract_size: float,
                       equity0: float, spread: float, slippage: float,
                       cost_model: CostModel | None,
                       execution: ExecutionModel | None,
                       n_trades: int = 30) -> dict:
    """Baseline pada window uji yang sama dengan strategi, ekuiti berantai.

    Perbandingan adil: baseline hanya mengisi window uji (bukan window
    latih), saldo di-chain antar window seperti strategi.
    """
    balance = equity0
    segments: list[dict] = []
    for w in windows:
        seg = [c for c in candles if w.test_start <= c["ts"] < w.test_end]
        if len(seg) < 2:
            continue
        if kind == "buy_and_hold":
            r = buy_and_hold(seg, symbol=symbol, contract_size=contract_size,
                             equity0=balance, spread=spread, slippage=slippage,
                             cost_model=cost_model, execution=execution)
        elif kind == "random_entry":
            r = random_entry(seg, symbol=symbol, seed=seed + w_index_of(windows, w),
                             n_trades=n_trades, contract_size=contract_size,
                             equity0=balance, spread=spread, slippage=slippage,
                             cost_model=cost_model, execution=execution)
        else:
            raise ValueError(f"baseline kind tidak dikenal: {kind}")
        balance = r.get("final_balance", balance)
        segments.append({"test_start": w.test_start.isoformat(),
                         "test_end": w.test_end.isoformat(), "result": r})
    return {"kind": kind, "equity0": equity0, "final_balance": round(balance, 2),
            "net_profit_usd": round(balance - equity0, 2),
            "return_pct": round(100 * (balance - equity0) / equity0, 3)
            if equity0 else None,
            "segments": segments}


def w_index_of(windows: list[Window], w: Window) -> int:
    return windows.index(w)


# ---------------------------------------------------------------- verify

def _model_from_config(cfg: dict) -> tuple[CostModel | None, ExecutionModel | None]:
    cm = cfg.get("cost_model")
    cost_model = None
    if cm:
        known = set(CostModel.__dataclass_fields__)
        cost_model = CostModel(**{k: v for k, v in cm.items() if k in known})
    ex = cfg.get("execution")
    execution = None
    if ex:
        known = set(ExecutionModel.__dataclass_fields__)
        execution = ExecutionModel(**{k: v for k, v in ex.items() if k in known})
    return cost_model, execution


def _metrics_hash(metrics: dict) -> str:
    from paper.provenance import canonical_json
    import hashlib
    return "sha256:" + hashlib.sha256(
        canonical_json(metrics).encode()).hexdigest()


async def verify_run(run_id: str, *, tf: str | None = None) -> bool:
    """Reproducibility check (PRD §8.2): muat run dari backtest_runs, hitung
    ulang config hash + checksum data + seluruh metrik window uji dari
    commit/config/data yang dicatat. True bila semuanya MATCH."""
    from paper.provenance import code_hash
    await _ensure_pool()
    async with db.pool().connection() as conn:
        rows = await (await conn.execute(
            "SELECT * FROM backtest_runs WHERE run_id = %s ORDER BY id",
            (run_id,))).fetchall()
    if not rows:
        raise SystemExit(f"run_id {run_id} tidak ditemukan di backtest_runs")
    cfg = dict(rows[0]["config"] or {})
    stored_hash = cfg.get("config_hash")
    body = {k: v for k, v in cfg.items() if k != "config_hash"}
    recomputed = config_hash(body)
    hash_ok = stored_hash == recomputed
    print(f"[verify] config hash: stored={stored_hash} recomputed={recomputed} "
          f"-> {'MATCH' if hash_ok else 'MISMATCH'}")

    # checksum data: muat ulang candle pada periode provenance
    prov_data = (cfg.get("provenance") or {}).get("data") or {}
    symbol = cfg["symbol"]
    tf_run = tf or cfg["tf"]
    data_ok = None
    if prov_data.get("period_start"):
        from datetime import datetime as _dt
        start = _dt.fromisoformat(prov_data["period_start"])
        end = _dt.fromisoformat(prov_data["period_end"])
        candles, _meta = await _load_data_range(symbol, tf_run, start, end)
        fresh = data_provenance(candles, symbol=symbol, tf=tf_run, raw_dir=None)
        data_ok = fresh["checksum"] == prov_data.get("checksum")
        print(f"[verify] data checksum: stored={prov_data.get('checksum')} "
              f"recomputed={fresh['checksum']} -> "
              f"{'MATCH' if data_ok else 'MISMATCH'}")

    # code hash: kode saat ini vs yang dicatat
    prov_code = (cfg.get("provenance") or {}).get("code") or {}
    code_ok = None
    if prov_code.get("code_hash"):
        code_ok = code_hash() == prov_code.get("code_hash")
        print(f"[verify] code hash: stored={prov_code.get('code_hash')} "
              f"-> {'MATCH' if code_ok else 'MISMATCH (kode berubah sejak run)'}")

    # Hitung ulang metrik tiap window uji dengan equity BERANTAI seperti run
    # asli (run_walkforward: test window di-chain dari saldo window sebelumnya),
    # lalu bandingkan hash metrik penuh yang tersimpan di backtest_runs.
    # Data dimuat TERBATAS pada periode provenance run: candle yang datang
    # setelah run (live feed) tidak boleh mengubah slice window uji.
    cost_model, execution = _model_from_config(cfg)
    if prov_data.get("period_start"):
        from datetime import datetime as _dt
        candles, _meta = await _load_data_range(
            symbol, tf_run, _dt.fromisoformat(prov_data["period_start"]),
            _dt.fromisoformat(prov_data["period_end"]))
    else:
        candles, _meta = await _load_data(symbol, tf_run)
    strategy = STRATEGIES.get(rows[0]["strategy_id"], london_breakout)
    ctx_bars = getattr(strategy, "CONTEXT_BARS", 0)
    equity0 = float(cfg.get("equity0", 10000.0))
    balance = equity0
    all_ok = hash_ok
    test_rows = [r for r in rows if r["role"] == "test"]
    test_rows.sort(key=lambda r: r["window_index"])
    for row in test_rows:
        test_start, test_end = row["test_start"], row["test_end"]
        seg = [c for c in candles
               if test_start <= c["ts"] < test_end]
        params = strategy.StrategyParams(**dict(row["params"] or {}))
        result = run_backtest(
            seg, tf_seconds=TF_SECONDS[canonical_tf(tf_run)],
            equity0=balance,
            spread=cfg.get("spread_usd", SPREAD_DEFAULT),
            slippage=cfg.get("slippage_usd_per_fill", SLIPPAGE_DEFAULT),
            params=params, cost_model=cost_model, strategy=strategy,
            symbol=symbol, contract_size=cfg.get("contract_size", 100.0),
            context_bars=ctx_bars, execution=execution)
        balance = result.get("final_balance", balance)
        stored_metrics = dict(row["metrics"] or {})
        ok = _metrics_hash(result) == _metrics_hash(stored_metrics)
        all_ok = all_ok and ok
        print(f"[verify] window {row['window_index']} test: "
              f"{'MATCH' if ok else 'MISMATCH'} "
              f"(trades={result.get('trades')}, pf={result.get('profit_factor')}, "
              f"net={result.get('net_profit_usd')})")
    print(f"[verify] run {run_id}: {'REPRODUCIBLE' if all_ok else 'TIDAK REPRODUCIBLE'}")
    return all_ok


async def _load_data_range(symbol: str, tf: str, start, end) -> tuple[list[dict], dict]:
    await _ensure_pool()
    async with db.pool().connection() as conn:
        db_tz = await db_timezone_offset_h(conn)
        rows = await (await conn.execute(
            "SELECT ts, open, high, low, close, volume FROM candles "
            "WHERE symbol = %s AND timeframe = %s AND ts >= %s AND ts <= %s "
            "ORDER BY ts ASC",
            (symbol, canonical_tf(tf), start, end))).fetchall()
    candles = to_utc_candles(rows, db_tz)
    meta = {"bars": len(candles)}
    return candles, meta


# ---------------------------------------------------------------- CLI

async def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward runner (PRD 5.4)")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--strategy", choices=sorted(STRATEGIES), default="london_breakout")
    parser.add_argument("--tf", default="H1",
                        help="H1/M15/M5/... (nama pendek 1h/5m juga diterima)")
    parser.add_argument("--train-months", type=int, default=6)
    parser.add_argument("--test-months", type=int, default=1)
    parser.add_argument("--step-months", type=int, default=1)
    parser.add_argument("--equity", type=float, default=10000.0)
    parser.add_argument("--spread", type=float, default=SPREAD_DEFAULT)
    parser.add_argument("--slippage", type=float, default=SLIPPAGE_DEFAULT)
    parser.add_argument("--cost-model", choices=["dukascopy", "settings"], default="",
                        help="biaya terkalibrasi PRD 5.2: dukascopy (XAUUSD) atau "
                             "settings (baca backtest_cost_calibration_<SYMBOL>)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                        help="random seed (dicatat di config, PRD 8.2)")
    parser.add_argument("--execution", choices=["model", "legacy"], default="model",
                        help="model: swap/latency/rejection/partial fill/closure "
                             "(PRD v2.2 8.2); legacy: perilaku lama")
    parser.add_argument("--baseline-random-trades", type=int, default=30)
    parser.add_argument("--out-md", default="")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--dry-run", action="store_true", help="jangan tulis backtest_runs")
    parser.add_argument("--verify", default="", metavar="RUN_ID",
                        help="verifikasi reproducibility run_id lalu keluar")
    args = parser.parse_args()

    if args.verify:
        ok = await verify_run(args.verify)
        raise SystemExit(0 if ok else 1)

    await _ensure_pool()
    candles, meta = await _load_data(args.symbol, args.tf)
    cost_model = None
    if args.cost_model == "dukascopy":
        from paper.dukascopy import build_dukascopy_cost_model
        await _ensure_pool()
        async with db.pool().connection() as conn:
            cost_model = await build_dukascopy_cost_model(conn)
        print("cost model:", json.dumps(cost_model.as_dict(), indent=1))
    elif args.cost_model == "settings":
        await _ensure_pool()
        async with db.pool().connection() as conn:
            cost_model = await _cost_model_from_settings(conn, args.symbol)
        print("cost model:", json.dumps(cost_model.as_dict(), indent=1))

    # ── Preflight data quality (PRD §8.2): SEBELUM eksperimen ──
    allowed_symbols = None
    try:
        await _ensure_pool()
        settings = await db.get_settings()
        allowed_symbols = settings.get("allowed_symbols")
    except Exception as exc:  # non-blocking: preflight tetap jalan
        print(f"preflight: settings tidak terbaca ({exc}); survivorship DOCUMENTED saja")
    pre = run_preflight(candles, symbol=args.symbol, tf=canonical_tf(args.tf),
                        tradeable_symbols=allowed_symbols)
    print(f"preflight data quality: {pre['overall_status']}")
    # Check data-korup (OHLC/monoton/duplikat/bad tick) = fatal: hasil backtest
    # tidak bisa dipercaya. Gap/completeness (bar hilang, libur pasar) = dicatat
    # + peringatan keras, backtest tetap jalan (PRD 8.2: deteksi + dokumentasi).
    corrupt = ("ohlc", "monotonicity", "duplicate_rate", "bad_ticks")
    for name in corrupt:
        if pre["checks"].get(name, {}).get("status") == "FAIL":
            raise SystemExit(
                f"preflight {name} FAIL: perbaiki data sebelum backtest "
                f"({pre['checks'][name].get('detail')})")
    if pre["overall_status"] in ("WARN", "FAIL"):
        print(f"AWAS preflight: {pre['overall_status']} - "
              f"{ {k: v.get('detail') for k, v in pre['checks'].items()} }")

    # ── Seed + execution model (PRD §8.2) ──
    seed = args.seed
    random.seed(seed)
    execution = (default_execution_model(args.symbol)
                 if args.execution == "model" else None)

    windows = plan_windows(meta["start"], meta["end"],
                           train_months=args.train_months,
                           test_months=args.test_months, step_months=args.step_months)
    if not windows:
        raise SystemExit(
            f"data {meta['start']} .. {meta['end']} terlalu pendek untuk latih "
            f"{args.train_months} bulan + uji {args.test_months} bulan")

    report = run_walkforward(
        candles, tf=args.tf, symbol=args.symbol, windows=windows,
        equity0=args.equity, spread=args.spread, slippage=args.slippage,
        cost_model=cost_model, strategy=STRATEGIES[args.strategy],
        data_end=meta["end"], execution=execution, seed=seed)
    report["config"]["train_months"] = args.train_months
    report["config"]["test_months"] = args.test_months
    report["config"]["step_months"] = args.step_months
    report["data"] = {"start": meta["start"].isoformat(), "end": meta["end"].isoformat(),
                      "bars": meta["bars"]}

    # ── Provenance (PRD §8.2): data + kode ──
    report["provenance"] = {
        "data": data_provenance(
            candles, symbol=args.symbol, tf=canonical_tf(args.tf)),
        "code": code_provenance(),
    }

    # ── Baseline pembanding (PRD §8.2): window uji yang sama, ekuiti berantai ──
    report["baseline"] = {
        "buy_and_hold": _stitched_baseline(
            candles, windows, kind="buy_and_hold", symbol=args.symbol,
            seed=seed, contract_size=contract_size_for(args.symbol),
            equity0=args.equity, spread=args.spread, slippage=args.slippage,
            cost_model=cost_model, execution=execution),
        "random_entry": _stitched_baseline(
            candles, windows, kind="random_entry", symbol=args.symbol,
            seed=seed, contract_size=contract_size_for(args.symbol),
            equity0=args.equity, spread=args.spread, slippage=args.slippage,
            cost_model=cost_model, execution=execution,
            n_trades=args.baseline_random_trades),
    }

    # ── Audit trail ke config (PRD §8.2): provenance, data quality, dan ──
    # baseline ikut tersimpan di backtest_runs.config JSONB + masuk config
    # hash, sehingga satu run_id bisa diaudit penuh dari DB.
    report["config"]["provenance"] = report["provenance"]
    report["config"]["baseline"] = report["baseline"]
    if report.get("data_quality") is not None:
        report["config"]["data_quality"] = report["data_quality"]

    # ── Config hash (PRD §8.2): dikunci SETELAH config lengkap ──
    report["config"]["config_hash"] = config_hash(
        {k: v for k, v in report["config"].items() if k != "config_hash"})

    if not args.dry_run:
        await db.init_pool()
        async with db.pool().connection() as conn:
            written = await write_report_rows(conn, report)
        await db.close_pool()
        print(f"backtest_runs: {written} baris ditulis (run_id {report['run_id']})")

    print(render_report(report))
    if args.out_json:
        with open(args.out_json, "w") as fh:
            json.dump(report, fh, indent=1, default=str)
    if args.out_md:
        with open(args.out_md, "w") as fh:
            fh.write(render_report(report))


if __name__ == "__main__":
    asyncio.run(main())
