#!/usr/bin/env bash
# =============================================================================
# bootstrap-vps.sh — Setup awal VPS untuk stack Lumine.
#
# 1. Update sistem + install paket dasar (git, curl, etc.)
# 2. Install Docker Engine + docker compose plugin
# 3. Buat user deploy (non-root) + direktorinya
# 4. Pasang state directories untuk 9router / hermes / openclaude
#
# Pemakaian:  ./bootstrap-vps.sh [VPS_USER]
# Default VPS_USER = root  (jalan sekali saja; biasanya langsung dari root)
# =============================================================================
set -euo pipefail

TARGET_USER="${1:-root}"
echo "==> Bootstrap VPS sebagai user: ${TARGET_USER}"

# ── 1. Paket dasar ──────────────────────────────────────────────────────────
apt-get update -y
apt-get install -y \
  ca-certificates curl git gnupg lsb-release \
  unzip zip jq htop screen ufw fail2ban

# ── 2. Docker Engine + compose plugin ────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  echo "==> Menginstall Docker Engine..."
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
  systemctl enable --now docker
else
  echo "==> Docker sudah terinstall."
fi
docker --version
docker compose version

# ── 3. User deploy (opsional, non-root) ─────────────────────────────────────
if [ "${TARGET_USER}" != "root" ]; then
  if ! id "${TARGET_USER}" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "${TARGET_USER}"
    usermod -aG docker "${TARGET_USER}"
    echo "==> User ${TARGET_USER} dibuat + masuk grup docker."
  fi
fi

# ── 4. State directories (9router / hermes / openclaude) ────────────────────
mkdir -p /opt/lumine/state/{9router,hermes,openclaude}
mkdir -p /opt/lumine/state/9router/{auth,db,bin,tunnel,logs,runtime}
mkdir -p /opt/lumine/state/hermes/{memories,logs}
mkdir -p /opt/lumine/state/openclaude/{plugins,memory}

echo ""
echo "==> Bootstrap selesai."
echo "    Stack tersedia di:  /opt/lumine"
echo "    State:              /opt/lumine/state"
echo "    Next: jalankan deploy-stack.sh"
