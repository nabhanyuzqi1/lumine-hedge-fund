# Skema Database v2.2 — Tabel Logical, Retensi & Partitioning

Referensi: PRD v2.2 §19.3 (Database logical tables), §19.4 (Append-only ledger).
Sumber keputusan retensi/partisi: **volume aktual live DB** (`fund2`, port 5433),
diukur 22 Nov 2026.

## Kanon skema

Skema dikelola dengan **Alembic** (`api/alembic.ini`, migrasi di `api/alembic/versions/`).
`schema.sql` sudah dihapus; satu-satunya sumber kebenaran adalah migrasi.

```bash
cd ~/fund2/api
DATABASE_URL=postgresql://fund2:***@127.0.0.1:5433/fund2 .venv/bin/python -m alembic upgrade head
.venv/bin/python -m alembic history        # riwayat versi
.venv/bin/python -m alembic current        # versi DB aktif
```

Aplikasi memanggil `alembic upgrade head` otomatis saat startup (`app/db.py::apply_schema`).

- `a001_baseline_p1` — skema P1 lengkap (13 tabel operasional), idempotent.
- `b002_v22_schema` — 14 tabel baru v2.2 + governance trigger + partisi
  `liquidity_samples`.

## Tabel logical PRD 19.3 (23) + operasional (4)

| # | Tabel | Peran | Partisi | Retensi | Dasar keputusan |
|---|-------|-------|---------|---------|-----------------|
| 1 | `users` | akun dashboard | - | permanen | 2 baris; data kecil |
| 2 | `sessions` | sesi login | - | sampai `expires_at` + 30 hari (cleanup rutin) | 12 baris aktif |
| 3 | `settings` | konfigurasi runtime (JSONB) | - | permanen (baris terakhir = nilai aktif) | 16 kunci |
| 4 | `settings_audit` | audit perubahan konfigurasi (PRD 18) | - | permanen | audit, volume kecil (~1 baris/ubah) |
| 5 | `orders` | ledger order + state machine (PRD 13) | - | permanen | 20 order live; ~ratusan/bulan di paper |
| 6 | `order_events` | **append-only ledger** transisi status (PRD 19.4) | - (monitor >1 juta baris) | **permanen** | 82 baris; audit kepatuhan |
| 7 | `positions` | posisi broker | - | permanen | 8 baris |
| 8 | `position_snapshots` | deret waktu state posisi/portofolio | - | 180 hari | baru; proyeksi kecil |
| 9 | `candles` | OHLC M1+ | **bulanan** (`candles_YYYY_MM` + default) | 24 bulan → arsip Parquet lalu drop partisi | 45.773 baris; ~25 rb/bulan; PRD 8.4 butuh ≥2 tahun |
| 10 | `liquidity_samples` | agregat spread 5 detik | **bulanan** (`liquidity_samples_YYYY_MM` + default) | 90 hari | **13.722 baris/hari** (~410 rb/bulan) — pertumbuhan tercepat |
| 11 | `signals` | keluaran `decide()` lintas mode | - | 12 bulan | baru |
| 12 | `strategies` | lifecycle strategi (PRD 5.3) | - | permanen | kecil |
| 13 | `strategy_versions` | rilis immutable (PRD 11.1) | - | permanen; immutable setelah final | audit rilis |
| 14 | `strategy_approvals` | audit approval (PRD 11.2) | - | permanen; **append-only** | audit |
| 15 | `backtest_runs` | registry semua percobaan (PRD 8.2) | - | permanen | 52 baris; audit anti-overfit |
| 16 | `paper_runs` | registry run paper/replay/walk-forward | - | permanen | baru; `paper_orders.run_id` FK |
| 17 | `shadow_runs` | registry run shadow (PRD 9) | - | permanen | baru |
| 18 | `regime_observations` | label regime + confidence (PRD 6.4) | - | 12 bulan | baru |
| 19 | `risk_decisions` | keputusan risk gate + input (PRD 7) | - | 12 bulan | 1 per order |
| 20 | `system_events` | event bus supervisor/audit (PRD 5.2, 18) | - | 12 bulan | baru |
| 21 | `reconciliation_runs` | snapshot broker vs ledger (PRD 15) | - | permanen (audit) | baru |
| 22 | `deployment_records` | audit deployment/migrasi (PRD 17/18) | - | permanen | baru |
| 23 | `research_reports` | laporan riset Hermes (PRD 12.3) | - | permanen | baru |
| - | `bridge_commands` | antrean command reconciler (P1b) | - | permanen | 36 baris |
| - | `paper_orders` | ledger paper trading (P1b) | - | permanen | 1 baris |
| - | `paper_state` | state runner paper | - | permanen | 2 baris |
| - | `kill_switch_events` | audit kill-switch (v2.1 §5.7) | - | permanen | 6 baris |

## Governance (trigger DB)

| Tabel | Aturan | Trigger |
|-------|--------|---------|
| `order_events` | UPDATE / DELETE / TRUNCATE **ditolak** (PRD 19.4: koreksi hanya via event kompensasi) | `order_events_append_only`, `order_events_no_truncate` |
| `strategy_approvals` | UPDATE / DELETE ditolak (audit approval) | `strategy_approvals_append_only` |
| `strategy_versions` | UPDATE / DELETE ditolak bila status final `APPROVED`/`REJECTED`/`SUPERSEDED` (PRD 11.1: buat versi baru, jangan timpa) | `strategy_versions_immutable` |
| `settings` | INSERT/UPDATE otomatis tercatat ke `settings_audit` (aktor via `SET app.actor`; `ea_last_seen_at` dikecualikan) | `settings_audit_trail` |

Cleanup test boleh melewati trigger hanya via `SET session_replication_role = replica`
setelah guard DB-test (lihat `tests/conftest.py::_clean_db`).

## Partisi — mekanisme

- `candles` dan `liquidity_samples`: `PARTITION BY RANGE (ts / window_start)`,
  partisi bulanan dibuat otomatis untuk bulan berjalan + depan saat migrasi/startup,
  plus partisi `default` sebagai jaring pengaman.
- Drop partisi lama (retensi): `DROP TABLE candles_2024_12;` /
  `DROP TABLE liquidity_samples_2026_08;` — murah, tanpa VACUUM besar.
- Sebelum drop partisi `candles`, arsipkan isinya ke Parquet (PRD 19.1) lalu
  verifikasi checksum.

## Kapan tinjau ulang

Tinjau keputusan ini saat salah satu terjadi:

1. `order_events` > 1 juta baris → pertimbangkan partisi bulanan (perlu konversi).
2. Volume `candles`/`liquidity_samples` berubah >10× dari pengukuran di atas
   (mis. TF M1 multi-simbol) → turunkan retensi atau pindahkan arsip lebih agresif.
3. Retensi final ditetapkan owner (nilai sekarang = usulan teknis berbasis volume).

## Rollback & immutability

Migrasi baseline dan v2.2 sengaja **tanpa downgrade** — tabel audit/ledger
bersifat permanen. Koreksi skema dilakukan dengan migrasi maju baru.
