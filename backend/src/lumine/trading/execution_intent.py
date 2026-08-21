"""Execution intent schema (19 Aug 2026 — P0).

Unified, semantic execution intent. Lumine TIDAK boleh menyamarkan
BE/Trailing/SL/TP/CutLoss sebagai sekadar BUY/SELL — setiap keputusan
eksekusi membawa `intent` yang eksplisit dan ter-audit dari proposal
sampai ke EA.

Intent enum:
- OPEN_POSITION       — buka posisi baru (BUY/SELL)
- CLOSE_POSITION      — tutup penuh
- PARTIAL_CLOSE       — tutup sebagian volume
- MODIFY_STOP_LOSS    — ubah SL saja
- MODIFY_TAKE_PROFIT  — ubah TP saja
- BREAKEVEN           — geser SL ke entry (amankan profit)
- TRAILING_STOP       — geser SL mengikuti harga (lock profit)
- CUT_LOSS            — tutup rugi (deterministic loss cap)

Primitive EA action mapping (EA tetap pakai OPEN/CLOSE/MODIFY):
- OPEN_POSITION  → OPEN
- CLOSE_POSITION / PARTIAL_CLOSE / CUT_LOSS → CLOSE
- MODIFY_STOP_LOSS / MODIFY_TAKE_PROFIT / BREAKEVEN / TRAILING_STOP → MODIFY
"""

from __future__ import annotations

from enum import Enum


class ExecutionIntent(str, Enum):  # noqa: UP042 — str mixin biar JSON-serial langsung
    OPEN_POSITION = "OPEN_POSITION"
    CLOSE_POSITION = "CLOSE_POSITION"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    MODIFY_STOP_LOSS = "MODIFY_STOP_LOSS"
    MODIFY_TAKE_PROFIT = "MODIFY_TAKE_PROFIT"
    BREAKEVEN = "BREAKEVEN"
    TRAILING_STOP = "TRAILING_STOP"
    CUT_LOSS = "CUT_LOSS"


# Primitive EA action per intent (EA handler baca `action`).
INTENT_TO_ACTION: dict[str, str] = {
    ExecutionIntent.OPEN_POSITION: "OPEN",
    ExecutionIntent.CLOSE_POSITION: "CLOSE",
    ExecutionIntent.PARTIAL_CLOSE: "CLOSE",
    ExecutionIntent.CUT_LOSS: "CLOSE",
    ExecutionIntent.MODIFY_STOP_LOSS: "MODIFY",
    ExecutionIntent.MODIFY_TAKE_PROFIT: "MODIFY",
    ExecutionIntent.BREAKEVEN: "MODIFY",
    ExecutionIntent.TRAILING_STOP: "MODIFY",
}

# Intent yang berhak mengubah SL (BREAKEVEN/TRAILING/MODIFY_STOP_LOSS).
SL_MODIFYING_INTENTS = {
    ExecutionIntent.MODIFY_STOP_LOSS,
    ExecutionIntent.BREAKEVEN,
    ExecutionIntent.TRAILING_STOP,
}

# Intent yang berhak mengubah TP.
TP_MODIFYING_INTENTS = {
    ExecutionIntent.MODIFY_TAKE_PROFIT,
}


def primitive_action(intent: str) -> str:
    """Map semantic intent → primitive EA action (fallback: intent as-is)."""
    return INTENT_TO_ACTION.get(intent, intent)


def normalize_side(side: str | None, action: str | None = None) -> str:
    """Normalisasi side dari LLM → "BUY"|"SELL" (20 Aug 2026 — CRITICAL).

    Temuan user: Lumine cuma bisa BUY — CIO kadang output side="SHORT"/
    "long" (bukan "BUY"/"SELL") → execution gate ``prop_side in ("BUY",
    "SELL")`` FAIL → SELL TIDAK PERNAH dieksekusi. Fallback ke action:
    SHORT→SELL, LONG→BUY. Return "" bila tidak bisa ditentukan (HOLD).
    """
    s = (side or "").upper().strip()
    if s in ("SELL", "SHORT"):
        return "SELL"
    if s in ("BUY", "LONG"):
        return "BUY"
    a = (action or "").upper().strip()
    if a in ("SELL", "SHORT"):
        return "SELL"
    if a in ("BUY", "LONG"):
        return "BUY"
    return ""
