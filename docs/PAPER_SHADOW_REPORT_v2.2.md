# Laporan Paper & Shadow Trading: Fund2 v2.2

Kartu: **t_f2v22a18** · Artefak wajib Lampiran B ("paper/shadow report") · Penyusun: hf-ceo
Tanggal: 26 Nov 2026 · Status: **BELUM LULUS** (paper: data belum cukup; shadow: sinyal tidak cukup)

Dokumen ini mengukur ulang sendiri, tidak mengutip laporan lama tanpa verifikasi. Semua angka berasal
dari DB `fund2` (read-only) dan eksekusi skrip gerbang pada 26 Nov 2026 01:3x-01:4x WIB.

## 1. Apa yang berjalan

| Runner | Mulai | Balance awal | Balance sekarang | Hari teramati |
| --- | --- | --- | --- | --- |
| `runner` (XAUUSD, London breakout) | 21 Nov 2026 11:59 UTC | 10.000 | 10.000 | 22-25 Nov |
| `runner_mean_reversion` (XAUUSD) | 22 Nov 2026 14:14 UTC | 10.000 | 10.000 | 22-25 Nov |
| `runner_btc_range_breakout` (BTCUSD) | 23 Nov 2026 04:31 UTC | 10.000 | 9.952,97 | 23-25 Nov |
| `shadow_lb-base` / `mr-base` / `btc-base` | 23 Nov 2026 17:54 UTC | 10.000 sim | 10.000 / 10.000 / 9.955,21 sim | 3 label |

Sumber: `paper_state` (8 baris), `shadow_runs` (52 baris), `paper_orders` (27 baris).

## 2. Gerbang paper (PRD §8.4 / B2 / P9)

Perintah (dijalankan 26 Nov 2026, strategi `llm`, sumber `orders`):

```bash
cd ~/fund2 && api/.venv/bin/python scripts/eval_gate_paper.py --strategy llm --out /tmp/a18_gate_llm
```

Hasil: **DATA_BELUM_CUKUP**

| Kriteria | Ambang | Hasil | Status |
| --- | --- | --- | --- |
| Hari kerja | ≥ 20 | 3 | GAGAL |
| Trade closed | ≥ 100 | 30 | GAGAL |
| Profit factor setelah biaya | ≥ 1,3 | **1,091** | GAGAL |
| Max drawdown | ≤ 5% | 2,45% | LULUS |

Rincian: net profit +32,08 USD dari 10.000 (ekuitas 10.032,08), winrate 0,30, max DD 245,17 USD.
Per sesi (UTC): asia 11 trade PF 0,55; london 6 trade PF 0; london_newyork 2 trade PF ∞ (net +145,70);
newyork 11 trade PF 2,94. Keputusan agent: total 111 (valid 31, hold 37, invalid 43).
Sumber profit: 22 dilaporkan broker, 8 dihitung ulang dari harga (bug EA lama `profit=0`), 0 unknown.

Bukti: `docs/EVIDENCE_paper_gate_llm_20261126T0140.json` / `.md`.

### Catatan perbandingan (jangan tertukar)

- `docs/QA_F2LLM4_eval_run355.*` (25 Nov 17:38): 26 trade, PF **0,324**, DD 2,45%, 2 hari.
- Ukur ulang 26 Nov: 30 trade, PF **1,091**, 3 hari. Selisih wajar karena empat trade baru masuk dan
  ekuitas bergerak; **arah kesimpulan sama: belum lulus**.
- Angka "PF 1,211" yang beredar di dokumen lama berasal dari periode/definisi berbeda; jangan dipakai
  sebagai bukti lulus. Sumber kebenaran = keluaran skrip terbaru dengan tanggal.

## 3. Gerbang shadow (PRD §9.3)

```bash
cd ~/fund2 && api/.venv/bin/python scripts/eval_gate_shadow.py --label lb-base  --out /tmp/a18_shadow_lb-base
cd ~/fund2 && api/.venv/bin/python scripts/eval_gate_shadow.py --label mr-base  --out /tmp/a18_shadow_mr-base
cd ~/fund2 && api/.venv/bin/python scripts/eval_gate_shadow.py --label btc-base --out /tmp/a18_shadow_btc-base
```

| Label | Run aktif | Sinyal | Verdict |
| --- | --- | --- | --- |
| `lb-base` (london_breakout v1.0.0, XAUUSD M5) | `e0e8f9f3…` | 0 (min 10) | **INSUFFICIENT** |
| `mr-base` (mean_reversion v1.0.0, XAUUSD M5) | `edd28cc2…` | 0 | **INSUFFICIENT** |
| `btc-base` (btc_range_breakout v1.0.0, BTCUSD H1) | `bfc8ab71…` | 0 | **INSUFFICIENT** |

Fakta penting: dari 52 `shadow_runs`, hanya **2 sinyal** tercatat (`shadow_signals`: 1 `lb-base`,
1 `btc-base`). Skrip gerbang memilih run **terbaru per label**, yang berstatus `RUNNING` dengan 0 sinyal.
Artinya pipeline shadow saat ini tidak menghasilkan bukti yang bisa dinilai.

Bukti: `docs/EVIDENCE_shadow_gate_*_20261126T0140.{json,md}`.

### Perbaikan alat yang dilakukan

`scripts/eval_gate_shadow.py` sebelumnya **crash** (`KeyError: 'metrics'`) ketika sinyal < minimum,
sehingga gate shadow tidak bisa dievaluasi sama sekali. Diperbaiki pada 26 Nov 2026: jalur
`INSUFFICIENT` kini mengeluarkan laporan lengkap dengan verdict jelas dan exit code 3. Perubahan
minimal, tanpa mengubah kriteria.

## 4. Paritas & provenance (bahan pendukung)

| Aspek | Hasil | Bukti |
| --- | --- | --- |
| Paritas backtest vs paper (P2) | tercatat; lihat dokumen | `docs/QA_P2_paritas.md` |
| Paritas v1 vs v2 | gerbang 1 diputuskan owner sebagai BLOCKED (bukan gagal teknis) | `docs/QA_P5_cutover.md` §1 |
| Provenance backtest | `backtest_runs` 1.432 baris, `data_versions` tersedia | `DATA_DICTIONARY_v2.2.md` |
| Registry paper | **0 baris** `paper_runs`; 27/27 `paper_orders.run_id` NULL | temuan D-5 `TEST_PLAN_v2.2.md` §8 |

Ketidaklengkapan registry paper adalah kekurangan audit yang nyata: hasil paper tidak bisa ditelusuri
ke konfigurasi/provenance run-nya. Ini harus diperbaiki sebelum angka paper dipakai sebagai dasar
keputusan live.

## 5. Kesimpulan dan syarat naik

**Kesimpulan: paper dan shadow BELUM memenuhi gerbang. Live tetap OFF.**

Syarat minimum agar gerbang paper bisa dinilai:
1. Runner LLM berjalan tanpa henti sampai ≥ 20 hari kerja dan ≥ 100 trade closed (proyeksi: 20 hari
   kerja ≈ 4 minggu kalender dari 21 Nov 2026).
2. PF setelah biaya ≥ 1,3 dan DD ≤ 5% pada periode penuh (bukan cherry-pick rentang).
3. `paper_runs` + `paper_orders.run_id` terisi sehingga setiap trade punya provenance.
4. Shadow runner menghasilkan ≥ 10 sinyal per label dengan biaya simulasi, atau label yang tidak
   produktif dipensiunkan secara eksplisit.

Yang tidak boleh dilakukan: menurunkan ambang gerbang, memilih rentang tanggal yang menguntungkan,
atau memakai angka dari periode berbeda untuk menyatakan lulus.

| Peran | Nama | Tanggal | Catatan |
| --- | --- | --- | --- |
| Penyusun (ukur ulang independen) | hf-ceo | 26 Nov 2026 | Skrip gerbang + DB read-only |
| QA | hf-qa | menunggu | verifikasi angka |
| Keputusan lanjut paper/live | Owner | menunggu | bergantung §5 |
