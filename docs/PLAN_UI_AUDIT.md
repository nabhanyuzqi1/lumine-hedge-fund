# GAP ANALYSIS: UI Fund v2 vs Backend/PRD §21 (24 Nov 2026)

## KONTEKS
Backend v2.2 sudah 100+ kartu done: auth/2FA/RBAC, audit ledger, risk portfolio,
regime detection, degradation, shadow, versioning/rollback, research intelligence,
metrics SEV-1..4, data quality, kill-switch, reconciler, LLM agent + guard.
UI HANYA 5 halaman (1.308 baris): Login, Dashboard, Riwayat, StrategyLab, Ops.

## GAP per PRD §21

### 21.2 Dashboard (PRIORITAS TERTINGGI)
ADA: price chart, order form, positions table, kill-switch, system metrics,
sesi pasar, spread (sebagian).
HILANG:
- Regime saat ini + confidence (backend ada, UI tidak tampil)
- Total open risk + margin (backend /risk/portfolio ada, UI tidak panggil)
- Daily/overall drawdown (metrics.py ada, UI tidak tampil)
- Latency p50/p95/p99 (metrics ada, UI tidak tampil)
- Alert aktif / SEV badge (metrics/alerting ada, UI tidak tampil)
- Strategi + versi aktif (UI tidak tampil versi)
- Indikator stale/timestamp umur data (PRD wajib, UI belum)

### 21.3 Riwayat / Event Ledger
ADA: timeline event per order, slippage, latency (History.jsx).
HILANG:
- Filter strategi, status, symbol, reason code
- Requested vs filled price berdampingan
- Risk decision + alasan reject di baris
- Export CSV dengan audit trail

### 21.4 Strategy Lab
ADA: daftar strategi + lifecycle, detail backtest, equity sparkline.
HILANG:
- Version diff antar versi (backend /strategies/{id}/versions ada)
- Walk-forward report view (wf_final.md/json backend ada)
- Shadow performance (backend shadow ada)
- Paper performance + gerbang paper
- Regime suitability per strategi
- Degradation status + re-enable (backend degradation ada)
- Approval history
- Rollback UI (backend rollback ada)

### 21.5 Operations & Recovery
ADA: health, metrics, audit (50 baris), kill-switch, usulan self-improve.
HILANG:
- Backup age + restore drill result (metrics ada DRILL_ROOT)
- Reconciliation status + orphan/stuck orders view
- Runbook shortcut

### 21.6 UX safety
ADA: konfirmasi dua langkah + 2FA di StrategyLab & Ops.
HILANG:
- Mobile monitoring view (PRD wajib: mobile bisa monitor + stop entry)
- Konsekuensi teks eksplisit per aksi berisiko

## RENCANA KARTU (untuk CEO pecah & assign)

1. [UI-D1] Dashboard: regime+confidence, open risk+margin, drawdown,
   latency p50/95/99, alert SEV, versi strategi, indikator stale
   -> assignee: hf-frontend, prioritas 1
2. [UI-D2] Riwayat: filter lengkap + requested vs filled + risk reason
   + export CSV -> assignee: hf-frontend, prioritas 1
3. [UI-D3] Strategy Lab: versions+diff, walk-forward report, shadow/paper
   perf, degradation, approval history, rollback -> assignee: hf-frontend
   + hf-backend support, prioritas 1
4. [UI-D4] Ops: backup/restore drill, reconciliasi+orphan, runbook link
   -> assignee: hf-frontend, prioritas 2
5. [UI-D5] UX safety: mobile view + teks konsekuensi -> assignee: hf-uiux,
   prioritas 2
6. [UI-D6] QA E2E alur UI: login->monitor->order->kill switch->audit
   -> assignee: hf-qa, prioritas 2 (setelah D1-D3)

## URUTAN
D1+D2 paralel (beda file) -> D3 (paling berat, butuh backend support) ->
D4+D5 paralel -> D6 QA. Estimasi total: 4-6 hari kerja worker.
