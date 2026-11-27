"""Risk gate: a pure function. No DB, no I/O - callers assemble RiskContext."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import degradation  # gate degradation status (PRD §10.3), modul murni
from . import drawdown  # logika + ambang drawdown harian bersama (A6)

# Toleransi floating-point untuk perbandingan boundary (spread/SL/risk tepat
# di limit harus LOULUS, bukan ditolak karena error biner 1e-13).
_EPS = 1e-9

# t_baeb3ce4 (lanjutan t_4651d431): order dari user ber-role 'qa' BUKAN trafik
# live. Posisi yang order-nya dibuat user qa tidak boleh dihitung daily_pnl --
# kontaminasinya membuat auto-halt drawdown palsu (insiden 25 Nov 18:18 WIB:
# 56 posisi QA closed -51.03 ikut terhitung, daily_pnl -121.36 <= -100 padahal
# rugi live hanya -70.33). Mirror anomaly.SQL_EXCLUDE_QA, dua jalur pengenalan:
# (1) compensating event QA_REATTRIBUTED (koreksi historis, append-only), atau
# (2) username pada event RECEIVED milik user ber-role 'qa'.
# Dipakai pada query yang meng-alias tabel positions sebagai `p`.
SQL_EXCLUDE_QA_POSITION = (
    "AND NOT EXISTS ("
    "  SELECT 1 FROM order_events e"
    "  WHERE e.order_id = p.order_id AND e.to_status = 'QA_REATTRIBUTED')"
    "AND NOT EXISTS ("
    "  SELECT 1 FROM users u"
    "  WHERE u.role = 'qa'"
    "    AND u.username = ("
    "      SELECT e2.payload->>'username' FROM order_events e2"
    "      WHERE e2.order_id = p.order_id AND e2.to_status = 'RECEIVED'"
    "      ORDER BY e2.id LIMIT 1))"
)

# Batas khusus agent LLM (t_f2llm2, lebih ketat dari A8). Didefinisikan di
# sini (modul murni) sebagai satu-sumber kebenaran; dibaca risk_gate dari
# RiskContext.settings key 'llm_risk' dan dipakai llm_risk.py untuk monitor.
DEFAULT_LLM_RISK: dict = {
    "max_orders_per_min": 2,        # usulan kartu (A8 = 10/min)
    "max_orders_per_day": 20,       # usulan kartu
    "cooldown_s": 240.0,            # jeda minimum antar order LLM diterima gate
    # AUDIT-A2: ambang drawdown breaker = ambang Risk Ops (persen), bukan
    # angka default terpisah (dulu 1.5% -> pause di 1.88% walau Ops 10%).
    "drawdown_pause_pct": drawdown.DEFAULT_DAILY_DRAWDOWN_PCT,
    "consecutive_failed_pause": 3,  # 3 order LLM FAILED beruntun -> pause agent
    "ea_offline_block_s": 60.0,     # EA offline > 60s -> tolak order LLM
    "check_interval_seconds": 10.0, # periodik evaluasi breaker (monitor loop)
}


@dataclass
class RiskContext:
    settings: dict
    bid: float | None = None
    ask: float | None = None
    tick_age_s: float | None = None
    daily_pnl: float = 0.0
    orders_last_minute: int = 0
    # Multipair (F1): eksposur terbuka AGREGAT lintas simbol (notional USD)
    # dan equity saat ini - keduanya dirakit caller dari DB + tick terbaru.
    open_exposure_usd: float = 0.0
    equity: float | None = None
    # LLM (t_f2llm2): lapisan batas tambahan untuk order milik agent LLM
    # (role 'agent' atau strategy 'llm'). Caller yang mengisi; gate umum
    # di bawah tetap berlaku penuh untuk order LLM.
    is_llm: bool = False
    llm_orders_last_minute: int = 0
    llm_orders_today: int = 0
    llm_cooldown_remaining_s: float = 0.0
    ea_offline_s: float | None = None
    # Degradation (PRD §10.3): status strategi peng order. DEGRADED = tidak
    # boleh tambah risiko baru; HALTED = berhenti entry baru. None/tanpa
    # state = NORMAL (order manual/legacy tanpa strategi terdaftar).
    degradation_status: str | None = None
    # RISK-D (t_a172bb7b): batas per-strategy dari config efektif
    # merge(global, override) -- override tidak pernah melebihi global
    # (hard ceiling divalidasi di app/risk_config.py). None = tidak ada
    # batas tambahan (order manual / limit = global yang sudah dicek).
    strategy_id: str | None = None
    strategy_max_positions: int | None = None
    strategy_open_positions: int = 0
    strategy_daily_loss_limit: float | None = None
    strategy_daily_pnl: float = 0.0


@dataclass
class RiskDecision:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    halt: bool = False  # daily drawdown breach -> caller must auto-halt


def symbol_spec(symbol: str, settings: dict) -> dict | None:
    """Spec risk per-simbol dari settings, atau None bila tidak ada (fail-closed).

    Spec parsial (key risk yang diwajibkan gate ada yang hilang) diperlakukan
    sebagai tidak dapat dibaca -> None -> order ditolak "no risk spec"
    (PRD 6.4), bukan KeyError 500 di tengah gate.
    """
    specs = settings.get("symbol_specs") or {}
    spec = specs.get(symbol)
    if not isinstance(spec, dict) or not spec:
        return None
    if any(k not in spec for k in
           ("contract_size", "sl_min_usd", "sl_max_usd", "vol_max_lot",
            "spread_abs_max_usd")):
        return None
    return dict(spec)


def _llm_limits(settings: dict) -> dict:
    """Batas LLM efektif: default <- settings key 'llm_risk' (merge parsial)."""
    cfg = dict(DEFAULT_LLM_RISK)
    raw = settings.get("llm_risk")
    if isinstance(raw, dict):
        for key in cfg:
            if raw.get(key) is not None:
                cfg[key] = raw[key]
    return cfg


def _kill_switch_blocks(order: dict, settings: dict) -> str | None:
    """Mode-aware kill-switch check. Return alasan penolakan atau None.

    Menerima state dict baru (kill_switch.normalize_state) atau bool legacy.

    Sumber kebenaran HANYA settings 'kill_switch'. Flag legacy 'halted' adalah
    mirror display (kill_switch.sync_legacy_halted) dan sengaja TIDAK dibaca di
    sini: mirror yang tertinggal True dulu membuat semua order ditolak
    selamanya setelah satu auto-halt (insiden 25 Nov 2026, t_4d524475).
    """
    raw = settings.get("kill_switch")
    active = False
    mode = None
    strategy = None
    if raw is True:
        active, mode = True, "STOP_NEW_ORDERS"
    elif isinstance(raw, dict):
        active = bool(raw.get("active"))
        mode = raw.get("mode")
        strategy = raw.get("strategy")
    if not active:
        return None

    if mode == "PAUSE_STRATEGY":
        paused = settings.get("paused_strategies") or []
        order_strategy = (order.get("strategy") or "manual").lower()
        if not any(s.lower() == order_strategy for s in paused):
            return None  # strategi ini tidak di-pause
        return f"kill-switch PAUSE_STRATEGY: strategi '{order_strategy}' sedang di-pause"
    return f"kill-switch aktif (mode: {mode or 'STOP_NEW_ORDERS'})"


def risk_gate(order: dict, ctx: RiskContext) -> RiskDecision:
    """Validate one order intent against settings and live market context.

    Checks: kill-switch (mode-aware), allowed symbol, per-symbol risk spec
    (fail-closed bila simbol belum punya spec), volume bounds (per-simbol A3
    + legacy global backstop), SL/TP mandatory and on the correct side of
    price, SL distance within per-symbol A2 bounds, per-trade risk A5
    (0.5% equity dari jarak SL × contract size), aggregate open exposure A4
    lintas simbol (notional USD), fresh tick + per-symbol spread filter A9,
    daily drawdown (auto-halt), account-level order rate limit A8.
    Untuk order LLM (ctx.is_llm) tambahan: rate limit LLM ketat (2/min,
    20/hari), cooldown setelah order diterima, EA offline, dan pause
    circuit breaker agent (t_f2llm2).
    """
    s = ctx.settings
    reasons: list[str] = []
    halt = False

    ks_reason = _kill_switch_blocks(order, s)
    if ks_reason:
        reasons.append(ks_reason)

    # Degradation gate (PRD §10.3): DEGRADED/HALTED memblokir entry baru
    # strategi terkait (order manual/LLM tanpa strategi terdaftar lolos).
    deg_reason = degradation.entry_block_reason(ctx.degradation_status)
    if deg_reason:
        reasons.append(deg_reason)

    if order["symbol"] not in (s.get("allowed_symbols") or ["XAUUSD"]):
        reasons.append(f"symbol {order['symbol']} not allowed")

    spec = symbol_spec(order["symbol"], s)
    if spec is None and isinstance(s.get("symbol_specs"), dict) and s.get("symbol_specs"):
        # Mode multipair (settings punya symbol_specs) tapi simbol ini tanpa
        # spec -> fail-closed: simbol tanpa spec risk tidak pernah lolos
        # (PRD 6.4: tolak bila contract specification tidak dapat dibaca).
        # Settings TANPA symbol_specs = mode legacy (backtest/paper): semantik
        # gate lama dipertahankan apa adanya.
        reasons.append(f"no risk spec for symbol {order['symbol']}")

    try:
        volume = float(order["volume"])
    except (TypeError, ValueError):
        volume = 0.0
    if volume <= 0:
        reasons.append("volume must be positive")
    else:
        if spec is not None:
            vol_max = float(spec["vol_max_lot"])
            if volume > vol_max + _EPS:
                reasons.append(
                    f"volume {volume} exceeds max {vol_max} for {order['symbol']}")
        legacy_max = float(s.get("max_volume", 1.0))
        if volume > legacy_max + _EPS:
            reasons.append(f"volume {volume} exceeds max {s.get('max_volume')}")

    sl = order.get("sl")
    tp = order.get("tp")
    if sl is None:
        reasons.append("SL is mandatory")
    if tp is None:
        reasons.append("TP is mandatory")

    price = ctx.ask if order.get("side") == "BUY" else ctx.bid
    if price is not None and sl is not None and tp is not None:
        if order.get("side") == "BUY" and not (sl < price < tp):
            reasons.append("BUY requires SL < price < TP")
        if order.get("side") == "SELL" and not (tp < price < sl):
            reasons.append("SELL requires TP < price < SL")

    # Jarak SL per-simbol (A2) + risiko per trade (A5). Distance diukur dari
    # harga eksekusi (ask utk BUY, bid utk SELL).
    sl_distance: float | None = None
    if price is not None and sl is not None:
        sl_distance = abs(price - float(sl))
        if spec is not None:
            sl_min = float(spec["sl_min_usd"])
            sl_max = float(spec["sl_max_usd"])
            if sl_distance < sl_min - _EPS:
                reasons.append(
                    f"SL distance {sl_distance:.2f} below min {sl_min} for {order['symbol']}")
            elif sl_distance > sl_max + _EPS:
                reasons.append(
                    f"SL distance {sl_distance:.2f} exceeds max {sl_max} for {order['symbol']}")

    if spec is not None:
        contract_size = float(spec["contract_size"])
        # A5: risk per trade = jarak SL × contract size × lot, ≤ risk pct equity.
        if sl_distance is not None:
            equity = ctx.equity
            if equity is None:
                equity = float(s.get("daily_start_balance", 10000.0))
            risk_pct = float(s.get("risk_per_trade_pct", 0.5))
            risk_usd = sl_distance * contract_size * volume
            risk_cap = abs(float(equity)) * risk_pct / 100.0
            if risk_usd > risk_cap + _EPS:
                reasons.append(
                    f"trade risk {risk_usd:.2f} exceeds {risk_pct}% of equity "
                    f"({risk_cap:.2f})")
        # A4: eksposur terbuka agregat lintas simbol (notional USD). Notional
        # order ini dihitung dari harga eksekusi saat ini.
        if price is not None:
            order_notional = volume * contract_size * price
            exposure_cap = float(s.get("exposure_max_usd", 0.0))
            total_exposure = ctx.open_exposure_usd + order_notional
            if total_exposure > exposure_cap + _EPS:
                reasons.append(
                    f"open exposure {total_exposure:.2f} exceeds max "
                    f"{exposure_cap:.2f} (open {ctx.open_exposure_usd:.2f} + "
                    f"order {order_notional:.2f})")

    # A10: tick basi -> tolak. Ambang dibaca dari settings `max_tick_age_s`
    # (final 3,0 s, KEPUTUSAN_OWNER §I / 26 Nov 2026). Sebelumnya hardcoded
    # 10 s, sehingga A10 tidak bisa ditegakkan lewat settings/policy.
    max_tick_age_s = float(s.get("max_tick_age_s", 3.0))
    if ctx.tick_age_s is None or ctx.tick_age_s > max_tick_age_s:
        reasons.append("no fresh market data for spread filter")
    elif ctx.bid is not None and ctx.ask is not None:
        spread = ctx.ask - ctx.bid
        if spec is not None:
            spread_max = float(spec["spread_abs_max_usd"])
        else:
            spread_max = float(s.get("max_spread", 0.5))
        if spread > spread_max + _EPS:
            reasons.append(f"spread {spread:.2f} exceeds max {spread_max}")

    # A6 (keputusan owner 25 Nov 2026, AUDIT-A2): auto-halt HANYA dari
    # persen equity awal hari di halaman Ops
    # (`kill_switch_triggers.daily_drawdown_pct`), sama dengan evaluator
    # kill-switch dan breaker LLM. Field profil `max_daily_drawdown` (USD)
    # TIDAK lagi memicu halt: dua angka untuk satu risiko membuat auto-halt
    # tidak sesuai parameter Ops (bug: Ops 10%, halt di -100 USD).
    dd_pct = drawdown.pct_from_pnl(ctx.daily_pnl,
                                   drawdown.start_balance(s))
    dd_limit_pct = drawdown.limit_pct(s)
    if dd_limit_pct is not None and dd_pct >= dd_limit_pct - _EPS:
        reasons.append(
            f"daily drawdown {dd_pct:.2f}% of start balance reached limit "
            f"{dd_limit_pct}% (kill_switch_triggers.daily_drawdown_pct)")
        halt = True

    # RISK-D: batas per-strategy (max posisi + rugi harian strategi). Nilai
    # sudah <= global saat masuk sini, jadi lapisan ini hanya bisa lebih
    # ketat. Pelanggaran per-strategy TIDAK memicu halt akun (halt tetap
    # domain drawdown global) -- hanya order strategi itu yang ditolak.
    if ctx.strategy_max_positions is not None and \
            ctx.strategy_open_positions >= int(ctx.strategy_max_positions):
        reasons.append(
            f"strategy '{ctx.strategy_id}' max positions reached "
            f"(open {ctx.strategy_open_positions} >= max "
            f"{int(ctx.strategy_max_positions)})")
    if ctx.strategy_daily_loss_limit is not None and \
            ctx.strategy_daily_pnl <= -abs(float(ctx.strategy_daily_loss_limit)):
        reasons.append(
            f"strategy '{ctx.strategy_id}' daily loss limit reached "
            f"(pnl {ctx.strategy_daily_pnl:.2f} <= "
            f"-{float(ctx.strategy_daily_loss_limit):.2f})")

    if ctx.orders_last_minute >= int(s.get("max_orders_per_min", 10)):
        reasons.append("order rate limit exceeded")

    if ctx.is_llm:
        reasons.extend(_llm_reasons(ctx, _llm_limits(s)))

    return RiskDecision(ok=not reasons, reasons=reasons, halt=halt)


def _llm_reasons(ctx: RiskContext, cfg: dict) -> list[str]:
    """Lapisan batas khusus order LLM (t_f2llm2), di atas gate umum.

    Pause circuit breaker dicek duluan: agent yang sudah di-pause owner
    tidak boleh order lagi walau semua limit lain masih longgar.
    """
    reasons: list[str] = []
    pause = ctx.settings.get("llm_agent_pause")
    if isinstance(pause, dict) and pause.get("active"):
        reasons.append(f"LLM agent paused: {pause.get('reason')}")
    if ctx.llm_orders_last_minute >= int(cfg["max_orders_per_min"]):
        reasons.append(
            f"LLM order rate limit exceeded (max {cfg['max_orders_per_min']}/min)")
    if ctx.llm_orders_today >= int(cfg["max_orders_per_day"]):
        reasons.append(
            f"LLM daily order limit exceeded (max {cfg['max_orders_per_day']}/day)")
    if ctx.llm_cooldown_remaining_s > 0:
        reasons.append(
            f"LLM cooldown active ({ctx.llm_cooldown_remaining_s:.0f}s remaining)")
    if ctx.ea_offline_s is not None and ctx.ea_offline_s > float(cfg["ea_offline_block_s"]):
        reasons.append(
            f"EA offline {ctx.ea_offline_s:.0f}s exceeds max "
            f"{float(cfg['ea_offline_block_s']):.0f}s")
    return reasons
