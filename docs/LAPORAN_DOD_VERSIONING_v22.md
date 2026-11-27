# LAPORAN DoD — Strategy Versioning, Approval & Rollback (PRD v2.2 §11)

Kartu: t_f2v22a6 | Assignee: hf-backend | Tanggal: 24 Nov 2026

## Cakupan implementasi

| Komponen | File | Status |
| --- | --- | --- |
| Registry versi + approval + rollback (core) | `api/app/versioning.py` (baru) | selesai |
| REST endpoints | `api/app/versioning_routes.py` (baru) | selesai |
| Wiring router | `api/app/main.py` (+2 baris) | selesai |
| Test suite (17 test) | `api/tests/test_versioning.py` (baru) | selesai |

Tidak ada migrasi skema baru: memakai tabel `strategy_versions`,
`strategy_approvals` (append-only), `strategies`, `system_events`,
`deployment_records`, `reconciliation_runs` (migrasi a001/b002 sudah
menyediakan trigger immutability + `trigger_source='POST_ROLLBACK'`).

## Endpoint

| Method | Path | Auth | Fungsi |
| --- | --- | --- | --- |
| GET | `/strategies/{id}/versions` | login | daftar versi + approval + status aktif + drift |
| POST | `/strategies/{id}/versions` | admin+2FA | registrasi versi baru (DRAFT) |
| GET | `/strategies/{id}/versions/{v}` | login | detail satu versi |
| POST | `/strategies/{id}/versions/{v}/artifacts` | admin+2FA | lengkapi artifact (hanya DRAFT) |
| POST | `/strategies/{id}/versions/{v}/submit` | admin+2FA | DRAFT → REVIEW (kunci artifact) |
| POST | `/strategies/{id}/versions/{v}/review` | admin; stage owner wajib owner | keputusan stage (PRD 11.2) |
| POST | `/strategies/{id}/versions/{v}/activate` | owner (2FA+owner_username) | aktifkan versi (mode paper/live) |
| POST | `/strategies/{id}/rollback` | owner (2FA+owner_username) | rollback ke versi terakhir disetujui |

## Pemenuhan PRD §11

### 11.1 Immutable release

Setiap versi menyimpan: strategy ID + version, `code_commit_hash`
(default git HEAD saat registrasi), `code_path`, `params` +
`config_hash` (SHA-256 params kanonik), `data_version`, laporan
`backtest/walkforward/shadow/paper`, `risk_profile`, `change_reason`,
`created_by/at`. Tanggal aktivasi/nonaktif dicatat append-only sebagai
baris `strategy_approvals` stage `ACTIVATE` (created_at = waktu aktivasi;
evidence memuat versi sebelumnya + waktunya nonaktif).

"Versi live tidak boleh ditimpa": versi final (APPROVED/REJECTED/
SUPERSEDED) diblokir UPDATE/DELETE oleh trigger DB
`strategy_versions_immutable` (b002) dan oleh API (409). Registrasi versi
duplikat ditolak 409. Bukti: `test_approved_version_immutable_api_and_db`
(API 409 + psycopg exception "immutable" untuk UPDATE dan DELETE),
`test_duplicate_version_rejected`, `test_rejection_freezes_version`.

### 11.2 Promotion workflow

`DRAFT → BACKTEST → REVIEW → SHADOW → PAPER → OWNER_APPROVAL →
CANARY/LOW_RISK_LIVE → FULL_APPROVED_LIVE` dipetakan ke:

- status versi: `DRAFT → REVIEW → APPROVED` (REJECTED = final);
- stage approval append-only: `BACKTEST_REVIEW → SHADOW_REVIEW →
  PAPER_REVIEW → OWNER_APPROVAL → LIVE_APPROVAL`, urutan di-enforce,
  satu stage satu keputusan, setiap keputusan membawa reviewer +
  rationale + evidence;
- lifecycle `strategies` (PRD 5.3): VALIDATING → BACKTEST_APPROVED →
  SHADOW → PAPER → LIVE_APPROVED → LIVE via
  `supervisor.transition_strategy` (owner-only transitions tetap
  di-enforce); strategi legacy yang sudah PAPER/LIVE tidak dimundur.

Auth: stage BACKTEST/SHADOW/PAPER_REVIEW = admin; OWNER_APPROVAL dan
LIVE_APPROVAL = owner (admin + 2FA + username == `owner_username`);
aktivasi dan rollback = owner. Bukti: `test_stage_order_enforced`,
`test_owner_stage_requires_owner_username`,
`test_activate_live_requires_owner_and_live_approval`,
`test_full_promotion_paper_activation_records_evidence`.

### 11.3 Rollback

- Owner memilih versi terakhir yang disetujui: `to_version` eksplisit
  (harus ter-approve) atau otomatis = versi terakhir yang pernah
  di-ACTIVATE selain versi sekarang.
- Sinyal baru dari versi bermasalah berhenti: `strategies.current_version`
  dipindah; `supervisor.decide` men-stamp versi registry pada setiap
  sinyal + OrderIntent. Bukti:
  `test_signals_carry_registry_version_and_rollback_switches` (stamp
  berubah 0.0.1 → 0.1.0 → 0.2.0 → rollback → 0.1.0).
- Posisi terbuka TIDAK diotomatis tutup: tidak ada pemanggilan
  flatten/close; kebijakan exit owner dicatat sebagai
  `position_policy` di evidence. Bukti:
  `test_rollback_restores_last_approved_keeps_positions` (posisi live
  `positions`+`orders` dan paper `paper_orders` tetap OPEN setelah
  rollback).
- Rollback tercatat sebagai event: `system_events` (STRATEGY_ROLLBACK,
  WARN), `strategy_approvals` stage `ROLLBACK` (append-only),
  `deployment_records` (action=ROLLBACK).
- Rekonsiliasi setelah rollback: baris `reconciliation_runs`
  `trigger_source='POST_ROLLBACK'`, status COMPLETED, ledger_summary
  memuat hitungan posisi terbuka live + paper.
- Params versi tujuan dipulihkan ke settings `strategy_params_<id>`
  (ter-audit `settings_audit`, atribusi aktor via `app.actor`).

### 11.4 Acceptance criteria

- ✅ Artifact versi disetujui tidak bisa diubah: API 409 + DB trigger.
- ✅ Setiap live strategy memiliki versi jelas: `strategies.current_version`
  menempel di setiap sinyal/intent; GET versions menampilkan
  `is_current`, `module_version`, dan `version_drift` (kode jalan vs
  registry).
- ✅ Rollback diuji di staging: seluruh alur diuji end-to-end di DB test
  terisolasi (staging pytest), 17 test lulus.
- ✅ Tidak ada auto-promotion: status versi hanya berubah lewat
  `decide_stage()` eksplisit; registrasi tidak mengubah apa pun
  (`test_no_auto_promotion`); `supervisor.AUTO_TRANSITIONS` hanya jalur
  fault turun (LIVE→DEGRADED, DEGRADED→DISABLED) dan semua transisi
  kenaikan privilege ada di `OWNER_ONLY_TRANSITIONS`.

## Hasil pengujian

```
.venv/bin/python -m pytest tests/test_versioning.py -q
17 passed

.venv/bin/python -m pytest tests/ -q   (full suite, 24 Nov 2026)
902 passed, 5 skipped in 512s -- EXIT=0, tidak ada regresi
```

## Catatan desain

- Tanpa migrasi baru: memakai trigger + tabel yang sudah ada (b002),
  termasuk `trigger_source='POST_ROLLBACK'` yang memang disiapkan skema.
- Status versi dibekukan di OWNER_APPROVAL; LIVE_APPROVAL diputuskan
  setelahnya sebagai baris approval tambahan (artifact tetap beku).
- Rollback ini registry-level (pointer versi + params + provenance).
  Rollback kode (git revert/redeploy) tetap ranah deployment DevOps dan
  tercatat terpisah di `deployment_records`.
- Live trading tetap OFF sesuai keputusan P1; aktivasi mode `live`
  tersedia namun tetap memerlukan gerbang owner terpisah (D1).
