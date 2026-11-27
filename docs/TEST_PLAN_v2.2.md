# Test Plan & Test Evidence: Fund2 v2.2

Kartu: **t_f2v22a18** · Artefak wajib Lampiran B ("test plan dan test evidence") · Penyusun: hf-ceo
Tanggal: 26 Nov 2026 · Status: **PLAN berlaku; bukti terakhir: 1.347 lulus / 1 gagal (drift migrasi),
dengan analisis penyebab di §5**

Dokumen ini menutup butir 5.3 `RELEASE_CHECKLIST_v2.2.md` yang sebelumnya ditunda. Isinya: apa yang
diuji, dengan alat apa, bagaimana menjalankannya, bukti nyata terakhir (dengan angka dan path log), dan
apa yang **belum** teruji.

## 1. Prinsip

1. **Bukti, bukan klaim.** Setiap butir harus punya perintah + log/JSON yang bisa dibuka ulang.
2. **Angka tidak pernah dipalsukan.** Data kurang = verdict `DATA_BELUM_CUKUP`/`INSUFFICIENT`,
   bukan PASS dengan asumsi.
3. **Kegagalan dianalisis, bukan di-rerun sampai hijau.** Setiap kegagalan diklasifikasikan: bug
   produk, test debt, atau drift lingkungan.
4. **Kontrol kritis diuji di level terendah yang mungkin** (risk gate = unit), lalu diverifikasi lagi
   end-to-end (order nyata ke EA demo).

## 2. Level dan alat

| Level | Cakupan | Alat | Lokasi |
| --- | --- | --- | --- |
| Unit | risk gate, portfolio risk, state machine, validasi tick, auth, metrik | pytest | `api/tests/test_risk.py`, `test_portfolio_risk.py`, `test_baseline.py`, ... |
| Property-based | invarian risk gate & level fibonacci | pytest + hypothesis | `test_property_based.py` |
| Integration | API + DB + worker + bridge (tanpa broker) | pytest + httpx ASGITransport | `test_bridge.py`, `test_orders_api.py`, `test_orders_reasons.py`, `test_kill_switch.py` |
| End-to-end | order nyata ke EA demo (T0..T4), SSE, UI | driver `_p5_latency_driver_v11.py`, playwright/UI QA | `docs/QA_P5_cutover.md`, `docs/QA_UI_D6_endtoend.md` |
| Fault injection | disconnect EA, DB down, bridge hang, orphan posisi, crash runner | skrip + simulasi insiden | `docs/SIMULASI_INSIDEN_*.md`, `test_alerts_resilience.py` |
| Keamanan | auth/RBAC/CSRF/lockout/2FA/HMAC/replay/injection/secret scan | `docs/pentest.py`, `test_security_v22.py`, `test_hmac_auth.py`, `test_llm_injection_guard*.py` | `docs/qa_security_v22_attempts.json` |
| Performa | latensi jalur order, load, soak | `scripts/latency_harness.py`, `load_soak_check.py`, `soak_extended.py` | `docs/LOAD_SOAK_v2.2.md` |
| DR | backup, restore ke instance terisolasi, integritas ledger | `scripts/fund2_backup.sh`, `fund2_restore_drill.sh` | `docs/DR_v2.2.md` |
| Gerbang strategi | paper & shadow (PF, DD, jumlah trade, leakage) | `scripts/eval_gate_paper.py`, `eval_gate_shadow.py` | `docs/PAPER_SHADOW_REPORT_v2.2.md` |
| Migrasi | upgrade/downgrade head, trigger append-only | `test_migrations.py`, `test_llm_agent_v2.py::test_l012_downgrade_upgrade` | `api/alembic/versions/` |

73 file test di `api/tests/`.

## 3. Matriks cakupan per area risiko

| Area | Yang wajib terbukti | Test kunci | Status bukti |
| --- | --- | --- | --- |
| SL wajib & jarak SL | order tanpa SL ditolak, jarak di luar A2 ditolak | `test_risk.py` (93 kasus bersama portfolio risk) | LULUS |
| Lot & eksposur | lot > maks ditolak; eksposur agregat > maks ditolak | `test_risk.py`, `test_portfolio_risk.py` | LULUS |
| Drawdown & auto-halt | DD harian/total memicu halt persisten; reset hanya owner | `test_kill_switch.py`, `test_e2e.py` | LULUS |
| Tick basi & spread | tick > 3 s ditolak; spread > filter ditolak | `test_risk.py`, `test_ingest_validation.py` | LULUS |
| State machine | semua transisi sah diizinkan, yang tidak sah ditolak, event append | `test_baseline.py`, `test_bridge.py` | LULUS |
| Bridge idempotensi | `result` ganda tidak menggandakan order | `test_bridge.py` | LULUS |
| Reconnect & orphan | 10/10 disconnect; orphan diadopsi + SL darurat | `docs/QA_P5_cutover.md` §3, `test_kill_switch.py` | LULUS (10/10) |
| Auth & RBAC | agent tidak bisa kontrol; CSRF wajib; lockout | `test_agent_role.py`, `test_auth.py`, `test_security_v22.py` | LULUS |
| 2FA/TOTP | challenge wajib untuk flatten; counter reuse ditolak | `test_totp.py` | LULUS |
| Prompt injection | 27 kasus agent-side ditolak / tidak dieksekusi | `test_llm_injection_guard*.py` | LULUS |
| Migrasi | upgrade head dan downgrade satu langkah bekerja | `test_migrations.py`, `test_l012_downgrade_upgrade` | **1 gagal** karena head bergeser ke `m013` (§5) |
| Gerbang paper | 20 hari/100 trade/PF ≥ 1,3/DD ≤ 5% | `eval_gate_paper.py` | **DATA_BELUM_CUKUP** |
| Gerbang shadow | ≥ 10 sinyal + tanpa leakage + approval owner | `eval_gate_shadow.py` | **INSUFFICIENT** (0 sinyal pada run aktif) |

## 4. Cara menjalankan (persis)

```bash
cd ~/fund2/api
set -a && . ./.env && set +a

# 1) suite penuh (≈13-16 menit, DB uji terpisah fund2_test*)
.venv/bin/python -m pytest -q 2>&1 | tee ../docs/TEST_EVIDENCE_pytest_$(date +%Y%m%dT%H%M%S).log

# 2) subset cepat untuk perubahan jalur order/bridge
.venv/bin/python -m pytest -q tests/test_risk.py tests/test_bridge.py tests/test_kill_switch.py

# 3) migrasi
.venv/bin/python -m alembic current && .venv/bin/python -m alembic heads

# 4) keamanan (BASE hardcode http://127.0.0.1:3110 di skrip; read-only probes)
cd ~/fund2 && api/.venv/bin/python docs/pentest.py

# 5) performa
api/.venv/bin/python scripts/latency_harness.py --help
api/.venv/bin/python scripts/load_soak_check.py

# 6) DR
scripts/fund2_backup.sh --verify-only
scripts/fund2_restore_drill.sh        # staging terisolasi :5599

# 7) gerbang strategi
api/.venv/bin/python scripts/eval_gate_paper.py --strategy llm --out /tmp/gate_llm
api/.venv/bin/python scripts/eval_gate_shadow.py --label lb-base --out /tmp/gate_lb
```

## 5. Bukti terakhir (nyata)

| # | Eksekusi | Waktu | Hasil | Verdict | Bukti |
| --- | --- | --- | --- | --- | --- |
| T-1 | Full pytest, HEAD `7c02c7c` + working tree (termasuk migrasi `m013` belum di-commit) | 26 Nov 2026 01:25-01:41 WIB | **1.347 passed, 1 failed**, 3 warning, 933 s | **FAIL (1)**: drift migrasi, bukan regresi produk | `docs/TEST_EVIDENCE_pytest_20261126T012510.log` |
| T-2 | Full pytest setelah perbaikan isolasi & kontrak test | 25 Nov 2026 08:42 WIB | **1.127 passed**, 773 s | PASS | `docs/QA_v22_pytest_25nov_fix_run2.log` |
| T-3 | Full pytest sebelum perbaikan | 25 Nov 2026 07:08 WIB | 1.115 passed, **6 failed** (isolasi `_ea_seen_mono`, kontrak regime) | FAIL → diperbaiki commit `90e4c1e` | `docs/QA_v22_pytest_25nov.log` |
| T-4 | Latensi jalur order rerun v11 (EA demo nyata) | 25 Nov 2026 18:05-19:39 WIB | 207 order, p95 T0→T2 **182,8 ms**, p99 215,5 ms, 0 ditolak | PASS (< 300 ms) | `docs/QA_P5_cutover.md` §2a |
| T-5 | Load 2.000 req + soak 30 s | 23 Nov 2026 17:34 WIB | 175 rps puncak, 0 error 5xx, p95 campuran 303,8 ms | LULUS (isolated) | `docs/LOAD_SOAK_v2.2.md` |
| T-6 | Extended soak 360 s | 25 Nov 2026 21:52 | 32.848 req, 91,2 rps, 0 5xx, p95 220,8 ms, RSS +5,9% | LULUS | `docs/QA_v22_soak_extended_20261125T215716Z.json` |
| T-7 | Keamanan: 42 probe (auth/RBAC/CSRF/lockout/2FA/replay/injection/secret) | 23 & 25 Nov 2026 | 41 probe berperilaku sesuai harapan, 0 fail, 4 deviasi non-kritis; 1 baris `ok:false` = langkah cleanup user uji | PASS dengan catatan | `docs/qa_security_v22_attempts.json`, `docs/qa_p1b_rerun.log` |
| T-8 | Restore drill 3x | 23 Nov 2026 | 3/3 LULUS, restore DB 9 s, total DB+API ~21 s | PASS | `docs/DR_v2.2.md` §3 |
| T-9 | Simulasi insiden (orphan close → auto halt → release 2FA) | 24 Nov 2026 | 2x LULUS, 6/6 langkah PASS | PASS | `docs/SIMULASI_INSIDEN_*.md` |
| T-10 | Gerbang paper (independen, ukur ulang) | 26 Nov 2026 01:3x WIB | 30 trade closed, PF **1,091**, DD 2,45%, 3 hari kerja; keputusan agent 111 (valid 31/hold 37/invalid 43) | **DATA_BELUM_CUKUP** | log eksekusi di `PAPER_SHADOW_REPORT_v2.2.md` §2 |
| T-11 | Gerbang shadow (3 label) | 26 Nov 2026 01:39 WIB | 0 sinyal pada run aktif → `INSUFFICIENT` (exit 3) | **INSUFFICIENT** | `docs/EVIDENCE_shadow_gate_*.md` |

### Analisis T-1 (satu-satunya kegagalan)

```
FAILED tests/test_llm_agent_v2.py::test_l012_downgrade_upgrade
AssertionError: assert 'm013' == 'l012'
```

Penyebab: file migrasi `api/alembic/versions/m013_risk_config_overrides.py` (untracked, milik pekerjaan
RISK-D yang sedang berjalan) membuat `alembic heads` = **m013**, sementara test (dan DB live) masih
`l012`. Jadi kegagalan ini adalah **assertion versi yang usang di test**, bukan bug produk: jalur
downgrade→upgrade sendiri berjalan (`llm_introspections` hilang lalu tercipta kembali).

Tindakan yang benar: pemilik migrasi `m013` menyesuaikan test ke head baru (atau pin ke `head`) saat
pekerjaan itu selesai, lalu suite dijalankan ulang. Sampai itu, angka resmi rilis adalah T-2
(1.127 lulus, tree bersih pada saat itu) + catatan T-1.

**Pelajaran lingkungan:** menjalankan suite penuh di host yang sama dengan layanan live memakai
koneksi DB tambahan (`max_connections=100`) dan sempat membuat `fund2-alerts` gagal mendapat koneksi
(restart 1x). Jadwalkan suite penuh di maintenance window, dan pastikan `max_connections` cukup.

## 6. Exit criteria rilis (semua wajib)

| # | Kriteria | Ambang | Status 26 Nov |
| --- | --- | --- | --- |
| E-1 | Full pytest | 0 failed | **BELUM** (1 gagal, penyebab drift §5) |
| E-2 | Risiko keamanan | 0 critical/high terbuka | TERPENUHI (0 fail, 4 deviasi non-kritis) |
| E-3 | Latensi T0→T2 | p95 < 300 ms pada ≥ 200 order | TERPENUHI (182,8 ms, n=207) |
| E-4 | Disconnect | 10/10 rekonsiliasi benar | TERPENUHI |
| E-5 | Gerbang paper | 20 hari kerja, 100 trade, PF ≥ 1,3, DD ≤ 5% | **BELUM** (3 hari, 30 trade, PF 1,09) |
| E-6 | Gerbang shadow | ≥ 10 sinyal/label + bebas leakage + approval owner | **BELUM** (0-1 sinyal) |
| E-7 | Restore drill | lulus, RTO/RPO terukur | TERPENUHI (3/3) |
| E-8 | Drill rollback aplikasi penuh | langkah 1-10 lulus | **BELUM** (`CHECKLIST_ROLLBACK_v2.2.md` deviasi 3.6) |
| E-9 | Migrasi | head tunggal, DB = head | **BELUM** (DB `l012`, head `m013`) |
| E-10 | UAT owner | berita acara | **BELUM** |

Rilis tidak boleh GO selama ada baris **BELUM**.

## 7. Kebijakan regresi dan test flaky

- Bug yang ditemukan di produksi/paper wajib mendapat test regresi yang gagal sebelum fix (RED),
  lulus sesudah fix (GREEN), dan tetap lulus di suite penuh.
- Test flaky tidak boleh di-`skip` diam-diam: harus dikarantina dengan alasan + tiket, dan diperbaiki
  dalam satu sprint. Contoh yang sudah diselesaikan: `_ea_seen_mono` bocor antar-test (`90e4c1e`),
  `test_bridge_command_roundtrip` flaky loop (`t_f1e35b49`).
- Suite penuh wajib dijalankan minimal: sebelum tag RC, sebelum deploy produksi, dan setelah merge
  perubahan jalur order/risk/migrasi.

## 8. Test debt dan batasan yang diakui

| # | Kekurangan | Dampak | Rencana |
| --- | --- | --- | --- |
| D-1 | Tidak ada pengukuran coverage otomatis (B4 "100% branch risk gate" belum diukur dengan tool) | Klaim coverage tidak terbukti | Tambah `pytest-cov` + ambang untuk `risk.py`/`portfolio_risk.py` |
| D-2 | Exclude order role `qa` dari P&L diuji lewat data, bukan isolasi penuh | Risiko halus bila role salah | Test kontrak role `qa` di CI |
| D-3 | Database uji sisa (`fund2_test_*`) tidak selalu dibersihkan | Menambah koneksi/katalog | Cleanup di fixture teardown |
| D-4 | Shadow runner praktis tidak menghasilkan sinyal (0-1 per label) | Gate shadow tidak bisa dinilai | Perbaiki frekuensi/parameter shadow (`t_f2v22a4`) |
| D-5 | `paper_runs` kosong, `paper_orders.run_id` NULL | Provenance paper tidak ter-link | Perbaiki penulisan registry (hf-backend) |
| D-6 | Uji beban dilakukan di host yang juga menjalankan layanan | Angka p95 bisa terpengaruh beban silang | Ulang di host bersih sebelum canary |

## 9. Sign-off

| Peran | Nama | Tanggal | Catatan |
| --- | --- | --- | --- |
| Penyusun | hf-ceo | 26 Nov 2026 | Menutup butir 5.3 release checklist |
| QA | hf-qa | menunggu | verifikasi T-1..T-11 |
| DevOps | hf-devops | menunggu | D-6, K-8 |

Referensi: PRD v2.2 §22 (test strategy), §23.12; `RELEASE_CHECKLIST_v2.2.md` §2-§5;
`QA_P5_cutover.md`; `LOAD_SOAK_v2.2.md`; `DR_v2.2.md`.
