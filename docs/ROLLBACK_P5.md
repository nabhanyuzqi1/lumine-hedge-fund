# P5 Cutover — Rollback Plan & Status (fund.lumine.biz.id v1 → v2)

Tanggal: 2026-11-25 (WIB). Kartu: [FUND2-P5] t_f2p5a2. PRD: PRD_v2.1_Fund_Core.md P5 hari 2-3.

## 1. Kondisi saat ini (terverifikasi 2026-11-25 ~03:00 WIB)

| Komponen | Status |
| --- | --- |
| `https://fund.lumine.biz.id/` | HTTP 200, title "Lumine Fund · Desk" (frontend v2) |
| `https://fund.lumine.biz.id/health` | `{"ok":true,"subscribers":2,"env":"demo"}` (API v2) |
| Caddy (container `caddy-edge`) | Blok `fund.lumine.biz.id` → `172.19.0.1:3110` |
| `fund2-edge-proxy.service` | `172.19.0.1:3110` → `127.0.0.1:3110` (active) |
| `fund2-api.service` | `127.0.0.1:3110` (active; EA menembak lokal, PRD §7) |
| Trading | OFF (demo) |

Cutover UI dilakukan direktur 22 Nov (permintaan owner, jendela pasar tutup Minggu = D13).

## 2. Snapshot rollback (di `/home/tekka/caddy-edge/`)

| File | Isi |
| --- | --- |
| `Caddyfile.v2-cutover` | Kondisi cutover: fund → v2 via edge-proxy 3110 (baseline aktif) |
| `Caddyfile.v1-rollback` | Varian rollback: fund → v1 native (frontend 3106, API 3107, forward_auth `/api/auth/verify`) |
| `Caddyfile` | File aktif yang di-mount container (selalu hasil copy dari salah satu snapshot di atas) |

## 3. Prosedur rollback (target < 5 menit)

```bash
# Arahkan domain kembali ke v1:
~/fund2/scripts/rollback_caddy_fund.sh v1

# Kembali ke v2 (kondisi cutover):
~/fund2/scripts/rollback_caddy_fund.sh v2
```

Script melakukan: copy snapshot → `caddy validate` (docker run, tanpa sentuh container) →
graceful reload (`caddy reload`, zero-downtime; otomatis inject via `docker cp` bila inode swap) →
post-check `curl https://fund.lumine.biz.id/`. Tidak perlu restart container.

## 4. Hasil uji (2026-11-25 ~03:03 WIB)

| Langkah | Hasil | Waktu |
| --- | --- | --- |
| `rollback_caddy_fund.sh v1` | reload OK, fund.lumine.biz.id → HTTP 502 (v1 mati, lihat §5) | 4 s |
| `rollback_caddy_fund.sh v2` | reload OK, fund.lumine.biz.id → HTTP 200, `/health` OK | 3 s |

Mekanisme Caddy (validate + graceful reload + post-check) **teruji dan jauh di bawah 5 menit**.
Rollback fungsional end-to-end (domain benar-benar menyajikan v1) **belum bisa diuji** karena
kondisi di §5.

## 5. BLOCKER — DoD-2: v1 tidak bisa dihidupkan

Kode aplikasi v1 (`lumine-hedge-fund`: frontend 3106 + API 3107) **sudah tidak ada**:

- `/home/tekka/lumine-hedge-fund/` tinggal `logs/`, `mt5.env/`, `scripts/deploy/mt5/` —
  kode frontend/backend dihapus sekitar 21-22 Nov saat migrasi ke fund2 v2.
- Bukan repo git (tanpa `.git`, tanpa remote).
- Tidak ada di backup (`fund2-backups/` kosong untuk app; hanya staging kosong).
- Tidak ada docker image v1 (hanya `caddy:2-alpine`, `postgres:16-alpine`).
- Unit `lumine-hedge-fund-web.service` / `lumine-hedge-fund-api.service` crash-loop
  (CHDIR/EXEC, WorkingDirectory hilang) — di-stop 2026-11-25 untuk menghentikan restart loop;
  unit file tetap ada di `~/.config/systemd/user/` bila kode v1 dipulihkan
  (`systemctl --user start lumine-hedge-fund-web lumine-hedge-fund-api`).

Konsekuensi: rollback Caddy ke v1 menghasilkan 502, bukan aplikasi v1.

Keputusan yang dibutuhkan (owner/direktur):
1. Sediakan source v1 (dari mesin lain / repo upstream) → DevOps pasang di subdomain cadangan
   (mis. `fund-v1.lumine.biz.id`) + rollback jadi fungsional penuh; atau
2. Terima v1 tidak dapat dipulihkan → rollback plan diubah menjadi "rollback ke build v2
   sebelumnya via git" (commit master fund2) dan DoD-2 direvisi.
