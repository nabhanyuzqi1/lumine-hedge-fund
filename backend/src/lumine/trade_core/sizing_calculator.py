# Copyright (c) 2026 Lumine. All rights reserved.
"""Deterministic position sizing (ADR-0016).

Sizing is pure arithmetic — no LLM input reaches ``final_volume``. The
LLM risk assessor may only pick a whole `regime_bucket`; the actual
multiplier is looked up deterministically from policy and applied here
(`final_volume = base_volume * multiplier`). This keeps the critical
path reproducible and auditable.

Contract: `risk-engine-determinism.md` (docs/08-trading), ADR-0016, and
Sprint 3 sizing_calculator.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal, InvalidOperation


@dataclass(frozen=True)
class SizeResult:
    """Outcome of sizing: the clamped trade volume plus its derivation."""

    base_volume: Decimal       # (equity * risk) / (stop * pip_value), unclamped
    final_volume: Decimal      # base_volume * multiplier, clamped
    stop_distance: Decimal     # atr_14 * multiplier (price units)
    stop_price: Decimal        # entry ∓ stop_distance (BUY / SELL)
    violations: tuple[str, ...]


class SizingError(ValueError):
    """Invalid sizing inputs (non-positive equity, stop, or ATR)."""


def stop_distance(atr_14: Decimal, multiplier: Decimal) -> Decimal:
    """Stop distance in price units: ``atr_14 * multiplier`` (ATR-based)."""
    return atr_14 * multiplier


def base_volume(
    equity: Decimal,
    risk_per_trade: Decimal,
    stop_distance_pips: Decimal,
    pip_value: Decimal,
) -> Decimal:
    """Risk-targeted base volume (lots).

    ``volume = (equity * risk) / (stop_distance_pips * pip_value)`` where
    ``stop_distance_pips`` is the stop distance measured in pips and
    ``pip_value`` is the USD-per-lot value of a one-pip move. Large
    trades are floor-rounded down (never rounded into over-risk).
    """
    if equity <= 0:
        msg = f"equity must be positive, got {equity}"
        raise SizingError(msg)
    if risk_per_trade <= 0 or risk_per_trade >= 1:
        msg = f"risk_per_trade must be in (0, 1), got {risk_per_trade}"
        raise SizingError(msg)
    if stop_distance_pips <= 0:
        msg = f"stop distance must be positive, got {stop_distance_pips}"
        raise SizingError(msg)
    if pip_value <= 0:
        msg = f"pip_value must be positive, got {pip_value}"
        raise SizingError(msg)
    numerator = equity * risk_per_trade
    denominator = stop_distance_pips * pip_value
    try:
        volume = numerator / denominator
    except InvalidOperation as exc:
        msg = f"non-finite volume from {numerator} / {denominator}"
        raise SizingError(msg) from exc
    return volume.quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def clamp_volume(volume: Decimal, min_volume: Decimal, max_volume: Decimal) -> Decimal:
    """Clamp ``volume`` to the broker's [``min_volume``, ``max_volume``] range."""
    if volume < min_volume:
        return min_volume
    if volume > max_volume:
        return max_volume
    return volume


def calculate_size(  # noqa: PLR0913 — sizing inputs are a fixed contract
    *,
    entry_price: Decimal,
    atr_14: Decimal,
    equity: Decimal,
    risk_per_trade: Decimal,
    atr_multiplier: Decimal,
    pip_value: Decimal,
    side: str = "BUY",
    pip_size: Decimal = Decimal("0.1"),
    min_volume: Decimal = Decimal("0.01"),
    max_volume: Decimal = Decimal(100),
    risk_adjustment_multiplier: Decimal = Decimal(1),  # policy lookup (ADR-0016)
) -> SizeResult:
    """Compute clamped final volume and stop levels for a BUY/SELL.

    ``atr_14`` is in price units; the stop (``atr_14 * atr_multiplier``)
    is converted to pips via ``pip_size`` (0.1 for XAUUSD) before the
    risk-targeted volume is computed, so ``base_volume`` stays in
    risk/pip terms. ``risk_adjustment_multiplier`` is the deterministic
    per-(regime, volatility) scaling from
    ``policy_versions.risk_adjustments``; the LLM risk assessor never
    supplies this value, only the ``regime_bucket`` key (ADR-0016).
    """
    if atr_14 <= 0:
        msg = f"atr_14 must be positive, got {atr_14}"
        raise SizingError(msg)
    if pip_size <= 0:
        msg = f"pip_size must be positive, got {pip_size}"
        raise SizingError(msg)
    stop_dist = stop_distance(atr_14, atr_multiplier)
    stop_pips = stop_dist / pip_size
    base = base_volume(equity, risk_per_trade, stop_pips, pip_value)
    final = clamp_volume(base * risk_adjustment_multiplier, min_volume, max_volume)
    signed_stop = normalized_stop_price(entry_price, stop_dist, side)
    return SizeResult(
        base_volume=base,
        final_volume=final,
        stop_distance=stop_dist,
        stop_price=signed_stop,
        violations=(),
    )


def normalized_stop_price(entry_price: Decimal, stop_dist: Decimal, side: str) -> Decimal:
    """Place the stop on the correct side: BUY below, SELL above entry."""
    if side == "BUY":
        return entry_price - stop_dist
    if side == "SELL":
        return entry_price + stop_dist
    msg = f"side must be BUY or SELL, got {side!r}"
    raise SizingError(msg)


__all__ = ("SizeResult", "SizingError", "base_volume", "calculate_size", "clamp_volume")
