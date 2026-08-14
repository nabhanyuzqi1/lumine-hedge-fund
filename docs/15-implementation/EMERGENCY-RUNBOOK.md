# Lumine Emergency Access & Operations Runbook

**Version:** 1.0.0 · **Updated:** 2026-08-14  
**Scope:** VPS `166.88.227.177` · Domain `lumine.biz.id` · Branch `dev`

---

## 1. Akses Darurat ke VPS

### SSH ke VPS
```bash
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177
```

Jika SSH key hilang:
1. Login ke panel IDwebhost → akses VPS console (web-based terminal)
2. Reset root password via console
3. Upload SSH key baru: `ssh-copy-id -i ~/.ssh/id_rsa.pub root@166.88.227.177`

### Jika VPS tidak merespons
1. Cek status di panel IDwebhost → restart VPS jika diperlukan
2. Setelah restart, semua Docker container akan otomatis restart (policy: `restart: unless-stopped`)
3. Verifikasi: `docker compose -f /opt/lumine/backend/docker-compose.vps.yml ps`

---

## 2. Lokasi File Kritis

| File | Lokasi VPS | Keterangan |
|------|-----------|------------|
| Env vars | `/opt/lumine/backend/.env` | Secrets: JANGAN commit |
| Caddyfile | `/opt/lumine/backend/Caddyfile.prod` | Reverse proxy config |
| Authelia config | `/opt/lumine/backend/authelia/configuration.yml` | SSO config |
| Authelia users | `/opt/lumine/backend/authelia/users_database.yml` | User & hashed password |
| Docker compose VPS | `/opt/lumine/backend/docker-compose.vps.yml` | Service definitions |
| Docker compose prod | `/opt/lumine/backend/docker-compose.prod.yml` | MT5 + 9router services |
| Backups | `/opt/lumine/backups/lumine_*.sql.gz` | pg_dump daily, retensi 7 hari |
| Health logs | `/var/log/lumine-health.log` | Cron setiap 5 menit |
| Alert log | `/var/log/lumine-alerts.log` | Throttled alerts |
| Backup log | `/var/log/lumine-backup.log` | pg_dump log harian |

---

## 3. Kill Switch Trading

### Aktifkan Kill Switch (hentikan semua trading)

```bash
# Via API (dari mesin apapun dengan HMAC key)
curl -X POST https://lumine.biz.id/api/v1/admin/kill-switch \
  -H "Content-Type: application/json" \
  -H "X-Lumine-Key-ID: web-frontend" \
  -H "X-Lumine-Signature: <HMAC>" \
  -d '{"armed": true, "reason": "Emergency stop", "tier": "halt_all"}'
```

### Via Superadmin UI
1. Buka `https://lumine.biz.id/superadmin`
2. Login Authelia: user `superadmin`
3. Klik Kill Switch di header → konfirmasi

### Darurat: Stop langsung di VPS
```bash
# Stop MT5 bridge (hentikan eksekusi order)
docker stop backend-mt5-bridge-1

# Stop seluruh stack
cd /opt/lumine/backend
docker compose -f docker-compose.vps.yml stop
docker compose -f docker-compose.prod.yml stop
```

---

## 4. Rollback Deployment

### Rollback ke commit sebelumnya
```bash
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177
cd /opt/lumine

# Lihat log commit
git log --oneline -10

# Rollback ke commit tertentu
git checkout <commit-sha>

# Rebuild dan restart service yang relevan
cd backend
docker compose -f docker-compose.vps.yml build api frontend
docker compose -f docker-compose.vps.yml up -d api frontend
```

### Rollback ke backup database
```bash
# Lihat backup yang tersedia
ls -lh /opt/lumine/backups/

# Restore dari backup (HATI-HATI: ini OVERWRITE database yang ada)
gunzip -c /opt/lumine/backups/lumine_YYYYMMDD_HHMMSS.sql.gz \
  | docker exec -i backend-postgres-1 psql -U lumine lumine

# Restart api setelah restore
docker restart backend-api-1
```

---

## 5. Secrets Recovery

### Semua secrets ada di `/opt/lumine/backend/.env`

Jika file `.env` hilang, semua secrets perlu di-regenerate:

| Secret | Cara Regenerate |
|--------|----------------|
| `HMAC_SECRET_KEY` | `openssl rand -hex 32` |
| `AUTHELIA_JWT_SECRET` | `openssl rand -hex 32` |
| `AUTHELIA_SESSION_SECRET` | `openssl rand -hex 32` |
| `AUTHELIA_STORAGE_ENCRYPTION_KEY` | `openssl rand -hex 32` |
| Authelia user password | `docker run --rm authelia/authelia:4.38 authelia crypto hash generate argon2 --password "new-pass"` |
| Database password | Buat baru, update di `DATABASE_URL` dan reconfigure PostgreSQL |

### Password Authelia Superadmin
- User: `superadmin`  
- Default password: `lumine-superadmin-2026` (ganti setelah trading perdana)
- Hash ada di: `/opt/lumine/backend/authelia/users_database.yml`
- Regenerate hash:
```bash
docker run --rm authelia/authelia:4.38 authelia crypto hash generate argon2 --password "new-password"
```

---

## 6. Restart Service Individual

```bash
cd /opt/lumine/backend

# API backend
docker compose -f docker-compose.vps.yml restart api

# Frontend (rebuild dulu jika ada code change)
docker compose -f docker-compose.vps.yml build frontend
docker compose -f docker-compose.vps.yml up -d frontend

# Caddy (reverse proxy)
docker compose -f docker-compose.vps.yml restart caddy

# Authelia (SSO)
docker stop lumine-authelia && docker rm lumine-authelia
docker compose -f docker-compose.vps.yml up -d authelia

# PostgreSQL
docker compose -f docker-compose.vps.yml restart postgres

# Redis
docker compose -f docker-compose.vps.yml restart redis

# MT5 + noVNC
docker compose -f docker-compose.prod.yml restart mt5

# 9router (LLM Gateway)
docker compose -f docker-compose.prod.yml restart 9router
```

---

## 7. Health Check Manual

```bash
# Cek semua service
cd /opt/lumine/backend
docker compose -f docker-compose.vps.yml ps

# Cek endpoint domain
curl -sI https://lumine.biz.id/health
curl -sI https://lumine.biz.id/

# Cek Authelia
curl -sI http://localhost:9091/auth/api/health

# Cek 9router
curl -sI http://localhost:20128  # Expect 401

# Jalankan health check script
bash /opt/lumine/scripts/health-check.sh

# Lihat alert log
tail -50 /var/log/lumine-alerts.log

# Lihat health log terakhir
tail -100 /var/log/lumine-health.log
```

---

## 8. Deploy Update dari GitHub

```bash
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177
cd /opt/lumine

# Pull terbaru dari branch dev
git pull origin dev

# Rebuild service yang berubah
cd backend
docker compose -f docker-compose.vps.yml build api frontend
docker compose -f docker-compose.vps.yml up -d api frontend

# Verifikasi
docker compose -f docker-compose.vps.yml ps
curl -sI https://lumine.biz.id/health
```

---

## 9. Disaster Recovery Lengkap (VPS baru)

Jika VPS perlu diganti sepenuhnya:

1. Provision VPS baru Ubuntu 24.04
2. Install Docker:
```bash
curl -fsSL https://get.docker.com | sh
```
3. Clone repo:
```bash
git clone git@github.com:MANOB_PC2/lumine-hedge-fund.git /opt/lumine
cd /opt/lumine && git checkout dev
```
4. Buat `.env` dari template + isi semua secrets:
```bash
cp backend/.env.prod.example backend/.env
# Edit backend/.env dengan semua secrets
```
5. Restore database dari backup:
```bash
docker compose -f backend/docker-compose.vps.yml up -d postgres redis
sleep 10
gunzip -c /path/to/backup/lumine_latest.sql.gz \
  | docker exec -i backend-postgres-1 psql -U lumine lumine
```
6. Start semua service:
```bash
cd backend
docker compose -f docker-compose.vps.yml up -d
docker compose -f docker-compose.prod.yml up -d
```
7. Update DNS Cloudflare ke IP baru
8. Install cron jobs monitoring:
```bash
bash /opt/lumine/scripts/install-cron.sh
```
9. Verifikasi semua endpoint

---

## 10. Kontak & Akses

| Resource | Detail |
|----------|--------|
| VPS IP | `166.88.227.177` |
| Domain | `lumine.biz.id` (Cloudflare Flexible SSL) |
| Superadmin | `https://lumine.biz.id/superadmin` |
| Authelia login | `https://lumine.biz.id/auth/` |
| MT5 noVNC | `https://lumine.biz.id/novnc/` |
| Dozzle logs | `https://lumine.biz.id/dozzle/` |
| 9router gateway | `https://lumine.biz.id/9router/` |
| SSH key | `~/.ssh/lumine/id_rsa_lumine` |
| GitHub | `branch: dev` |
| VPS panel | IDwebhost (email pemilik) |
| Cloudflare | dash.cloudflare.com (email pemilik) |

---

## 11. Monitoring & Alerting

Monitoring aktif via cron:

| Script | Jadwal | Log |
|--------|--------|-----|
| `backup-postgres.sh` | Setiap hari jam 02:00 | `/var/log/lumine-backup.log` |
| `health-check.sh` | Setiap 5 menit | `/var/log/lumine-health.log` |
| `resource-watchdog.sh` | Setiap jam | `/var/log/lumine-resources.log` |

Alert threshold:
- Disk ≥ 80% → alert
- Memory ≥ 90% → alert  
- Container unhealthy → alert
- Backup > 25 jam lama → alert
- Alert di-throttle 1x/30 menit per service

Semua alert masuk ke `/var/log/lumine-alerts.log`.
