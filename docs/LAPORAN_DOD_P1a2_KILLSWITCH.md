# Laporan DoD P1a2 — Kill-switch Manual + Auto-trigger + Halt Persisten

| | |
| --- | --- |
| Tanggal | 2026-11-21 |
| Pengerja | hf-backend |
| Status | **SELESAI — DoD terpenuhi** |
| Sumber | `PRD_v2.1_Fund_Core.md` §5.7 (Kill-switch) & P1a hari 6; tambahan v2.2 §16 (4 mode, pemicu dapat dikonfigurasi); keputusan owner D6 (auto-trigger tidak pernah auto-flatten) & D11 (pelepasan GLOBAL_HALT wajib owner + checklist recovery) |
| Commit | `3ff9bbf` (test isolation kill-switch) di atas checkpoint `8e40d59` (implementasi `kill_switch.py`, `telegram_bot.py`, `routes.py`, `risk.py`, tabel `kill_switch_events`) |

## 1. Butir DoD

| # | Butir DoD | Status | Bukti |
| --- | --- | --- | --- |
| 1 | Semua auto-trigger teruji dengan simulasi | **LULUS** | 5/5 trigger teruji simulasi di `api/tests/test_kill_switch.py` (rincian §2); suite penuh **160/160 PASS** (74.6 s, 2026-11-21 23:47 WIB) |
| 2 | Status kill-switch bertahan setelah restart service | **LULUS** | E2E live terhadap `fund2-api.service` (port 3110): activate → `systemctl --user restart` → state identik (mode, reason, `activated_at` sama persis), order tetap ditolak 422 (rincian §3) |

## 2. Auto-trigger (simulasi, PRD §5.7)

| Trigger | Default | Mode default | Test |
| --- | --- | --- | --- |
| Drawdown harian ≥ 3% (A6) | `daily_drawdown_pct: 3.0` | GLOBAL_HALT | `test_trigger_daily_drawdown` (+below-threshold, configurable off/mode) |
| Drawdown total ≥ 8% dari puncak equity (A7) | `total_drawdown_pct: 8.0` | GLOBAL_HALT | `test_trigger_total_drawdown` |
| EA offline > 60 dtk dengan posisi terbuka | `ea_offline_seconds: 60`, `ea_offline_requires_positions: true` | GLOBAL_HALT | `test_trigger_ea_offline_with_open_positions` (+tanpa posisi tidak menyala, EA online tidak menyala) |
| 3 order FAILED beruntun | `consecutive_failed_orders: 3` | STOP_NEW_ORDERS | `test_trigger_consecutive_failed_orders` (+2x tidak menyala, risk-rejection tidak dihitung, terputus order FILLED, reset saat release) |
| Reconciler: selisih posisi tak terjelaskan | `position_mismatch: true` | GLOBAL_HALT | `test_position_mismatch_triggers_kill_switch` (+penutupan sah tidak memicu, dapat dinonaktifkan) |

Semua pemicu dapat dikonfigurasi via `PUT /kill-switch/triggers` (termasuk mode per-trigger dan `check_interval_seconds`); monitor loop berjalan sebagai background task `kill-switch-monitor`. Auto-trigger hanya `STOP_NEW_ORDERS`/`GLOBAL_HALT`, tidak pernah auto-flatten (D6). Trigger yang sudah aktif tidak memproduksi event duplikat; aktifasi mode lebih berat tercatat sebagai `ESCALATE`.

## 3. E2E persistensi lintas restart (service live)

Timeline uji terhadap service live `fund2-api.service` (user E2E sementara `e2e-ks`, dihapus setelah uji):

1. **Pra-restart** — `POST /kill-switch {mode: STOP_NEW_ORDERS}` → 200, `activated_at = 2026-11-21T16:53:24.423947+00:00`; `POST /orders` → **422** `rejected_reasons: ["kill-switch aktif (mode: STOP_NEW_ORDERS)", ...]`.
2. **`systemctl --user restart fund2-api`** → service `active`.
3. **Pasca-restart** — `GET /kill-switch` → state **identik** (mode STOP_NEW_ORDERS, reason & activated_at sama persis) → `persisted: true`; `POST /orders` → **422** lagi dengan alasan kill-switch.
4. **Eskalasi & guard** — `POST /kill-switch {mode: GLOBAL_HALT}` → 200 (`ESCALATE` tercatat); `POST /kill-switch/release` tanpa checklist → **400** beserta 7 butir `recovery_checklist`; dengan `checklist_ack: true` → 200, state inactive.
5. **Audit** — `kill_switch_events` mencatat `ACTIVATE`, `ESCALATE`, `RELEASE` lengkap dengan mode/source/actor/reason/timestamp.

Bukti organik tambahan: state `STOP_AND_FLATTEN` sisa uji `tester` (19:18 WIB) ditemukan **masih aktif** setelah restart service 22:50 WIB — persistensi juga terbukti pada kondisi sebelum uji terkontrol. Sisa state uji tersebut dilepas saat persiapan E2E dan kondisi akhir live: kill-switch **inactive**, metrik bersih (streak FAILED 0, DD 0%, EA online).

## 4. Cakupan 4 mode (v2.2 §16)

| Mode | Perilaku | Guard |
| --- | --- | --- |
| `STOP_NEW_ORDERS` | Semua order baru ditolak risk gate | — |
| `STOP_AND_FLATTEN` | Tolak order baru + kirim CLOSE semua posisi | Wajib `confirm: true`; tanpa confirm → 400 + peringatan slippage; **hanya manual**, tidak pernah auto (D6) |
| `PAUSE_STRATEGY` | Order strategi tertentu ditolak; strategi lain normal | Per strategi, resume satu per satu |
| `GLOBAL_HALT` | Semua entry dihentikan | Pelepasan wajib owner + checklist recovery 7 butir (D11) |

Eskalasi otomatis ke mode lebih berat; downgrade manual saat aktif diabaikan (no-op). Flatten tidak lewat risk gate (penutupan selalu boleh) dan roundtrip CLOSE → EA poll → FILLED → posisi tertutup teruji E2E (`test_stop_and_flatten_close_order_roundtrip`).

## 5. Kanal manual

| Kanal | Endpoint / perintah | Otorisasi |
| --- | --- | --- |
| Dashboard (API) | `GET /kill-switch` (state+metrics+triggers+slippage_warning), `POST /kill-switch`, `POST /kill-switch/release`, `POST /kill-switch/flatten`, `PUT /kill-switch/triggers` | Sesi login + CSRF; event kill-switch di-broadcast SSE |
| Telegram | `/status`, `/stop`, `/halt`, `/stopflatten [confirm]`, `/flatten [confirm]`, `/pause <strategi>`, `/resume [strategi\|ACK]`, `/help` | Hanya `TELEGRAM_OWNER_ID`; pengirim lain diabaikan (`test_non_owner_ignored`) |

Tombol Dashboard sudah ada di frontend (card `t_9c9f4b14`, status review): `StrategyLab.jsx` (hold-to-activate), `OrderForm.jsx` (blokir order), `lib/api.js` (memanggil `/kill-switch`).

## 6. Catatan

- Pelepasan kill-switch mereset streak FAILED (`trigger_ack.failed_streak_after`) agar order lama tidak langsung memicu ulang.
- `ea_last_seen_at` dipersist throttled (15 s) sehingga restart service tidak me-reset jam offline EA.
- Test suite dijalankan ulang dari worktree bersih pada commit `3ff9bbf`: 58/58 test kill-switch + risk + auth PASS (commit self-consistent, tidak bergantung file belum-commit milik kartu ingest).
- Sisa 2 order FAILED hasil uji (risk-rejected, tidak dihitung streak) dibiarkan sebagai audit dengan `user_id` NULL; user E2E dihapus.
