#!/bin/bash
# ============================================
# Lumine VPS Bootstrap Script
# Purpose: Install all prerequisites on FRESH Ubuntu 24.04 server
# Usage: Can be run manually OR via CI/CD GitHub Actions
# ============================================

set -e

echo "=========================================="
echo "🦞 LUMINE VPS INITIAL SETUP SCRIPT"
echo "=========================================="
echo ""
echo "This script will:"
echo "1. Update and upgrade system packages"
echo "2. Install Docker & Docker Compose"
echo "3. Configure firewall and security"
echo "4. Create directory structure"
echo "5. Deploy control plane services"
echo ""
read -p "Press Enter to continue..." || true

# ──────────────────────────────────────────────────────────
# STEP 1: System Update & Prerequisites
# ──────────────────────────────────────────────────────────

echo "[1/6] Updating system packages..."
apt update
apt upgrade -y

echo "[1/6] Installing required packages..."
apt install -y curl wget git vim net-tools ufw fails2ban

echo "[1/6] ✅ System update complete!"

# ──────────────────────────────────────────────────────────
# STEP 2: Install Docker Engine
# ──────────────────────────────────────────────────────────

echo "[2/6] Installing Docker Engine..."

# Add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Add repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Verify installation
docker --version
docker compose version

echo "[2/6] ✅ Docker installed successfully!"

# ──────────────────────────────────────────────────────────
# STEP 3: Configure Firewall & Security
# ──────────────────────────────────────────────────────────

echo "[3/6] Configuring firewall..."

# Allow only necessary ports
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw allow 20128/tcp # 9router LLM gateway (if needed directly)
ufw default deny incoming
ufw default allow outgoing
ufw --force enable

echo "[3/6] Firewall configured!"

echo "[3/6] Installing Fail2Ban..."
apt install -y fail2ban
systemctl enable fail2ban
systemctl start fail2ban

echo "[3/6] ✅ Security configured!"

# ──────────────────────────────────────────────────────────
# STEP 4: Create Directory Structure
# ──────────────────────────────────────────────────────────

echo "[4/6] Creating directory structure..."

mkdir -p /opt/lumine/backend
mkdir -p /opt/lumine/backend/scripts/deploy
mkdir -p /srv/control-plane/caddy
mkdir -p /srv/control-plane/authelia
mkdir -p /srv/control-plane/homepage
mkdir -p /srv/control-plane/uptime-kuma
mkdir -p /root/lumine-backups

chmod 700 /root/lumine-backups

echo "[4/6] ✅ Directories created!"

# ──────────────────────────────────────────────────────────
# STEP 5: Clone Repository & Setup Backend Services
# ──────────────────────────────────────────────────────────

echo "[5/6] Cloning Lumine repository..."

# Check if Git clone token needed (for private repos)
if [ -n "$GITHUB_TOKEN" ]; then
    REPO_URL="https://x-access-token:${GITHUB_TOKEN}@github.com/nabhanyuzqi1/lumine-hedge-fund.git"
else
    REPO_URL="https://github.com/nabhanyuzqi1/lumine-hedge-fund.git"
fi

cd /opt/lumine
git clone $REPO_URL . || echo "Note: Git clone may need authentication token"

echo "[5/6] Repository cloned!"

# ──────────────────────────────────────────────────────────
# STEP 6: Deploy Infrastructure & Control Plane
# ──────────────────────────────────────────────────────────

echo "[6/6] Deploying control plane services..."

cd /opt/lumine

# Check if .env file exists, if not create from template
if [ ! -f "/opt/lumine/.env" ]; then
    echo "Creating .env from template..."
    cp .env.template .env
    
    # If no template, create minimal env
    if [ ! -f ".env" ]; then
        cat > .env << 'ENVEOF'
DB_PASSWORD=CHANGE_ME_IN_SECURE_STORAGE
HMAC_SECRET_KEY=CHANGE_ME_IN_SECURE_STORAGE
LLM_GATEWAY_API_KEY=CHANGE_ME_IN_SECURE_STORAGE
VNC_PASSWORD=LumineVnc!2026
ENVEOF
        chmod 600 .env
    fi
fi

# Start control plane services
cd /opt/lumine/infrastructure/control-plane
docker compose up -d

echo "[6/6] Control plane deployed!"

# ──────────────────────────────────────────────────────────
# FINAL VERIFICATION
# ──────────────────────────────────────────────────────────

echo ""
echo "=========================================="
echo "✅ INITIAL SETUP COMPLETE!"
echo "=========================================="
echo ""
echo "Services deployed:"
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "Control plane accessible at:"
echo "  Homepage:    http://166.88.227.177/homepage/"
echo "  Uptime Kuma: http://166.88.227.177/uptime-kuma/"
echo "  Dozzle:      http://166.88.227.177/dozzle/"
echo ""
echo "Next steps:"
echo "1. Copy secrets into /opt/lumine/.env file"
echo "2. Push to main branch to trigger CI/CD deployment"
echo "3. Monitor workflow at: https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions"
echo ""
echo "⚠️ IMPORTANT: Change DB_PASSWORD and other secrets in secure storage!"
echo "=========================================="
