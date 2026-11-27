"""Portfolio Risk Manager (PRD v2.2 §7).

Lapisan risiko PORTOFOLIO di atas risk gate per-order (app.risk):
mengukur worst-case loss seluruh posisi + order pending/SENT sampai SL,
termasuk biaya (komisi) dan buffer (spread + slippage), lalu memutuskan
apakah order BARU masih boleh masuk.

Murni fungsi keputusan: tidak ada DB/IO di path evaluasi. Caller merakit
PortfolioLeg + PortfolioFeed (collector DB tersedia di bawah untuk fund2).
Modul ini TIDAK pernah menutup posisi terbuka (PRD §7.3): hanya memutuskan
order baru; penutupan tetap policy owner eksplisit (kill-switch/flatten).

Prinsip gagal-aman (fail-closed):
- Contract spec / tick value yang tidak terverifikasi -> order ditolak.
- Posisi tanpa SL (ditolak broker / tidak terpasang) -> loss tak terbatas
  -> order BARU diblokir sampai posisi itu diselesaikan owner.
- Equity/margin feed hilang atau stale -> tidak ada posisi baru.
- Tidak ada kredit hedging/korelasi: semua posisi diasumsikan kena SL
  bersamaan (worst case), sebagaimana diperlukan PRD §7.3.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

# Kunci advisory lock PostgreSQL untuk serialisasi evaluasi portofolio.
# Dua sinyal simultan harus dievaluasi terhadap snapshot portofolio yang
# sama; tanpa lock, dua request bisa membaca state yang sama lalu sama-sama
# lolos (oversubscription). Dipanggil via pg_advisory_xact_lock() di dalam
# transaksi order sehingga otomatis dilepas saat commit/rollback.
PORTFOLIO_LOCK_KEY = 7_312_011_002_022_003

# Status order yang masih "hidup" dan harus dihitung sebagai risiko tertunda
# (PRD §7.2: order pending dan SENT agar tidak oversubscription). RECEIVED/
# RISK_PASS adalah status transient dalam transaksi /orders; tetap dihitung
# bila ditemukan (request crash sebelum transisi).
PENDING_ORDER_STATUSES = ("RECEIVED", "RISK_PASS", "SENT", "STUCK")

# Default konfigurasi portofolio. Semua nilai adalah [USULAN] PRD §7.4 /
# turunan kalibrasinya; owner dapat mengubah via settings key 'portfolio_risk'
# (merge parsial: key yang ada di DB menang).
DEFAULT_PORTFOLIO_RISK: dict = {
    "enabled": True,
    "max_risk_per_trade_pct": 0.5,     # A5: risiko per trade ≤ % equity
    "max_open_risk_pct": 2.0,          # total worst-case open risk ≤ % equity (≈4 trade)
    "stress_max_risk_pct": 3.0,        # loss skenario stress ≤ % equity (= halt harian A6)
    "max_total_volume_lot": 0.30,      # PRD §7.4: total volume maksimum
    "max_margin_utilization_pct": 20.0,  # margin terpakai ≤ % equity
    "max_symbol_risk_pct": 1.0,        # konsentrasi: worst-case loss per simbol ≤ % equity
    "commission_per_lot_usd": 7.0,     # komisi round-turn per lot (biaya)
    "leverage": 100.0,                 # untuk margin = notional / leverage
    "max_feed_age_s": 60.0,            # equity/margin feed lebih tua -> blokir
    "stress": {
        "gap_pct": 0.5,                # gap melewati SL: % harga mark
        "spread_multiplier": 3.0,      # spread melebar 3x saat stress
        "slippage_usd": 0.35,          # slippage default (satuan harga)
    },
}


def portfolio_config(settings: dict) -> dict:
    """Batas portofolio efektif: default <- settings key 'portfolio_risk' (merge parsial)."""
    cfg = {
        **DEFAULT_PORTFOLIO_RISK,
        "stress": dict(DEFAULT_PORTFOLIO_RISK["stress"]),
    }
    raw = settings.get("portfolio_risk")
    if isinstance(raw, dict):
        for key, val in raw.items():
            if key == "stress" and isinstance(val, dict):
                cfg["stress"].update({k: v for k, v in val.items() if v is not None})
            elif val is not None:
                cfg[key] = val
    return cfg


def _finite(x) -> float | None:
    """Float berhingga (bukan NaN/Inf) atau None."""
    if isinstance(x, bool) or x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


@dataclass(frozen=True)
class PortfolioSpec:
    """Contract spec terverifikasi untuk perhitungan risiko portofolio.

    tick_value = nilai USD per tick per lot; tick_size = perubahan harga per
    tick. value_per_price_unit = tick_value / tick_size = USD per 1.0 pergerakan
    harga per lot (sumber kebenaran tick value, bukan asumsi contract_size).
    """
    symbol: str
    contract_size: float
    tick_value: float
    tick_size: float
    slippage_usd: float
    spread_fallback_usd: float = 0.0  # dipakai sbg spread stress bila tick absen

    @property
    def value_per_price_unit(self) -> float:
        return self.tick_value / self.tick_size


def portfolio_spec(symbol: str, settings: dict) -> tuple[PortfolioSpec | None, str | None]:
    """Spec portofolio terverifikasi, atau (None, alasan) bila tak terverifikasi.

    PRD §7.3: tolak order bila contract specification/tick value tidak dapat
    diverifikasi. Verifikasi berarti: settings symbol_specs[symbol] memuat
    contract_size, tick_value, tick_size yang berhingga dan positif, plus
    flag spec_verified=True (provenance verifikasi manual/owner).
    """
    specs = settings.get("symbol_specs") or {}
    raw = specs.get(symbol) if isinstance(specs, dict) else None
    if not isinstance(raw, dict) or not raw:
        return None, f"contract spec not verified for {symbol}: no spec"
    if not raw.get("spec_verified"):
        return None, f"contract spec not verified for {symbol}: spec_verified flag missing/false"
    contract_size = _finite(raw.get("contract_size"))
    tick_value = _finite(raw.get("tick_value"))
    tick_size = _finite(raw.get("tick_size"))
    if contract_size is None or contract_size <= 0:
        return None, f"contract spec not verified for {symbol}: invalid contract_size"
    if tick_value is None or tick_value <= 0:
        return None, f"contract spec not verified for {symbol}: invalid tick_value"
    if tick_size is None or tick_size <= 0:
        return None, f"contract spec not verified for {symbol}: invalid tick_size"
    slippage = _finite(raw.get("slippage_usd"))
    spread_fb = _finite(raw.get("spread_abs_max_usd")) or 0.0
    return PortfolioSpec(
        symbol=symbol,
        contract_size=contract_size,
        tick_value=tick_value,
        tick_size=tick_size,
        slippage_usd=slippage if slippage is not None and slippage >= 0 else 0.0,
        spread_fallback_usd=spread_fb if spread_fb > 0 else 0.0,
    ), None


@dataclass(frozen=True)
class PortfolioLeg:
    """Satu sumber risiko: posisi terbuka atau order pending/SENT.

    state: 'OPEN' (posisi), atau status order ('RECEIVED', 'RISK_PASS',
    'SENT', 'STUCK'). entry = harga fill (posisi) atau harga diminta
    (pending/SENT). sl=None berarti SL tidak terpasang/ditolak broker.
    """
    symbol: str
    side: str
    volume: float
    entry: float
    sl: float | None
    state: str = "OPEN"
    ref: str = ""  # ticket posisi / order id untuk audit


@dataclass(frozen=True)
class PortfolioFeed:
    """Feed akun: equity + margin (broker) dengan umur masing-masing.

    margin_used=None berarti feed margin broker tidak tersedia; margin lalu
    dihitung dari notional posisi (selalu segar by construction). Umur diukur
    dalam detik; None berarti umur tidak diketahui -> stale.
    """
    equity: float | None = None
    equity_age_s: float | None = None
    margin_used: float | None = None
    margin_age_s: float | None = None
    balance: float | None = None
    free_margin: float | None = None
    margin_source: str = "computed"  # 'broker' | 'computed'


# ── Perhitungan loss ─────────────────────────────────────────────────────────


def _mark_mid(mark: tuple[float, float] | None) -> float | None:
    if mark is None:
        return None
    bid, ask = mark
    b, a = _finite(bid), _finite(ask)
    if b is None or a is None or a < b:
        return None
    return (b + a) / 2.0


def _spread_of(mark: tuple[float, float] | None) -> float | None:
    if mark is None:
        return None
    bid, ask = mark
    b, a = _finite(bid), _finite(ask)
    if b is None or a is None or a < b:
        return None
    return a - b


def _worst_fill(side: str, entry: float, slippage: float) -> float:
    """Harga fill terburuk untuk order pending/SENT (slippage melawan posisi)."""
    return entry + slippage if side == "BUY" else entry - slippage


def leg_worst_case_loss(
    leg: PortfolioLeg,
    spec: PortfolioSpec,
    mark: tuple[float, float] | None,
    cfg: dict,
    stress: bool = False,
) -> float | None:
    """Worst-case loss satu leg sampai SL, termasuk biaya + buffer (USD).

    Base (stress=False): jarak SL dari harga referensi terburuk + spread saat
    ini + slippage, dikali tick value, plus komisi round-turn.
    Stress (stress=True): tambahan gap (gap_pct × harga mark), spread
    dilebar (spread_multiplier × spread), slippage tetap. Beberapa SL kena
    bersamaan = jumlahkan semua leg (tidak ada kredit hedging/korelasi).

    Return None bila SL tidak terpasang (loss tak terbatas).
    """
    sl = _finite(leg.sl)
    if sl is None:
        return None
    volume = _finite(leg.volume)
    entry = _finite(leg.entry)
    if volume is None or volume <= 0 or entry is None or entry <= 0:
        return None
    s = cfg["stress"]
    slippage = spec.slippage_usd
    ref = entry
    if leg.state != "OPEN":
        # Pending/SENT: fill bisa lebih buruk dari harga diminta.
        ref = _worst_fill(leg.side, entry, slippage)
    dist = abs(ref - sl)
    spread = _spread_of(mark)
    if stress:
        mid = _mark_mid(mark) or entry
        gap = mid * float(s["gap_pct"]) / 100.0
        spread_eff = (spread if spread is not None else spec.spread_fallback_usd) \
            * float(s["spread_multiplier"])
        buffer = spread_eff + slippage + gap
    else:
        buffer = (spread if spread is not None else 0.0) + slippage
    loss = (dist + buffer) * spec.value_per_price_unit * volume \
        + float(cfg["commission_per_lot_usd"]) * volume
    return max(loss, 0.0)


def leg_notional(leg: PortfolioLeg, spec: PortfolioSpec, mark_price: float) -> float:
    """Notional bruto satu leg (Σ absolut, tanpa netting hedging)."""
    return abs(leg.volume * spec.contract_size * mark_price)


# ── Snapshot & keputusan ─────────────────────────────────────────────────────


@dataclass
class PortfolioSnapshot:
    """Angka agregat portofolio untuk audit/UI (JSON-able via asdict)."""
    equity: float | None = None
    open_risk_usd: float = 0.0
    stress_risk_usd: float = 0.0
    gross_exposure_usd: float = 0.0
    total_volume_lot: float = 0.0
    margin_used_usd: float = 0.0
    margin_utilization_pct: float = 0.0
    open_positions: int = 0
    pending_orders: int = 0
    sent_orders: int = 0
    unbounded_sl: int = 0
    per_symbol: dict = field(default_factory=dict)
    limits: dict = field(default_factory=dict)


@dataclass
class PortfolioDecision:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    snapshot: PortfolioSnapshot = field(default_factory=PortfolioSnapshot)


def _leg_mark(leg: PortfolioLeg, marks: dict) -> tuple[float, float] | None:
    return marks.get(leg.symbol)


def portfolio_snapshot(
    legs: list[PortfolioLeg],
    feed: PortfolioFeed,
    marks: dict,
    settings: dict,
) -> PortfolioSnapshot:
    """Agregat portofolio tanpa order kandidat (untuk UI/monitoring)."""
    cfg = portfolio_config(settings)
    snap = PortfolioSnapshot(equity=feed.equity, limits=cfg)
    margin_sum = 0.0
    for leg in legs:
        spec, err = portfolio_spec(leg.symbol, settings)
        mark = _leg_mark(leg, marks)
        mid = _mark_mid(mark) or leg.entry
        if spec is None:
            # Spec tidak terverifikasi untuk posisi hidup -> risiko tidak
            # dapat dihitung; tandai sebagai unbounded (fail-closed).
            snap.unbounded_sl += 1
            continue
        if _finite(leg.sl) is None:
            snap.unbounded_sl += 1
            continue
        volume = _finite(leg.volume) or 0.0
        base = leg_worst_case_loss(leg, spec, mark, cfg, stress=False)
        stress_loss = leg_worst_case_loss(leg, spec, mark, cfg, stress=True)
        if base is None or stress_loss is None:
            snap.unbounded_sl += 1
            continue
        notional = leg_notional(leg, spec, mid)
        margin_sum += notional / float(cfg["leverage"])
        snap.open_risk_usd += base
        snap.stress_risk_usd += stress_loss
        snap.gross_exposure_usd += notional
        snap.total_volume_lot += volume
        if leg.state == "OPEN":
            snap.open_positions += 1
        elif leg.state == "SENT":
            snap.sent_orders += 1
        else:
            snap.pending_orders += 1
        ps = snap.per_symbol.setdefault(leg.symbol, {
            "risk_usd": 0.0, "stress_usd": 0.0, "exposure_usd": 0.0,
            "volume_lot": 0.0, "unverified_spec": False})
        ps["risk_usd"] += base
        ps["stress_usd"] += stress_loss
        ps["exposure_usd"] += notional
        ps["volume_lot"] += volume
    snap.margin_used_usd = feed.margin_used if feed.margin_used is not None else margin_sum
    if feed.equity and feed.equity > 0:
        snap.margin_utilization_pct = snap.margin_used_usd / feed.equity * 100.0
    return snap


# ── Evaluasi order kandidat ──────────────────────────────────────────────────


def evaluate(
    candidate: dict,
    legs: list[PortfolioLeg],
    feed: PortfolioFeed,
    marks: dict,
    settings: dict,
) -> PortfolioDecision:
    """Putuskan apakah order BARU boleh masuk portofolio saat ini.

    candidate: {symbol, side, volume, sl, price?} — price opsional (harga
    eksekusi yang diharapkan); default mid tick. Semua limit dihitung
    SETELAH kandidat ditambahkan (post-trade), jadi order yang membuat
    total risk melewati limit pasti ditolak.
    """
    cfg = portfolio_config(settings)
    reasons: list[str] = []

    spec_c, spec_err = portfolio_spec(str(candidate.get("symbol") or ""), settings)
    if spec_c is None:
        reasons.append(spec_err or "contract spec not verified")

    # Feed equity/margin: hilang atau stale -> tidak buka posisi baru (PRD §7.3).
    equity_f = _finite(feed.equity)
    if equity_f is None:
        reasons.append("equity feed missing: new positions blocked")
    if feed.equity_age_s is None:
        reasons.append("equity feed age unknown: new positions blocked")
    elif feed.equity_age_s > float(cfg["max_feed_age_s"]):
        reasons.append(
            f"equity feed stale ({feed.equity_age_s:.0f}s > {float(cfg['max_feed_age_s']):.0f}s): "
            "new positions blocked")
    if feed.margin_used is not None:
        if _finite(feed.margin_used) is None:
            reasons.append("margin feed invalid: new positions blocked")
        elif feed.margin_age_s is None:
            reasons.append("margin feed age unknown: new positions blocked")
        elif feed.margin_age_s > float(cfg["max_feed_age_s"]):
            reasons.append(
                f"margin feed stale ({feed.margin_age_s:.0f}s > "
                f"{float(cfg['max_feed_age_s']):.0f}s): new positions blocked")

    # Kandidat tanpa SL = loss tak terbatas -> tolak (SL wajib, PRD §6.4).
    cand_leg = PortfolioLeg(
        symbol=str(candidate.get("symbol") or ""),
        side=str(candidate.get("side") or "BUY"),
        volume=_finite(candidate.get("volume")) or 0.0,
        entry=_finite(candidate.get("price")) or 0.0,
        sl=_finite(candidate.get("sl")),
        state="CANDIDATE",
        ref="candidate",
    )
    if cand_leg.entry <= 0:
        mark = marks.get(cand_leg.symbol)
        cand_leg = PortfolioLeg(
            symbol=cand_leg.symbol, side=cand_leg.side, volume=cand_leg.volume,
            entry=_mark_mid(mark) or 0.0, sl=cand_leg.sl, state="CANDIDATE",
            ref="candidate")
    if cand_leg.entry <= 0:
        reasons.append("candidate entry price unavailable")
    if cand_leg.sl is None:
        reasons.append("candidate SL missing: worst-case loss unbounded")
    if cand_leg.volume <= 0:
        reasons.append("candidate volume must be positive")

    snap = portfolio_snapshot(legs, feed, marks, settings)
    # Gabungkan kandidat ke snapshot post-trade (bila masih dapat dihitung).
    if spec_c is not None and cand_leg.entry > 0 and cand_leg.sl is not None \
            and cand_leg.volume > 0:
        mark = marks.get(cand_leg.symbol)
        cand_base = leg_worst_case_loss(cand_leg, spec_c, mark, cfg, stress=False)
        cand_stress = leg_worst_case_loss(cand_leg, spec_c, mark, cfg, stress=True)
        if cand_base is None or cand_stress is None:
            snap.unbounded_sl += 1
            reasons.append("candidate worst-case loss uncomputable")
        else:
            snap.open_risk_usd += cand_base
            snap.stress_risk_usd += cand_stress
            snap.gross_exposure_usd += leg_notional(
                cand_leg, spec_c, _mark_mid(mark) or cand_leg.entry)
            snap.total_volume_lot += cand_leg.volume
            snap.margin_used_usd += leg_notional(
                cand_leg, spec_c, _mark_mid(mark) or cand_leg.entry) / float(cfg["leverage"])
            if feed.equity and feed.equity > 0:
                snap.margin_utilization_pct = snap.margin_used_usd / feed.equity * 100.0
            ps = snap.per_symbol.setdefault(cand_leg.symbol, {
                "risk_usd": 0.0, "stress_usd": 0.0, "exposure_usd": 0.0,
                "volume_lot": 0.0, "unverified_spec": False})
            ps["risk_usd"] += cand_base
            ps["stress_usd"] += cand_stress
            ps["exposure_usd"] += leg_notional(
                cand_leg, spec_c, _mark_mid(mark) or cand_leg.entry)
            ps["volume_lot"] += cand_leg.volume

    # ── Limit portofolio (post-trade) ──
    if equity_f is not None and equity_f > 0:
        cap_per_trade = equity_f * float(cfg["max_risk_per_trade_pct"]) / 100.0
        if spec_c is not None and cand_leg.entry > 0 and cand_leg.sl is not None:
            cand_base = leg_worst_case_loss(cand_leg, spec_c, marks.get(cand_leg.symbol),
                                            cfg, stress=False)
            if cand_base is not None and cand_base > cap_per_trade + 1e-9:
                reasons.append(
                    f"portfolio: trade risk {cand_base:.2f} exceeds "
                    f"{cfg['max_risk_per_trade_pct']}% of equity ({cap_per_trade:.2f})")
        cap_open = equity_f * float(cfg["max_open_risk_pct"]) / 100.0
        if snap.open_risk_usd > cap_open + 1e-9:
            reasons.append(
                f"portfolio: total open risk {snap.open_risk_usd:.2f} exceeds "
                f"{cfg['max_open_risk_pct']}% of equity ({cap_open:.2f})")
        cap_stress = equity_f * float(cfg["stress_max_risk_pct"]) / 100.0
        if snap.stress_risk_usd > cap_stress + 1e-9:
            reasons.append(
                f"portfolio: stress loss {snap.stress_risk_usd:.2f} exceeds "
                f"{cfg['stress_max_risk_pct']}% of equity ({cap_stress:.2f})")
        cap_margin = equity_f * float(cfg["max_margin_utilization_pct"]) / 100.0
        if snap.margin_used_usd > cap_margin + 1e-9:
            reasons.append(
                f"portfolio: margin used {snap.margin_used_usd:.2f} exceeds "
                f"{cfg['max_margin_utilization_pct']}% of equity ({cap_margin:.2f})")
        cap_sym = equity_f * float(cfg["max_symbol_risk_pct"]) / 100.0
        for sym, ps in snap.per_symbol.items():
            if ps["risk_usd"] > cap_sym + 1e-9:
                reasons.append(
                    f"portfolio: concentration {sym} risk {ps['risk_usd']:.2f} exceeds "
                    f"{cfg['max_symbol_risk_pct']}% of equity ({cap_sym:.2f})")

    cap_exposure = _finite(settings.get("exposure_max_usd"))
    if cap_exposure is not None and snap.gross_exposure_usd > cap_exposure + 1e-9:
        reasons.append(
            f"portfolio: gross exposure {snap.gross_exposure_usd:.2f} exceeds "
            f"max {cap_exposure:.2f}")
    cap_volume = float(cfg["max_total_volume_lot"])
    if snap.total_volume_lot > cap_volume + 1e-9:
        reasons.append(
            f"portfolio: total volume {snap.total_volume_lot:.2f} exceeds "
            f"max {cap_volume:.2f} lot")
    if snap.unbounded_sl > 0:
        reasons.append(
            f"portfolio: {snap.unbounded_sl} open leg(s) without SL "
            "(missing/rejected): new positions blocked")

    return PortfolioDecision(ok=not reasons, reasons=reasons, snapshot=snap)


# ── Collector DB (fund2) ─────────────────────────────────────────────────────


async def collect_legs(conn, settings: dict) -> list[PortfolioLeg]:
    """Semua sumber risiko hidup: posisi OPEN + order pending/SENT (PRD §7.2)."""
    # import lambat: hindari siklus saat modul dipakai murni (fungsi keputusan)
    from . import config, market

    legs: list[PortfolioLeg] = []
    rows = await conn.execute(
        "SELECT ticket, symbol, side, volume, open_price, sl FROM positions "
        "WHERE status = 'OPEN'")
    for r in await rows.fetchall():
        legs.append(PortfolioLeg(
            symbol=r["symbol"], side=r["side"], volume=float(r["volume"]),
            entry=float(r["open_price"]) if r["open_price"] is not None else 0.0,
            sl=float(r["sl"]) if r["sl"] is not None else None,
            state="OPEN", ref=str(r["ticket"])))
    rows = await conn.execute(
        """
        SELECT id, symbol, side, volume, price_requested, sl, status FROM orders
        WHERE status = ANY(%s)
          -- STUCK yang sudah lewat grace period bukan risiko pending lagi:
          -- auto-reconciler worker (app.worker.resolve_stuck_orders)
          -- menyelesaikannya ke FILLED/FAILED. Tanpa pengecualian ini satu
          -- order STUCK dihitung sebagai leg tanpa SL dan memblokir semua
          -- order baru selamanya (insiden 25 Nov 2026).
          AND NOT (status = 'STUCK'
                   AND updated_at < now() - (%s * interval '1 second'))
        """,
        (list(PENDING_ORDER_STATUSES), float(config.STUCK_RESOLVE_AFTER_S)))
    for r in await rows.fetchall():
        tick = market.latest(r["symbol"])
        mid = ((float(tick["bid"]) + float(tick["ask"])) / 2.0) if tick else None
        entry = float(r["price_requested"]) if r["price_requested"] is not None else (
            mid or 0.0)
        legs.append(PortfolioLeg(
            symbol=r["symbol"], side=r["side"], volume=float(r["volume"]),
            entry=entry,
            sl=float(r["sl"]) if r["sl"] is not None else None,
            state=r["status"], ref=str(r["id"])))
    return legs


def collect_marks(symbols: list[str]) -> dict:
    """Tuple (bid, ask) terbaru per simbol dari tick in-memory; None bila absen."""
    from . import market

    marks: dict = {}
    for sym in set(symbols):
        tick = market.latest(sym)
        if tick and tick.get("bid") is not None and tick.get("ask") is not None:
            marks[sym] = (float(tick["bid"]), float(tick["ask"]))
        else:
            marks[sym] = None
    return marks


async def gate_order(conn, order: dict, settings: dict, equity: float | None) -> PortfolioDecision:
    """Gerbang portofolio untuk satu order baru di jalur /orders.

    equity berasal dari perhitungan DB dalam transaksi yang sama (segar by
    construction, age=0); margin dihitung dari notional (feed broker belum
    ada). Panggil di DALAM transaksi yang memegang pg_advisory_xact_lock
    (PORTFOLIO_LOCK_KEY) agar dua sinyal simultan tidak oversubscribe.
    """
    legs = await collect_legs(conn, settings)
    marks = collect_marks([l.symbol for l in legs] + [str(order.get("symbol"))])
    feed = PortfolioFeed(
        equity=equity,
        equity_age_s=0.0 if equity is not None else None,
        margin_used=None,
        margin_age_s=None,
        margin_source="computed",
    )
    return evaluate(order, legs, feed, marks, settings)
