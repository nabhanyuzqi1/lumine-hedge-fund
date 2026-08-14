#!/usr/bin/env bash
# resource-watchdog.sh — pantau disk, memory, dan docker di VPS Lumine
# Cron: 0 * * * * /opt/lumine/scripts/resource-watchdog.sh >> /var/log/lumine-resources.log 2>&1
#
# Alert threshold:
#   Disk: ≥ 80% terpakai
#   Memory: ≥ 90% terpakai
#   Backup age: ≥ 25 jam (harian backup mungkin terlambat)

set -uo pipefail

TS=$(date -Iseconds)
ALERT_FILE="/var/log/lumine-alerts.log"
BACKUP_DIR="/opt/lumine/backups"

DISK_THRESHOLD=80
MEM_THRESHOLD=90
BACKUP_MAX_AGE_HOURS=25

alert() {
  echo "[${TS}] ALERT $*" | tee -a "${ALERT_FILE}"
}

# --- Disk usage ---
DISK_PCT=$(df / | awk 'NR==2 {gsub(/%/,"",$5); print $5}')
DISK_FREE=$(df -h / | awk 'NR==2 {print $4}')
echo "[${TS}] DISK   ${DISK_PCT}% used, ${DISK_FREE} free"
if [ "${DISK_PCT}" -ge "${DISK_THRESHOLD}" ]; then
  alert "DISK: ${DISK_PCT}% used (threshold ${DISK_THRESHOLD}%) — free: ${DISK_FREE}"
fi

# --- Memory usage ---
MEM_INFO=$(free | awk 'NR==2 {printf "%d %d", $3, $2}')
MEM_USED=$(echo "${MEM_INFO}" | awk '{print $1}')
MEM_TOTAL=$(echo "${MEM_INFO}" | awk '{print $2}')
MEM_PCT=$(awk "BEGIN {printf \"%d\", ${MEM_USED}*100/${MEM_TOTAL}}")
MEM_FREE_H=$(free -h | awk 'NR==2 {print $4}')
echo "[${TS}] MEMORY ${MEM_PCT}% used, ${MEM_FREE_H} free"
if [ "${MEM_PCT}" -ge "${MEM_THRESHOLD}" ]; then
  alert "MEMORY: ${MEM_PCT}% used (threshold ${MEM_THRESHOLD}%) — free: ${MEM_FREE_H}"
fi

# --- Docker containers summary ---
TOTAL=$(docker ps -q | wc -l)
HEALTHY=$(docker ps --filter health=healthy -q | wc -l)
UNHEALTHY=$(docker ps --filter health=unhealthy -q | wc -l)
echo "[${TS}] DOCKER ${TOTAL} running, ${HEALTHY} healthy, ${UNHEALTHY} unhealthy"
if [ "${UNHEALTHY}" -gt 0 ]; then
  NAMES=$(docker ps --filter health=unhealthy --format '{{.Names}}' | tr '\n' ' ')
  alert "DOCKER: ${UNHEALTHY} unhealthy container(s): ${NAMES}"
fi

# --- Backup freshness ---
if [ -d "${BACKUP_DIR}" ]; then
  LATEST=$(find "${BACKUP_DIR}" -name "lumine_*.sql.gz" -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | awk '{print $2}')
  if [ -n "${LATEST}" ]; then
    MTIME=$(stat -c %Y "${LATEST}")
    NOW=$(date +%s)
    AGE_HOURS=$(( (NOW - MTIME) / 3600 ))
    BACKUP_SIZE=$(du -sh "${LATEST}" | cut -f1)
    echo "[${TS}] BACKUP last=${LATEST##*/} age=${AGE_HOURS}h size=${BACKUP_SIZE}"
    if [ "${AGE_HOURS}" -ge "${BACKUP_MAX_AGE_HOURS}" ]; then
      alert "BACKUP: latest backup is ${AGE_HOURS}h old (threshold ${BACKUP_MAX_AGE_HOURS}h)"
    fi
  else
    echo "[${TS}] BACKUP no backup files found in ${BACKUP_DIR}"
    alert "BACKUP: no backup files found in ${BACKUP_DIR}"
  fi
else
  echo "[${TS}] BACKUP directory ${BACKUP_DIR} does not exist"
fi

echo "[${TS}] Done."
