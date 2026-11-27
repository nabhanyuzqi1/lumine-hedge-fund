# Bukti — [FUND2-LLM-P3] Pre-flight gate, fail_reason wajib, anggaran latensi

Kartu: `t_afd7fe4e`. Commit kode: `d96b0cc`.
Tanggal pengambilan bukti: 26 Nov 2026, 07:30-08:40 WIB.

## Ringkas

| Kriteria selesai | Status | Bukti |
| --- | --- | --- |
| 1. 30 siklus berturut tanpa panggilan LLM saat pasar tutup / EA offline | LULUS | 30/30 siklus diblok gate, 0 panggilan LLM (`scripts/verify_preflight_30cycles.py`) + 5 event `CYCLE_SKIPPED` nyata di produksi |
| 2. `orders` FAILED 24 jam: 0 baris `fail_reason` NULL | LULUS | 194 FAILED / 24 jam, 0 NULL; seluruh riwayat juga 0 NULL; constraint `orders_failed_requires_reason` aktif |
| 3. p95 latensi siklus <= 35 s | LULUS | 8 siklus nyata pasca-perbaikan: p50 15,0 s / p95 20,7 s / maks 21,7 s; produksi 08:20-08:32 WIB: 10,3-13,3 s |
| 4. Test regresi A dan B lulus di `api/tests` | LULUS | `tests/test_preflight_gate.py` 31 tes; 134 tes terkait lulus di worktree terpisah; full suite 1.595 tes lulus (7 kegagalan sisa berasal dari `tests/test_anomaly.py` versi HEAD yang belum adaptasi constraint, versi worktree lulus 35/35) |

## A. Rantai pre-flight sebelum LLM

Gate dihitung proses API (`app/preflight.py`) memakai state yang hanya ada di
sana (tick terakhir, heartbeat EA, drawdown) dan baris `market_sessions`
(migrasi `o015`), bukan jam yang ditulis di kode. Loop agent memanggil
`POST /llm-agent/preflight` sebelum konteks dikumpulkan; bila gate tidak bisa
dipastikan, siklus dilewati (fail-closed), bukan menebak.

Bukti 30 siklus (deterministik, tiga skenario blok bergiliran):

```
$ cd ~/fund2/api
$ TELEGRAM_ALERTS_OFF=1 .venv/bin/python -m scripts.verify_preflight_30cycles \
      --cycles 30 --symbol XAUUSD --out /tmp/preflight_30cycles.jsonl
...
[28/30] market_closed    gate_block=['market_closed']    loop_skip=True llm_calls=0
[29/30] ea_offline       gate_block=['ea_offline']       loop_skip=True llm_calls=0
[30/30] spread_too_wide  gate_block=['spread_too_wide']  loop_skip=True llm_calls=0
{
  "cycles_requested": 30,
  "cycles_run": 30,
  "llm_calls_total": 0,
  "all_blocked": true,
  "all_skipped": true,
  "failures": [],
  "verdict": "PASS"
}
```

Bukti produksi (event audit, bukan simulasi):

```
to_status = CYCLE_SKIPPED (5 event terakhir)
08:14:24  XAUUSD: tick_stale (market_data) - tick basi 3.5s > max_tick_age_s 3.0s
08:14:26  XAUUSD: tick_stale (market_data) - tick basi 5.5s > max_tick_age_s 3.0s
08:26:04  XAUUSD: llm_agent_paused (control) - circuit breaker 3 order LLM FAILED beruntun
08:26:06  XAUUSD: llm_agent_paused (control) - idem
08:26:08  XAUUSD: llm_agent_paused (control) - idem

AGENT_EVIDENCE / panggilan LLM pada cycle_id yang diblok: 0 baris.
```

## B. `fail_reason` wajib

`orders.fail_detail` JSONB `{code, message, stage}` + `fail_reason` TEXT untuk
UI. Semua jalur FAILED mengisi alasan (risk gate, hasil EA, reconciler), dan
CHECK constraint membuat jalur baru yang lupa mengisi gagal keras.

```
$ SELECT count(*) FROM orders WHERE status='FAILED'
       AND created_at > now() - interval '24 hours';           -> 194
$ SELECT count(*) FROM orders WHERE status='FAILED' AND fail_reason IS NULL
       AND created_at > now() - interval '24 hours';           -> 0
$ SELECT count(*) FROM orders WHERE status='FAILED' AND fail_reason IS NULL;  -> 0

constraint: CHECK (status <> 'FAILED' OR fail_reason IS NOT NULL)
contoh fail_detail hasil backfill + jalur baru:
  {"code":"risk_gate_rejected","stage":"risk_gate",
   "message":"llm_position_exists: 1 posisi llm OPEN di XAUUSD; LLM daily order limit exceeded (max 20/day)"}
```

## C. Anggaran latensi

Biang latensi bukan prefill: `max_tokens` hanya membatasi token jawaban,
token reasoning tetap dihasilkan penuh. Terbukti pada specialist technical:
`max_tokens=450` tetapi `completion_tokens` 1.496-2.351 (usage
`completion_tokens_details.reasoning_tokens`).

Perbaikan: plafon thinking per tahap (specialist tanpa thinking, synthesizer
budget 400 token), deadline tahap (specialist yang melewati anggaran dibatalkan
dan ditandai timeout, synthesizer tetap jalan), urutan prompt ramah prefix
cache (blok stabil di depan, harga/waktu di belakang), dan `max_tokens` per
tahap.

Ukur langsung (jalur produksi tanpa submit order):

```
$ TELEGRAM_ALERTS_OFF=1 .venv/bin/python -m scripts.measure_cycle_latency --runs 8
{"n": 8, "p50_s": 14.977, "p95_s": 20.703, "max_s": 21.742,
 "target_p95_s": 35.0, "within_budget": true}
```

Siklus nyata di produksi (`order_events.decision.cycle_latency_ms`):

| Waktu WIB | Latensi siklus | Completion token |
| --- | --- | --- |
| 08:01:21 | 46,9 s | 4.132 |
| 08:05:50 | 39,6 s | 3.301 |
| 08:10:26 | 38,1 s | 3.384 |
| 08:15:19 | 33,0 s | 3.490 |
| 08:20:38 | 10,3 s | 853 |
| 08:21:56 | 13,0 s | 876 |
| 08:23:27 | 10,7 s | 901 |
| 08:24:02 | 11,5 s | 878 |
| 08:25:08 | 11,6 s | 856 |
| 08:32:15 | 10,8 s | 853 |
| 08:32:30 | 13,3 s | 1.059 |
| 08:32:45 | 13,3 s | 883 |
| 08:41:58 | 10,1 s | 841 |
| 08:46:30 | 9,5 s | 850 |
| 08:52:15 | 10,1 s | 846 |
| 08:57:29 | 11,8 s | 829 |
| 09:03:19 | 15,6 s | 844 |
| 09:08:10 | 18,1 s | 1.020 |

Empat belas siklus produksi pasca-perbaikan: rentang 9,5-18,1 s, p95 18,1 s
(target 35 s). Sebelum perbaikan: 33,0-46,9 s pada 80 siklus terakhir
(rata-rata 48,8 s, maks 119,7 s menurut catatan kartu). Prompt cache: `prompt_cache_hit_tokens`
26.368 dari 33.154 token prompt (±80% hit) per siklus.

## Catatan rilis

- `HEAD` (commit 95b6267) mengimpor `app/llm_facts.py` yang saat itu belum
  di-commit; commit kartu ini tidak menambah ketergantungan baru (skrip ukur
  memakai fakta Layer 0 yang sudah dipakai `run_cycle`). File itu tetap wajib
  di-commit oleh pemilik kartu pipeline paralel sebelum rilis bersih.
- Migration `o015` sudah diterapkan di DB demo (market_sessions, fail_detail,
  backfill, constraint).
