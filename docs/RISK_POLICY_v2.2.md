# Risk Policy: Fund2 v2.2 (disetujui owner)

Kartu: **t_f2v22a18** · Artefak wajib Lampiran B ("risk policy yang ditandatangani owner") ·
Penyusun: hf-ceo · Tanggal: 26 Nov 2026

## 0. Kedudukan dokumen

Kebijakan risiko yang **mengikat** adalah `KEPUTUSAN_OWNER.md` bagian A-D, dengan amendemen F1, G1,
dan H1. Owner sudah menyatakan **"SETUJU SEMUA"** pada 21 Nov 2026 (bagian E), sehingga baseline itu
sah sebagai risk policy.

Dokumen ini adalah **konsolidasi** untuk keperluan rilis: ia menyatakan kebijakan itu berlaku, di mana
ia ditegakkan di kode, apa yang masih menyimpang di runtime, dan tanda tangan apa yang masih kurang.
Dokumen ini **tidak** menggantikan `KEPUTUSAN_OWNER.md` dan **tidak** menetapkan angka baru. Angka baru
hanya boleh lahir dari keputusan owner tertulis (mis. kartu `t_d3ab9839` untuk G-01..G-06).

Bila ada konflik antar dokumen: `KEPUTUSAN_OWNER.md` menang atas dokumen operasional; nilai runtime di
DB **bukan** kebijakan sampai disetujui dan dicatat.

## 1. Pernyataan kebijakan (ringkas per domain)

| Domain | Kebijakan yang berlaku | Sumber | Ditegakkan di |
| --- | --- | --- | --- |
| Keselamatan order | SL wajib dipasang di sisi broker; tanpa SL order ditolak | A1 | `api/app/risk.py`, `routes.py` |
| Batas per order | Volume maksimum per order; jarak SL min/maks sesuai contract spec | A2, A3 | `risk.py` + `symbol_specs` (per simbol) |
| Eksposur | Eksposur total terbuka maksimum; risiko per trade maksimum | A4, A5 | `portfolio_risk.py` |
| Drawdown | DD harian → auto-halt; DD total dari puncak → auto-halt + notifikasi; reset hanya owner | A6, A7 | `kill_switch.py`, `kill_switch_triggers` |
| Laju order | Order per menit maksimum (anti runaway) | A8 | `risk.py`, `auth.action_rate_limited` |
| Kualitas data | Spread filter (absolut + relatif median 15 menit); tick basi ditolak | A9, A10 | `risk.py`, `validate.py` |
| Disconnect | EA OFFLINE → tolak order baru; posisi tetap dilindungi SL broker; tidak auto-close | A11, D4 | `kill_switch`, `risk.py` |
| Heartbeat | Heartbeat 2 s; 3 terlewat = OFFLINE | A12 | `bridge.py`, `kill_switch.py` |
| Gerbang strategi | Data ≥ 2 tahun; paper ≥ 20 hari kerja, ≥ 100 trade, PF ≥ 1,3 setelah biaya, DD ≤ 5% | B2 | `scripts/eval_gate_paper.py`, `eval_gate_shadow.py` |
| Validasi strategi | Walk-forward latih 6 bln / uji 1 bln / geser 1 bln; window ditetapkan sebelum eksperimen | B1 | `backtest_runs` (registry semua percobaan) |
| Kualitas uji | 100% branch pada fungsi risk gate kritis; nol bug critical/high terbuka | B4 | `TEST_PLAN_v2.2.md` |
| Backup & DR | Backup harian 30 hari; RPO ≤ 24 jam; RTO target 4 jam; dataset parquet disimpan | C1-C3, D8 | `scripts/fund2_backup.sh`, `DR_v2.2.md` |
| Otoritas halt | Hanya owner yang mengaktifkan/melepas halt; agent tidak berhak | D11 | `auth.py` (role admin + 2FA), `kill_switch.py` |
| Flatten | `STOP_AND_FLATTEN` hanya manual oleh owner dengan konfirmasi eksplisit; auto hanya STOP_NEW_ORDERS/GLOBAL_HALT | D6 | `kill_switch.py`, `routes.py` |
| Orphan position | Adopsi + monitoring + alert; SL darurat hanya bila owner setuju jaraknya | D5 | `bridge.py` (`_emergency_sl_distance`) |
| Live LLM | LLM boleh memutuskan order, tetapi setiap order melewati risk gate yang sama; kill-switch menghentikannya | G1 | `llm_agent_loop.py`, `llm_risk.py`, `routes.py` |
| Modal live | **D1 DEFER**: modal live dan batas kerugian absolut belum diisi owner; live trading tetap OFF | D1, F2 | Gerbang terpisah (`PRASYARAT_LIVE_v2.2.md`) |
| Alert | Telegram kanal primer + email cadangan; kontak darurat owner | D12 | `alerts.py`, `INCIDENT_PLAYBOOK_v2.2.md` |
| Kanal perubahan parameter | Hanya lewat UI dengan konfirmasi password + audit; bukan `psql` | PRD §14 | `settings_audit`, `risk_config_routes.py` |

## 2. Cara kebijakan ditegakkan

1. **Deterministik di kode.** Risk gate adalah fungsi murni; keputusan dan input tercatat di
   `risk_decisions`, sehingga setiap penolakan bisa direproduksi.
2. **Parameter di DB, bukan konstanta.** Nilai dibaca dari `settings`/`portfolio_risk`/`symbol_specs`
   sehingga bisa diubah owner tanpa deploy, tetapi setiap perubahan diaudit (`settings_audit`).
3. **Halt persisten.** Auto-halt menulis state; restart tidak menghapus halt. Pelepasan butuh owner +
   2FA + checklist recovery.
4. **Audit append-only.** `kill_switch_events`, `order_events`, `strategy_approvals`,
   `llm_introspections` dilindungi trigger `fund2_deny_mutation()`.
5. **Gerbang rilis membandingkan kebijakan dengan runtime.** `scripts/validate_release_packet.py`
   memeriksa kecocokan angka; gate `guardrails` harus PASS sebelum canary.

## 3. Status implementasi (diukur 26 Nov 2026, read-only)

Rincian angka per guardrail ada di `PRASYARAT_LIVE_v2.2.md` §3 (sumber kebenaran untuk perbandingan
disetujui vs runtime). Ringkasannya:

| Status | Guardrail | Keterangan |
| --- | --- | --- |
| SESUAI | G-07 eksposur total, G-08 risiko per trade, G-09 spread filter, G-13 margin | angka runtime = angka disetujui |
| **DRIFT** | G-01 `max_volume`, G-02 `max_orders_per_min`, G-03 DD harian, G-04 DD total, G-05 FAILED beruntun | nilai runtime lebih longgar dari kebijakan (jejak pengujian), **wajib ditutup sebelum canary** |
| INKONSISTEN | G-06 `ea_offline_seconds` | 60 s vs A12 6 s; butuh angka final owner |
| TERVERIFIKASI 26 Nov | G-12 tick basi | Gate membaca `settings.max_tick_age_s` default **3,0 s** (`risk.py` baris 256-260); key tidak ada di DB sehingga default berlaku = sesuai A10 |
| BELUM TERPETAKAN | G-11 jarak SL A2 | Belum satu key settings; tersebar di `symbol_specs` per simbol |
| **BELUM (keputusan)** | G-01..G-06 angka final | Menunggu kartu `t_d3ab9839` + keputusan owner tertulis |

Konsekuensi jujur: selama tabel di atas masih memuat DRIFT/INKONSISTEN/BELUM, syarat A-07 di
`PRASYARAT_LIVE_v2.2.md` belum terpenuhi dan keputusan rilis live tetap **NO-GO**. Tidak ada
pengecualian lisan.

## 4. Larangan yang berlaku sekarang

- Tidak mengubah `settings` risiko agar lebih longgar, dan tidak mematikan auto-trigger.
- Tidak mengaktifkan `FUND2_ENV=live`, tidak menyalakan auto-trading di akun live, tidak menjalankan
  canary "modal kecil dulu" tanpa D1 dan approval tertulis.
- Tidak menghapus/mengedit baris `kill_switch_events`, `order_events`, atau log insiden.
- Tidak memberi agent LLM wewenang kontrol (halt, approval, perubahan parameter).

## 5. Perubahan kebijakan

1. Owner menyatakan keputusan (chat kantor atau formulir UAT), menyebut ID parameter.
2. Perubahan dicatat di `KEPUTUSAN_OWNER.md` (bagian baru, bertanggal) **dan** diterapkan lewat UI
   dengan konfirmasi password sehingga muncul di `settings_audit`.
3. Verifikasi ulang dengan query read-only, hasil dicatat di tiket; `PRASYARAT_LIVE_v2.2.md` §3
   diperbarui pada baris terkait.
4. Dokumen operasional (`ROLLBACK_PLAN_v2.2.md` §1, `RELEASE_CHECKLIST_v2.2.md`) diselaraskan agar
   tidak ada tiga sumber angka.

## 6. Tanda tangan

| Peran | Nama | Tanggal | Cakupan | Status |
| --- | --- | --- | --- | --- |
| Owner | owner | 2026-11-21 | Baseline A1-A12, B1-B4, C1-C3, D2-D16 ("SETUJU SEMUA") | **DISETUJUI** |
| Owner | owner | 2026-11-22 | Multipair (F1), live tetap OFF (F2), full LLM trading dengan pengaman (G1) | **DISETUJUI** |
| Owner | owner | 2026-11-23 | H1: buka gate P2 dengan pengecualian tertulis; kartu live tetap ditahan | **DISETUJUI** |
| Owner | owner | - | Angka final G-01..G-06, G-12 (drift) | **BELUM** |
| Owner | owner | - | Persetujuan risiko residual D14 (`THREAT_MODEL_v2.2.md` §7) | **BELUM** |
| Owner | owner | - | D1 modal live + batas kerugian absolut | **BELUM (DEFER)** |
| Owner | owner | - | Approval rilis/live tertulis (`OWNER_RELEASE_APPROVAL_v2.2.md`) | **BELUM** |

Risk policy baseline **sudah** ditandatangani; yang belum adalah amendemen angka dan persetujuan
risiko residual. Keduanya prasyarat rilis, bukan formalitas: tanpa itu, `RELEASE_NOTES_v2.2.md`
menyatakan status NO-GO.
