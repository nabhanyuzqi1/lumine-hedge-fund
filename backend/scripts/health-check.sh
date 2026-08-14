#!/usr/bin/env bash
# health-check.sh — cek semua service Lumine + domain setiap 5 menit
# Cron: */5 * * * * /opt/lumine/scripts/health-check.sh >> /var/log/lumine-health.log 2>&1
#
# Alert: tulis ke /var/log/lumine-alerts.log jika ada service turun
# Supaya tidak spam, alert di-throttle 1x/30 menit per service

set -uo pipefail

LOG_FILE="/var/log/lumine-health.log"
ALERT_FILE="/var/log/lumine-alerts.log"
ALERT_STATE_DIR="/tmp/lumine-health-state"
COMPOSE_DIR="/opt/lumine/backend"

mkdir -p "${ALERT_STATE_DIR}"

TS=$(date -Iseconds)
FAILURES=0

check_http() {
  local name="$1"
  local url="$2"
  local expected="${3:-200}"

  local code
  code=$(curl -sS -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 "${url}" 2>/dev/null || echo "000")

  if [ "${code}" = "${expected}" ]; then
    echo "[${TS}] OK    ${name} (${code}) ${url}"
  else
    echo "[${TS}] FAIL  ${name} (got ${code}, expect ${expected}) ${url}"
    alert "${name}" "HTTP ${code} (expected ${expected}) at ${url}"
    FAILURES=$((FAILURES + 1))
  fi
}

check_container() {
  local name="$1"
  local state
  state=$(docker inspect --format='{{.State.Status}}' "${name}" 2>/dev/null || echo "missing")
  local health
  health=$(docker inspect --format='{{.State.Health.Status}}' "${name}" 2>/dev/null || echo "none")

  if [ "${state}" = "running" ]; then
    echo "[${TS}] OK    container/${name} (${state}/${health})"
  else
    echo "[${TS}] FAIL  container/${name} (${state}/${health})"
    alert "container/${name}" "State=${state} Health=${health}"
    FAILURES=$((FAILURES + 1))
  fi
}

alert() {
  local service="$1"
  local message="$2"
  local state_file="${ALERT_STATE_DIR}/$(echo "${service}" | tr '/' '_')"
  local now
  now=$(date +%s)

  # Throttle: 1 alert per 30 minutes per service
  if [ -f "${state_file}" ]; then
    local last
    last=$(cat "${state_file}")
    local diff=$(( now - last ))
    if [ "${diff}" -lt 1800 ]; then
      return 0
    fi
  fi

  echo "${now}" > "${state_file}"
  echo "[${TS}] ALERT ${service}: ${message}" | tee -a "${ALERT_FILE}"
}

# --- Container checks ---
check_container "backend-api-1"
check_container "backend-caddy-1"
check_container "backend-frontend-1"
check_container "backend-postgres-1"
check_container "backend-redis-1"
check_container "backend-mt5-bridge-1"
check_container "lumine-authelia"
check_container "lumine-mt5"
check_container "9router"

# --- HTTP endpoint checks ---
check_http "domain-health"    "https://lumine.biz.id/health"
check_http "domain-frontend"  "https://lumine.biz.id/"
check_http "local-health"     "http://localhost/health"
check_http "authelia-health"  "http://localhost:9091/auth/api/health"
check_http "9router"          "http://localhost:20128" "401"

# --- Summary ---
if [ "${FAILURES}" -gt 0 ]; then
  echo "[${TS}] SUMMARY: ${FAILURES} FAILURE(S) detected"
else
  echo "[${TS}] SUMMARY: all checks passed"
fi
