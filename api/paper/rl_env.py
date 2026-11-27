"""RL environment Track C (PRD 5.3, eksperimental — t_f2p3a2).

Action space Discrete(4) sesuai PRD: 0=hold, 1=buy, 2=sell, 3=close.
Reward: perubahan equity mark-to-market per bar yang dinormalisasi ATR14
(PnL disesuaikan risiko; 1.0 = satu ATR keuntungan).

Semantik eksekusi DISADUR PERSIS dari paper/backtest.run_backtest agar
hasil RL bisa dibandingkan adil dengan baseline rule-based:

  - fill market di bar close: BUY di ask + slippage, SELL di bid - slippage;
  - SL/TP dicek intrabar oleh PaperBroker (SL menang saat bar menyentuh
    dua level / gap), time exit 16:00 UTC (force_close_hour_utc);
  - biaya CostModel PRD 5.2 (spread per sesi + haircut, komisi, slippage)
    atau biaya konstan spread/slippage;
  - risk gate yang sama (app.risk.risk_gate) dengan settings backtest yang
    sama: max_volume 0.10, max_spread 0.50, drawdown harian 1% (= 100 USD
    di saldo 10.000; gate memakai persen, AUDIT-A2);
  - sizing 0.5% equity per trade, dibulatkan ke step 0.01 lot.

Perbedaan tunggal vs run_backtest: keputusan entry/exit datang dari policy
RL (4 aksi) alih-alih decide() rule-based, dan aksi `close` menutup posisi
di harga close bar (biaya slippage + spread sama dengan exit broker).

Observation (73 dim, semua kausal, tidak ada lookahead):
  - 32 bar terakhir x 2 channel: log-return / sigma(100), range/ATR14;
  - RSI14/100, ATR14/close x 10, jam UTC sin/cos, hari kerja/4,
    spread teramati / 0.50;
  - posisi: side (+1/-1/0), unrealized dalam satuan R, durasi/24 bar.

Aksi tidak valid (buy/sell saat masih pegang posisi, close saat flat)
diperlakukan sebagai hold.
"""

from __future__ import annotations

import math
from datetime import timedelta

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

from app.ingest import session_of
from app.risk import RiskContext, risk_gate
from paper.backtest import summarize
from paper.broker import PaperBroker, PaperPosition, unrealized

HOLD, BUY, SELL, CLOSE = 0, 1, 2, 3
N_ACTIONS = 4
OBS_BARS = 32
SIGMA_WINDOW = 100
RSI_PERIOD = 14
ATR_PERIOD = 14

OBS_DIM = OBS_BARS * 2 + 9


def compute_rl_features(candles: list[dict], tf_seconds: int) -> dict[str, np.ndarray]:
    """Indikator kausal per bar (hanya data <= bar ts). Returns arrays float64."""
    n = len(candles)
    close = np.array([c["close"] for c in candles], dtype=float)
    high = np.array([c["high"] for c in candles], dtype=float)
    low = np.array([c["low"] for c in candles], dtype=float)
    ret = np.zeros(n)
    if n > 1:
        ret[1:] = np.diff(np.log(close))
    s = pd.Series(ret)
    sigma = s.rolling(SIGMA_WINDOW, min_periods=20).std()
    sigma = sigma.fillna(s.expanding(min_periods=5).std()).fillna(1e-3).to_numpy()
    sigma = np.maximum(sigma, 1e-6)

    # Wilder RSI
    delta = np.diff(close, prepend=close[0])
    gain = pd.Series(np.maximum(delta, 0.0)).ewm(alpha=1 / RSI_PERIOD, adjust=False).mean()
    loss = pd.Series(np.maximum(-delta, 0.0)).ewm(alpha=1 / RSI_PERIOD, adjust=False).mean()
    rs = gain / loss.replace(0.0, np.nan)
    rsi = (100.0 - 100.0 / (1.0 + rs)).fillna(50.0).to_numpy()

    # Wilder ATR
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close),
                                           np.abs(low - prev_close)))
    atr = pd.Series(tr).ewm(alpha=1 / ATR_PERIOD, adjust=False).mean().to_numpy()
    atr = np.maximum(atr, 1e-6)

    hours = np.array([(c["ts"] + timedelta(seconds=tf_seconds)).hour for c in candles])
    dows = np.array([(c["ts"] + timedelta(seconds=tf_seconds)).weekday() for c in candles])
    return {
        "ret": ret, "sigma": sigma, "rsi": rsi, "atr": atr,
        "hour_sin": np.sin(2 * np.pi * hours / 24.0),
        "hour_cos": np.cos(2 * np.pi * hours / 24.0),
        "dow": dows / 4.0,
        "close": close, "high": high, "low": low,
    }


class RlTradingEnv(gym.Env):
    """Env backtest XAUUSD dengan aksi {buy, sell, hold, close}.

    Bound ke satu window [start_idx, end_idx) dari seri candle penuh; obs
    boleh memakai trailing history sebelum start_idx (data masa lalu, bukan
    lookahead). reset() mengembalikan window ke start_idx sehingga auto-reset
    SB3 mengulang window yang sama (satu env = satu window).
    """

    metadata = {"render_modes": []}

    def __init__(self, candles: list[dict], features: dict[str, np.ndarray],
                 start_idx: int, end_idx: int, *, tf_seconds: int,
                 cost_model=None, spread: float = 0.50, slippage: float = 0.10,
                 equity0: float = 10000.0, contract_size: float = 100.0,
                 symbol: str = "XAUUSD", sl_atr_mult: float = 1.5,
                 tp_rr: float = 1.5, max_trades_per_day: int = 1,
                 force_close_hour_utc: int | None = 16,
                 risk_per_trade: float = 0.005, max_volume: float = 0.10,
                 max_spread_abs: float = 0.50, min_sl_distance: float = 0.10):
        super().__init__()
        self.candles = candles
        self.feat = features
        self.start_idx = start_idx
        self.end_idx = end_idx
        self.tf_seconds = tf_seconds
        self.cost_model = cost_model
        self.spread = spread
        self.slippage = slippage
        self.equity0 = equity0
        self.contract_size = contract_size
        self.symbol = symbol
        self.sl_atr_mult = sl_atr_mult
        self.tp_rr = tp_rr
        self.max_trades_per_day = max_trades_per_day
        self.force_close_hour_utc = force_close_hour_utc
        self.risk_per_trade = risk_per_trade
        self.max_volume = max_volume
        self.max_spread_abs = max_spread_abs
        self.min_sl_distance = min_sl_distance

        self.action_space = spaces.Discrete(N_ACTIONS)
        self.observation_space = spaces.Box(-np.inf, np.inf, (OBS_DIM,), np.float32)
        # AUDIT-A2: gate memakai persen dari saldo awal hari, bukan USD.
        # 1% x 10.000 = 100 USD -> ambang sama dengan run_backtest.
        self.settings = {"allowed_symbols": [symbol], "max_volume": max_volume,
                         "max_spread": max_spread_abs,
                         "kill_switch_triggers": {"daily_drawdown_pct": 1.0},
                         "max_orders_per_min": 10}
        self.broker = PaperBroker(force_close_hour_utc=force_close_hour_utc)
        self.strategy_id = "rl_ppo"
        self.reset()

    # ---------------------------------------------------------------- API gym

    def reset(self, *, seed: int | None = None, options=None):
        super().reset(seed=seed)
        self.i = self.start_idx
        self.balance = self.equity0
        self.position: PaperPosition | None = None
        self.trades: list[dict] = []
        self.trades_today = 0
        self.daily_realized = 0.0
        self.day = None
        self.commission_total = 0.0
        self.equity_prev = self.equity0
        self._done = False
        self._bars_held = 0
        return self._obs(), {}

    def step(self, action: int):
        if self._done:
            raise RuntimeError("step setelah episode selesai; reset() dulu")
        i = self.i
        bar = self.candles[i]
        now = bar["ts"] + timedelta(seconds=self.tf_seconds)
        if now.date() != self.day:
            self.day = now.date()
            self.trades_today = 0
            self.daily_realized = 0.0
        sprd = self.cost_model.spread_at(now) if self.cost_model else self.spread
        sprd_obs = (self.cost_model.filter_spread_at(now)
                    if self.cost_model else self.spread)
        slip = (self.cost_model.slippage_usd_per_fill
                if self.cost_model else self.slippage)
        o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]

        # 1) kelola posisi terbuka: SL/TP/time exit (identik run_backtest)
        if self.position is not None:
            event = self.broker.on_bar(self.position, o, h, l, c, sprd, now,
                                       slippage=slip)
            if event is not None:
                self._close_position(event.price, event.reason, now, sprd)

        # 2) keputusan policy saat flat
        if self.position is None and self.trades_today < self.max_trades_per_day:
            if action == BUY:
                self._try_entry("BUY", c, sprd, sprd_obs, slip, now, i)
            elif action == SELL:
                self._try_entry("SELL", c, sprd, sprd_obs, slip, now, i)
        elif self.position is not None and action == CLOSE:
            exit_price = (c - sprd / 2 - slip if self.position.side == "BUY"
                          else c + sprd / 2 + slip)
            self._close_position(exit_price, "AGENT", now, sprd)

        # 3) akhir window: tutup posisi tersisa di close terakhir (END),
        #    persis penanganan akhir run_backtest
        if i == self.end_idx - 1 and self.position is not None:
            exit_price = (c - sprd / 2 - slip if self.position.side == "BUY"
                          else c + sprd / 2 + slip)
            self._close_position(exit_price, "END", now, sprd)

        # 4) reward: delta equity mark-to-market / ATR14 (PnL disesuaikan risiko)
        if self.position is not None:
            self._bars_held += 1
        bid = c - sprd_obs / 2
        ask = c + sprd_obs / 2
        equity = self.balance
        if self.position is not None:
            equity = round(equity + unrealized(self.position, bid, ask), 2)
        atr = self.feat["atr"][i]
        reward = (equity - self.equity_prev) / atr if atr > 0 else 0.0
        self.equity_prev = equity

        self.i += 1
        terminated = False
        truncated = self.i >= self.end_idx
        self._done = truncated
        info = {"i": self.i - 1, "balance": self.balance, "equity": equity,
                "trades": len(self.trades), "daily_realized": self.daily_realized}
        return self._obs(), float(reward), terminated, truncated, info

    # ---------------------------------------------------------------- helpers

    def _obs(self) -> np.ndarray:
        i = self.i
        f = self.feat
        lo = max(0, i - OBS_BARS + 1)
        idx = np.arange(lo, i + 1)
        ch1 = f["ret"][idx] / f["sigma"][idx]
        ch2 = (f["high"][idx] - f["low"][idx]) / f["atr"][idx]
        if len(idx) < OBS_BARS:  # padding nol di awal seri
            pad = OBS_BARS - len(idx)
            ch1 = np.concatenate([np.zeros(pad), ch1])
            ch2 = np.concatenate([np.zeros(pad), ch2])
        bar = self.candles[i]
        now = bar["ts"] + timedelta(seconds=self.tf_seconds)
        sprd_obs = (self.cost_model.filter_spread_at(now)
                    if self.cost_model else self.spread)
        pos_side = 0.0
        pos_r = 0.0
        pos_bars = 0.0
        if self.position is not None:
            pos_side = 1.0 if self.position.side == "BUY" else -1.0
            bid = bar["close"] - sprd_obs / 2
            ask = bar["close"] + sprd_obs / 2
            unr = unrealized(self.position, bid, ask)
            pos_r = unr / max(self.balance * self.risk_per_trade, 1e-9)
            pos_bars = self._bars_held / 24.0
        obs = np.concatenate([
            ch1, ch2,
            [f["rsi"][i] / 100.0,
             f["atr"][i] / f["close"][i] * 10.0,
             f["hour_sin"][i], f["hour_cos"][i], f["dow"][i],
             sprd_obs / self.max_spread_abs,
             pos_side, pos_r, pos_bars],
        ]).astype(np.float32)
        assert obs.shape == (OBS_DIM,)
        return obs

    def _try_entry(self, side: str, close: float, sprd: float, sprd_obs: float,
                   slip: float, now, i: int) -> None:
        atr = self.feat["atr"][i]
        sl_dist = self.sl_atr_mult * atr
        if sl_dist < self.min_sl_distance:
            return
        sl = close - sl_dist if side == "BUY" else close + sl_dist
        tp = close + self.tp_rr * sl_dist if side == "BUY" else close - self.tp_rr * sl_dist
        bid = close - sprd_obs / 2
        ask = close + sprd_obs / 2
        volume = self._size_volume(sl_dist, self.balance)
        intent = {"symbol": self.symbol, "side": side, "volume": volume,
                  "sl": round(sl, 2), "tp": round(tp, 2)}
        decision = risk_gate(intent,
                             RiskContext(settings=self.settings, bid=bid, ask=ask,
                                         tick_age_s=0.1,
                                         daily_pnl=self.daily_realized,
                                         orders_last_minute=0))
        if not decision.ok:
            return
        entry = ask + slip if side == "BUY" else bid - slip
        self.position = PaperPosition(
            order_id=str(i), side=side, volume=volume, entry_price=entry,
            sl=round(sl, 2), tp=round(tp, 2), opened_at=now,
            strategy=self.strategy_id, contract_size=self.contract_size)
        self._bars_held = 0
        self.trades_today += 1
        self.trades.append({
            "entry_bar": i, "side": side, "volume": volume,
            "entry_price": round(entry, 2), "sl": round(sl, 2), "tp": round(tp, 2),
            "opened_at": now.isoformat(),
            "risk_usd": round(self.balance * self.risk_per_trade, 2),
            "reason": f"rl_action_{side.lower()}", "session": session_of(now),
            "spread_at_entry": round(sprd, 3),
            "filter_spread_at_entry": round(sprd_obs, 3),
        })

    def _close_position(self, exit_price: float, reason: str, now,
                        sprd: float) -> None:
        pos = self.position
        gross = ((exit_price - pos.entry_price) if pos.side == "BUY"
                 else (pos.entry_price - exit_price)) * self.contract_size * pos.volume
        commission = (self.cost_model.commission_usd(pos.volume)
                      if self.cost_model else 0.0)
        net = round(gross - commission, 2)
        self.balance = round(self.balance + net, 2)
        self.daily_realized = round(self.daily_realized + net, 2)
        self.commission_total = round(self.commission_total + commission, 2)
        risk_usd = self.trades[-1]["risk_usd"] if self.trades else 0.0
        self.trades[-1].update({
            "exit_price": round(exit_price, 2), "exit_reason": reason,
            "gross_profit": round(gross, 2), "commission_usd": commission,
            "profit": net, "closed_at": now.isoformat(),
            "r_multiple": round(net / risk_usd, 3) if risk_usd else None,
        })
        self.position = None
        self._bars_held = 0

    def _size_volume(self, sl_dist: float, equity: float) -> float:
        """Risk-based sizing, mirror strategies/london_breakout._size_volume."""
        raw = equity * self.risk_per_trade / (sl_dist * self.contract_size)
        step = 0.01
        volume = max(0.01, min(self.max_volume, math.floor(raw / step) * step))
        return round(volume, 2)

    def metrics(self, *, keep_trades: bool = False) -> dict:
        """Metrik identik dengan run_backtest (paper.backtest.summarize)."""
        result = summarize(self.trades, self.equity0, self.balance, self.spread,
                           self.slippage, cost_model=self.cost_model,
                           commission_total=self.commission_total,
                           strategy_id=self.strategy_id)
        if not keep_trades:
            result.pop("trades_detail", None)
        return result


def run_policy(env: RlTradingEnv, model, *, deterministic: bool = True) -> dict:
    """Jalankan policy deterministik di env; kembalikan metrik window."""
    obs, _ = env.reset()
    done = False
    actions = {HOLD: 0, BUY: 0, SELL: 0, CLOSE: 0}
    while not done:
        action, _ = model.predict(obs, deterministic=deterministic)
        action = int(action)
        actions[action] += 1
        obs, _reward, _term, trunc, _info = env.step(action)
        done = trunc
    metrics = env.metrics()
    metrics["action_counts"] = actions
    return metrics
