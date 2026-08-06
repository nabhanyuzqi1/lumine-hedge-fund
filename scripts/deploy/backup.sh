#!/usr/bin/env bash
# =============================================================================
# backup.sh — Backup data (Postgres/Redis) + state agent (9router/hermes/openclaude).
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

# ── 3. State agent (9router/hermes/openclaude) ───────────────────────────────
for d in 9router hermes openclaude; do
  if [[ -d "/opt/lumine/state/${d}" ]]; then
    echo "==> Tar state ${d} ..."
    tar -czf "${BACKUP_DIR}/${DATE_STAMP}/state-${d}.tar.gz" \
      -C /opt/lumine/state "${d}"
  else
    echo "    (skip) /opt/lumine/state/${d} tidak ada"
  fi
done

# ── 4. Kemas hari ini + bersihkan lama ───────────────────────────────────────
echo "==> Kemas → ${BACKUP_DIR}/${DATE_STAMP}.tar.gz"
tar -czf "${BACKUP_DIR}/${DATE_STAMP}.tar.gz" -C "${BACKUP_DIR}" "${DATE_STAMP}"
rm -rf "${BACKUP_DIR}/${DATE_STAMP}"

echo "==> Bersihkan backup > ${BACKUP_RETENTION_DAYS} hari..."
find "${BACKUP_DIR}" -name '*.tar.gz' -mtime "+${BACKUP_RETENTION_DAYS}" -delete

echo "==> Selesai. Isi:"
ls -lh "${BACKUP_DIR}/" | tail -5