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

# VNC_PASSWORD wajib untuk service mt5 (compose ${VNC_PASSWORD:?...}).
if [[ -z "${VNC_PASSWORD:-}" ]] || [[ ${#VNC_PASSWORD} -lt 6 ]]; then
  echo "ERROR: VNC_PASSWORD wajib di .env dan minimal 6 karakter."
  echo "  Service mt5 tidak bisa start tanpa password VNC."
  exit 1
fi

echo "==> Target: ${SSH_DEST} (port ${VPS_SSH_PORT})"

# ── 1. Pastikan bootstrap & compose terkirim ─────────────────────────────────
REMOTE_DIR=/opt/lumine
echo "==> Membuat direktori remote + mengirim file..."
ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" \
  "mkdir -p ${REMOTE_DIR}/backend ${REMOTE_DIR}/backend/scripts/deploy/mt5"
scp -P "${VPS_SSH_PORT}" \
  bootstrap-vps.sh \
  "${SSH_DEST}:${REMOTE_DIR}/bootstrap-vps.sh"
scp -P "${VPS_SSH_PORT}" \
  "${SCRIPT_DIR}/../../backend/docker-compose.prod.yml" \
  "${SSH_DEST}:${REMOTE_DIR}/backend/docker-compose.prod.yml"
scp -P "${VPS_SSH_PORT}" \
  "${SCRIPT_DIR}/../../backend/Dockerfile" \
  "${SSH_DEST}:${REMOTE_DIR}/backend/Dockerfile"
# Kirim context build MT5 (Dockerfile + entrypoint.sh). Compose memakai
# context: ../scripts/deploy/mt5 relatif dari backend/ — path konsisten.
scp -P "${VPS_SSH_PORT}" \
  "${SCRIPT_DIR}/mt5/Dockerfile" \
  "${SCRIPT_DIR}/mt5/entrypoint.sh" \
  "${SSH_DEST}:${REMOTE_DIR}/backend/scripts/deploy/mt5/"
ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" \
  "chmod +x ${REMOTE_DIR}/backend/scripts/deploy/mt5/entrypoint.sh"

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
VNC_PASSWORD=${VNC_PASSWORD}
EOF
ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" "chmod 600 ${REMOTE_DIR}/.env"

# ── 4. Deploy container stack ─────────────────────────────────────────────────
echo "==> docker compose up -d --build (postgres, redis, api, mt5, 9router, headroom)..."
ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" \
  "cd ${REMOTE_DIR}/backend && docker compose -f docker-compose.prod.yml up -d --build"

# ── 5. Health check ───────────────────────────────────────────────────────────
# API: HTTP /health (cepat). MT5: container healthcheck (Xvfb + x11vnc +
# terminal64.exe). MT5 butuh waktu lebih lama untuk Wine init + MT5 start
# (start_period: 60s di compose), jadi polling 3 menit.
echo "==> Health check API /health (maks 90 detik)..."
API_OK=false
for i in $(seq 1 45); do
  if ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" \
      "curl -sf http://localhost:8000/health >/dev/null 2>&1"; then
    echo "    OK: API healthy setelah ${i} percobaan."
    API_OK=true
    break
  fi
  sleep 2
done

if [[ "${API_OK}" != "true" ]]; then
  echo "ERROR: API tidak healthy dalam 90 detik. Cek: ssh ${SSH_DEST} 'docker compose -f /opt/lumine/backend/docker-compose.prod.yml logs api'"
  exit 1
fi

echo "==> Health check MT5 container (maks 180 detik — Wine init lambat)..."
MT5_OK=false
for i in $(seq 1 36); do
  STATUS=$(ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" \
    "docker inspect --format='{{.State.Health.Status}}' lumine-mt5 2>/dev/null || echo missing")
  if [[ "${STATUS}" == "healthy" ]]; then
    echo "    OK: MT5 healthy setelah ${i} percobaan."
    MT5_OK=true
    break
  fi
  # Jika MT5 belum di-install di volume, healthcheck akan unhealthy selamanya.
  # Itu expected — user install manual via noVNC (VPS-GUIDE Bagian 3.7).
  # Kita hanya warning, bukan error fatal.
  if [[ "${STATUS}" == "missing" ]]; then
    echo "    WARN: container lumine-mt5 tidak ditemukan. Skip MT5 health check."
    break
  fi
  sleep 5
done

if [[ "${MT5_OK}" != "true" ]] && [[ "${STATUS}" != "missing" ]]; then
  echo "    WARN: MT5 belum healthy dalam 180 detik."
  echo "    Jika MT5 belum di-install, install via noVNC: http://${VPS_HOST}:6901/vnc.html"
  echo "    Jika sudah terinstall, cek: ssh ${SSH_DEST} 'docker compose -f /opt/lumine/backend/docker-compose.prod.yml logs mt5 --tail 50'"
fi

# ── 6. Deploy marketing site (opsional) ───────────────────────────────────────
# Aktifkan dengan: DEPLOY_SITE=1 ./deploy-stack.sh
# Site berjalan di nginx :8080 (port 80/443 milik Caddy — tidak disentuh).
# Default off: alur deploy stack utama tetap sama tanpa variabel ini.
if [[ "${DEPLOY_SITE:-0}" == "1" ]]; then
  echo "==> DEPLOY_SITE=1 — menjalankan deploy-site.sh (nginx :8080)..."
  bash "${SCRIPT_DIR}/deploy-site.sh"
fi

echo "==> Deploy selesai. Service: postgres, redis, api, mt5, 9router, headroom"
echo "    noVNC (MT5 desktop): http://${VPS_HOST}:6901/vnc.html"
if [[ "${DEPLOY_SITE:-0}" == "1" ]]; then
  echo "    Site (nginx :8080):   http://${VPS_HOST}:8080/"
fi
exit 0