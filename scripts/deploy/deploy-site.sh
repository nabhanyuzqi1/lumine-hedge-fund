#!/usr/bin/env bash
# =============================================================================
# deploy-site.sh — Build + deploy marketing site (site/) ke VPS via nginx :8080.
#
# Alur:
#   1. Baca .env (kredensial target VPS; JANGAN commit).
#   2. Build site lokal: npm ci && npm run build (base './' → site/dist).
#   3. Kirim dist + nginx config ke VPS via scp (staging /tmp, lalu install).
#   4. Install config nginx (listen 8080 — port 80/443 milik Caddy, JANGAN sentuh).
#   5. ufw allow 8080/tcp + restart nginx.
#   6. Health check http://localhost:8080.
#
# Pemakaian:  ./deploy-site.sh
# Prasyarat:  file .env (copy dari .env.sample), ssh key ke VPS, Node.js 20+ lokal.
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

SITE_DIR="${SCRIPT_DIR}/../../site"
NGINX_CONF="nginx-lumine-site.conf"
REMOTE_DIST=/var/www/lumine
REMOTE_CONF=/etc/nginx/sites-available/lumine

[[ -f "${NGINX_CONF}" ]] || { echo "ERROR: ${NGINX_CONF} tidak ditemukan."; exit 1; }

echo "==> Target: ${SSH_DEST} (port ${VPS_SSH_PORT})"

# ── 1. Build site (base './' → kompatibel GH Pages subpath & VPS root) ───────
echo "==> Build site (npm ci + npm run build)..."
(
  cd "${SITE_DIR}"
  npm ci --no-audit --no-fund
  npm run build
)

# ── 2. Kirim dist + nginx config (staging /tmp, tulis-disk tanpa sudo) ───────
echo "==> Mengirim dist dan nginx config ke remote..."
ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" "rm -rf /tmp/lumine-dist && mkdir -p /tmp/lumine-dist"
scp -P "${VPS_SSH_PORT}" -r "${SITE_DIR}/dist/." "${SSH_DEST}:/tmp/lumine-dist/"
scp -P "${VPS_SSH_PORT}" "${NGINX_CONF}" "${SSH_DEST}:/tmp/lumine-site.conf"

# ── 3. Install site + config nginx (idempotent) ───────────────────────────────
echo "==> Install ke ${REMOTE_DIST} + config nginx (listen 8080)..."
ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" \
  "sudo rm -rf ${REMOTE_DIST} && sudo mkdir -p ${REMOTE_DIST} && sudo cp -r /tmp/lumine-dist/. ${REMOTE_DIST}/ && sudo chown -R www-data:www-data ${REMOTE_DIST}"
ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" \
  "sudo cp /tmp/lumine-site.conf ${REMOTE_CONF} && sudo ln -sf ${REMOTE_CONF} /etc/nginx/sites-enabled/lumine"
ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" "sudo ufw allow 8080/tcp >/dev/null 2>&1 || true"
ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" "sudo nginx -t"
ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" \
  "sudo systemctl enable nginx >/dev/null 2>&1 || true; sudo systemctl restart nginx"

# ── 4. Health check ───────────────────────────────────────────────────────────
echo "==> Health check site (maks 60 detik)..."
SITE_OK=false
for i in $(seq 1 30); do
  if ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" \
      "curl -sf http://localhost:8080/ >/dev/null 2>&1"; then
    echo "    OK: site live setelah ${i} percobaan."
    SITE_OK=true
    break
  fi
  sleep 2
done

if [[ "${SITE_OK}" != "true" ]]; then
  echo "ERROR: site tidak respond di :8080. Cek: ssh ${SSH_DEST} 'sudo journalctl -u nginx -n 50'"
  exit 1
fi

echo "==> Deploy site selesai: http://${VPS_HOST}:8080/"
echo "    GitHub Pages (jalur kedua): https://nabhanyuzqi1.github.io/lumine-hedge-fund/"
exit 0
