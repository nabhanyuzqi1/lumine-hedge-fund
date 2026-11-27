"""Cek konsistensi dokumen guardrail terhadap KEPUTUSAN_OWNER §I (read-only).

Kartu t_d3ab9839 (F-03/F-12). Tidak menyentuh DB atau file: hanya membaca
dokumen di docs/ dan memastikan angka final di §I muncul di dokumen turunan,
serta tidak ada angka lama yang bertentangan (mis. "live: 5%").

Jalankan: python3 scripts/check_guardrail_docs.py [--json]
Exit 0 = semua cek lulus.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# (dokumen, pola yang WAJIB ada, pola yang DILARANG ada)
CHECKS: list[tuple[str, list[str], list[str]]] = [
    ("KEPUTUSAN_OWNER.md",
     ["## I. Penetapan angka guardrail final",
      "`max_volume` = 0.10",
      "`max_orders_per_min` = 5",
      "`kill_switch_triggers.daily_drawdown_pct` = 3.0",
      "`kill_switch_triggers.total_drawdown_pct` = 8.0",
      "`kill_switch_triggers.consecutive_failed_orders` = 3",
      "`kill_switch_triggers.ea_offline_seconds` = 6.0",
      "`kill_switch_triggers.ea_offline_halt_seconds` = 60.0",
      "`max_tick_age_s` = 3.0",
      "292,02 USD"],
     []),
    ("ROLLBACK_PLAN_v2.2.md",
     ["DD harian ≥ **3%**", "DD total ≥ **8%**", "**3** FAILED beruntun",
      "EA offline > **6 s**", "**60 s** untuk `GLOBAL_HALT`",
      "KEPUTUSAN_OWNER.md` §I"],
     ["live: 5%", "DD harian 5%"]),
    ("RELEASE_CHECKLIST_v2.2.md",
     ["| 5.9 | Guardrail runtime sesuai policy final",
      "KEPUTUSAN_OWNER.md` §I", "`guardrails_sesuai_policy`"],
     []),
    ("PRASYARAT_LIVE_v2.2.md",
     ["## 3. Guardrail: angka final vs nilai runtime",
      "KEPUTUSAN_OWNER.md` §I", "G-12", "`max_tick_age_s`",
      "G-06b", "`ea_offline_halt_seconds`"],
     ["A10 tick 3 s belum terpetakan"]),
    ("RELEASE_PACKET_v2.2.md",
     ["F-12", "**TERTUTUP", "KEPUTUSAN_OWNER.md` §I"],
     []),
]

# Angka lama yang tidak boleh muncul lagi sebagai nilai yang berlaku.
FORBIDDEN_ANYWHERE = [
    (r"DD harian live 5%", "angka DD harian lama 5%"),
    (r"live: 5%\)", "angka DD harian lama 5%"),
]


def run_checks() -> tuple[list[dict], bool]:
    results: list[dict] = []
    ok_all = True
    for name, must, must_not in CHECKS:
        f = DOCS / name
        if not f.exists():
            results.append({"doc": name, "error": "tidak ditemukan"})
            ok_all = False
            continue
        text = f.read_text(errors="replace")
        missing = [p for p in must if p not in text]
        forbidden = [p for p in must_not if p in text]
        ok = not missing and not forbidden
        ok_all &= ok
        results.append({"doc": name, "ok": ok, "missing": missing,
                        "forbidden_found": forbidden})
    for pattern, label in FORBIDDEN_ANYWHERE:
        hits = [r["doc"] for r in results
                if "ok" in r and re.search(pattern, (DOCS / r["doc"]).read_text(errors="replace"))]
        if hits:
            ok_all = False
            results.append({"global_forbidden": label, "docs": hits, "ok": False})
    return results, ok_all


def main() -> int:
    results, ok = run_checks()
    if "--json" in sys.argv:
        print(json.dumps({"ok": ok, "results": results}, indent=2, ensure_ascii=False))
    else:
        for r in results:
            if r.get("global_forbidden"):
                print(f"GAGAL  {r['global_forbidden']}: {', '.join(r['docs'])}")
                continue
            status = "LULUS " if r.get("ok") else "GAGAL "
            print(f"{status} {r['doc']}")
            for m in r.get("missing", []):
                print(f"        kurang: {m}")
            for m in r.get("forbidden_found", []):
                print(f"        terlarang muncul: {m}")
        print("\nhasil:", "SEMUA DOKUMEN SINKRON" if ok else "ADA KETIDAKSESUAIAN")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
