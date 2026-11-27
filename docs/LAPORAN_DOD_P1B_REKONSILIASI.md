# Laporan DoD P1b: Reconciler (PRD 5.8)

Tanggal: 2026-11-22. Task: t_f2p1b1. Owner: hf-backend.

## Ruang lingkup

Reconciler disconnect/reconnect sesuai PRD v2.1 §5.8 dan sprint P1b hari 8-10:

1. Order `SENT` > 60 detik tanpa konfirmasi → `STUCK`, reconciler dijadwalkan.
2. EA reconnect mengirim snapshot: posisi terbuka + deal 24 jam terakhir.
3. Reconciler membandingkan snapshot dengan `positions` / `orders`:
   - posisi broker tanpa order DB → `ORPHAN_ADOPTED` (dicatat, SL darurat
     bila belum ada, notifikasi owner);
   - posisi DB tanpa broker → `FILLED_THEN_CLOSED` bila ada deal penutup
     (deal OUT di snapshot atau order CLOSE `FILLED`), selain itu `FAILED`
     dan dianggap tak terjelaskan;
   - tak terjelaskan → kill-switch (`position_mismatch`, mode GLOBAL_HALT) + alert.
4. Semua langkah tercatat di `order_events`.

## Implementasi

| File | Perubahan |
| --- | --- |
| `api/app/bridge.py` | Snapshot `/bridge/positions`: model `DealItem` + `sl`/`tp` per posisi; klasifikasi deal OUT; orphan adoption; klasifikasi `FILLED_THEN_CLOSED` / `ORPHAN_CLOSED` / `FAILED`; kill-switch `position_mismatch`; antrian `bridge_commands` dilayani di `/bridge/poll` (MODIFY_SL) dan diselesaikan `/bridge/result` (idempotent, DONE/FAILED). |
| `api/app/telegram_bot.py` | `notify_owner()`: alert owner (orphan adopted, rekonsiliasi gagal); no-op bila token belum diset, tidak pernah menggagalkan rekonsiliasi. |
| `ea/LumineEA.mq5` | Snapshot mengirim `sl`/`tp` posisi + array `deals` 24 jam (`HistorySelect`, cap 500 deal terakhir, buang balance/credit); aksi `MODIFY_SL` diterima `ProcessCommand`. |
| `api/app/state_machine.py` | (run sebelumnya) transisi `STUCK`, `FILLED_THEN_CLOSED`, `ORPHAN_ADOPTED`, `ORPHAN_CLOSED`, `RECONCILED` + helper `record_event`. |
| `api/app/schema.sql` | (run sebelumnya) tabel `bridge_commands` (MODIFY_SL/CLOSE) + kolom `positions.sl/tp`. |
| `api/app/config.py` | (run sebelumnya) konstanta reconciler: `RECONCILE_AFTER_S=60`, `DEAL_WINDOW_H=24`, `EMERGENCY_SL_DISTANCE=15.0`. |
| `api/tests/conftest.py` | `bridge_commands` masuk truncate antar test. |
| `api/tests/test_bridge.py` | 7 test reconciler baru + test DoD. |

## DoD: uji disconnect 10×

`tests/test_bridge.py::test_dod_disconnect_10x_reconciliation` — 10 siklus
disconnect/reconnect, skenario berputar (posisi masih terbuka / tertutup deal
OUT / hilang tanpa deal / orphan baru). Hasil: **rekonsiliasi benar 10/10**,
setiap siklus diverifikasi status order, status posisi, kill-switch, dan
catatan `order_events`.

```
tests/test_bridge.py::test_dod_disconnect_10x_reconciliation PASSED
20 passed tests/test_bridge.py
167 passed seluruh suite api (baseline 160 + 7 baru)
17 passed ea/test_ea_v0.py (kontrak HMAC EA tidak berubah)
```

## Kontrak snapshot EA ↔ backend

Terverifikasi: format JSON keluaran `SendPositionsSnapshot()` (posisi dengan
`sl`/`tp` + `deals`) di-parse langsung ke model `PositionsBody` backend.

## Catatan operasional

- `fund2-api.service` masih menjalankan kode lama; perlu restart (DevOps)
  untuk mengaktifkan reconciler. Backward compatible: `deals` dan `sl`/`tp`
  opsional di snapshot, EA lama tetap diterima.
- Snapshot pertama setelah deploy akan mengadopsi posisi broker yang tidak
  dikenal DB sebagai `ORPHAN_ADOPTED` + SL darurat — pastikan DB bersih
  sebelum restart di live.
- Live trading tetap OFF (D1 defer); reconciler aktif di paper/demo.
