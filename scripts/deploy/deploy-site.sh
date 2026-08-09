#!/usr/bin/env bash
# =============================================================================
# deploy-site.sh — Build + deploy marketing site (site/) ke VPS.
#
# Landing page disajikan lewat Caddy `/` (dan alias legacy `/site*`) →
# container `control-landing` (nginx:alpine, compose control-plane) yang
# bind-mount read-only `/var/www/lumine` (2026-08-09 — host nginx sudah
# dinonaktifkan; jangan hidupkan lagi, port 8080 dipakai container).
#
# Alur:
#   1. Baca .env (kredensial target VPS; JANGAN commit).
#   2. Build site lokal: npm ci && npm run build (base './' → site/dist).
#   3. Kirim dist ke VPS via scp (staging /tmp).
#   4. Deploy KEDALAM `/var/www/lumine` — jangan pernah `rm -rf` +
#      `mkdir` ulang direktori ini: bind mount nginx terkunci ke inode,
#      direktori baru tidak terlihat container (insiden 2026-08-09).
#   5. Health check http://127.0.0.1:8080 (via container).
#
# Pemakaian:  ./deploy-site.sh
# Prasyarat:  file .env (copy dari .env.sample), ssh key ke VPS,
#             Node.js 20+ lokal.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# CI mode: env vars sudah di-set oleh workflow (lewati .env).
# Local mode: baca .env (jangan commit — berisi kredensial VPS).
if [[ -n "${VPS_HOST:-}" ]]; then
  echo "==> CI mode — env vars sudah diset (skip .env)."
else
  if [[ ! -f .env ]]; then
    echo "ERROR: .env tidak ditemukan. Copy dari .env.sample dulu:"
    echo "  cp .env.sample .env && \$EDITOR .env"
    exit 1
  fi
  # shellcheck disable=SC1091
  set -a; source ./.env; set +a
fi

VPS_HOST="${VPS_HOST:?VPS_HOST wajib di .env}"
VPS_USER="${VPS_USER:-root}"
VPS_SSH_PORT="${VPS_SSH_PORT:-22}"
SSH_DEST="${VPS_USER}@${VPS_HOST}"

SITE_DIR="${SCRIPT_DIR}/../../site"
REMOTE_DIST=/var/www/lumine

echo "==> Target: ${SSH_DEST} (port ${VPS_SSH_PORT})"

# ── 1. Build site (base './' → kompatibel GH Pages subpath & VPS root) ───────
echo "==> Build site (npm ci + npm run build)..."
(
  cd "${SITE_DIR}"
  npm ci --no-audit --no-fund
  npm run build
)

# ── 2. Kirim dist (staging /tmp) ─────────────────────────────────────────────
echo "==> Mengirim dist ke remote..."
ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" "rm -rf /tmp/lumine-dist && mkdir -p /tmp/lumine-dist"
scp -P "${VPS_SSH_PORT}" -r "${SITE_DIR}/dist/." "${SSH_DEST}:/tmp/lumine-dist/"

# ── 3. Install — in-place copy; HANYA hapus isi lama, JANGAN rm direktori
#        (bind mount nginx terkunci ke inode — insiden 2026-08-09) ────────────
echo "==> Install ke ${REMOTE_DIST} (in-place; bind mount container)..."
ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" \
  "find ${REMOTE_DIST} -mindepth 1 -delete && cp -a /tmp/lumine-dist/. ${REMOTE_DIST}/"

# ── 4. Health check ───────────────────────────────────────────────────────────
echo "==> Health check site (maks 60 detik)..."
SITE_OK=false
for i in $(seq 1 30); do
  if ssh -p "${VPS_SSH_PORT}" "${SSH_DEST}" \
      "curl -sf http://127.0.0.1:8080/ >/dev/null 2>&1"; then
    echo "    OK: site live setelah ${i} percobaan."
    SITE_OK=true
    break
  fi
  sleep 2
done

if [[ "${SITE_OK}" != "true" ]]; then
  echo "ERROR: site tidak respond di :8080. Cek: docker logs control-landing"
  exit 1
fi

echo "==> Deploy site selesai: https://${VPS_HOST}/ (lewat Caddy)"
echo "    Alias legacy: https://${VPS_HOST}/site/"
exit 0
