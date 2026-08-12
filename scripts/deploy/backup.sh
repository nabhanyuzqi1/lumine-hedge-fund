#!/usr/bin/env bash
# =============================================================================
# backup.sh — Backup data (Postgres/Redis) + state service (9router, hermes,
# authelia, uptime-kuma, caddy). MT5 sengaja TIDAK di-backup: instalasi docker
# murni (recreate-only), tidak menyimpan data operasional (keputusan 2026-08-12).
#
# Lokasi hasil: BACKUP_DIR (default /root/lumine-backups), 1 file per tanggal.
# Rotasi otomatis: hapus backup lebih tua dari BACKUP_RETENTION_DAYS (default 7).
#
# Pemakaian:
#   Di VPS:   ./backup.sh              (jalankan langsung di VPS)
#   Dari luar: ./backup.sh --remote     (jalankan via SSH, tar ditarik ke lokal)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source ./.env; set +a
fi

# ── Variabel (dengan fallback) ───────────────────────────────────────────────
BACKUP_DIR="${BACKUP_DIR:-/root/lumine-backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
DATE_STAMP="$(date +%Y%m%d)"
STAMP="${BACKUP_DIR}/${DATE_STAMP}"

DB_USER="${DB_USER:-lumine}"
DB_NAME="${DB_NAME:-lumine}"
COMPOSE_DIR="/opt/lumine/backend"

REMOTE_MODE="${1:-}"

# ── Mode remote: jalankan script yang sama di VPS, lalu tarik hasil ──────────
if [[ "${REMOTE_MODE}" == "--remote" ]]; then
  VPS_HOST="${VPS_HOST:?VPS_HOST wajib}"
  VPS_USER="${VPS_USER:-root}"
  VPS_SSH_PORT="${VPS_SSH_PORT:-22}"
  DEST="${VPS_USER}@${VPS_HOST}"
  echo "==> Menjalankan backup di ${DEST}..."
  ssh -p "${VPS_SSH_PORT}" "${DEST}" "bash -s" < "${BASH_SOURCE[0]}"
  echo "==> Menarik hasil ke lokal scripts/deploy/state-exports/ ..."
  mkdir -p state-exports
  scp -p -P "${VPS_SSH_PORT}" \
    "${DEST}:${BACKUP_DIR}/${DATE_STAMP}.tar.gz" \
    "state-exports/${DATE_STAMP}.tar.gz" 2>/dev/null \
    || echo "    (warn: tidak ada archive ${DATE_STAMP}.tar.gz — cek log di VPS)"
  exit 0
fi

echo "==> Backup ke ${STAMP}.tar.gz ..."
mkdir -p "${BACKUP_DIR}/${DATE_STAMP}"

# ── 1. Dump Postgres (via docker exec) ───────────────────────────────────────
if docker ps --format '{{.Names}}' | grep -q 'postgres'; then
  PG_CONTAINER="$(docker ps --format '{{.Names}}' | grep 'postgres' | head -1)"
  echo "==> Dump Postgres dari container ${PG_CONTAINER} ..."
  docker exec "${PG_CONTAINER}" pg_dump -U "${DB_USER:-lumine}" "${DB_NAME}" \
    > "${BACKUP_DIR}/${DATE_STAMP}/postgres.sql"
else
  echo "    (skip Postgres: container tidak berjalan)"
fi

# ── 2. Redis RDB snapshot ────────────────────────────────────────────────────
if docker ps --format '{{.Names}}' | grep -q 'redis'; then
  REDIS_CONTAINER="$(docker ps --format '{{.Names}}' | grep 'redis' | head -1)"
  echo "==> Snapshot Redis dari container ${REDIS_CONTAINER} ..."
  docker exec "${REDIS_CONTAINER}" redis-cli SAVE >/dev/null
  docker cp "${REDIS_CONTAINER}:/data/dump.rdb" \
    "${BACKUP_DIR}/${DATE_STAMP}/redis.rdb"
else
  echo "    (skip) container redis tidak berjalan"
fi

# ── 3. State service (9router / hermes / openclaude / authelia / kuma / caddy)
# Path asli (ground truth 2026-08-12):
#   9router   → volume  backend_9router_data  (auth/, db/, jwt-secret, machine-id)
#   hermes    → /root/.hermes                  (state.db, kanban.db, auth.json, pairing/, memories/)
#               exlude cache: home/ (420M), bin/ (22M) — tidak dibutuhkan untuk restore
#   authelia  → /srv/control-plane/authelia/   (db.sqlite3 TOTP + users_database.yml)
#   uptime    → /srv/control-plane/uptime-kuma/ (kuma.db — monitor config)
#   caddy     → volume control-plane_caddy_data (sertifikat; 140K)
# MT5: recreate-only (keputusan 2026-08-12) — tidak di-backup.
echo "==> State 9router (volume backend_9router_data) ..."
if docker volume inspect backend_9router_data >/dev/null 2>&1; then
  docker run --rm -v backend_9router_data:/data:ro \
    -v "${BACKUP_DIR}/${DATE_STAMP}":/backup alpine \
    sh -c 'tar -czf /backup/state-9router.tar.gz -C /data .'
else
  echo "    (skip) volume backend_9router_data tidak ada"
fi

echo "==> State hermes (/root/.hermes, exlude cache) ..."
if [[ -d /root/.hermes ]]; then
  tar -czf "${BACKUP_DIR}/${DATE_STAMP}/state-hermes.tar.gz" \
    --exclude='/root/.hermes/home' --exclude='/root/.hermes/bin' \
    -C /root .hermes
else
  echo "    (skip) /root/.hermes tidak ada"
fi

echo "==> State authelia (TOTP db.sqlite3 + users_database.yml) ..."
if [[ -d /srv/control-plane/authelia ]]; then
  mkdir -p "${BACKUP_DIR}/${DATE_STAMP}/authelia"
  cp -a /srv/control-plane/authelia/db.sqlite3 \
    "${BACKUP_DIR}/${DATE_STAMP}/authelia/" 2>/dev/null || echo "    (skip db.sqlite3)"
  cp -a /srv/control-plane/authelia/users_database.yml \
    "${BACKUP_DIR}/${DATE_STAMP}/authelia/" 2>/dev/null || echo "    (skip users_database.yml)"
else
  echo "    (skip) /srv/control-plane/authelia tidak ada"
fi

echo "==> State uptime-kuma (kuma.db) ..."
if [[ -d /srv/control-plane/uptime-kuma ]]; then
  mkdir -p "${BACKUP_DIR}/${DATE_STAMP}/uptime-kuma"
  cp -a /srv/control-plane/uptime-kuma/kuma.db* \
    "${BACKUP_DIR}/${DATE_STAMP}/uptime-kuma/" 2>/dev/null || echo "    (skip kuma.db)"
else
  echo "    (skip) /srv/control-plane/uptime-kuma tidak ada"
fi

echo "==> State caddy (sertifikat) ..."
if docker volume inspect control-plane_caddy_data >/dev/null 2>&1; then
  docker run --rm -v control-plane_caddy_data:/data:ro \
    -v "${BACKUP_DIR}/${DATE_STAMP}":/backup alpine \
    sh -c 'tar -czf /backup/state-caddy.tar.gz -C /data .'
else
  echo "    (skip) volume control-plane_caddy_data tidak ada"
fi

echo "==> State openclaude — SKIP (tidak terpasang di server, 2026-08-12)"

# ── 4. Kemas hari ini + bersihkan lama ───────────────────────────────────────
echo "==> Kemas → ${BACKUP_DIR}/${DATE_STAMP}.tar.gz"
tar -czf "${BACKUP_DIR}/${DATE_STAMP}.tar.gz" -C "${BACKUP_DIR}" "${DATE_STAMP}"
rm -rf "${BACKUP_DIR}/${DATE_STAMP}"

echo "==> Bersihkan backup > ${BACKUP_RETENTION_DAYS} hari..."
find "${BACKUP_DIR}" -name '*.tar.gz' -mtime "+${BACKUP_RETENTION_DAYS}" -delete

echo "==> Selesai. Isi:"
ls -lh "${BACKUP_DIR}/" | tail -5