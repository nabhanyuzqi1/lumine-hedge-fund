#!/usr/bin/env bash
# install-cron.sh — install semua cron jobs Lumine ke VPS
# Jalankan SEKALI di VPS setelah scripts di-deploy:
#   bash /opt/lumine/scripts/install-cron.sh
#
# Cron schedule:
#   backup-postgres: 02:00 setiap hari
#   health-check:    setiap 5 menit
#   resource-watchdog: setiap jam

set -euo pipefail

SCRIPTS_DIR="/opt/lumine/scripts"

echo "Installing cron jobs for Lumine monitoring..."

# Pastikan scripts executable
chmod +x "${SCRIPTS_DIR}/backup-postgres.sh"
chmod +x "${SCRIPTS_DIR}/health-check.sh"
chmod +x "${SCRIPTS_DIR}/resource-watchdog.sh"

# Baca cron saat ini (jika ada), hilangkan entri Lumine lama
CURRENT_CRON=$(crontab -l 2>/dev/null | grep -v "lumine" | grep -v "backup-postgres" | grep -v "health-check" | grep -v "resource-watchdog" || true)

# Tambah cron jobs baru
NEW_CRON="${CURRENT_CRON}
# === Lumine monitoring ===
# Backup PostgreSQL harian jam 02:00
0 2 * * * ${SCRIPTS_DIR}/backup-postgres.sh >> /var/log/lumine-backup.log 2>&1
# Health check setiap 5 menit
*/5 * * * * ${SCRIPTS_DIR}/health-check.sh >> /var/log/lumine-health.log 2>&1
# Resource watchdog setiap jam
0 * * * * ${SCRIPTS_DIR}/resource-watchdog.sh >> /var/log/lumine-resources.log 2>&1
"

echo "${NEW_CRON}" | crontab -

echo "Cron jobs installed:"
crontab -l | grep -A10 "Lumine monitoring"

# Buat log files dengan permission yang benar
for log in /var/log/lumine-backup.log /var/log/lumine-health.log /var/log/lumine-resources.log /var/log/lumine-alerts.log; do
  touch "${log}"
  chmod 644 "${log}"
  echo "  Created: ${log}"
done

# Buat backup dir
mkdir -p /opt/lumine/backups
echo "  Created: /opt/lumine/backups"

echo ""
echo "Done. Test dengan:"
echo "  bash ${SCRIPTS_DIR}/backup-postgres.sh"
echo "  bash ${SCRIPTS_DIR}/health-check.sh"
echo "  bash ${SCRIPTS_DIR}/resource-watchdog.sh"
