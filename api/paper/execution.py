"""Execution simulator untuk backtest (PRD v2.2 §8.2).

Melengkapi CostModel (spread/komisi/slippage, paper/costs.py) dengan sisi
eksekusi: swap, latency, rejection, partial fill, dan market closure.

Desain: model DETERMINISTIK tanpa RNG di jalur utama supaya backtest
reproducible dari config hash (PRD §8.2). Semua nilai default yang belum
dikalibrasi broker ditandai [USULAN] dan wajib diganti begitu data broker
tersedia.

- swap: biaya per malam (rollover) untuk posisi yang tertahan. Triple swap
  pada rollover yang jatuh hari Rabu waktu server (konvensi MT5; server A1
  = UTC+7 tetap, lihat strategies/broker_time.py). Swap hanya dibebankan
  saat pasar buka pada saat rollover (XAUUSD tutup akhir pekan).
- latency: sinyal di close bar i dieksekusi di open bar i+fill_delay_bars.
  Resolusi backtest adalah bar, jadi latency_ms dicatat sebagai metadata;
  fill_delay_bars=1 adalah model standar "no look-ahead fill".
- rejection: deterministik. Order ditolak bila (a) spread saat fill >
  max_spread_fill, atau (b) gap |open fill - close sinyal| > max_gap_usd
  (requote). Setiap penolakan dicatat dengan alasannya (audit).
- partial fill: bila diaktifkan, bar dengan tick volume tipis (di bawah
  partial_volume_ratio x median volume 20 bar) hanya terisi
  partial_fill_fraction dari volume yang diminta; sisanya dibatalkan.
  Butuh kalibrasi depth-of-market [USULAN]; default nonaktif.
- market closure: entry diblokir pada jam pasar tutup
  (app.data_quality.market_closed_minutes); pending order hangus bila bar
  fill jatuh di jam tutup; posisi yang tertahan weekend mengambil fill gap
  di open (PaperBroker.on_bar sudah konservatif: gap menembus SL diisi di
  open, SL menang bila bar menyentuh dua level).

Semua field immutable (frozen dataclass) agar config hash stabil.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# Swap default USD per lot per malam (long, short) [USULAN]:
# belum ada akses nilai swap broker HFM; ganti begitu tersedia.
SWAP_DEFAULTS: dict[str, tuple[float, float]] = {
    "XAUUSD": (-8.0, 1.5),
    "BTCUSD": (-25.0, 5.0),
}
# Rejection default per simbol: spread fill maksimum (USD) dan gap requote
# maksimum (USD) [USULAN]. XAU: 1.5x max_spread_abs 0.50; BTC: 1.5x 100.
REJECTION_DEFAULTS: dict[str, tuple[float, float]] = {
    "XAUUSD": (0.75, 5.0),
    "BTCUSD": (150.0, 50.0),
}

BROKER_UTC_OFFSET_H = 7  # strategies/broker_time.py (terukur 2026-11-22)


@dataclass(frozen=True)
class ExecutionModel:
    """Model eksekusi backtest. Immutable agar reproducible."""

    swap_long_usd_per_lot_night: float | None = None
    swap_short_usd_per_lot_night: float | None = None
    swap_triple_weekday_server: int = 2      # Rabu (Server, UTC+7)
    rollover_utc_hour: int = 17              # 00:00 server UTC+7
    fill_delay_bars: int = 0                 # 1 = fill di open bar berikutnya
    latency_ms: float = 0.0                  # metadata resolusi bar
    max_spread_fill: float | None = None     # rejection: spread > ini
    max_gap_usd: float | None = None         # rejection: |gap| > ini
    partial_volume_ratio: float | None = None  # partial fill: ambang volume
    partial_fill_fraction: float = 0.5
    block_entry_closed_market: bool = True
    source: str = "defaults_usulan"
    notes: list[str] = field(default_factory=list)

    @property
    def swap_enabled(self) -> bool:
        return (self.swap_long_usd_per_lot_night is not None
                and self.swap_short_usd_per_lot_night is not None)

    @property
    def rejection_enabled(self) -> bool:
        return self.max_spread_fill is not None or self.max_gap_usd is not None

    @property
    def partial_fill_enabled(self) -> bool:
        return self.partial_volume_ratio is not None and self.partial_fill_fraction > 0

    def swap_usd(self, side: str, volume: float, *, triple: bool) -> float:
        """Biaya swap satu rollover untuk posisi side/volume (negatif = bayar)."""
        if not self.swap_enabled:
            return 0.0
        rate = (self.swap_long_usd_per_lot_night if side == "BUY"
                else self.swap_short_usd_per_lot_night)
        if rate is None:
            return 0.0
        mult = 3 if triple else 1
        return round(rate * float(volume) * mult, 2)

    def as_dict(self) -> dict:
        return {
            "swap_long_usd_per_lot_night": self.swap_long_usd_per_lot_night,
            "swap_short_usd_per_lot_night": self.swap_short_usd_per_lot_night,
            "swap_triple_weekday_server": self.swap_triple_weekday_server,
            "rollover_utc_hour": self.rollover_utc_hour,
            "fill_delay_bars": self.fill_delay_bars,
            "latency_ms": self.latency_ms,
            "max_spread_fill": self.max_spread_fill,
            "max_gap_usd": self.max_gap_usd,
            "partial_volume_ratio": self.partial_volume_ratio,
            "partial_fill_fraction": self.partial_fill_fraction,
            "block_entry_closed_market": self.block_entry_closed_market,
            "source": self.source,
            "notes": list(self.notes),
            "swap_enabled": self.swap_enabled,
            "rejection_enabled": self.rejection_enabled,
            "partial_fill_enabled": self.partial_fill_enabled,
        }


def default_execution_model(symbol: str, *, source: str = "defaults_usulan") -> ExecutionModel:
    """Model eksekusi default per simbol (nilai [USULAN], lihat docstring modul)."""
    swap = SWAP_DEFAULTS.get(symbol.upper())
    rej = REJECTION_DEFAULTS.get(symbol.upper())
    notes = [
        "nilai swap/rejection [USULAN]: ganti dengan nilai broker HFM saat tersedia",
        "latency model: fill di open bar berikutnya (resolusi backtest = bar)",
    ]
    return ExecutionModel(
        swap_long_usd_per_lot_night=swap[0] if swap else None,
        swap_short_usd_per_lot_night=swap[1] if swap else None,
        max_spread_fill=rej[0] if rej else None,
        max_gap_usd=rej[1] if rej else None,
        fill_delay_bars=1,
        latency_ms=0.0,
        source=source,
        notes=notes,
    )


def rollover_crossings(prev_now, now, *, rollover_utc_hour: int) -> list:
    """Instant rollover (jam rollover_utc_hour UTC) dalam interval (prev_now, now]."""
    if prev_now is None:
        return []
    if prev_now.tzinfo is None or now.tzinfo is None:
        raise ValueError("timestamp harus timezone-aware")
    out: list[datetime] = []
    cur = prev_now.astimezone(timezone.utc)
    end = now.astimezone(timezone.utc)
    # rollover pertama setelah cur
    cand = cur.replace(hour=rollover_utc_hour, minute=0, second=0, microsecond=0)
    if cand <= cur:
        cand += timedelta(days=1)
    while cand <= end:
        out.append(cand)
        cand += timedelta(days=1)
    return out


def is_triple_swap_day(ts_utc: datetime, *, triple_weekday_server: int = 2,
                       broker_offset_h: int = BROKER_UTC_OFFSET_H) -> bool:
    """True bila rollover ts_utc jatuh hari triple-swap pada jam server."""
    server = ts_utc + timedelta(hours=broker_offset_h)
    return server.weekday() == triple_weekday_server
