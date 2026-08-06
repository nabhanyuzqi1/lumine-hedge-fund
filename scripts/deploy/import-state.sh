#!/usr/bin/env bash
# =============================================================================
# import-state.sh — Kirim state agent (9router/hermes/openclaude) ke VPS.
#
# Memakai tar.gz hasil export-state.sh. File dikirim via scp → langsung direstore.
# TIDAK lewat git — file state bukan bagian repo.
#
# Pemakaian:  ./import-state.sh <tar.gz> [VPS_HOST] [VPS_USER]
# Contoh:     ./import-state.sh state-exports/20260805-153000.tar.gz
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source ./.env; set +a
fi

ARCHIVE="${1:?Berikan path ke tar.gz hasil export}"
VPS_HOST="${2:-${VPS_HOST:?VPS_HOST wajib (arg ke-2 atau .env)}}"
VPS_USER="${3:-${VPS_USER:-root}}"
VPS_SSH_PORT="${VPS_SSH_PORT:-22}"

if [[ ! -f "${ARCHIVE}" ]]; then
  echo "ERROR: ${ARCHIVE} tidak ditemukan."
  exit 1
fi

DEST="${VPS_USER}@${VPS_HOST}"
REMOTE=/opt/lumine/state

echo "==> Kirim ${ARCHIVE} ke ${DEST}..."
scp -P "${VPS_SSH_PORT}" "${ARCHIVE}" "${DEST}:/tmp/lumine-state.tar.gz"

echo "==> Ekstrak ke ${REMOTE}/ ..."
ssh -p "${VPS_SSH_PORT}" "${DEST}" \
  "mkdir -p ${REMOTE} && tar -xzf /tmp/lumine-state.tar.gz -C ${REMOTE} && rm -f /tmp/lumine-state.tar.gz"

echo "==> Beres. Cek isi:"
ssh -p "${VPS_SSH_PORT}" "${DEST}" "ls -la ${REMOTE}/"

echo ""
echo "Next steps di VPS:"
echo "  1. Set ulang env HERMES_CUSTOM_9ROUTER_API_KEY (token 9router lama mungkin berubah)."
echo "  2. Restart 9router/hermes/openclaude (lihat systemd/lumine*.service)."