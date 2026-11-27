# Bukti `t_1b2d66ab` — event loop `fund2-alerts` beku: `read_ticks` sinkron → `PoolTimeout` palsu → auto-halt

Kartu: `t_1b2d66ab` (turunan `t_925637a0`) · Assignee: hf-backend · 26 Nov 2026
Sifat: perubahan kode + verifikasi live. **Kebijakan kill-switch tidak diubah, halt tidak dilepas** (wewenang owner).

---

## 1. Ringkasan

1. Tiga cacat pada jalur `read_ticks` sudah ditutup, satu cacat tambahan (SIGUSR1) ditemukan saat verifikasi dan diperbaiki:
   - **event loop tidak lagi beku**: semua pemanggil async memakai `asyncio.to_thread` (`feed.read_ticks_async`, `alerts._paper_market_open_async`, `runner_service_status`);
   - **baca ekor, bukan seluruh file**: start dingin memindai mundur per 512 KB dari EOF lalu hanya memparse window yang diminta. Di data produksi nyata: `read_ticks(16, XAUUSD)` **2 770 ms → 87 ms** (32×), panggilan hangat 0,5 ms, hasil 315 tick identik dengan parse penuh;
   - **`PoolTimeout` bukan lagi "DB mati"**: sudah ada sejak `42c6167` (`DbUnavailTracker` + probe langsung); diverifikasi ulang di kartu ini dengan test pool `min_size=1`.
   - **`SIGUSR1` dump tidak pernah bekerja** (`add_signal_handler` memanggil callback tanpa argumen, handler mewajibkan `(signum, frame)` → `TypeError`). Artinya dump yang dipakai mendiagnosa freeze selama ini hanya berasal dari watchdog, bukan SIGUSR1. Sekarang benar untuk kedua gaya pemanggilan.
2. Test baru: **8 gagal pada kode lama, semuanya lulus pada kode baru** (bukti di §3). DoD pool-timeout deterministik: 5× `PoolTimeout: couldn't get a connection after 1.00 sec` sebelum fix, 0 sesudahnya.
3. Live: `fund2-alerts` restart dengan kode baru, diamati 15 menit: `NRestarts` tidak bertambah, tidak ada `STALE`, tidak ada `SEV-2 db_unavailable`, SIGUSR1 dump bersih dari frame `read_ticks`, dan tidak ada event kill-switch baru.

---

## 2. Perubahan kode

| File | Isi |
| --- | --- |
| `api/paper/feed.py` | `_tail_start_for()` + `_first_line_offset_at_or_after()` + `_iter_block_lines()`: start dingin memindai ekor per blok 512 KB dan mengembalikan offset baris pertama dengan `ts_utc >= cutoff`. `_read_incremental(path, cutoff, keep_after)` menyimpan `from_ts` (tick tertua yang dijamin ada) sehingga panggilan dengan window lebih lebar memicu pemindaian ulang, bukan mengembalikan data terpotong diam-diam. `_TICK_LOCK` (cache dipakai dari thread worker), hasil dikembalikan sebagai salinan list. Baru: `read_ticks_async()` = `asyncio.to_thread(read_ticks, …)`. |
| `api/app/alerts.py` | `_paper_market_open_async()` (to_thread atas `paper_market_open`, nama dibaca runtime sehingga monkeypatch test tetap berlaku). `paper_check_once` + `candle_check_once` memakainya; `runner_service_status()` (subprocess, timeout 5 s) juga di-offload. `_dump_stacks(signum=None, frame=None)`. |
| `api/paper/runner.py` | `tick_once`: `await feed.read_ticks_async(...)`. |
| `api/shadow/loop.py` | `tick_once`: idem. |
| `api/shadow/replay.py` | `replay_window`: idem. |
| `api/tests/test_feed_tail.py` (baru) | 9 test: biaya konstan (110 MB <1 s, hitungan baris diparse <20 000 dari ~700 ribu), hasil identik file besar vs kecil, log kemarin yang seluruhnya tua dilewati murah, window melebar, filter simbol + rotasi tanggal, baris setengah jadi, file dipotong, salinan cache, direktori/log kosong. |
| `api/tests/test_alerts_loop_offload.py` (baru) | 5 test: `paper_check_once`/`candle_check_once` tidak membekukan loop (ticker iterasi), `read_ticks_async` offload, pool `min_size=1,max_size=1` + 5 waiter tanpa `PoolTimeout`, SIGUSR1 dump untuk kedua gaya pemanggilan. |

Yang **tidak** disentuh: kebijakan/threshold kill-switch, migrasi & kode RISK-D (`m013_risk_config_overrides.py`, `risk_config*.py`), `DbUnavailTracker` (sudah benar sejak `42c6167`), dan tidak ada event kill-switch yang diaktifkan/dilepas.

---

## 3. Bukti test (gagal sebelum, lulus sesudah)

Metode: worktree bersih `git worktree add /tmp/f2-prefix HEAD --detach` (HEAD = `2dedf64`, kode pra-fix), dua file test baru disalin ke sana, `.venv`/`.env` di-symlink (secret tidak disalin).

```
HEAD pra-fix : 8 failed, 5 passed
kode baru    : 13 passed (test_feed_tail.py 9 + test_alerts_loop_offload.py 5, satu file dijalankan dua kali)
```

| Test | Hasil pra-fix | Hasil pasca-fix |
| --- | --- | --- |
| `test_no_pool_timeout_when_market_probe_is_slow` (DoD) | **gagal**: `["PoolTimeout: couldn't get a connection after 1.00 sec" ×5]` | lulus, 15/15 akuisisi selesai, 0 error |
| `test_paper_check_once_does_not_block_event_loop` | **gagal**: `event loop beku: hanya 1 iterasi` | lulus, ≥30 iterasi selama probe 3 s |
| `test_candle_check_once_does_not_block_event_loop` | gagal (1 iterasi) | lulus |
| `test_read_ticks_async_offloads_blocking_read` | gagal (`AttributeError`/loop beku) | lulus |
| `test_sigusr1_dump_callable_with_loop_handler_signature` | gagal: `TypeError: _dump_stacks() missing 2 required positional arguments` | lulus, 2 dump tercetak |
| `test_cold_read_tail_only_constant_cost_on_100mb_file` (DoD) | gagal (baca 16 MB ekor tetap >1 s) | lulus, <1 s, <20 000 baris diparse |
| `test_cost_does_not_grow_with_file_size` | gagal (beda hitungan parse ~100 ribu baris) | lulus |
| `test_fully_old_yesterday_file_is_skipped_cheaply` | gagal | lulus |
| `test_window_expands_after_narrow_first_read` | gagal | lulus |

Pengukuran di data produksi nyata (`ticks_2026-11-25.jsonl` 100,5 MB + `ticks_2026-11-24.jsonl` 116,2 MB), cache dikosongkan tiap sampel:

| Sampel | Pra-fix | Pasca-fix |
| --- | --- | --- |
| start dingin #1, `read_ticks(16, XAUUSD)` | 2 770 ms | **87 ms** |
| start dingin #2 | 2 790 ms | **89 ms** |
| panggilan hangat | 1 ms | **0,5 ms** |
| 240 menit (window lebar, picu rescan) | (parse penuh) | 177 ms / 4 167 tick |

Kesetaraan hasil diukur terhadap parse penuh seluruh file: 16 menit tanpa filter (474 tick), 16 menit `XAUUSD` (322 tick), 120 menit `XAUUSD` (1 793 tick) — **daftar `ts_utc` identik**.

Suite terkait di tree bersama: `test_feed`, `test_feed_tail`, `test_alerts`, `test_alerts_active`, `test_alerts_resilience`, `test_alerts_loop_offload`, `test_db_unavail_gate`, `test_metrics` → **108 passed**; `test_paper_runner`, `test_shadow*`, `test_eval_gate_*`, `test_paper_broker` → **73 passed**.

---

## 4. Bukti live (`fund2-alerts`)

Restart terkontrol pada **26 Nov 2026 06:54:57 WIB** (kode baru, termasuk fix SIGUSR1). Observasi 15 menit, sampel tiap 30 detik (`06:55:15 → 07:10:17`, 30 sampel).

| Metrik | Pra-fix (siklus insiden) | Pasca-fix 15 menit |
| --- | --- | --- |
| `NRestarts` | 12, restart tiap ~5m15s (`STALE` exit 70) | **0** (semua 30 sampel, `ActiveState=active` sejak 06:54:57) |
| log `alerts daemon STALE` | 34 kejadian hari ini | **0** |
| log `SEV-2 db_unavailable` | 224/226/228 → halt | **0** |
| frame `read_ticks` di stack dump | berhenti persis di `paper/feed.py:60` | **0** |
| `ERROR/CRITICAL/Traceback` di journal | banyak | **0** |
| CPU daemon | 19,3 s / 91 menit (0,35 %) | 2,55 s / 14,5 menit (**0,29 %**) |
| Memori | 43,6 MB (peak 158,9 MB) | 21,5 MB |
| `kill_switch_events` ACTIVATE baru | 224, 226, 228 | **tidak ada**; hanya 236 `AGENT_RESUME` manual owner (07:00:07), bukan halt |
| state kill-switch | `STOP_NEW_ORDERS` aktif | `{"active": false, "mode": null}` — kondisi warisan yang sudah dirilis owner di event 231/233, tidak disentuh kartu ini |

Dump SIGUSR1 manual saat daemon berjalan (07:0x): handler berjalan, `Current thread` tercetak, **tidak ada frame `read_ticks`** (`grep -c read_ticks` = 0). Sebelum fix, `kill -USR1` menghasilkan `TypeError: _dump_stacks() missing 2 required positional arguments` dan nol dump.

Catatan: full suite paralel (1 518 passed, 18m20s) mencatat 2 kegagalan di `test_fib_levels.py` dan `test_llm_introspection.py` yang **bukan** dari perubahan ini: keduanya membaca source file yang sedang ditulis worker lain (`assert 'from .llm_introspection import ...' in '        "data": result.get("data"),\n'`). Dijalankan ulang sendirian pada tree yang sama: `48 passed`.

---

## 5. Catatan keputusan

1. **Item opsional #4 (heartbeat dari task terpisah) tidak dikerjakan.** Setelah `read_ticks` pindah ke thread dan biayanya turun ke <0,1 s, tidak ada iterasi watcher yang bisa melewati batas watchdog 300 s. Heartbeat global dari task terpisah justru akan **melemahkan** watchdog: daemon yang event loop-nya hidup tapi salah satu watcher-nya benar-benar macet tidak akan pernah di-restart lagi. Watchdog tetap berbasis thread (tidak ikut beku) dan tetap per-watcher.
2. **Bug SIGUSR1 diperbaiki di kartu ini** karena DoD meminta bukti dari dump SIGUSR1; sebelum fix, SIGUSR1 tidak pernah menghasilkan dump sama sekali (`TypeError` di log). Dump yang terlihat pada insiden 26 Nov berasal dari loader watchdog (jalur exit 70), bukan SIGUSR1.
3. **Tidak ada perubahan kebijakan.** Halt dan pelepasan tetap wewenang owner; `DbUnavailTracker` (ambang 2× berturut-turut / probe gagal) tidak diubah.
