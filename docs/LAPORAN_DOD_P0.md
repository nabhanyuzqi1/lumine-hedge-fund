# Laporan DoD Gate P0 — Lumine Fund v2 (Fund Core)

| | |
| --- | --- |
| Tanggal | 2026-11-21 |
| Penilai | hf-ceo (koordinasi & review DoD, PRD §12) |
| Status | **P0 LULUS — fase P1 dilanjutkan** |
| Sumber | `PRD_v2.1_Fund_Core.md` §11 (P0) — DoD: EA heartbeat+tick API dummy HMAC valid; data spread HFM tersimpan; angka risk default disetujui |

## 1. Butir DoD P0

| # | Butir DoD | Status | Bukti |
| --- | --- | --- | --- |
| 1 | EA mengirim heartbeat + tick ke API dummy dengan HMAC valid | **LULUS** | `ea/test_ea_v0.py` **17/17 PASS** (dijalankan ulang hf-ceo, 2026-11-21); dummy API `scripts/dummy_bridge.py` (verifikasi ts/nonce/signature, replay cache); kontrak lengkap `ea/HMAC_CONTRACT.md` |
| 2 | Data spread HFM tersimpan | **LULUS** | Service `fund2-hfm-recorder` ACTIVE (systemd user, enabled, linger); `~/fund2/data/hfm_recording/` berisi `parquet/` + `log/` (ticks & fills harian); tick termasuk terus sampai detik pemeriksaan (16:54 WIB); reconnect otomatis teruji; verifikasi tercatat di `VERIFICATION.txt` |
| 3 | Angka risk default disetujui owner | **LULUS** | `docs/KEPUTUSAN_OWNER.md` §E: **DISETUJUI OWNER 2026-11-21 — SETUJU SEMUA** (A1–A12, B1–B4, C1–C3, D2–D16 dikunci sebagai baseline risk policy); commit `cd4319d` di master |

## 2. Cakupan 6 baris tugas P0 (PRD §11)

| Tugas | Owner | Bukti keluaran |
| --- | --- | --- |
| Repo `fund2`, struktur, CI (lint + test), env template | hf-backend | Repo `~/fund2` di master; test suite hijau (56 pytest API + 17 EA v0) |
| Postgres `fund2` + migrasi awal + permission append-only | hf-backend | Skema v0 terpakai (users, orders, order_events, positions, candles, settings; E2E order chain tercatat). Catatan: dibuat via DDL aplikasi, **Alembic belum terpasang** — usul dilengkapi di P1a |
| EA v0: heartbeat, tick batch + spread ke endpoint dummy, HMAC | hf-backend | 17/17 test lulus; dummy_bridge + kontrak HMAC |
| Perekaman spread/slippage HFM (parquet + log), jalan terus sampai P5 | hf-devops | Recorder aktif dan live; data harian terkumpul |
| Harness latensi T0..T4 (skeleton) | hf-qa | `scripts/latency_harness.py` + `LATENCY_REPORT.md` (commit `2eee1ca`); verifikasi E2E 10/10 order FILLED, T0–T2 p95 273 ms / p99 275 ms (SLO <300 ms PASS) |
| Keputusan owner atas semua angka [USULAN] | owner | `KEPUTUSAN_OWNER.md` disetujui penuh (commit `cd4319d`) |

Bukti tambahan jalur produksi: EA v4 (Bearer) live di chart XAUUSD H1 — `/bridge/poll`, `/bridge/tick`, `/bridge/positions` 200 OK; aliran tick EA→API→SSE→recorder terverifikasi langsung saat pemeriksaan.

## 3. Catatan & keputusan terbuka

- **Live trading tetap OFF.** D1 (modal live + batas kerugian absolut) sengaja di-DEFER oleh owner; go-live butuh pengisian D1 + approval live terpisah (PRD §9 gerbang 7). P0 tidak mengubah ini.
- **Auth produksi = Bearer**, bukan HMAC: kontrak HMAC v0 didokumentasikan sebagai target migrasi auth berikutnya (`HMAC_CONTRACT.md` §Catatan P1a). Butir DoD 1 dinilai pada deliverable EA v0 + dummy API sesuai baris tugas P0.
- **Alembic belum ada** pada skema v0 (lihat tabel di atas); tidak menghalangi DoD P0, disarankan masuk P1a.
- Working tree repo berisi perubahan belum commit (file EA live, screenshot UI) milik kartu P1 yang masih berjalan; rapikan saat review P1.
- Kartu P1 `t_7694b38c` (EA bridge) diarsipkan setelah 2x budget habis, namun cakupannya terkirim dan terverifikasi lewat `t_f2p0a4` (EA v4 live).

## 4. Keputusan

**Gerbang P0: LULUS.** Seluruh butir DoD P0 terpenuhi dan diverifikasi langsung (bukan hanya mengandalkan laporan kartu). Fase P1a/P1b dilanjutkan sesuai jadwal PRD.
