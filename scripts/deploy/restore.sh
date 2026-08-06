#!/usr/bin/env bash
# =============================================================================
# restore.sh — Restore backup Lumine (Postgres/Redis/state agent).
#
# Input: file .tar.gz dari backup.sh, mis. /root/lumine-backups/20260805.tar.gz
# Alur:
#   1. Ekstrak ke folder sementara.
#   2. Restore Postgres via docker exec psql (drop + recreate schema).
#   3. Restore Redis RDB ke container.
#   4. Pulihkan state 9router/hermes/openclaude ke /opt/lumine/state.
#
# Pemakaian:  ./restore.sh <path-ke-archive.tar.gz>
# =============================================================================
set -euo pipefail

ARCHIVE="${1:-}"
if [[ -z "${ARCHIVE}" || ! -f "${ARCHIVE}" ]]; then
  echo "ERROR: berikan path ke file backup (.tar.gz)."
  echo "  Contoh: ./restore.sh /root/lumine-backups/20260805.tar.gz"
  exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

echo "==> Ekstrak ${ARCHIVE} ..."
tar -xzf "${ARCHIVE}" -C "${WORK}"
SNAP="$(ls -d "${WORK}"/2026* 2>/dev/null | head -1 || echo "${WORK}")"

DB_USER="${DB_USER:-lumine}"
DB_NAME="${DB_NAME:-lumine}"

# ── 1. Restore Postgres ──────────────────────────────────────────────────────
if [[ -f "${SNAP}/postgres.sql" ]]; then
  PG_CONTAINER="$(docker ps --format '{{.Names}}' | grep 'postgres' | head -1)"
  if [[ -z "${PG_CONTAINER}" ]]; then
    echo "ERROR: container postgres tidak berjalan. Start dulu: docker compose up -d postgres"
    exit 1
  fi
  echo "==> Restore Postgres (drop + recreate + load)..."
  docker exec "${PG_CONTAINER}" \
    psql -U "${DB_USER}" -d postgres -c "DROP DATABASE IF EXISTS ${DB_NAME};"
  docker exec "${PG_CONTAINER}" \
    psql -U "${DB_USER}" -d postgres -c "CREATE DATABASE ${DB_NAME};"
  docker exec -i "${PG_CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" \
    < "${SNAP}/postgres.sql"
else
  echo "    (skip) tidak ada postgres.sql"
fi

# ── 2. Restore Redis ─────────────────────────────────────────────────────────
if [[ -f "${SNAP}/redis.rdb" ]]; then
  REDIS_CONTAINER="$(docker ps --format '{{.Names}}' | grep 'redis' | head -1)"
  if [[ -z "${REDIS_CONTAINER}" ]]; then
    echo "ERROR: container redis tidak berjalan."
    exit 1
  fi
  echo "==> Restore Redis RDB..."
  docker cp "${SNAP}/redis.rdb" "${REDIS_CONTAINER}:/data/dump.rdb"
  docker exec "${REDIS_CONTAINER}" redis-cli FLUSHALL
  docker restart "${REDIS_CONTAINER}" >/dev/null
else
  echo "    (skip) tidak ada redis.rdb"
fi

# ── 3. Restore state agent ───────────────────────────────────────────────────
for d in 9router hermes openclaude; do
  if [[ -f "${SNAP}/state-${d}.tar.gz" ]]; then
    echo "==> Restore state ${d} ..."
    tar -xzf "${SNAP}/state-${d}.tar.gz" -C /opt/lumine/state
  else
    echo "    (skip) tidak ada state-${d}.tar.gz"
  fi
done

echo ""
echo "==> Restore selesai. Restart stack:"
echo "    cd /opt/lumine/backend && docker compose -f docker-compose.prod.yml restart"