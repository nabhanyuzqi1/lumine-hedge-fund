"""Model biaya backtest terkalibrasi (PRD 5.2, P2).

Rumus PRD 5.2: biaya backtest = spread Dukascopy x faktor koreksi
(rasio median HFM/Dukascopy per sesi) + haircut keamanan 20%.
Ditambah komisi per lot (round-turn) dan model slippage per fill.

Sesi mengikuti app.ingest.session_of: asia 21-07, london 07-12,
london_newyork 12-16, newyork 16-21 (UTC).

Faktor koreksi dihitung dari data HFM yang tersedia (baru ~2 hari pada
22 Nov 2026) dan wajib dikalibrasi ulang setiap data HFM bertambah.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.ingest import session_of

HAIRCUT_DEFAULT = 0.20           # PRD 5.2: haircut keamanan 20%
COMMISSION_PER_LOT_DEFAULT = 7.0  # USD per lot round-turn [USULAN]; HFM klasik
SLIPPAGE_PER_FILL_DEFAULT = 0.10  # USD per fill [USULAN]; dari fill nyata saat ada
FACTOR_CAP = 3.0                  # pengaman sampel HFM tipis
SESSIONS = ("asia", "london", "london_newyork", "newyork")


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    n = len(xs)
    mid = n // 2
    return xs[mid] if n % 2 else (xs[mid - 1] + xs[mid]) / 2.0


@dataclass(frozen=True)
class CostModel:
    """Spread per sesi + komisi + slippage. Immutable agar reproducible."""

    duka_spread_by_session: dict[str, float]
    hfm_spread_by_session: dict[str, float]
    factor_by_session: dict[str, float]
    filter_spread_by_session: dict[str, float]   # Duka x faktor (spread teramati)
    spread_by_session: dict[str, float]          # + haircut (biaya fill)
    haircut: float = HAIRCUT_DEFAULT
    commission_per_lot_round_usd: float = COMMISSION_PER_LOT_DEFAULT
    slippage_usd_per_fill: float = SLIPPAGE_PER_FILL_DEFAULT
    source: str = "dukascopy_m1+hfm_liquidity_samples"
    notes: list[str] = field(default_factory=list)

    # ------------------------------------------------------------- akses
    def spread_at(self, when: datetime) -> float:
        """Spread biaya fill (termasuk haircut) untuk sesi ts."""
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return self.spread_by_session[session_of(when)]

    def filter_spread_at(self, when: datetime) -> float:
        """Spread teramati (tanpa haircut): untuk snapshot likuiditas dan
        spread filter decide()/risk gate, meniru apa yang dilihat live."""
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return self.filter_spread_by_session[session_of(when)]

    def spread_median_15m(self, when: datetime) -> float:
        """Median 15 menit spread teramati: model per-sesi konstan per sesi,
        jadi median jendela 15 menit == nilai sesi saat itu."""
        return self.filter_spread_at(when)

    def commission_usd(self, volume: float) -> float:
        """Komisi round-turn untuk volume (lot) tertentu."""
        return round(self.commission_per_lot_round_usd * float(volume), 2)

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "duka_spread_by_session": self.duka_spread_by_session,
            "hfm_spread_by_session": self.hfm_spread_by_session,
            "factor_by_session": self.factor_by_session,
            "filter_spread_by_session": self.filter_spread_by_session,
            "spread_by_session": self.spread_by_session,
            "haircut": self.haircut,
            "commission_per_lot_round_usd": self.commission_per_lot_round_usd,
            "slippage_usd_per_fill": self.slippage_usd_per_fill,
            "notes": list(self.notes),
        }


def build_cost_model(duka_medians: dict[str, float], hfm_medians: dict[str, float],
                     *, haircut: float = HAIRCUT_DEFAULT,
                     commission_per_lot: float = COMMISSION_PER_LOT_DEFAULT,
                     slippage_per_fill: float = SLIPPAGE_PER_FILL_DEFAULT,
                     factor_cap: float = FACTOR_CAP,
                     source: str = "dukascopy_m1+hfm_liquidity_samples") -> CostModel:
    """Gabungkan median spread Dukascopy & HFM per sesi jadi CostModel.

    - faktor(sesi) = median HFM(sesi) / median Duka(sesi); sesi tanpa sampel
      memakai faktor global (median semua HFM / median semua Duka).
    - spread_akhir(sesi) = Duka(sesi) x faktor(sesi) x (1 + haircut).
    - faktor di-cap FACTOR_CAP agar sampel HFM tipis tidak menghasilkan
      spread mustahil; setiap penyimpangan dicatat di notes.
    """
    notes: list[str] = []
    duka = {k: float(v) for k, v in (duka_medians or {}).items() if v}
    hfm = {k: float(v) for k, v in (hfm_medians or {}).items() if v}
    if not duka:
        raise ValueError("median Dukascopy kosong: tidak bisa membangun cost model")
    duka_all = _median(list(duka.values()))
    hfm_all = _median(list(hfm.values()))
    if hfm_all is None or hfm_all <= 0 or duka_all is None or duka_all <= 0:
        raise ValueError("median HFM/Duka tidak valid untuk faktor koreksi")
    global_factor = hfm_all / duka_all
    if not hfm:
        notes.append("sampel HFM kosong: faktor global 1.0 dipakai (hanya haircut)")
        global_factor = 1.0

    factors: dict[str, float] = {}
    spreads: dict[str, float] = {}
    filters: dict[str, float] = {}
    for session in SESSIONS:
        d = duka.get(session)
        if d is None:
            d = duka_all
            notes.append(f"sesi {session}: tanpa sampel Duka, pakai median global {duka_all:.3f}")
        f = hfm.get(session)
        if f is None:
            f = global_factor
            notes.append(f"sesi {session}: tanpa sampel HFM, pakai faktor global {global_factor:.3f}")
        else:
            f = f / d
        if f > factor_cap:
            notes.append(f"sesi {session}: faktor {f:.3f} di-cap {factor_cap}")
            f = factor_cap
        factors[session] = round(f, 4)
        filters[session] = round(d * f, 3)              # spread teramati (filter)
        spreads[session] = round(d * f * (1.0 + haircut), 3)  # biaya fill (haircut)
    return CostModel(
        duka_spread_by_session={k: round(v, 4) for k, v in duka.items()},
        hfm_spread_by_session={k: round(v, 4) for k, v in hfm.items()},
        factor_by_session=factors,
        filter_spread_by_session=filters,
        spread_by_session=spreads,
        haircut=haircut,
        commission_per_lot_round_usd=commission_per_lot,
        slippage_usd_per_fill=slippage_per_fill,
        source=source,
        notes=notes,
    )


def hfm_session_medians(rows: list[dict]) -> dict[str, float]:
    """Median spread_avg per sesi dari baris liquidity_samples."""
    by: dict[str, list[float]] = {}
    for row in rows:
        by.setdefault(row["session"], []).append(float(row["spread_avg"]))
    out = {}
    for session, values in by.items():
        med = _median(values)
        if med is not None:
            out[session] = med
    return out


def duka_session_medians(spread_series: list[tuple[datetime, float]]) -> dict[str, float]:
    """Median spread per sesi dari seri (ts_utc, spread) candle m1 Dukascopy."""
    by: dict[str, list[float]] = {}
    for ts, spread in spread_series:
        by.setdefault(session_of(ts), []).append(float(spread))
    out = {}
    for session, values in by.items():
        med = _median(values)
        if med is not None:
            out[session] = med
    return out
