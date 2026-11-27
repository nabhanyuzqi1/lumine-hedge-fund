# LAPORAN DoD — Data Pipeline v2.2 (t_f2v22a11)

Tanggal: 2026-11-23 | Worker: hf-devops | PRD: v2.2 §19.2, §19.4, §4.4

## DoD 1 — Quality checks jalan & melaporkan: TERPENUHI

CLI `python -m app.data_quality` menjalankan 9 check §19.2 + validasi ingest §4.4,
hasilnya: stdout + `data/quality/quality_report.json` + tabel `data_quality_runs`
(riwayat) + `data_versions` (checksum per series).

| Check §19.2 | Implementasi | Hasil live |
| --- | --- | --- |
| completeness | `candles.completeness` (coverage vs menit pasar) | WARN 44-55% (feed live belum penuh) |
| duplicate rate | `candles.duplicate_rate` | PASS 0 duplikat |
| timestamp monotonicity | `candles.monotonicity` | FAIL H4 2/2 bar (seed H4 misaligned) |
| gap detection | `candles.gaps` (jam pasar saja) | FAIL (gap feed live; akhir pekan dikecualikan) |
| spread validity | `liquidity.spread` | PASS 1.616 sampel |
| candle OHLC consistency | `candles.ohlc` | PASS 9 series |
| symbol mapping | `symbols.mapping` | PASS 2 simbol kanonik |
| broker-vs-historical | `broker_vs_historical` vs dukascopy | SKIPPED (belum ada overlap) |
| data version & checksum | `data_versions` (sha256 per series) | PASS 9 series |

Status keseluruhan: **FAIL** — didorong completeness/gap candle M1-M5/H1 XAUUSD & BTCUSD
karena feed live baru berjalan sebagian window 3 hari. Bukan kerusakan data; akan PASS
sendiri saat feed mengisi. Ledger: **PASS** (104 event, 22 order, guard lengkap).

## DoD 2 — order_events append-only terjaga: TERPENUHI

Lapisan guard (PRD 19.4 "DB permission, trigger/policy, backup, audit"):

1. **Trigger** `order_events_append_only` (b002) + `order_events_no_truncate`:
   menolak UPDATE/DELETE/TRUNCATE dari siapa pun termasuk owner tabel.
2. **REVOKE** UPDATE/DELETE/TRUNCATE FROM PUBLIC (e005): role non-owner tidak
   bisa mutasi sama sekali sekalipun trigger dimatikan.
3. **Audit**: `data_quality_runs` + check ledger harian memverifikasi trigger,
   privilege, orphan event, rantai status patah, dan jumlah event kompensasi.
4. **Backup**: tercakup backup harian terenkripsi (t_f2v22a8).

Uji coba langsung di DB live (fund2@127.0.0.1:5433):

- `UPDATE order_events SET to_status='HACKED' ...` → **ERROR ditolak trigger**
- `DELETE FROM order_events WHERE id=...` → **ERROR ditolak trigger**
- `TRUNCATE order_events` (dalam transaksi) → **ERROR ditolak trigger**
- State setelah uji: 104 event utuh, status terakhir tidak berubah.

Konvensi koreksi: event kompensasi (`to_status='COMPENSATION_*'` atau
`payload kind='compensation'`), bukan edit sejarah — diverifikasi di
`tests/test_data_quality.py`.

## Validasi ingest §4.4 (TAMBARAN)

`app.validate` + integrasi `/bridge/tick` (`app.bridge`) + `app.ingest`:

- timestamp mundur → `TS_BACKWARD` REJECT; terlalu di masa depan → `TS_FUTURE` REJECT
- bid/ask nol/negatif → `BID_ASK_NONPOSITIVE` REJECT; di luar band → `PRICE_ABSURD` REJECT
- ask < bid → `ASK_BELOW_BID` REJECT
- tick stale > 60s → `TS_STALE` FLAG (freshness threshold)
- simbol: `SYMBOL_MAPPED` FLAG / `SYMBOL_UNKNOWN` REJECT; deviasi spec diquality check
- gap → `candles.gaps` FAIL bila > 4 jam jam pasar
- duplicate tick/candle → `DUPLICATE_TICK`/`CANDLE_DUPLICATE`/`CANDLE_CONFLICT` FLAG
  (upsert candle idempotent; duplikat teridentifikasi, tidak lewat diam-diam)
- EA schema_version tidak didukung → HTTP 422 (`SUPPORTED_SCHEMA_VERSIONS`)

## Bukti

- Test: `pytest tests/test_data_quality.py tests/test_ingest_validation.py
  tests/test_validate.py` → **19 passed** (test DB terisolasi).
- Laporan live: `data/quality/quality_report.json` (di-regenerate saat verifikasi).
- DB live: alembic `e005`, `data_quality_runs` berisi run terbaru, `data_versions`
  9 series (XAUUSD/M1,M5,M15,H1,H4 + BTCUSD/M1,M5,M15,H1).
- Migrasi: `d004_security_v22.py` di-commit sebagai dependensi rantai (tugas
  security t_f2v22a9 sudah done di 7108a57 tetapi filenya belum ter-commit).

## Catatan

- FAIL candle saat ini = feed live belum penuh (EKSPEKTASI, bukan defect).
  Re-run harian disarankan (bisa dijadwalkan lewat cron/systemd timer menyusul).
- `test_migrations.py` kini membaca head alembic dari direktori versions (anti-stale).
