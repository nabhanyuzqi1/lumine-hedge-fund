"""Shadow strategy specs (PRD 9.2): beberapa versi strategi bersamaan.

Sumber daftar versi: settings key `shadow_strategies` (JSON list). Tiap
entri: label (unik, label perubahan kode/parameter yang diuji), module
(import path modul strategi), params (override), opsional symbol/timeframe.
Entri tidak valid dilewati dengan log — tidak pernah menjatuhkan runner.
"""
from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import dataclass, field

from strategies.btc_range_breakout import STRATEGY_ID as BTC_ID
from strategies.btc_range_breakout import STRATEGY_VERSION as BTC_VERSION
from strategies.london_breakout import STRATEGY_ID as LB_ID
from strategies.london_breakout import STRATEGY_VERSION as LB_VERSION
from strategies.mean_reversion import STRATEGY_ID as MR_ID
from strategies.mean_reversion import STRATEGY_VERSION as MR_VERSION

# XAUUSD 100 oz/lot, BTCUSD 1 BTC/lot (kontrak multipair P2).
SYMBOL_CONTRACT = {"XAUUSD": 100.0, "BTCUSD": 1.0}
SYMBOL_DEFAULT_TF = {"XAUUSD": ("M5", 300), "BTCUSD": ("H1", 3600)}

# Default: strategi produksi yang sama dengan paper runner (baseline
# pembanding sinyal shadow vs live, PRD 9.2).
DEFAULT_SPECS = [
    {"label": "lb-base", "module": "strategies.london_breakout", "params": {}},
    {"label": "mr-base", "module": "strategies.mean_reversion", "params": {}},
    {"label": "btc-base", "module": "strategies.btc_range_breakout", "params": {}},
]


@dataclass(frozen=True)
class ShadowSpec:
    """Satu versi strategi yang di-shadow. State: paper_state `shadow_<label>`."""

    label: str
    strategy_id: str
    strategy_version: str
    module: str
    params: dict = field(default_factory=dict)
    symbol: str = "XAUUSD"
    timeframe: str = "M5"
    tf_seconds: int = 300
    contract_size: float = 100.0

    @property
    def state_key(self) -> str:
        return f"shadow_{self.label}"


def params_hash(params: dict) -> str:
    """Hash stabil parameter yang diuji (label perubahan parameter, PRD 9.2)."""
    blob = json.dumps(params or {}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _module_strategy_meta(module: str) -> tuple[str, str]:
    mod = importlib.import_module(module)
    sid = str(getattr(mod, "STRATEGY_ID", module))
    ver = str(getattr(mod, "STRATEGY_VERSION", "0.0.0"))
    return sid, ver


def load_specs(settings: dict) -> tuple[list[ShadowSpec], list[str]]:
    """(specs, errors) dari settings `shadow_strategies`; default bila kosong.

    Label harus unik; module wajib punya decide() + STRATEGY_ID. Symbol/
    timeframe default mengikuti simbol strategi (XAUUSD M5, BTCUSD H1).
    """
    raw = settings.get("shadow_strategies")
    if not raw:
        raw = DEFAULT_SPECS
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = DEFAULT_SPECS
    specs: list[ShadowSpec] = []
    errors: list[str] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(entry, dict):
            errors.append(f"[{i}] entry bukan object")
            continue
        label = str(entry.get("label") or "").strip()
        module = str(entry.get("module") or "").strip()
        if not label or not module:
            errors.append(f"[{i}] label/module wajib")
            continue
        if label in seen:
            errors.append(f"[{i}] label duplikat: {label}")
            continue
        try:
            sid, ver = _module_strategy_meta(module)
        except Exception as exc:  # noqa: BLE001 - spec invalid dilewati
            errors.append(f"[{i}] module {module} gagal diimport: {exc!r}")
            continue
        symbol = str(entry.get("symbol") or ("BTCUSD" if sid == BTC_ID else "XAUUSD"))
        tf, tf_s = SYMBOL_DEFAULT_TF.get(symbol, ("5m", 300))
        tf = str(entry.get("timeframe") or tf)
        tf_s = int(entry.get("tf_seconds") or tf_s)
        seen.add(label)
        specs.append(ShadowSpec(
            label=label, strategy_id=sid, strategy_version=ver, module=module,
            params=dict(entry.get("params") or {}), symbol=symbol,
            timeframe=tf, tf_seconds=tf_s,
            contract_size=SYMBOL_CONTRACT.get(symbol, 100.0)))
    return specs, errors
