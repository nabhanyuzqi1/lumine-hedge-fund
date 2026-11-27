# Bukti IA-MERGE: Guardrail / Ops / Strategy Lab tanpa duplikasi

Kartu: **t_f412fd48** · Tanggal: 26 Nov 2026 (WIB) · Pelaksana: CEO
Rujukan keputusan: `KEPUTUSAN_OWNER.md` §I · `RELEASE_CHECKLIST_v2.2.md`

> Live trading tetap **OFF** (`FUND2_ENV=demo` di staging). Kartu ini tidak
> mengubah angka risiko di DB live, tidak melepas halt, dan tidak menyentuh
> kredensial. Verifikasi dilakukan di staging terisolasi (DB throwaway
> `fund2_test_ia_merge_*`, port 3112) yang menyajikan `frontend/dist` asli.

## 1. Pembagian halaman yang sekarang berlaku

| Halaman | Isi | Kanal tulis |
| --- | --- | --- |
| Guardrail `/admin/guardrail` | guardrail inti, auto-trigger kill-switch, ringkasan LLM read-only | `PUT /admin/risk-settings` (password + 2FA + rentang + audit + diff) |
| Ops `/ops` | health, backup & drill, rekonsiliasi, order stuck/orphan, aksi darurat kill-switch + event log, runbook, audit, sesi | aksi darurat kill-switch (+2FA) |
| Strategy Lab `/lab` | strategi, versi/diff, walk-forward, shadow, degradasi, supervisor/lifecycle, approval self-improve, riset, status + pause/resume agent, setelan agent LLM | setelan lewat `PUT /admin/risk-settings` (dialog password + 2FA) |

Tidak ada dua jalur tulis untuk satu setelan: halaman yang bukan pemilik aksi
hanya menampilkan status + tautan silang ("Ubah di Guardrail", "Buka Strategy
Lab", "hanya dari halaman Ops").

## 2. Perubahan kode

Backend:

- `api/app/guardrail_ranges.py` (baru): satu modul rentang + validator untuk
  auto-trigger kill-switch, `llm_risk`, `llm_auto_lot`, dan interval siklus agent.
- `api/app/routes.py`:
  - `PUT /kill-switch/triggers` ditandai **deprecated** dan memakai
    `validate_trigger_updates()` yang sama dengan kanal admin (rentang + mode),
    menulis `TRIGGERS_UPDATED` + `audit_log` dengan `source=dashboard:ops-legacy`.
  - `PUT /admin/risk-settings` menerima `kill_switch_triggers`, `llm_risk`,
    `llm_auto_lot`, `llm_interval_s`, `portfolio_risk`; merge parsial, validasi
    rentang, audit `CONFIG_CHANGED` + `settings_audit` old→new, event
    `TRIGGERS_UPDATED` `source=dashboard:guardrail`.
  - `GET /admin/risk-settings` mengirim blok `llm`
    (`interval_s`, `interval_range_s`, `auto_lot`, `risk`, `risk_ranges`).
- `api/tests/test_ia_merge_guardrail_channels.py` (baru): kontrak satu kanal +
  penolakan angka di luar rentang pada kedua endpoint.

Frontend:

- `pages/OperationsRecovery.jsx`: seluruh panel setelan dicabut (dialog
  "Ubah trigger risiko", SupervisorPanel, ResearchPanel, LlmAgentPanel,
  DegradationPanel, Approval self-improve); diganti kartu "Di luar halaman ini"
  berisi tautan ke Guardrail dan Strategy Lab.
- `pages/StrategyLab.jsx`: menerima panel pindahan (agent LLM, setelan agent,
  supervisor, riset, approval self-improve) + view degradasi per strategi.
- `components/LlmSettingsPanel.jsx` (baru): interval siklus (detik/menit/jam/hari,
  floor 30 s), auto-lot on/off + override risk, batas `llm_risk`, versi + system
  prompt read-only; simpan lewat `PUT /admin/risk-settings` (password + 2FA).
- `components/KillSwitchCard.jsx`: prop `statusOnly` untuk Lab (status + tautan
  `→ /ops`, tanpa tombol arm/flatten/release).
- `pages/AdminGuardrails.jsx`: ringkasan LLM read-only + tautan ke Lab.
- `lib/api.js`: method klien `setTriggers` (jalur lama) **dihapus**; tidak ada
  lagi pemanggil `PUT /kill-switch/triggers` dari UI.

## 3. Bukti eksekusi

### 3.1 Test backend

```
cd api && .venv/bin/python -m pytest -q
1480 passed, 4 warnings in 891.60s (0:14:51)
```

Target suite terkait (kanal guardrail, kill-switch, risk-settings, UI admin):

```
pytest tests/test_ia_merge_guardrail_channels.py tests/test_kill_switch.py \
       tests/test_risk_settings_api.py tests/test_guardrail_admin_ui.py -q
73 passed, 1 warning in 43.21s
```

### 3.2 E2E API di staging terisolasi (28 assert)

`e2e_ia_merge.py` (log: `docs/evidence/ia_merge_t_f412fd48/e2e_ia_merge_out.txt`):

- login admin + 2FA; `PUT /admin/risk-settings` menulis interval, `llm_auto_lot`,
  `llm_risk`, dan `kill_switch_triggers` dalam satu panggilan.
- `GET /llm-agent/config` melaporkan interval aktif 900 s (nilai baru dipakai).
- `PUT /kill-switch/triggers` menolak DD 500% (422) dan nilai tidak berubah:
  jalur lama kini tunduk pada validator yang sama.
- interval 10 s ditolak floor 30 s (422); key `llm_risk` asing ditolak (422);
  password salah → 403 tanpa perubahan.
- `settings_audit` memuat `llm_interval_s` dan `kill_switch_triggers` dengan
  old/new + `changed_by`.

Hasil: `RINGKASAN: SEMUA LULUS` (exit 0).

### 3.3 Bukti dari bundle yang disajikan (`frontend/dist`)

`npm run build` (vite) ulang 26 Nov 05:50 WIB → `assets/index-DxKywzhm.js`
(sha256:16 `b56204b5de906c86`), `assets/index-DL-DhjD5.css`.

- `grep -c "/kill-switch/triggers" dist/assets/*.js` → **0** (UI tidak punya
  jalur ke endpoint lama).
- Marker hadir di bundle: `Setelan agent LLM`, `Ubah di Guardrail`,
  `Buka Strategy Lab`, `Lanjut verifikasi 2FA`.
- Browser menuju staging yang menyajikan dist:
  - `/ops`: h2 = Health status, Backup & restore drill, Rekonsiliasi,
    Order pending / stuck / orphan, Kill-switch control, Runbook recovery,
    Audit history, Di luar halaman ini, Sesi aktif. Tidak ada "Ubah trigger
    risiko", tidak ada panel supervisor/riset/degradasi/approval, tidak ada
    input setelan (`inputs: []`), ada tautan `Ubah di Guardrail →` dan
    `Buka Strategy Lab →`.
  - `/lab`: h2 memuat "Agent LLM (circuit breaker)", "Setelan agent LLM",
    "Supervisor & lifecycle strategi", "Riset Hermes", "Approval self-improve";
    `KillSwitchCard` hanya berisi tautan `Ops` (tanpa tombol arm/flatten/release).
  - `/admin/guardrail`: form Guardrail inti + Auto-trigger kill-switch, ringkasan
    "Setelan LLM & agent" berlabel `read-only di sini` + tombol ke Lab.
- Simpan lewat UI (bukan API): di `/lab` interval diubah 5 → 7 menit, dialog
  menampilkan diff `300,00 → 420,00`, password + kode 2FA diisi, hasil:
  toast "Setelan agent LLM tersimpan", panel aktif berubah menjadi
  `420 detik · 7,0 menit`, dan ringkasan di Guardrail ikut 420 detik.

Screenshot (dari dist di port 3112):
`docs/evidence/ia_merge_t_f412fd48/dist_ops_scope_1280.png`,
`dist_lab_llm_1280.png`, `dist_guardrail_llm_1280.png`.

## 4. Yang sengaja TIDAK dikerjakan di kartu ini

- **Angka runtime live vs §I** (max_volume 1.0, max_orders_per_min 10,
  max_daily_drawdown 100, trigger 10/15/100/60, `llm_risk.drawdown_pause_pct`
  dan `llm_auto_lot=true`): per 26 Nov 06:00 WIB DB `fund2` masih drift.
  Perubahan angka risiko adalah keputusan bisnis + wajib lewat Guardrail dengan
  password + 2FA owner, jadi ditangani kartu `t_bf4b85f9` (samakan dev/staging)
  dan `t_728f89e4` (terapkan via UI admin + gate PASS).
- **Deploy**: bundle sudah dibangun di `frontend/dist`; memindahkannya ke server
  produksi mengikuti prosedur rilis (`RELEASE_CHECKLIST_v2.2.md`), bukan
  tindakan kartu ini.
