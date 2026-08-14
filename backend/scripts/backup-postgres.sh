#!/usr/bin/env bash
# backup-postgres.sh — pg_dump harian Lumine ke /opt/lumine/backups/
# Retensi: 7 hari. Jalankan sebagai root di VPS.
# Cron: 0 2 * * * /opt/lumine/scripts/backup-postgres.sh >> /var/log/lumine-backup.log 2>&1

set -euo pipefail

BACKUP_DIR="/opt/lumine/backups"
COMPOSE_DIR="/opt/lumine/backend"
COMPOSE_FILE="docker-compose.vps.yml"
DB_CONTAINER="backend-postgres-1"
DB_NAME="lumine"
DB_USER="lumine"
RETENTION_DAYS=7
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/lumine_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

echo "[$(date -Iseconds)] Starting pg_dump backup → ${BACKUP_FILE}"

# Run pg_dump inside container, compress inline
docker exec "${DB_CONTAINER}" \
  pg_dump -U "${DB_USER}" "${DB_NAME}" \
  | gzip > "${BACKUP_FILE}"

BACKUP_SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
echo "[$(date -Iseconds)] Backup complete: ${BACKUP_FILE} (${BACKUP_SIZE})"

# Verify backup is non-empty
if [ ! -s "${BACKUP_FILE}" ]; then
  echo "[$(date -Iseconds)] ERROR: Backup file is empty! Removing and exiting."
  rm -f "${BACKUP_FILE}"
  exit 1
fi

# Prune backups older than RETENTION_DAYS
PRUNED=$(find "${BACKUP_DIR}" -name "lumine_*.sql.gz" -mtime +${RETENTION_DAYS} -print -delete | wc -l)
if [ "${PRUNED}" -gt 0 ]; then
  echo "[$(date -Iseconds)] Pruned ${PRUNED} backup(s) older than ${RETENTION_DAYS} days"
fi

# List current backups
echo "[$(date -Iseconds)] Current backups:"
ls -lh "${BACKUP_DIR}"/lumine_*.sql.gz 2>/dev/null || echo "  (none)"

echo "[$(date -Iseconds)] Done."
