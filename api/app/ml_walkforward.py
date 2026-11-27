"""Walk-forward ML P3 (t_f2p3a1): feature store -> LightGBM -> backtest.

Window: latih 6 bulan / uji 1 bulan, geser 1 bulan (identik dengan run P2 —
paper/walkforward.py), biaya terkalibrasi PRD 5.2, ekuiti berantai, engine
dan risk gate sama dengan baseline rule-based (paper/backtest.py).

Aturan ketat (PRD 5.4):
  1. Model dilatih HANYA dari window latih; early stopping memakai 20%
     terakhir window latih (time-ordered, tetap di dalam data latih).
  2. Yang dilaporkan hanya hasil window uji.
  3. SEMUA percobaan (12 kombinasi latih + 1 uji per window) dicatat ke
     backtest_runs dengan run_id yang sama.
  4. Seed + hyperparameter tetap, deterministic; fit ulang = prediksi sama.

Fitur dihitung per bar dari trailing 300 bar (sama dengan CONTEXT_BARS live)
memakai ml_features.compute_features — jalur yang sama dengan decide().

Run:
  .venv/bin/python -m app.ml_walkforward --symbol XAUUSD --tf M5 \
      --cost-model dukascopy --out-json ../docs/ml_wf.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np

from . import db
from .ml_features import FEATURE_NAMES, MIN_BARS, compute_features_batch
from .ml_label import BARRIER_CONFIGS, barrier_key, triple_barrier_labels
from paper.backtest import canonical_tf, run_backtest
from paper.costs import CostModel
from paper.dukascopy import build_dukascopy_cost_model
from paper.walkforward import (  # noqa: F401 (re-export untuk CLI)
    Window, plan_windows, record_run, select_best, _failure_note,
)
import paper.walkforward as wf
from .strategies import ml_gbm

STRATEGY = ml_gbm
STRATEGY_ID = ml_gbm.STRATEGY_ID
STRATEGY_VERSION = ml_gbm.STRATEGY_VERSION

# grid 12 kombinasi: 4 barrier x 3 ambang probabilitas
THRESHOLDS = [0.55, 0.60, 0.65]

LGBM_PARAMS = {
    "objective": "binary",
    "metric": "binary_logloss",
    "learning_rate": 0.05,
    "num_leaves": 15,
    "max_depth": 5,
    "min_data_in_leaf": 400,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 5.0,
    "seed": 42,
    "deterministic": True,
    "num_threads": 4,
    "verbose": -1,
}
NUM_BOOST_ROUND = 500
EARLY_STOPPING_ROUNDS = 50
VAL_FRACTION = 0.20
TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600}


def slice_feats(all_feats: dict, start: datetime, end: datetime) -> list[dict]:
    """Ambil fitur batch per bar pada [start, end)."""
    return [f for f in all_feats if start <= f["ts"] < end]


def _matrix(rows: list[dict]) -> np.ndarray:
    return np.array([[float(r[k]) for k in FEATURE_NAMES] for r in rows],
                    dtype=float)


def train_models(train_rows: list[dict], labels_by_key: dict[str, dict],
                 ) -> dict:
    """Latih booster long+short per barrier config dari window latih.

    train_rows: fitur (dict per bar, ada 'ts'); labels_by_key: barrier_key ->
    {ts: label_long/label_short}. Val = 20% terakhir time-ordered.
    """
    models: dict[str, dict] = {}
    for sl_mult, rr in BARRIER_CONFIGS:
        key = barrier_key(sl_mult, rr)
        lab = labels_by_key.get(key)
        if not lab:
            continue  # config tanpa label pada window latih -> dilewati
        rows = [r for r in train_rows if r["ts"] in lab]
        if len(rows) < 500:
            raise RuntimeError(
                f"baris latih {key} terlalu sedikit: {len(rows)} (min 500)")
        rows = sorted(rows, key=lambda r: r["ts"])
        X = _matrix(rows)
        cut = int(len(rows) * (1.0 - VAL_FRACTION))
        models[key] = {}
        for side, lab_field in (("long", "label_long"), ("short", "label_short")):
            y = np.array([lab[r["ts"]][lab_field] for r in rows], dtype=int)
            dtrain = lgb.Dataset(X[:cut], label=y[:cut],
                                 feature_name=FEATURE_NAMES, free_raw_data=False)
            dvalid = lgb.Dataset(X[cut:], label=y[cut:],
                                 feature_name=FEATURE_NAMES, reference=dtrain)
            booster = lgb.train(
                LGBM_PARAMS, dtrain, num_boost_round=NUM_BOOST_ROUND,
                valid_sets=[dvalid],
                callbacks=[lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False)])
            models[key][side] = booster
    return models


def run_ml_walkforward(candles: list[dict], *, tf: str, symbol: str = "XAUUSD",
                       windows: list[Window], cost_model: CostModel | None,
                       equity0: float = 10000.0, data_end: datetime | None = None,
                       model_dir: Path | None = None) -> dict:
    """Walk-forward ML: latih per window, pilih 12 kombinasi dari latih,
    uji dengan ekuiti berantai. Murni kecuali simpan model (model_dir)."""
    tf_seconds = TF_SECONDS[canonical_tf(tf)]
    grid = []
    for sl_mult, rr in BARRIER_CONFIGS:
        for thr in THRESHOLDS:
            grid.append({"sl_mult": sl_mult, "rr": rr, "threshold": thr})
    config = {
        "symbol": symbol, "tf": canonical_tf(tf), "tf_seconds": tf_seconds,
        "equity0": equity0, "cost_model": cost_model.as_dict() if cost_model else None,
        "grid": grid, "lgbm_params": LGBM_PARAMS,
        "num_boost_round": NUM_BOOST_ROUND,
        "early_stopping_rounds": EARLY_STOPPING_ROUNDS,
        "val_fraction": VAL_FRACTION,
        "min_bars": MIN_BARS, "context_bars": ml_gbm.CONTEXT_BARS,
        "label": "triple-barrier per sisi; SL=sl_mult x ATR14; TP=rr x SL; "
                 "horizon sampai force-close 16:00 UTC; timeout=tanda close; "
                 "SL-first saat bar menyentuh dua barrier",
        "selection": "expectancy_r > profit_factor > trades (trades >= 5 "
                     "diprioritaskan) — sama dengan baseline",
        "min_trades_train": wf.MIN_TRADES_TRAIN,
    }
    report = {
        "run_id": str(uuid.uuid4()), "strategy": STRATEGY_ID,
        "version": STRATEGY_VERSION, "symbol": symbol, "tf": canonical_tf(tf),
        "config": config, "windows": [], "attempts_total": 0,
    }
    # fitur batch untuk SELURUH seri (sekali; paritas dengan jalur per-bar
    # decide() diuji di test suite)
    spread_fn = cost_model.filter_spread_at if cost_model else None
    t_batch = datetime.now(timezone.utc)
    all_feats = compute_features_batch(candles, spread_fn=spread_fn)
    print(f"features batch: {len(all_feats)} bar "
          f"({(datetime.now(timezone.utc) - t_batch).total_seconds():.1f}s)", flush=True)
    balance = equity0
    for index, window in enumerate(windows):
        train = [c for c in candles if window.train_start <= c["ts"] < window.train_end]
        test = [c for c in candles if window.test_start <= c["ts"] < window.test_end]
        train_feats = slice_feats(all_feats, window.train_start, window.train_end)
        labels_by_key = {}
        for sl_mult, rr in BARRIER_CONFIGS:
            key = barrier_key(sl_mult, rr)
            rows = triple_barrier_labels(
                train, sl_mult, rr,
                entry_start_utc=ml_gbm.StrategyParams.entry_start_utc,
                entry_end_utc=ml_gbm.StrategyParams.entry_end_utc,
                force_close_utc=ml_gbm.StrategyParams.force_close_utc,
                min_sl_dist=ml_gbm.StrategyParams.min_sl_distance_usd,
                max_sl_dist=ml_gbm.StrategyParams.max_sl_distance_usd)
            labels_by_key[key] = {r["ts"]: r for r in rows}
        models = train_models(train_feats, labels_by_key)
        if model_dir is not None:
            outdir = Path(model_dir) / report["run_id"]
            outdir.mkdir(parents=True, exist_ok=True)
            for key, sides in models.items():
                for side, booster in sides.items():
                    booster.save_model(str(outdir / f"{key}_{side}.txt"))
        # ---- prediksi batch untuk SELURUH bar latih (cache decide())
        ml_gbm.set_model_bundle({"long": {k: v["long"] for k, v in models.items()},
                                 "short": {k: v["short"] for k, v in models.items()},
                                 "feature_names": FEATURE_NAMES})
        ml_gbm.clear_prediction_cache()
        cache_rows = []
        matrices = {}
        for key in models:
            X = _matrix(train_feats)
            matrices[key] = X
            P = models[key]["long"].predict(X)
            S = models[key]["short"].predict(X)
            cache_rows += [(key, f["ts"].isoformat(), float(P[i]), float(S[i]))
                           for i, f in enumerate(train_feats)]
        ml_gbm.prime_prediction_cache(cache_rows)
        # ---- 12 kombinasi pada window latih (seleksi)
        train_rows = []
        ctx_bars = ml_gbm.CONTEXT_BARS
        for combo in grid:
            params = ml_gbm.StrategyParams(tf_seconds=tf_seconds, **combo)
            result = run_backtest(train, tf_seconds=tf_seconds, equity0=equity0,
                                  cost_model=cost_model, strategy=STRATEGY,
                                  params=params, symbol=symbol,
                                  contract_size=100.0, context_bars=ctx_bars)
            train_rows.append({"params": {**asdict(params)}, "metrics": _metrics(result),
                               "combo": combo})
        chosen = select_best(train_rows)
        chosen_params = ml_gbm.StrategyParams(tf_seconds=tf_seconds, **chosen["combo"])
        # ---- prediksi window uji + backtest ekuiti berantai
        test_feats = slice_feats(all_feats, window.test_start, window.test_end)
        key = barrier_key(chosen_params.sl_mult, chosen_params.rr)
        Xt = _matrix(test_feats)
        ml_gbm.clear_prediction_cache()
        P = models[key]["long"].predict(Xt)
        S = models[key]["short"].predict(Xt)
        ml_gbm.prime_prediction_cache([
            (key, f["ts"].isoformat(), float(P[i]), float(S[i]))
            for i, f in enumerate(test_feats)])
        test_result = run_backtest(test, tf_seconds=tf_seconds, equity0=balance,
                                   cost_model=cost_model, strategy=STRATEGY,
                                   params=chosen_params, symbol=symbol,
                                   contract_size=100.0, context_bars=ctx_bars)
        balance = test_result["final_balance"]
        partial = data_end is not None and window.test_end > data_end
        entry = {
            "window_index": index,
            "train": {"start": window.train_start.isoformat(),
                      "end": window.train_end.isoformat(), "bars": len(train)},
            "test": {"start": window.test_start.isoformat(),
                     "end": window.test_end.isoformat(), "bars": len(test),
                     "partial": partial},
            "n_attempts": len(grid),
            "n_train_rows": {k: len(v) for k, v in
                             ((key, [f for f in train_feats if f["ts"] in labels_by_key[key]]),)},
            "selected_params": chosen["params"],
            "train_metrics": chosen["metrics"],
            "test_metrics": _metrics(test_result, keep_trades=True),
            "note": _failure_note(test_result),
            "_train_rows": train_rows,
        }
        report["windows"].append(entry)
        report["attempts_total"] += len(grid) + 1
        print(f"window {index + 1}/{len(windows)}: {chosen['combo']} "
              f"test trades={test_result['trades']} net={test_result['net_profit_usd']}",
              flush=True)
    ml_gbm.set_model_bundle(None)
    ml_gbm.clear_prediction_cache()
    report["aggregate"] = _aggregate(report, equity0)
    return report


def _metrics(result: dict, keep_trades: bool = False) -> dict:
    metrics = {k: v for k, v in result.items() if k not in ("meta",)}
    if not keep_trades:
        metrics.pop("trades_detail", None)
    return metrics


def _aggregate(report: dict, equity0: float) -> dict:
    closed = [w for w in report["windows"] if w["test_metrics"].get("trades")]
    curve = [equity0] + [w["test_metrics"]["final_balance"] for w in report["windows"]]
    peak = equity0
    max_dd = 0.0
    for value in curve:
        peak = max(peak, value)
        max_dd = max(max_dd, peak - value)
    balance = curve[-1]
    all_trades = [t for w in report["windows"]
                  for t in (w["test_metrics"].get("trades_detail") or [])]
    wins = [t for t in all_trades if t["profit"] > 0]
    losses = [t for t in all_trades if t["profit"] <= 0]
    gross_win = sum(t["profit"] for t in wins)
    gross_loss = abs(sum(t["profit"] for t in losses))
    pnls = [t["profit"] for t in all_trades]
    pf_windows = [w["test_metrics"].get("profit_factor") for w in report["windows"]]
    pf_below_1 = sum(1 for pf in pf_windows if pf is not None and pf < 1.0)
    return {
        "n_windows": len(report["windows"]),
        "windows_with_trades": len(closed),
        "windows_profitable": sum(1 for w in report["windows"]
                                  if (w["test_metrics"].get("net_profit_usd") or 0) > 0),
        "windows_pf_below_1": pf_below_1,
        "total_attempts": report["attempts_total"],
        "trades": len(all_trades),
        "winrate": round(len(wins) / len(all_trades), 4) if all_trades else None,
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else None,
        "expectancy_usd": round(sum(pnls) / len(pnls), 2) if pnls else None,
        "stitched_final_balance": balance,
        "stitched_net_profit_usd": round(balance - equity0, 2),
        "stitched_max_drawdown_usd": round(max_dd, 2),
        "stitched_max_drawdown_pct": round(max_dd / peak, 4) if peak else None,
        "stitched_curve": curve,
    }

def render_report(report: dict) -> str:
    agg = report["aggregate"]
    cfg = report["config"]
    cm = cfg.get("cost_model")
    lines = [
        f"# Walk-forward {report['strategy']} v{report['version']} "
        f"({report['symbol']} {report['tf']}) — P3 ML",
        "",
        f"Run ID: `{report['run_id']}`",
        "Window: latih 6 bulan / uji 1 bulan, geser 1 bulan (identik run P2)",
    ]
    if cm:
        lines.append(
            "Biaya terkalibrasi (PRD 5.2): spread per sesi = Dukascopy x faktor "
            f"HFM + haircut {int(round(cm['haircut'] * 100))}%; komisi "
            f"{cm['commission_per_lot_round_usd']} USD/lot round-turn; slippage "
            f"{cm['slippage_usd_per_fill']} USD per fill. Spread akhir: "
            f"{cm['spread_by_session']}")
    lines += [
        f"equity awal {cfg['equity0']} USD; risiko 0.5% per trade; maks 1 trade/hari",
        f"Grid: {len(cfg['grid'])} kombinasi (4 barrier x 3 ambang); "
        f"total percobaan tercatat di backtest_runs: {agg['total_attempts']}",
        f"Model: LightGBM per sisi per barrier; params={cfg['lgbm_params']}; "
        f"rounds={cfg['num_boost_round']} early_stop={cfg['early_stopping_rounds']} "
        f"val={cfg['val_fraction']:.0%} time-ordered dalam window latih",
        "",
        "## Hasil per window uji",
        "",
        "| # | Window uji (UTC) | Bar | Trades | Winrate | PF | Expectancy | Max DD | Net (USD) | Catatan |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
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
            f"| {m.get('net_profit_usd')} | {w['note']} |")
    lines += [
        "",
        "## Ringkasan gabungan (ekuiti berantai antar window uji)",
        "",
        f"- Window uji: {agg['n_windows']} (dengan trade: {agg['windows_with_trades']}, "
        f"profit: {agg['windows_profitable']}, PF<1: {agg['windows_pf_below_1']})",
        f"- Total percobaan parameter: {agg['total_attempts']} "
        f"(semua tercatat di backtest_runs)",
        f"- Trades: {agg['trades']}; winrate {agg['winrate']}; PF {agg['profit_factor']}; "
        f"expectancy {agg['expectancy_usd']} USD/trade",
        f"- Net profit gabungan: {agg['stitched_net_profit_usd']} USD "
        f"(saldo akhir {agg['stitched_final_balance']} USD)",
        f"- Max drawdown gabungan: {agg['stitched_max_drawdown_usd']} USD "
        f"({agg['stitched_max_drawdown_pct']})",
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
        "(PRD 5.4).",
        "",
    ]
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward ML P3 (t_f2p3a1)")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--tf", default="M5")
    parser.add_argument("--train-months", type=int, default=6)
    parser.add_argument("--test-months", type=int, default=1)
    parser.add_argument("--step-months", type=int, default=1)
    parser.add_argument("--equity", type=float, default=10000.0)
    parser.add_argument("--cost-model", choices=["dukascopy", "settings", ""],
                        default="dukascopy")
    parser.add_argument("--model-dir", default="../data/ml_models")
    parser.add_argument("--out-md", default="")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--max-windows", type=int, default=0,
                        help="batasi jumlah window (0 = semua; untuk smoke test)")
    parser.add_argument("--dry-run", action="store_true", help="jangan tulis backtest_runs")
    args = parser.parse_args()

    candles, meta = await wf._load_data(args.symbol, args.tf)
    cost_model = None
    if args.cost_model == "dukascopy":
        await db.init_pool()
        async with db.pool().connection() as conn:
            cost_model = await build_dukascopy_cost_model(conn)
        await db.close_pool()
        print("cost model:", json.dumps(cost_model.as_dict(), indent=1))
    windows = plan_windows(meta["start"], meta["end"],
                           train_months=args.train_months,
                           test_months=args.test_months, step_months=args.step_months)
    if args.max_windows:
        windows = windows[:args.max_windows]
    if not windows:
        raise SystemExit("data terlalu pendek untuk window yang diminta")

    report = run_ml_walkforward(
        candles, tf=args.tf, symbol=args.symbol, windows=windows,
        cost_model=cost_model, equity0=args.equity, data_end=meta["end"],
        model_dir=Path(args.model_dir) if args.model_dir else None)
    report["config"]["train_months"] = args.train_months
    report["config"]["test_months"] = args.test_months
    report["data"] = {"start": meta["start"].isoformat(), "end": meta["end"].isoformat(),
                      "bars": meta["bars"]}

    if not args.dry_run:
        await db.init_pool()
        async with db.pool().connection() as conn:
            written = await wf.write_report_rows(conn, report)
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


