# Bukti kartu t_e086d30a — Layer 0 facts wiring (FUND2-LLM-P4b)

Tanggal: 26 Nov 2026, 08:20–09:05 WIB. Repo `~/fund2` (branch `master`).
Kartu: `[FUND2-LLM-P4b] Layer 0 facts wiring: synthesizer tidak boleh memutuskan
di atas angka null`.

## 1. Cacat yang ditutup

Siklus 26 Nov 07:12 (`cycle 46710d82b7c243f0`, `AGENT_HOLD`) memutuskan `hold`
dengan alasan "equity, drawdown, guardrail null" dan "harga/spread/ATR null".
Akar masalahnya: `llm_specialists._slice()`/`_snapshot()` membaca kunci yang
tidak pernah ada di konteks (`price`, `spread`, `tick`, `indicators`,
`structure`, `ctx["account"]`, `ctx["guards"]`), dan technical menerima 684
candle M5 mentah tanpa indikator terhitung.

Perbaikan = Layer 0 deterministik (`app/llm_facts.py`) + wiring specialist dan
synthesizer ke `ctx["facts"]`.

## 2. Commit

| Commit | Isi |
| --- | --- |
| `8d87f36` | `api/app/llm_facts.py` (235 baris) + `api/tests/test_llm_facts_p4.py` (13 tes). Modul ini **dirujuk `llm_agent_loop` sejak `d96b0cc` tetapi belum pernah di-commit**, sehingga checkout bersih gagal `ImportError: cannot import name 'llm_facts' from 'app'` dan seluruh tes API merah sebelum satu tes pun berjalan. |
| `65ee664` | `api/app/llm_models.py` (+13 baris): `DEFAULT_ROLE_MODELS` / `roles`. Tanpa ini `tests/test_llm_parallel_pipeline.py::test_resolve_defaults_and_override` merah di checkout bersih (`KeyError: 'roles'`) dan override model per peran tidak aktif di produksi. Isi diambil apa adanya dari working tree. |
| `bc71b64` | `api/app/llm_agent.py` (+9 baris) + `api/tests/test_llm_decision_audit.py` (2 tes). `AgentDecisionBody` tidak punya field `evidence`/`evidence_missing`, jadi Pydantic membuang data yang dikirim klien: audit `/decisions` tidak pernah membuktikan keputusan mana yang berjalan terdegradasi. |

Gate risiko tidak disentuh: `app/risk.py`, `app/portfolio_risk.py`,
`app/llm_risk.py`, `app/kill_switch.py` tidak ada di commit mana pun di atas.

## 3. Bukti test

Bersih (worktree lepas pada commit hasil, `env -u DATABASE_URL`,
`TELEGRAM_ALERTS_OFF=1`, `-p no:cacheprovider`):

```
commit 65ee664, 6 file:
  tests/test_llm_facts_p4.py  tests/test_llm_parallel_pipeline.py
  tests/test_risk.py  tests/test_llm_risk.py
  tests/test_llm_agent_v2.py  tests/test_db_unavail_gate.py
  -> 171 passed in 134,85 s

commit bc71b64, 7 file (tambah test_llm_decision_audit.py + test_llm_agent.py):
  -> 166 passed in 89,37 s
```

Fail-before (bukan sekadar hijau):

| Uji | Kode lama | Kode baru |
| --- | --- | --- |
| `pytest tests/test_llm_facts_p4.py` di `9df59b2` | collection error `ImportError: cannot import name 'llm_facts'` | hijau |
| `pytest tests/test_llm_decision_audit.py` di `65ee664` | `KeyError: 'evidence'` pada baris `order_events` | hijau |

## 4. Bukti produksi (read-only, tanpa submit order)

Siklus nyata setelah proses agent loop dijalankan ulang 08:31:43 (memuat
`llm_facts.py`):

| Waktu | Cycle | Synth | Technical | Macro/Sentiment/Portfolio | Siklus |
| --- | --- | --- | --- | --- | --- |
| 08:46:23–29 | `9f5f2d0b` | `lucif` 8.993 ms | `lucif-claude` 3.412 ms | `lucif-flash` 2.949–3.443 ms | 9.535 ms |
| 08:41:51–58 | `8292bf33` | `lucif` 9.993 ms | `lucif-claude` 3.822 ms | `lucif-flash` 3.190–4.580 ms | 10.086 ms |
| 08:36:06–15 | `b58dcd9b` | `lucif` 12.315 ms | `lucif-claude` 4.600 ms | `lucif-flash` 2.829–4.675 ms | 12.920 ms |

Kutipan `order_events.decision` specialist portfolio, cycle `9f5f2d0b`:

> `room {'XAUUSD': 'boleh_tambah', 'BTCUSD': 'boleh_tambah'}, exposure 0.0`

Sebelum perbaikan baris ini selalu `hold_saja` dengan equity/drawdown null.
Kutipan synthesizer cycle yang sama:

> "Setup short technical (entry 3556.31, SL 3568.74, TP 3546.47) hanya R:R 0.79,
> jauh di bawah syarat 1.5 ... Macro bias XAUUSD bullish (0.45) dan sentiment
> +0.35 (Extreme Fear, safe-haven) bertentangan dengan technical bearish
> M5/M15/H4 ..."

Semua angka nyata; tidak ada lagi field `null` sebagai dasar keputusan.
Keempat specialist `state=ok`, `missing=[]`, dan override model per peran
terbukti hidup (technical = `lucif-claude`, peran lain `lucif-flash`).

## 5. Sisa pekerjaan / catatan

1. **Restart service API** (`uvicorn app.main` port 3110) agar commit `bc71b64`
   aktif: sampai restart, baris `order_events` masih tidak memuat `evidence`
   (data hilang di sisi route, bukan di sisi agent). Agent loop **tidak** perlu
   di-restart untuk facts (sudah memuat `llm_facts`).
2. **Index git bersama sempat rusak**: `git status` menampilkan staging yang
   isinya persis tree commit `0279d68` (file `llm_budget.py`, `preflight.py`,
   `fail_reason.py`, `market_sessions.py`, migration `o015` tampil sebagai
   *staged deletion*). Commit biasa dari index itu akan MENGHAPUS empat modul
   produksi. Index sudah dikembalikan ke `HEAD` (`git read-tree HEAD`) setelah
   dipastikan isinya identik dengan commit lama (tidak ada staging unik yang
   hilang). Pola aman: `GIT_INDEX_FILE=<tmp> git read-tree HEAD`, jangan
   `git read-tree` pada index bersama.
