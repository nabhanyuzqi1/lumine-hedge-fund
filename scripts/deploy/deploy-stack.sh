#!/usr/bin/env bash
# =============================================================================
# deploy-stack.sh — Deploy / update full stack Lumine ke VPS.
#
# Alur:
#   1. Baca .env (kredensial target VPS; JANGAN commit).
#   2. Copy bootstrap-vps.sh + compose file ke VPS via rsync/scp.
#   3. Jalankan bootstrap sekali (idempotent) jika Docker belum ada.
#   4. Jalankan docker compose up -d (postgres, redis, api).
#   5. Health check endpoint /health.
#
# Pemakaian:  ./deploy-stack.sh
# Prasyarat:  file .env (copy dari .env.sample), sshpass atau ssh key setup.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [[ ! -f .env ]]; then
  echo "ERROR: .env tidak ditemukan. Copy dari .env.sample dulu:"
  echo "  cp .env.sample .env && $EDITOR .env"
  exit 1
fi
# shellcheck disable=SC1091
set -a; source ./.env; set +a

VPS_HOST="${VPS_HOST:?VPS_HOST wajib di .env}"
VPS_USER="${VPS_USER:-root}"
VPS_SSH_PORT="${VPS_SSH_PORT:-22}"
SSH_DEST="${VPS_USER}@${VPS_HOST}"

echo "==> Target: ${SSH_DEST} (port ${VPS_SSH_PORT})"

# ── 1. Pastikan bootstrap & compose terkirim ─────────────────────────────────
REMOTE_DIR=/opt/lumine
echo "==> Membuat direktori remote + mengirim file..."
ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" "mkdir -p ${REMOTE_DIR}/backend"
scp -P "${VPS_SSH_PORT}" \
  bootstrap-vps.sh \
  "${SSH_DEST}:${REMOTE_DIR}/bootstrap-vps.sh"
scp -P "${VPS_SSH_PORT}" \
  "${SCRIPT_DIR}/../../backend/docker-compose.prod.yml" \
  "${SSH_DEST}:${REMOTE_DIR}/backend/docker-compose.prod.yml"
scp -P "${VPS_SSH_PORT}" \
  "${SCRIPT_DIR}/../../backend/Dockerfile" \
  "${SSH_DEST}:${REMOTE_DIR}/backend/Dockerfile"

# ── 2. Bootstrap (idempotent) ────────────────────────────────────────────────
echo "==> Menjalankan bootstrap-vps.sh di remote (idempotent)..."
ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" \
  "chmod +x ${REMOTE_DIR}/bootstrap-vps.sh && ${REMOTE_DIR}/bootstrap-vps.sh ${VPS_USER}"

# ── 3. Kirim .env produksi (berisi DB_PASSWORD dsb.) ─────────────────────────
# .env dikirim via stdin — tidak pernah tersimpan di disk lokal/repo.
echo "==> Menulis .env produksi ke remote (via stdin, tidak di-repo)..."
ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" \
  "cat > ${REMOTE_DIR}/.env" <<EOF
DB_PASSWORD=${DB_PASSWORD}
HMAC_SECRET_KEY=${HMAC_SECRET_KEY}
LLM_GATEWAY_API_KEY=${LLM_GATEWAY_API_KEY}
EOF
ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" "chmod 600 ${REMOTE_DIR}/.env"

# ── 4. Deploy container stack ─────────────────────────────────────────────────
echo "==> docker compose up -d (postgres, redis, api)..."
ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" \
  "cd ${REMOTE_DIR}/backend && docker compose -f docker-compose.prod.yml up -d --build"

# ── 5. Health check ───────────────────────────────────────────────────────────
echo "==> Health check /health (maks 90 detik)..."
for i in $(seq 1 45); do
  if ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" \
      "curl -sf http://localhost:8000/health >/dev/null 2>&1"; then
    echo "    OK: API healthy setelah ${i} percobaan."
    echo "==> Deploy selesai."
    exit 0
  fi
  sleep 2
done

echo "ERROR: API tidak healthy dalam 90 detik. Cek: ssh ${SSH_DEST} 'docker compose -f /opt/lumine/backend/docker-compose.prod.yml logs api'"
exit 1