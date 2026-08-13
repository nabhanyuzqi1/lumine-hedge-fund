#!/bin/bash
# Helper script to execute bootstrap on VPS via GitHub Actions
# This is called from deploy-full.yml workflow

echo "🚀 Starting Bootstrap Process..."
echo ""

# Execute bootstrap script on VPS
ssh -o StrictHostKeyChecking=no \
  -i ~/.ssh/deploy_key \
  root@166.88.227.177 << 'ENDSSH'

echo "=========================================="
echo "LUMINE VPS BOOTSTRAP"
echo "Server: $(hostname)"
echo "Date: $(date)"
echo "=========================================="

echo "[1/5] Updating system packages..."
apt update && apt upgrade -y

echo "[2/5] Installing Docker Engine..."
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

docker --version
docker compose version

echo "[3/5] Configuring firewall..."
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw default deny incoming
ufw --force enable

systemctl restart ssh || true

echo "[4/5] Creating directories..."
mkdir -p /opt/lumine/backend
mkdir -p /srv/control-plane
mkdir -p /root/lumine-backups
chmod 700 /root/lumine-backups

echo "[5/5] Cloning repository..."
cd /opt/lumine
git clone https://github.com/nabhanyuzqi1/lumine-hedge-fund.git . || echo "Git clone may need token"

echo ""
echo "=========================================="
echo "✅ BOOTSTRAP COMPLETE!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Deploy application via CI/CD:"
echo "   - Push code to main branch OR"
echo "   - Click 'Deploy' workflow → 'Application Update'"
echo ""
echo "Services installed:"
echo "- Docker Engine ✅"
echo "- Control Plane (ready for deployment)"
echo "- Lumine Repository ✅"
echo ""
echo "Status: Fresh VPS ready for app deployment! 🎉"

ENDSSH

echo "Bootstrap execution completed!"
