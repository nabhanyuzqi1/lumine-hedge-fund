# Artefak Rilis v2.2: build, tag, dan manifes

Kartu: **t_128a9dee** (paket kesiapan operasional) · Tanggal: 25 Nov 2026 (WIB) · Pemilik: hf-devops
Referensi: PRD v2.2 Lampiran B (artefak wajib sebelum rilis), `RELEASE_CHECKLIST_v2.2.md` butir 5.6

> Kartu ini menyusun dan memvalidasi daftar artefak. Ia **tidak membuat tag, tidak membangun arsip rilis, dan tidak deploy**. Tag hanya dibuat setelah P9 lulus dan code freeze.

## 1. Identitas build saat ini (diverifikasi 25 Nov 2026)

| Item | Nilai | Status |
| --- | --- | --- |
| Repo | `/home/tekka/fund2`, branch `master` | - |
| HEAD | `f39c60f` (docs(p5): rerun v11 LULUS gerbang 2) | - |
| Tree bersih | **TIDAK**: `api/app/routes.py` dimodifikasi (fix AUDIT-B, 64 baris), `api/tests/test_orders_reasons.py` baru belum di-track, beberapa dokumen QA baru belum di-track | **BLOKER freeze** |
| Tag | **belum ada** (`git tag` kosong) | **BLOKER rilis** |
| Skema DB | Alembic `l012` (head), DB produksi juga `l012` | sinkron |
| Lock dependensi | `api/pyproject.toml` + `api/uv.lock`, `frontend/package.json` + `frontend/package-lock.json` | ada |
| Frontend build | `frontend/dist` ada (`index.html` + `assets/`), dilayani API (`config.FRONTEND_DIST`) | ada |

**Artikel rilis harus dibangun dari commit yang bersih.** Fix AUDIT-B di `routes.py` harus selesai diuji dan di-commit (atau dikeluarkan dari rilis) sebelum tag. Dilarang men-tag tree yang kotor.

## 2. Skema penamaan

| Kegunaan | Nama | Syarat |
| --- | --- | --- |
| Release candidate | `fund2-v2.2-rc<N>` | commit bersih, pytest penuh lulus, secret scan bersih |
| Rilis final | `fund2-v2.2.0` | setelah canary lulus DoD |
| Arsip | `fund2-v2.2-<tag>.tar.gz` + `SHA256SUMS` | dibuat dari `git archive` pada tag |
| Catat | `deployment_records` (versi, env, commit, tag, sha256, aktor, waktu) | wajib diisi saat deploy |

## 3. Prosedur build (untuk dieksekusi di window rilis, bukan sekarang)

```bash
cd ~/fund2
git fetch --tags && git checkout fund2-v2.2-rc1
git status --porcelain            # wajib kosong

# API (Python 3.14, uv)
cd api
uv sync --frozen                  # atau: uv pip install -e . sesuai lock
.venv/bin/python -m alembic history | head -3
.venv/bin/python -m pytest -q     # lulus penuh

# Frontend
cd ../frontend
npm ci
npm run lint && npm run build     # output dist/

# Arsip + checksum
cd ~/fund2
git archive --format=tar.gz -o /tmp/fund2-v2.2-rc1.tar.gz fund2-v2.2-rc1
sha256sum /tmp/fund2-v2.2-rc1.tar.gz > /tmp/SHA256SUMS
```

Verifikasi pasca-build: `/health` ok, `alembic current` = `l012`, `frontend/dist` dilayani, unit systemd tidak berubah tanpa catatan.

## 4. Manifes artefak wajib (PRD Lampiran B)

| # | Artefak | Path | Status 25 Nov | Catatan |
| --- | --- | --- | --- | --- |
| 1 | PRD disetujui | `docs/PRD_v2.2_End_to_End.md`, `docs/KEPUTUSAN_OWNER.md` | ADA | D1 DEFER, H1 menahan release-path |
| 2 | Architecture diagram + ADR | (belum ada file khusus) | **BELUM** | Kartu `t_f2v22a18` berjalan (hf-ceo) |
| 3 | Threat model | `docs/RISK_REGISTER_v2.2.md` §4 | ADA (DRAFT) | 14 STRIDE + 5 ancaman AI |
| 4 | Data dictionary | `docs/SCHEMA_v2.2.md` | ADA | Tabel logical + retensi + partisi |
| 5 | API/EA protocol spec | `ea/HMAC_CONTRACT.md`, `docs/LAPORAN_DOD_P0.md` | ADA SEBAGIAN | Bridge produksi masih Bearer (deviasi 4.3 non-kritis); HMAC di dummy_bridge |
| 6 | Risk policy ditandatangani owner | `docs/KEPUTUSAN_OWNER.md` bagian E | ADA (baseline) | SETUJU SEMUA 21 Nov; D1 DEFER |
| 7 | Test plan + evidence | `docs/RELEASE_CHECKLIST_v2.2.md`, `docs/QA_*.md`, `api/tests/` | ADA SEBAGIAN | TEST_PLAN.md ditunda (butir 5.3); pytest 1127 lulus 25 Nov |
| 8 | Backtest/walk-forward | `docs/BT_*`, `docs/wf2_*`, `docs/LAPORAN_WALKFORWARD_P2.md` | ADA | 4 set WF + paritas |
| 9 | Paper/shadow report | `docs/qa_p5_gate5_london_breakout.md`, `docs/QA_shadow_t_f2v22a4.md`, `docs/QA_F2LLM4_*` | ADA (belum lulus) | PF 1,211 < 1,3; P9 jalan |
| 10 | Security review | `docs/qa_p1b_rerun.log`, `docs/qa_security_v22_attempts.json`, `docs/pentest.py` | ADA | 0 fail, 4 deviasi non-kritis |
| 11 | Backup/restore evidence | `docs/DR_v2.2.md`, `~/fund2-backups/logs/` | ADA | 3x drill lulus; backup harian offsite |
| 12 | Runbook + incident playbook | `docs/RUNBOOK_v2.2.md`, `docs/RUNBOOK_v2.2_UJI.md`, `docs/INCIDENT_PLAYBOOK_v2.2.md` | ADA | Diuji pihak lain; temuan F1/F2 terbuka |
| 13 | Release notes | (belum ada) | **BELUM** | Wajib sebelum tag rilis |
| 14 | Rollback plan | `docs/ROLLBACK_PLAN_v2.2.md`, `docs/CHECKLIST_ROLLBACK_v2.2.md` | ADA | Drill aplikasi penuh belum |
| 15 | Owner release approval | (belum ada) | **BELUM** | G3 di `PRASYARAT_LIVE_v2.2.md` |

## 5. Celah dan pemilik tindakan

| # | Celah | Pemilik | Syarat tutup |
| --- | --- | --- | --- |
| C-1 | Architecture diagram + ADR | hf-ceo (`t_f2v22a18`) | Dokumen ada di `docs/`, terindeks README |
| C-2 | Release notes | hf-ceo (`t_f2v22a18`) | Versi, perubahan, bug diketahui, parameter final |
| C-3 | Tree kotor: fix AUDIT-B belum di-commit | pemilik kartu terkait (QA/audit) | Commit + pytest lulus, atau keluar dari rilis |
| C-4 | Full-app rollback drill belum | hf-devops (kartu tindak lanjut) | Laporan drill: tag sehat -> inject -> langkah 1-10 -> resume-ready |
| C-5 | UAT owner + berita acara | QA + owner | Formulir UAT diisi |
| C-6 | Owner release approval | owner | G3 `PRASYARAT_LIVE_v2.2.md` |

## 6. Penyimpanan dan retensi

- Arsip rilis: `~/fund2-backups/releases/<tag>/` (di luar repo, sama pola backup) dengan `SHA256SUMS`.
- Tag tidak pernah dipindah/dihapus setelah dipakai canary.
- `deployment_records` append-only; koreksi = baris baru, bukan edit.

## 7. Penahan rilis (semua harus nol)

1. Tree kotor atau tag belum ada.
2. P9 belum lulus atau QA sign-off belum.
3. Ada critical/high security issue terbuka.
4. Drill rollback aplikasi penuh belum lulus.
5. Guardrail drift `PRASYARAT_LIVE_v2.2.md` §3 belum disetujui owner.
6. Approval live tertulis belum ada.

## 8. Sign-off

| Peran | Nama | Tanggal | Catatan |
| --- | --- | --- | --- |
| Penyusun | hf-devops | 25 Nov 2026 | Kartu t_128a9dee |
| Review | hf-ceo | menunggu | Celah C-1/C-2 milik a18 |
| Review | hf-qa | menunggu | Bukti test plan |
