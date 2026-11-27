"""Alasan gagal order yang WAJIB terisi + terstruktur (t_afd7fe4e butir B).

Temuan kartu: 917 order FAILED/24 jam, 757+160 di antaranya `fail_reason`
NULL, termasuk seluruh penolakan risk gate (yang alasannya hanya menempel di
`decision.reasoning` sebagai 300 karakter pertama body API). Akibatnya
penyebab kegagalan tidak bisa diquery, dihitung, atau dipelajari.

Kontrak modul ini (dipakai semua jalur yang menghasilkan FAILED):

    fail_reason  TEXT   -> "code: message (stage=stage)"   (manusia: UI History)
    fail_detail  JSONB  -> {"code", "message", "stage"}     (mesin: query/audit)

`stage` = titik kegagalan, bukan tebakan:

    risk_gate       ditolak gate deterministik POST /orders (sebelum dikirim)
    api_validate    body order tidak sah / endpoint menolak permintaan
    bridge_result   EA melaporkan hasil eksekusi FAILED
    reconciler      order STUCK diselesaikan tanpa bukti eksekusi
    bridge_reconcile  snapshot posisi broker tidak terjelaskan
    unknown         data lama pra-perbaikan (backfill migrasi o015)

Kode selalu snake_case singkat dan stabil; pesan bebas teks berbahasa
Indonesia karena dibaca owner di dashboard.
"""
from __future__ import annotations

import re

STAGE_RISK_GATE = "risk_gate"
STAGE_API_VALIDATE = "api_validate"
STAGE_BRIDGE_RESULT = "bridge_result"
STAGE_RECONCILER = "reconciler"
STAGE_BRIDGE_RECONCILE = "bridge_reconcile"
STAGE_UNKNOWN = "unknown"

MAX_MESSAGE = 900          # fail_reason TEXT; pesan panjang dipotong rapi
_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,60}$")


def detail(code: str, message: str, stage: str) -> dict:
    """Bentuk kanonik `{code, message, stage}` (dipakai fail_detail + event)."""
    code = (code or "unknown").strip().lower()
    if not _CODE_RE.match(code):
        code = "unknown"
    stage = (stage or STAGE_UNKNOWN).strip().lower() or STAGE_UNKNOWN
    text = " ".join(str(message or "").split())  # rapatkan whitespace/baris baru
    return {"code": code, "message": text[:MAX_MESSAGE], "stage": stage}


def render(d: dict) -> str:
    """fail_reason TEXT yang terbaca manusia dari detail terstruktur."""
    code = d.get("code") or "unknown"
    message = d.get("message") or "-"
    stage = d.get("stage") or STAGE_UNKNOWN
    return f"{code}: {message} (stage={stage})"


def build(code: str, message: str, stage: str) -> tuple[dict, str]:
    """Praktis untuk satu baris: return (detail_dict, text)."""
    d = detail(code, message, stage)
    return d, render(d)


def code_from_reason(reason: str | None, default: str = "rejected") -> str:
    """Ambil kode dari string alasan gate berbentuk `code: penjelasan`.

    Contoh: "spread_too_wide: spread 0.61 > 0.50" -> "spread_too_wide";
    "Volume melebihi batas" -> default.
    """
    text = str(reason or "").strip()
    if not text:
        return default
    head = text.split(":", 1)[0].strip().lower().replace("-", "_").replace(" ", "_")
    return head if _CODE_RE.match(head) else default


_RETCODE_RE = re.compile(r"retcode\s*=?\s*(-?\d+)")


def from_text(text: str | None, *, stage: str, default_code: str = "failed") -> dict:
    """Detail dari pesan bebas (alasan EA / reconciler), kode stabil.

    Pesan EA MT5 memuat `retcode=N` (10018 = market closed, 10012 = timeout).
    Kode diturunkan dari retcode supaya penyebab bisa dihitung di SQL, bukan
    hanya dibaca manusia. Pesan tanpa retcode memakai awalan `code:` bila ada.
    """
    raw = " ".join(str(text or "").split())
    match = _RETCODE_RE.search(raw)
    if match:
        code = f"retcode_{match.group(1).lstrip('-')}"
        return detail(code, raw or f"retcode {match.group(1)}", stage)
    if not raw:
        return detail(default_code, "gagal tanpa pesan dari EA/reconciler", stage)
    return detail(code_from_reason(raw, default_code), raw, stage)


def from_reasons(reasons: list[str] | tuple[str, ...] | None, *, stage: str,
                 default_code: str = "rejected") -> dict:
    """Ringkas daftar alasan gate menjadi satu detail terstruktur.

    `code` = kode alasan PERTAMA (alasan pertama selalu yang paling
    menentukan urutan gate), seluruh alasan digabung di `message` supaya
    tidak ada informasi yang hilang dari audit.
    """
    items = [str(r).strip() for r in (reasons or []) if str(r or "").strip()]
    if not items:
        return detail(default_code, "ditolak tanpa alasan terperinci", stage)
    return detail(code_from_reason(items[0], default_code), "; ".join(items), stage)
