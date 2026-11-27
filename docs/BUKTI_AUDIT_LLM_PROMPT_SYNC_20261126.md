# Audit Sinkronisasi Keluaran LLM Multi-Agent vs System Prompt

Tanggal: 26 Nov 2026 (WIB) · Auditor: direktur · Scope: `app/llm_agent_loop.py`,
`app/llm_specialists.py`, `app/llm_budget.py`, tabel `settings`, `order_events`.

## Pertanyaan

Owner menanyakan mengapa keluaran LLM multi-agent tidak sinkron dengan system prompt.

## Temuan utama

Keluaran model **memang** mengikuti system prompt. Yang rusak adalah **pipa eksekusinya**:

- `app/llm_agent_loop.py` memanggil `_run_parallel_pipeline(..., budget=budget)`, tetapi
  fungsi itu tidak memiliki parameter `budget` dan meneruskannya ke `synthesize()` yang
  juga tidak menerimanya → setiap siklus paralel mati dengan `NameError` sebelum sempat
  submit ke `/llm-agent/decisions`.
- Gejala di jurnal: `simbol X gagal: NameError`. Karena mati sebelum submit, tidak ada
  keputusan yang tercatat dan terlihat seperti "output tidak sinkron".
- Pemicu: `llm_models.parallel = true` di tabel `settings`.

## Perbaikan

- Commit `95b6267`: `budget` dijadikan parameter eksplisit `_run_parallel_pipeline`,
  diteruskan ke `run_specialists()` + `synthesize()`; plus tes regresi
  `tests/test_llm_parallel_budget.py` dan skrip audit `scripts/audit_prompt_sync.py`
  (read-only: tanpa tulis DB, tanpa order, tanpa ubah settings).
- Commit `0279d68`: stub tes disamakan dengan signature terbaru `_chat(extra=...)` /
  `run_specialists(deadline=...)` agar tidak false-negative.
- Unit `fund2-llm-agent` di-restart setelah fix.

## Bukti hidup pasca-fix (40 menit terakhir)

- **21 siklus, 16 keputusan `AGENT_HOLD` tercatat di `order_events`, 0 `NameError` /
  0 `gagal` di jurnal.**
- Siklus `oneshot656296` (08:25 WIB): `kind=hold`, `confidence=0.3`, `model=lucif`,
  `prompt_version=2.0.0`, `latency=11.0 s`, prompt 33.158 token (26.368 cache hit),
  completion 856 token.
- Reasoning keputusan menyebut keempat peran dengan angka nyata (harga, support/resistance,
  F&G 11, US10Y 4.85%, DXY gagal) dan menurunkan `confidence` saat arah antar-timeframe
  konflik — perilaku yang sama diperintahkan oleh `SYNTH_PROMPT`.
- `pytest -k "llm or prompt or agent"`: **275 passed**.

## Sisa kerja (di luar kartu ini)

- `t_e086d30a` (Layer 0 facts wiring, commit `8d87f36`, masih running): synthesizer kadang
  menyebut "tidak ada evidence missing" padahal feed DXY gagal; penanda `missing` dari
  `llm_facts` perlu benar-benar dipakai di prompt synthesizer.
- Latensi: koleksi evidence ±107 s lebih dominan daripada specialist (4-12 s); kandidat
  cache evidence antar siklus.
