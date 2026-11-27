# Checklist Rollback v2.2: 1 halaman operasional

Kartu: **t_128a9dee** · Tanggal: 25 Nov 2026 · Pemilik: hf-devops
Referensi lengkap: `ROLLBACK_PLAN_v2.2.md` (detail, alasan, perintah) · `INCIDENT_PLAYBOOK_v2.2.md` · `DR_v2.2.md`

> **Prinsip: halt dulu, diagnosis kemudian. Snapshot sebelum menyentuh apa pun. Tidak pernah auto-flatten.**

## 0. Identifikasi cepat

| Gejala | Trigger | Mode default |
| --- | --- | --- |
| Order duplicate/orphan baru | T1 | GLOBAL_HALT |
| Posisi broker vs DB beda | T2 | GLOBAL_HALT |
| Posisi tanpa SL broker-side | T3 | GLOBAL_HALT |
| Ledger corrupt / DB down | T4 | GLOBAL_HALT |
| Kill switch tidak berfungsi | T5 | Halt manual darurat |
| Indikasi kompromi kredensial | T6 | GLOBAL_HALT |
| DD harian >= ambang / DD total >= ambang | T7 | GLOBAL_HALT |
| Spread/slippage abnormal | T8 | STOP_NEW_ORDERS |
| API/EA instability | T9 | GLOBAL_HALT / STOP_NEW_ORDERS |

## 1. Langkah (dikerjakan berurutan)

| # | Aksi | Pihak | Target | Verifikasi | ☐ |
| --- | --- | --- | --- | --- | --- |
| 1 | Aktifkan `GLOBAL_HALT` (darurat, tanpa 2FA) | OPS | < 1 menit | `GET /kill-switch` → `active: true` | ☐ |
| 2 | Stop runner penulis order: `systemctl --user stop fund2-llm-agent fund2-paper-runner` | OPS | 1 menit | status `inactive` | ☐ |
| 3 | Putuskan posisi: default dikelola + SL broker; flatten hanya owner (`confirm=true` + 2FA + TOTP) | OWNER | sesuai keputusan | keputusan tercatat di tiket | ☐ |
| 4 | Snapshot broker (MT5: posisi, ticket, SL/TP, balance, equity) + `fund2_backup.sh pre-deploy` + dump cepat | OPS | < 10 menit | file screenshot + JSON backup + sha256 | ☐ |
| 5 | Rollback aplikasi ke tag/commit sehat: `git checkout <tag>` + restart `fund2-api` | OPS | < 5 menit | `/health` → `{"ok":true}` | ☐ |
| 6 | Schema: forward-fix saja (`alembic upgrade head`), jangan downgrade/DROP | OPS | 1 menit | `alembic current` = head | ☐ |
| 7 | Reconcile broker vs DB; selisih = event kompensasi/adopsi, jangan edit ledger | OPS + QA | < 30 menit | 0 mismatch; integritas ledger lulus | ☐ |
| 8 | Uji read-only + bridge demo (`/health`, `/auth/me`, `/positions`, `/metrics`; poll/result idempotent) | OPS | 10 menit | semua sehat; latensi < 300 ms | ☐ |
| 9 | Owner review 7 butir `RECOVERY_CHECKLIST`, lalu release halt (2FA + `checklist_ack`) | OWNER | sesuai | event RELEASE oleh owner | ☐ |
| 10 | Incident report + append `INSIDEN_LOG_v2.2.md` + corrective action berpemilik | OPS → OWNER | 1x24 jam | log id baru | ☐ |

## 2. Pilih jalur rollback (langkah 5)

| Masalah | Jalur |
| --- | --- |
| Bug kode API/bridge | `git checkout <tag/commit-rilis-sehat>` + restart `fund2-api` |
| Versi strategi buruk | `POST /strategies/{id}/rollback` (owner: 2FA + `owner_username`) ke versi APPROVED terakhir |
| Caddy/edge | `~/fund2/scripts/rollback_caddy_fund.sh v1` (snapshot v1 tersedia) |
| DB corrupt (T4) | Restore ke instance baru dari arsip terverifikasi (DR §5), validasi sha256, lalu alihkan |
| Kredensial kompromi (T6) | Rotasi `bridge_token` + password admin + secret; revoke semua sesi; blok IP di Caddy |

## 3. Jangan

- Jangan melepas halt sebelum 7 butir checklist recovery penuh dan owner menyetujui.
- Jangan `alembic downgrade` atau ALTER/DROP destruktif di produksi.
- Jangan edit/hapus baris `order_events`, `orders`, `kill_switch_events`, `INSIDEN_LOG`.
- Jangan flatten tanpa owner, confirm, 2FA, TOTP, dan penjelasan slippage.
- Jangan resume auto-trading sebelum langkah 8 lulus.

## 4. RTO / RPO

| Komponen | Target | Terukur |
| --- | --- | --- |
| Halt manual | < 1 menit | instan |
| Restore DB | 4 jam (D7) | ~21 s (DB 64 MB) |
| RPO | <= 24 jam | backup harian 04:30 UTC + pre-deploy |
| Rollback edge | < 5 menit | `rollback_caddy_fund.sh v1` |
