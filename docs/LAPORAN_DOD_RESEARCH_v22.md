# Laporan DoD — Hermes Research Intelligence (PRD v2.2 §12)

Task: t_f2v22a7 · Tanggal: 24 Nov 2026 · Worker: hf-backend

## Yang dibangun

Lapisan riset Hermes dengan garis merah PRD §12.1 yang di-enforce secara
teknis (bukan sekadar konvensi):

| Komponen | Fungsi |
| --- | --- |
| `app/research.py` | Registry `TOOL_ALLOWLIST` (10 tool) + `run_tool()` + CLI `python -m app.research` |
| `app/research_tools.py` | Tool read-only: data_quality, pnl_summary, event_log, pattern_scan |
| `app/research_write.py` | Tool write-terbatas: run_backtest, write_report, create_proposal, list_*, weekly_report |
| `app/research_sanitize.py` | `redact()` (key sensitif → `***`), `scan_injection()` (instruksi di data = temuan, bukan eksekusi), `find_exec_injection()` (argumen berpola eksekusi ditolak) |
| `app/research_sandbox.py` + `_child.py` | Backtest di subprocess `python -I -E -B`: env kosong, rlimits (AS/CPU/FSIZE), socket dinetralkan, Landlock best-effort, wall-clock killpg |
| `app/research_routes.py` | Endpoint `/research/*` (role `research`\|`admin`) + keputusan proposal owner-only |
| `app/research_schemas.py` | Skema Pydantic input/output tiap tool (output schema PRD §12.4) |
| `app/research_candles.py` | Loader candle read-only (konversi UTC sama dengan paper.backtest) |
| Migrasi `j010` | Tabel `research_proposals` + role `research` di `users_role_check` |

## Pemenuhan DoD

### 1. Hermes bisa buat laporan & proposal — LULUS

- CLI: `.venv/bin/python -m app.research weekly-report --days 7` menghasilkan
  laporan komposit (data_quality + pnl_summary + pattern_scan) yang tersimpan
  di `research_reports` status DRAFT, format PRD §12.3 (summary, findings
  terukur, hipotesis terpisah, risks, data sources).
- `create_proposal` menyimpan usulan ke `research_proposals` status PROPOSED
  dengan change/baseline/risks/backtest_run_ids tervalidasi referensinya.
- Anti-klaim sampel kecil (PRD §12.1): `write_report` memperingatkan bila teks
  mengklaim "profitable" dengan sampel < 30 trade (teruji).

### 2. Tidak bisa akses endpoint order/risk write (teruji negatif) — LULUS

- Role `research` ditolak default-deny di `auth.require_csrf` (satu titik
  yang dilalui SEMUA endpoint mutasi ber-session): hanya `/research/*`,
  `/auth/login`, `/auth/logout` yang diizinkan.
- 16 percobaan write diuji 403: POST /orders, kill-switch (activate/release/
  flatten/triggers), strategy mode & lifecycle, /llm-agent/decisions (audit
  log), /llm-agent/close, versioning submit/review/activate, improve decision,
  degradation re-enable, proposal decision & deployed.
- `tests/test_research.py::test_research_role_denied_on_all_writes` (16 kasus).
- Read tetap berjalan (GET /orders, /positions, /kill-switch = 200);
  GET /audit tetap 403 (admin-only).
- Role `agent`/`user` tidak bisa memakai tool riset (403).

### 3. Proposal tidak bisa deploy tanpa owner — LULUS

- Keputusan proposal: `POST /research/proposals/{id}/decision` — owner-only
  (admin + CSRF + 2FA + username == settings.owner_username), hanya dari
  status PROPOSED, sekali putus (putusan kedua → 422), tercatat append-only
  di audit_log.
- Penandaan DEPLOYED: `POST /research/proposals/{id}/deployed` — owner-only,
  hanya dari APPROVED, strategy_version_id harus ada; ini bookkeeping saja —
  eksekusi perubahan tetap lewat release workflow versioning (activate
  owner+2FA), sesuai PRD §12.2 langkah 11.
- Teruji: research → 403; admin tanpa 2FA → 403; admin non-owner+2FA → 403;
  PROPOSED → deployed → 422; version palsu → 422.

### Anti prompt-injection (PRD §12.4) — LULUS

- `event_log` memindai payload/decision; instruksi terdeteksi dilaporkan
  sebagai `injection_findings`, data tetap tersimpan sebagai data (tidak
  dieksekusi, tidak dibuang).
- Argumen tool dengan pola eksekusi (perintah shell, aksi order, sabotase
  kill-switch, SQL) ditolak 422.
- Output tool di-redact (key token/secret/password/api key → `***`);
  tool tidak pernah membaca tabel settings.
- Semua input/output tervalidasi skema Pydantic; output non-konform → 422.

## Verifikasi

- `tests/test_research.py`: 34 passed (negatif 16 write + read +
  referensi + injection + gate proposal + weekly komposit).
- Suite penuh `pytest -q`: **936 passed, 5 skipped** (0 gagal).
- Isolasi DB live: snapshot users/orders/order_events/positions/sessions/
  bridge_commands identik sebelum-sesudah test (drift hanya candle/settings
  dari service hidup).

## Keterbatasan & risiko residual

- Weekly report saat ini dijalankan on-demand (CLI/HTTP oleh Hermes);
  penjadwalan otomatis mingguan bisa jadi kartu tindak lanjut.
- Sandbox Landlock best-effort: bila kernel tak mendukung, lapisan
  env-kosong + rlimits + socket-block tetap aktif.
- `run_backtest` hanya mengizinkan 3 strategi murni (london_breakout,
  mean_reversion, btc_range_breakout), window ≤ 90 hari, candle ≤ 20rb;
  ml_gbm (butuh artefak model) sengaja belum masuk allowlist.

## Keputusan yang dibutuhkan owner

Tidak ada — kartu ini deliverable teknis. Live trading tetap OFF sesuai
keputusan P1; layer riset tidak menyentuh order/risk/kontrol apa pun.
