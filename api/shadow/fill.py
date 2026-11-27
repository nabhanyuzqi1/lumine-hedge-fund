"""Model fill konservatif untuk shadow (PRD 9.2).

Konvensi sama dengan engine backtest terkalibrasi P2 (paper/backtest.py +
paper/costs.py): spread aktual live sudah dilalui lewat bid/ask, lalu tiap
fill mendapat slippage menguntungkan lawan (adverse) dan komisi round-turn
didiskon dari P&L simulasi. SL menang saat bar menembus dua level sekaligus
(PaperBroker). Semua angka adalah SIMULASI, bukan realized P&L.

    entry BUY  = ask + slippage      exit BUY  = price - slippage
    entry SELL = bid - slippage      exit SELL = price + slippage
    pnl = (pergerakan harga) x contract_size x volume - komisi round-turn
"""
from __future__ import annotations

from dataclasses import dataclass

SLIPPAGE_PER_FILL_DEFAULT = 0.10     # USD harga per fill (kalibrasi P2)
COMMISSION_PER_LOT_DEFAULT = 7.0     # USD per lot round-turn (kalibrasi P2)


@dataclass(frozen=True)
class FillModel:
    slippage: float = SLIPPAGE_PER_FILL_DEFAULT
    commission_per_lot_round_usd: float = COMMISSION_PER_LOT_DEFAULT

    def entry_price(self, side: str, bid: float, ask: float) -> float:
        if side == "BUY":
            return round(ask + self.slippage, 5)
        return round(bid - self.slippage, 5)

    def exit_price(self, side: str, trigger_price: float) -> float:
        if side == "BUY":
            return round(trigger_price - self.slippage, 5)
        return round(trigger_price + self.slippage, 5)

    def commission_usd(self, volume: float) -> float:
        return round(self.commission_per_lot_round_usd * float(volume), 2)

    def pnl_usd(self, *, side: str, entry: float, exit: float, volume: float,
                contract_size: float) -> float:
        diff = (exit - entry) if side == "BUY" else (entry - exit)
        return round(diff * contract_size * float(volume), 2)

    def slippage_cost_usd(self, volume: float, contract_size: float) -> float:
        """Estimasi biaya slippage 2 fill (entry+exit) dalam USD."""
        return round(2.0 * self.slippage * contract_size * float(volume), 2)


def fill_model_from_settings(settings: dict) -> FillModel:
    cfg = settings.get("shadow_cost") or {}
    if isinstance(cfg, str):
        import json
        try:
            cfg = json.loads(cfg)
        except json.JSONDecodeError:
            cfg = {}
    cfg = cfg if isinstance(cfg, dict) else {}
    return FillModel(
        slippage=float(cfg.get("slippage_usd_per_fill", SLIPPAGE_PER_FILL_DEFAULT)),
        commission_per_lot_round_usd=float(
            cfg.get("commission_per_lot_round_usd", COMMISSION_PER_LOT_DEFAULT)))
