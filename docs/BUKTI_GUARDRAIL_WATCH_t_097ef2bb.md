# BUKTI — Timer harian pengawas drift guardrail (§I.4) + alert Telegram

| | |
| --- | --- |
| Kartu | `t_097ef2bb` (hf-devops), tindak lanjut §8 `BUKTI_GUARDRAIL_PARITY_t_bf4b85f9.md` |
| Tanggal | 26 Nov 2026 |
| Lingkup | unit timer/service systemd user, skrip gate guardrail, alert Telegram, log JSON harian |
| Sifat | **read-only** terhadap `settings`: skrip tidak menulis dan tidak memperbaiki nilai |
| Status | unit `active`, drill di DB test PASS, eksekusi live menulis log + mengirim alert |

## 1. Artefak

| Path | Isi |
| --- | --- |
| `scripts/check_guardrail_runtime.py` | pengawas: panggil `check_db()` dari `scripts/validate_release_packet.py` (koneksi `read_only = True`), tulis log JSON, kirim satu alert saat `guardrail_drift`/`guardrail_open` tidak kosong, exit code 0 (bersih) / 2 (drift/open) / 1 (gate gagal) |
| `deploy/fund2-guardrail-watch.service` | oneshot, `WorkingDirectory=/home/tekka/fund2`, `SuccessExitStatus=2` (rc=2 = hasil sah: alert + log sudah dikirim), `TimeoutStartSec=300` |
| `deploy/fund2-guardrail-watch.timer` | `OnCalendar=*-*-* 05:10:00 UTC` (12:10 WIB), `Persistent=true`, `AccuracySec=1min`, `RandomizedDelaySec=120` |
| `api/tests/test_guardrail_watch.py` | 14 test: escape Markdown, exit code, log JSON, override DB, regresi "tidak ada jalur tulis" |
| `~/fund2-backups/logs/guardrail-<YYYY-MM-DD>.json` | log harian (tren) |

Gate **tidak diduplikasi**: skrip mengimpor `check_db()` yang sama dengan
`validate_release_packet.py`, sehingga angka §I dan logika A6 absolut
(`ceiling = 3% x daily_start_balance`) hanya punya satu sumber.

## 2. Hasil pengujian

### 2.1 Unit test

```
cd ~/fund2/api && env -u DATABASE_URL TELEGRAM_ALERTS_OFF=1 \
  .venv/bin/python -m pytest tests/test_guardrail_watch.py -q
14 passed, 1 warning in 6.08s
```

Termasuk validator entity Markdown legacy Telegram (`md_entities_balanced`
dari `tests/test_alerts_resilience.py`) dan pengecekan tidak ada `_` telanjang
di luar backtick (pelajaran 23 Nov 2026).

### 2.2 Drill drift di DB TEST (bukan DB live)

Database `fund2_test_guardraildrill` (cluster :5433, nama berprefix
`fund2_test_` sesuai konvensi isolasi conftest) diisi 11 nilai longgar sisa
harness uji beban, lalu skrip dijalankan dengan `--label DRILL`:

```
--- run label='DRILL' alert=True rc=2
2026-11-26T00:32:24Z guardrail_watch status=DRIFT rc=2 drift=11 open=2 alert_sent=True
🚨 DRILL - GUARDRAIL DRIFT (runtime tidak sama dengan §I)
Sumber kebenaran: KEPUTUSAN\_OWNER.md §I.1 (angka final) + §I.4 (paritas dev/staging)
Cek: 2026-11-26T00:32:24Z | DB: fund2\_test\_guardraildrill@127.0.0.1:5433
Nilai menyimpang (11): 1. max\_volume: aktif 1, §I 0.1 (A3) ... (11 baris)
Perlu ditinjau (open, bukan pelonggaran) (2): ...
--- run label=None alert=False rc=0
2026-11-26T00:33:00Z guardrail_watch status=OK (sesuai §I) rc=0 drift=0 open=0

checks: {"drift_rc_nonzero": true, "drift_alert_sent": true, "drift_log_ok": true,
         "parity_rc_zero": true, "settings_audit_unchanged": true}
DRILL RESULT: PASS
```

`alert_sent=True` berarti Telegram Bot API menerima pesan dengan
`parse_mode=Markdown` (HTTP `ok=true`); pesan dengan entity rusak akan
ditolak 400 dan `notify_owner` mengembalikan `False`.

### 2.3 Eksekusi live lewat systemd

```
systemctl --user start fund2-guardrail-watch.service
Result=success  ExecMainStatus=2   (rc=2 = drift terdeteksi, dianggap hasil sah)
journal: 2026-11-26T00:33:24Z guardrail_watch status=DRIFT rc=2 drift=3 open=0
         alert_sent=True log=/home/tekka/fund2-backups/logs/guardrail-2026-11-26.json
```

Isi `~/fund2-backups/logs/guardrail-2026-11-26.json` (ringkas):

```json
{"ts": "2026-11-26T00:33:24Z", "mode": "live", "db": "fund2@127.0.0.1:5433",
 "ok": false, "exit_code": 2, "drift_count": 3, "open_count": 0,
 "guardrail_drift": [
   {"key": "ea_offline_seconds", "expected": 6.0, "actual": 60.0},
   {"key": "ea_offline_halt_seconds", "expected": 60.0, "actual": 180.0},
   {"key": "max_daily_drawdown", "expected": 292.02, "actual": 300.0}],
 "alert": {"attempted": true, "sent": true, "error": null}}
```

Timer terpasang dan aktif:

```
systemctl --user list-timers fund2-guardrail-watch.timer
Thu 2026-11-26 12:10:30 WIB  fund2-guardrail-watch.timer  fund2-guardrail-watch.service
systemctl --user is-active fund2-guardrail-watch.timer -> active
```

Catatan riwayat unit: percobaan start pertama (07:32 WIB) gagal
`status=216/GROUP` karena unit sempat memuat `User=tekka` (tidak boleh di
systemd user manager tanpa privilege). Baris itu tetap terlihat di journal
sebagai riwayat; `User=` dihapus (user unit sudah berjalan sebagai `tekka`),
lalu start berikutnya `Result=success`. Eksekusi sesudah perbaikan bersih:
`journalctl ... --since <ts> | grep -ci "error|fail" -> 0`.

### 2.4 Read-only terbukti

```
audit_before=374 audit_after=374 delta=0   (satu siklus service penuh)
journalctl --user -u fund2-guardrail-watch.service --since <ts> | grep -ci "error|fail" -> 0
```

Drill di DB test juga `settings_audit` delta 0. Skrip tidak memuat perintah
tulis apa pun (dijaga test `test_script_is_read_only`).

## 3. Temuan nyata saat pemasangan (perlu keputusan pemilik)

Eksekusi live pertama menemukan **drift sungguhan** di DB `fund2`, bukan
artefak kartu ini:

| Key | Aktif | §I.1 | Jejak |
| --- | --- | --- | --- |
| `kill_switch_triggers.ea_offline_seconds` | 60.0 | 6.0 | `settings_audit` #367, `changed_by=owner`, 26 Nov 07:00:07 WIB |
| `kill_switch_triggers.ea_offline_halt_seconds` | 180.0 | 60.0 | idem #367 |
| `max_daily_drawdown` | 300.0 | 292.02 | `settings_audit` #362, `changed_by=owner`, 26 Nov 07:00:07 WIB |

Perubahan itu terjadi 21 menit setelah paritas §I.4 (06:39) dan tidak punya
entri `§I.3`/revisi §I yang menyertainya. Sesuai batas kartu, nilai **tidak**
diubah di sini: alert Telegram sudah dikirim ke owner (3 key, nilai aktif,
nilai §I, rujukan §I). Keputusan pemilik dilacak di kartu `t_aaf88988`
(hf-ceo). Penyelesaian butuh salah satu:

1. nilai dikembalikan ke §I lewat `PUT /admin/risk-settings` +
   `PUT /kill-switch/triggers` (sesi 2FA), atau
2. §I direvisi tertulis oleh owner (kalau 60 s / 180 s / 300 USD memang
   keputusan baru), lalu dokumen turunan disinkronkan.

Sampai salah satu terjadi, timer akan mengirim alert yang sama setiap hari
05:10 UTC (anti-spam dedup 300 s tidak menahan antar-hari, memang disengaja:
drift tidak boleh jadi latar belakang).

## 4. Operasional

```bash
# manual (live)         : systemctl --user start fund2-guardrail-watch.service
# lihat hasil terakhir  : journalctl --user -u fund2-guardrail-watch.service -n 40
# tren harian           : cat ~/fund2-backups/logs/guardrail-$(date -u +%F).json
# uji tanpa kirim alert : cd ~/fund2 && api/.venv/bin/python scripts/check_guardrail_runtime.py --no-alert
# uji drift di DB test  : DATABASE_URL=$(test-db-url) api/.venv/bin/python \
#                         scripts/check_guardrail_runtime.py --label DRILL --out-dir /tmp/drill
```

`TELEGRAM_ALERTS_OFF=1` mematikan pengiriman (dipakai saat uji); jangan
diset di unit produksi.

## 5. Sisa risiko

- Alert hanya dikirim saat drift/open terdeteksi; hari bersih hanya tercatat
  di log JSON. Kalau timer/service mati, tidak ada yang menegur: pantau
  `systemctl --user list-timers` (masuk `RB-09`/peta alarm RUNBOOK).
- `max_daily_drawdown` mengikuti `daily_start_balance`; saat D1 (modal live)
  diisi, ceiling berubah dan timer akan menandai drift sampai nilai
  diperbarui lewat §I.3 (lihat §I.2 butir 1).
