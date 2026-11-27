# QA t_f2llm4 — Kriteria Gerbang Paper Agent LLM (FUND2-LLM)

| | |
| --- | --- |
| Kartu | t_f2llm4 (assignee hf-qa) |
| Referensi | KEPUTUSAN_OWNER.md B2 + G1; PRD v2.2 §8.4 (gerbang strategi) dan §5.3 P3; kartu t_f2llm1 (agent loop), t_f2llm2 (risk gate & circuit breaker), t_f2llm3 (injection guard) |
| Status | **KRITERIA DIDEKLARASI SEBELUM EKSEKUSI — eksekusi menunggu t_f2llm1 + t_f2llm2** |

## Kriteria lulus (dideklarasikan sebelum dijalankan)

Gerbang sama dengan strategi mana pun (B2/G1: "paper 20 hari kerja / 100 trade,
LLM harus lulus gerbang yang sama"). Semua angka dihitung dari `paper_orders`
(medium paper runner) oleh `scripts/eval_gate_paper.py`; laporan owner-readable
dihasilkan otomatis (`.md` + `.json`).

| ID | Kriteria | Ambang | Definisi operasional |
| --- | --- | --- | --- |
| K1 | Durasi paper | >= 20 hari kerja | Hari Senin–Jumat (UTC) dengan >= 1 keputusan agent tercatat (trade atau hold). Hari kerja dihitung dari gabungan tanggal `closed_at` trade dan tanggal keputusan di audit. |
| K2 | Volume trade | >= 100 trade | Round-trip closed (status `CLOSED`/`FILLED_THEN_CLOSED`, profit tidak NULL), gabungan XAUUSD + BTCUSD. |
| K3 | Profit factor | >= 1.3 setelah biaya | Gross profit / |gross loss| dari profit paper yang sudah net spread+slippage pada fill, dikurangi komisi 7.0 USD/lot round-turn (kalibrasi P2, `LAPORAN_DOD_P2.md`). Jika runner paper mulai membebankan komisi, set `--commission-per-lot 0`. |
| K4 | Max drawdown | <= 5% | Kurva ekuitas dari ekuitas awal + kumulatif profit closed trade (urut `closed_at`); DD = penurunan terbesar dari peak, persen terhadap peak. |
| K5 | Distribusi per sesi | Dilaporkan (informatif) | Sesi `app.ingest.session_of` UTC: asia 21–07, london 07–12, london_newyork 12–16, newyork 16–21. Trades, net, winrate, PF per sesi, per simbol. Owner + QA menilai sampel & distribusi (PRD §8.4: bukan bukti statistik otomatis). |
| K6 | Rasio keputusan valid vs hold | Dilaporkan (informatif) | Dari audit keputusan agent (JSONL: `{"ts","decision":"order|close|hold|invalid","symbol","confidence","reason"}`): valid = keluaran lolos validasi skema OrderIntent; hold = keputusan eksplisit tidak entry; invalid = output gagal skema (harusnya HOLD + log, t_f2llm3 B3/B5). Jika audit belum tersedia, dilaporkan N/A — tidak pernah dipalsukan. |

## Keputusan

- **LULUS (K1–K4 semua pass)**: rekomendasi lanjut ke owner. Live trading tetap
  butuh D1 + approval terpisah owner (G1 butir 4).
- **TIDAK LULUS**: agent dihentikan; laporan pembelajaran ditulis — itu hasil
  sah (PRD §5.3 P3).
- Laporan mingguan selama run (kartu tugas 3): rekap keputusan-keputusan penting
  + reasoning + metrik berjalan (K1–K6), dikirim ke owner via Telegram + UI
  (pola rekap harian fund2-alerts), tiap akhir pekan selama 20 hari kerja.

## Blokir saat ini (23 Nov 2026)

Agent LLM belum dibangun: `t_f2llm1` (agent loop) dan `t_f2llm2` (risk gate &
circuit breaker LLM) masih `ready` di hf-backend — belum ada service agent,
belum ada config LLM di `api/.env`. Kartu ini diblok dependency pada kedua
kartu tersebut dan otomatis lanjut ketika keduanya selesai. Rasio keputusan
(K6) akan dihubungkan ke format audit yang ditetapkan t_f2llm1 (order_events
dengan reasoning + confidence + model + prompt version, G1 butir 3).

## Harness

- `scripts/eval_gate_paper.py` — unit test: `api/tests/test_eval_gate_paper.py`
  (18 passed, 23 Nov 2026).
- Smoke run terhadap DB paper live: `api/.venv/bin/python scripts/eval_gate_paper.py
  --strategy <id>` dari root repo; exit code 0 lulus / 2 gagal / 3 data belum cukup.

## Addendum 25 Nov 2026 — kebijakan perubahan material di tengah run (dideklarasikan sebelum window baru dimulai)

Insiden 25 Nov (order STUCK → breaker pause agent 03:43 WIB) memicu perbaikan
berturut-turut: auto-reconciler STUCK (t_06b189fd, approved), recompute profit
close di bridge (t_6c30e62b, commit 20e6e80), dan RISK-A lot sizing deterministik
0.5% equity (t_8bf257a2, berjalan; feature flag default OFF, owner yang aktifkan).

Kebijakan (QA, t_f2llm4):

1. **RISK-A flag ON selama run = window gerbang di-RESTART.** Lot berubah dari
   usulan LLM menjadi hitungan deterministik — sistem yang dievaluasi berubah,
   atribusi K1–K6 tercampur bila dilanjutkan. Data 24–25 Nov (2 hari kerja,
   24 trade, PF 0.41) diperlakukan sebagai data kalibrasi, tidak dihitung.
2. **Flag tetap OFF = window 24–25 Nov dilanjutkan.** Jam pause breaker tidak
   dihitung hari kerja (tidak ada keputusan tercatat).
3. Window resmi (baru/lama) hanya berjalan setelah agent di-resume owner
   (admin+2FA). Ambang K1–K6 tidak berubah sama sekali.
4. Cron evaluasi akhir 24 Des 09:00 WIB sah bila window resmi mulai paling
   lambat 26 Nov 2026 (hari kerja ke-20 = 23 Des). Bila lebih lambat, kartu ini
   yang menjadwalkan ulang cron evaluasi akhir.
