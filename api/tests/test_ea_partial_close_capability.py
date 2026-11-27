"""Tripwire kapabilitas partial close EA (RISK-C, t_00db2872).

Keputusan scope RISK-C: partial close (TP1/TP2/TP3) DIDESCOPE karena EA
LumineEA v5.03 yang berjalan hanya bisa menutup SELURUH volume posisi
(`ExecuteClose` memakai POSITION_VOLUME dan mengabaikan field `volume` pada
payload command). Bukti lengkap: docs/PROBE_PARTIAL_CLOSE_t_00db2872.md.

Test ini mengunci asumsi itu di source EA. Kalau EA suatu saat benar-benar
mendukung partial close, test ini GAGAL dan memaksa:
- review ulang docs/PROBE_PARTIAL_CLOSE_t_00db2872.md,
- desain ulang: ledger volume posisi (positions.volume saat ini = volume total,
  satu baris = satu posisi) + penanganan result CLOSE parsial di bridge
  (bridge.py menandai posisi CLOSED untuk setiap result CLOSE FILLED), supaya
  sisa volume tetap ter-trail RISK-B.
"""
from __future__ import annotations

from pathlib import Path

import pytest

EA_PATH = Path(__file__).resolve().parents[2] / "ea" / "LumineEA.mq5"


@pytest.fixture(scope="module")
def ea_source() -> str:
    if not EA_PATH.exists():  # checkout tanpa folder ea/ (mis. paket API saja)
        pytest.skip(f"source EA tidak ada: {EA_PATH}")
    return EA_PATH.read_text(encoding="utf-8", errors="replace")


def test_ea_close_uses_full_position_volume(ea_source: str):
    """ExecuteClose mengirim volume = POSITION_VOLUME (bukan payload volume)."""
    start = ea_source.index("void ExecuteClose(")
    end = ea_source.index("void ExecuteModify(", start)
    body = ea_source[start:end]
    assert "double volume = PositionGetDouble(POSITION_VOLUME);" in body
    assert "req.volume       = volume;" in body
    # Tidak ada jalur volume parsial di ExecuteClose saat ini.
    assert "NormalizeVolume" not in body


def test_ea_close_ignores_payload_volume(ea_source: str):
    """ProcessCommand mem-parse `volume` tapi CLOSE tidak meneruskannya."""
    start = ea_source.index("void ProcessCommand(")
    end = ea_source.index("double NormalizeVolume(", start)
    body = ea_source[start:end]
    assert 'double lots = ExtractJsonDouble(json, "volume");' in body
    assert 'action = "CLOSE";' in body
    assert "ExecuteClose(id, ticket);" in body   # ticket saja, tanpa lots


def test_bridge_marks_position_closed_on_any_close_result():
    """Bridge/reconciler memperlakukan hasil CLOSE sebagai penutupan PENUH.

    Selama posisi tidak punya ledger volume sisa, close parsial dari EA akan
    membuat DB menandai posisi CLOSED padahal broker masih memegang sisa
    volume -> trailing RISK-B berhenti mengawal posisi nyata. Karena itu
    partial close tidak boleh diaktifkan sebelum skema/penanganan ini diubah.
    """
    from pathlib import Path as _P

    bridge_path = _P(__file__).resolve().parents[1] / "app" / "bridge.py"
    source = bridge_path.read_text(encoding="utf-8")
    assert "UPDATE positions SET status = 'CLOSED'" in source
    assert "remaining_volume" not in source
