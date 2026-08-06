#!/usr/bin/env bash
# =============================================================================
# export-state.sh — Paket state lokal (9router/hermes/openclaude) → tar.gz.
#
# Hasil disimpan di: scripts/deploy/state-exports/<timestamp>.tar.gz
# File ini TIDAK di-commit (lihat .gitignore di folder ini).
#
# Pemakaian:  ./export-state.sh [--skip-openclaude]
# Catatan: state berisi kredensial (token, jwt-secret, session). Berhati-hati.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"
mkdir -p state-exports

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="state-exports/${STAMP}.tar.gz"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

copy_state() {
  local name="$1" src="$2"
  if [[ -d "${src}" ]]; then
    echo "==> ${name}: ${src}"
    mkdir -p "${WORK}/${name}"
    cp -R "${src}/." "${WORK}/${name}/"
  else
    echo "    (skip) ${src} tidak ditemukan"
  fi
}

copy_state 9router   "${HOME}/.9router"
copy_state hermes    "${HOME}/.hermes"
copy_state openclaude "${HOME}/.openclaude"

if [[ -x "${HOME}/.local/bin/hermes" ]]; then
  echo "==> hermes binary: ~/.local/bin/hermes"
  mkdir -p "${WORK}/bin"
  cp "${HOME}/.local/bin/hermes" "${WORK}/bin/hermes"
fi

if [[ ! -d "${WORK}/9router" && ! -d "${WORK}/hermes" && ! -d "${WORK}/openclaude" ]]; then
  echo "ERROR: tidak ada state yang ditemukan di HOME. Tidak ada yang diekspor."
  exit 1
fi

tar -czf "${OUT}" -C "${WORK}" .
echo ""
echo "==> Ekspor selesai: ${OUT}"
echo "    Ukuran: $(du -h "${OUT}" | cut -f1)"
echo "    Next:   ./import-state.sh ${OUT}"