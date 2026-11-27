# Release Notes: Fund2 v2.2

Kartu: **t_f2v22a18** · Artefak wajib Lampiran B ("release notes") · Penyusun: hf-ceo ·
Tanggal: 26 Nov 2026 · Status rilis: **RC belum di-tag; live = NO-GO**

## 1. Ringkasan rilis

| Item | Nilai |
| --- | --- |
| Versi target | `fund2-v2.2.0` (RC: `fund2-v2.2-rc<N>`) |
| Tag saat ini | **belum ada** (`git tag` kosong) |
| Commit acuan | `7c02c7c` (docs release packet) · HEAD saat pemeriksaan 26 Nov 2026 |
| Tree | **kotor** (perubahan UI/LLM/kill-switch belum di-commit; fix AUDIT-B sudah di commit `1f6c390`) |
| Migrasi DB | Alembic **`l012`** (dev = prod) |
| EA | `LumineEA.mq5` **v5.03**, schema v5 |
| Python / Node | 3.14 / Vite (build di `frontend/dist`, dilayani API) |
| Lingkungan | `FUND2_ENV` belum live; live trading **OFF** |

Arti status ini secara praktis: kode sudah layak untuk paper/P9 dan UAT, tetapi **belum layak** untuk
canary/live. Daftar penahan ada di §5.

## 2. Yang berubah di v2.2 (dibanding v2.1 / P1)

### 2.1 Eksekusi & risiko
- Auto break-even + trailing stop deterministik di bridge (`RISK-B`).
- Lot sizing otomatis berbasis risk-percent 0,5% untuk order LLM, flag default OFF (`RISK-A`).
- Serialisasi event risk: alasan penolakan selalu string manusiawi, tidak pernah `[object Object]`
  (`AUDIT-B`, commit `1f6c390`).
- Fix legacy flag `halted` yang membuat order ditolak permanen setelah satu halt (`f0334cb`).
- Daily P&L mengecualikan order role `qa` agar auto-halt tidak terpicu oleh uji (`1dfea07`).
- Ambang auto-halt dibaca dari `kill_switch_triggers` (DB), bukan konstanta kode.

### 2.2 Latensi & keandalan
- Pickup `/bridge/poll` 0,25 s → 0,05 s: p95 T0→T2 turun ke **182,8 ms** (n=207, p99 215,5 ms).
- Reconciler: `SENT` > 60 s → `STUCK`, orphan diadopsi dengan SL darurat per simbol, deal penutup
  memindahkan order ke `FILLED_THEN_CLOSED`.
- Isolasi test `_ea_seen_mono` + kontrak test regime diperbarui (6 kegagalan 25 Nov ditutup, `90e4c1e`).

### 2.3 Agent LLM (G1)
- Konteks multi-timeframe M5/M15/H1/H4 + ringkasan struktur pasar.
- Breaker mengikuti settings Risk Ops; event pause/resume menyimpan threshold efektif.
- Enum jenis posisi aktif (`cut`/`sl`/`be`/`tp`/`layer`) + anti-spam dua lapis; migrasi `l012`.
- Introspeksi harian/per trade berbasis data; endpoint `GET /llm-agent/config|decisions|introspection`.
- `POST /llm-agent/resume` + `/status` untuk gerbang pemulihan agent.

### 2.4 Data & strategi
- Portfolio Risk Manager (exposure agregat + stress test), regime detection deterministik.
- Shadow runner (sinyal live tanpa order) + registry run; degradation NORMAL→WATCH→DEGRADED→HALTED.
- Strategy versioning immutable + approval + rollback; provenance backtest (checksum, rentang).
- Multipair: XAUUSD + BTCUSD dengan `symbol_specs` per simbol dan biaya terkalibrasi.

### 2.5 Keamanan & operasional
- Password Argon2id (hash bcrypt legacy di-rehash saat login), 2FA/TOTP untuk aksi berbahaya.
- Trigger append-only pada 5 tabel audit; redaksi log; secret scan bersih.
- Backup harian terenkripsi age + offsite + manifest sha256; restore drill 3/3 LULUS (23 Nov).
- Runbook + incident playbook + simulasi insiden 2x LULUS; observability SEV-1..SEV-4.

## 3. Cara upgrade

```bash
cd ~/fund2
git fetch --tags && git checkout fund2-v2.2-rc1     # setelah tag dibuat
cd api && uv sync --frozen && .venv/bin/python -m alembic upgrade head
cd ../frontend && npm ci && npm run build
systemctl --user restart fund2-api fund2-paper-runner fund2-shadow-runner fund2-llm-agent
curl -s http://127.0.0.1:3110/health
```

Urutan wajib saat window rilis: backup `pre-deploy` → tag pada commit bersih → deploy → verifikasi
`/health`, `alembic current = l012`, `frontend/dist` tersaji → catat di `deployment_records`.
Detail: `ARTEFAK_RILIS_v2.2.md` §3 dan `CHECKLIST_ROLLBACK_v2.2.md`.

## 4. Masalah yang diketahui (jujur, belum selesai)

| # | Temuan | Dampak | Status / pemilik |
| --- | --- | --- | --- |
| K-1 | Guardrail runtime masih longgar vs kebijakan owner (G-01..G-06) | Risiko order 10x, halt hampir tidak terpicu | **BLOCKER canary**; kartu `t_d3ab9839` + keputusan owner |
| K-2 | Paper gate belum lulus (3 hari, 30 trade, PF 1,09; syarat 20 hari/100 trade/PF ≥ 1,3) | Belum ada bukti statistik | `t_f2v22a14` (paper 20 hari), `t_f2llm4` |
| K-3 | Bridge menerima Bearer legacy tanpa anti-replay | Pemalsuan command bila token bocor | ADR-006; hapus/batasi sebelum canary |
| K-4 | Offsite backup pernah `WARN: size mismatch` (25 Nov 04:33 UTC) | Integritas offsite belum terbukti otomatis | Verifikasi manual + perbaiki skrip (DevOps) |
| K-5 | `fund2-alerts` restart 1x saat full pytest berjalan (pool DB jenuh) | Alert bisa tertunda saat pengujian berat | Jalankan suite di maintenance window / naikkan `max_connections` |
| K-6 | `paper_runs` kosong; 27 baris `paper_orders.run_id` NULL | Provenance paper tidak ter-link (PRD §8.2/§19.3) | Perbaiki penulisan registry (hf-backend) |
| K-7 | Tree kotor, belum ada tag, drill rollback aplikasi penuh belum | Belum bisa freeze rilis | `t_f2v22a16` + DevOps |
| K-8 | 6 database uji sisa (`fund2_test_*`) di server | Menambah pemakaian koneksi/katalog | Bersihkan sebelum window rilis |
| K-9 | Host tunggal, memori ketat (5,1/7,8 GB terpakai, swap 4 GB sudah terpakai 1,5 GB), desktop stack ikut berjalan | OOM/host mati = trading berhenti | ADR-015; pertimbangkan VPS produksi bersih |
| K-10 | `RELEASE_CHECKLIST_v2.2.md` 4.3 masih menyebut HMAC hanya di `dummy_bridge` | Dokumen usang vs kode (HMAC sudah aktif di `bridge.py`) | Perbarui pada review QA |

Temuan di atas **tidak** disembunyikan dari release notes: rilis yang tidak menyebut masalahnya
adalah rilis yang menipu operator.

## 5. Penahan rilis (gate)

Rilis live/canary tidak boleh jalan selama salah satu benar:

1. Guardrail G-01..G-06/G-12 belum disetujui owner dan terpasang (A-07).
2. P9 (paper 20 hari/100 trade/PF ≥ 1,3/DD ≤ 5%) belum lulus.
3. UAT owner + QA sign-off belum ada.
4. D1 (modal live + batas kerugian) belum diisi dan approval live tertulis belum diberikan.
5. Tag belum dibuat pada commit bersih / tree masih kotor.
6. Drill rollback aplikasi penuh belum lulus.
7. Ada temuan critical/high keamanan terbuka (saat ini tidak ada; 4 deviasi non-kritis).

Status per 26 Nov 2026: **NO-GO** untuk live, **GO** untuk melanjutkan paper/P9.

## 6. Rollback

`ROLLBACK_PLAN_v2.2.md` (rencana) + `CHECKLIST_ROLLBACK_v2.2.md` (langkah 1-10) + `ROLLBACK_P5.md`
(rollback cutover). Ringkas: halt dulu, restore arsip terakhir yang terverifikasi, `alembic downgrade`
hanya bila migrasi rilis memang menambah kolom yang tidak kompatibel, nyalakan API, verifikasi
`/health`, rekonsiliasi posisi broker sebelum menerima order baru.

## 7. Bukti rilis

| Artefak | Path |
| --- | --- |
| PRD disetujui | `docs/PRD_v2.2_End_to_End.md`, `docs/KEPUTUSAN_OWNER.md` |
| Arsitektur + ADR | `docs/ARCHITECTURE_v2.2.md`, `docs/ADR_v2.2.md` |
| Threat model | `docs/THREAT_MODEL_v2.2.md` |
| Data dictionary + protocol | `docs/DATA_DICTIONARY_v2.2.md`, `docs/API_EA_PROTOCOL_SPEC_v2.2.md` |
| Risk policy | `docs/RISK_POLICY_v2.2.md` + `docs/KEPUTUSAN_OWNER.md` |
| Test plan + evidence | `docs/TEST_PLAN_v2.2.md`, `docs/TEST_EVIDENCE_pytest_*.log` |
| Backtest/WF | `docs/BT_*`, `docs/wf2_*`, `docs/LAPORAN_WALKFORWARD_P2.md` |
| Paper/shadow | `docs/PAPER_SHADOW_REPORT_v2.2.md` |
| Security review | `docs/qa_security_v22_attempts.json`, `docs/qa_p1b_rerun.log` |
| Backup/restore | `docs/DR_v2.2.md` + `~/fund2-backups/manifest.tsv` |
| Runbook & playbook | `docs/RUNBOOK_v2.2.md`, `docs/INCIDENT_PLAYBOOK_v2.2.md` |
| Rollback | `docs/ROLLBACK_PLAN_v2.2.md`, `docs/CHECKLIST_ROLLBACK_v2.2.md` |
| Approval owner | `docs/OWNER_RELEASE_APPROVAL_v2.2.md` |
| Indeks | `docs/README.md` |

| Peran | Nama | Tanggal | Catatan |
| --- | --- | --- | --- |
| Penyusun | hf-ceo | 26 Nov 2026 | Kartu `t_f2v22a18` |
| Review | hf-qa | menunggu | K-2, K-10 |
| Review | hf-devops | menunggu | K-4, K-5, K-7, K-8 |
| Approval rilis | Owner | menunggu | §5 gate |
