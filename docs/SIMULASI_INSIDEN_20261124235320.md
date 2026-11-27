# Simulasi Insiden — Drill Incident Playbook (t_f2v22a17)

Tanggal: 2026-11-24T23:53:20+00:00 · Skenario: T2 mismatch posisi (orphan close) · Verdict: **LULUS**

Lingkungan: DB test terisolasi `fund2_test_sim_20261124235320_13503` (drop setelah drill), Telegram dimatikan,
tanpa koneksi broker. Jalur kode yang dipakai = jalur produksi (`app.kill_switch`,
`app.bridge`, auth + 2FA, endpoint HTTP asli via ASGITransport).

## Ringkasan langkah

| # | Langkah playbook | Status | Bukti ringkas |
| --- | --- | --- | --- |
| 0 | login admin, sesi + CSRF | PASS | `{"http": 200}` |
| 1 | orphan close -> auto GLOBAL_HALT (auto:position_mismatch) | PASS | `{"closed": [9001], "mode": "GLOBAL_HALT", "source": "auto:position_mismatch", "reason": "reconciler: 1 posisi hilang dar` |
| 2 | snapshot posisi + kill_switch_events | PASS | `{"open_positions": 0, "events": 1}` |
| 3 | manifest backup sha256 valid + restore drill terakhir ada | PASS | `{"verify_rc": 0, "verify_tail": ["2026-11-24T23:53:25Z VERIFY OK: semua file di manifest cocok"], "latest_restore_drill"` |
| 4 | 0 order tanpa event, trigger append-only aktif | PASS | `{"orders_without_events": 0, "append_only_triggers": 2}` |
| 5 | 2FA challenge + checklist_ack -> release, halt lepas | PASS | `{"challenge_http": 200, "release_http": 200, "active_after": false, "mode_after": null}` |

## Field incident report (template §3 playbook)

| Field | Isi |
| --- | --- |
| Severity | SEV-1 (drill) — mismatch posisi/orphan |
| Waktu mulai / selesai | 2026-11-24T23:53:20+00:00 / 2026-11-24T23:53:26+00:00 |
| Terdeteksi oleh | auto:position_mismatch (reconciler snapshot bridge) |
| Dampak posisi & order | 1 posisi uji XAUUSD 0.01 ditutup broker tanpa CLOSE order; tidak ada order baru |
| Timeline | trigger (langkah 1) -> snapshot (2) -> artifact (3) -> reconcile (4) -> resume (5) |
| Penyebab langsung | snapshot broker kehilangan ticket 9001 tanpa deal penutup tercatat |
| Akar masalah | (drill) skenario disuntik manual; di produksi: koneksi EA putus saat close |
| Tindakan otomatis | GLOBAL_HALT source auto:position_mismatch (idempotent, ter-audit) |
| Tindakan manual | snapshot, verifikasi artifact, verifikasi integritas ledger |
| Keputusan owner | resume disetujui (simulasi: 2FA + checklist_ack, 7 butir RECOVERY_CHECKLIST) |
| Bukti ledger | `simulasi_insiden_evidence_20261124235320.json` (positions, kill_switch_events, trigger append-only) |
| Bukti broker | snapshot `/bridge/positions` di langkah 1-2 (drill) |
| Corrective action | drill terjadwal rutin sebelum canary (ROLLBACK_PLAN §4) |
| Preventive action | pertahankan auto-trigger position_mismatch + alert SEV-1 |
| Status | CLOSED (drill) |

## Catatan

- Pengujian ini membuktikan jalur **playbook**, bukan performa broker live.
- Restore drill backup: lihat `DR_v2.2.md` (3x LULUS, 23 Nov) dan path di langkah 3.
