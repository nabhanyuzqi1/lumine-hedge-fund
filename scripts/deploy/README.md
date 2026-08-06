# Lumine — Deployment Automation ke VPS

Paket ini berisi otomasi untuk memindahkan seluruh workflow Lumine ke VPS:
**9router** (LLM gateway), **hermes agent**, **openclaude**, dan **lumine
stack** (FastAPI + Postgres + Redis via Docker).

## Isi Paket

| File | Fungsi |
|------|--------|
| `bootstrap-vps.sh` | Setup awal VPS: paket dasar, Docker Engine + compose, user deploy, direktori state. Idempotent. |
| `deploy-stack.sh` | Deploy penuh: kirim bootstrap + compose, jalankan bootstrap, `up -d`, health check. |
| `backup.sh` | Backup Postgres + Redis + state agent ke `BACKUP_DIR`, rotasi otomatis. |
| `restore.sh` | Restore dari `backup.sh` (postgres dump, redis RDB, state tar). |
| `export-state.sh` | Paket state lokal (9router/hermes/openclaude) menjadi tar.gz. |
| `import-state.sh` | Kirim + restore state tar.gz ke VPS. |
| `systemd/lumine-api.service` | Unit opsional: stack auto-start saat boot. |
| `.env.sample` | Template kredensial target VPS (copy ke `.env`, jangan di-commit). |

## Alur Cepat (pertama kali di VPS)

```bash
cd scripts/deploy
cp .env.sample .env && $EDITOR .env   # isi VPS_HOST, VPS_USER, DB_PASSWORD, HMAC, LLM key
./deploy-stack.sh                     # bootstrap Docker + deploy lumine stack
./import-state.sh state-exports/<stamp>.tar.gz   # pindah state 9router/hermes/openclaude
```

## Alur Migrasi State (dari mesin lokal)

```bash
# Di mesin lama:
./export-state.sh                      # → state-exports/20260805-153000.tar.gz

# Dari mesin baru / laptop: kirim ke VPS
./import-state.sh state-exports/20260805-153000.tar.gz
```

## Backup & Restore

```bash
# Di VPS langsung:
/opt/lumine/backup.sh

# Via SSH dari laptop (archive ditarik ke state-exports/):
./backup.sh --remote

# Restore di VPS:
/opt/lumine/restore.sh /root/lumine-backups/20260805.tar.gz
```

Rotasi: backup lebih tua dari `BACKUP_RETENTION_DAYS` (default 7) dihapus otomatis.

## Keamanan

- **Jangan commit `.env`** — isinya kredensial nyata. Sudah di-gitignore.
- Backup state(Dumpatau bisa berisi **token/session 9router, jwt-secret hermes**. Simpan backup di tempat terenkripsi / disk terpisah.
- Password VPS tidak pernah masuk repo — hanya dipakai runtime lewat SSH.

## Sistemd (opsional)

```bash
sudo install -m 0644 systemd/lumine-api.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now lumine-api
```