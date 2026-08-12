#!/bin/bash
# Generate secure values untuk .env file
# Jalankan script ini di mesin lokal (bukan VPS) untuk produce values aman

echo "================================================"
echo "Generate Secure Values for Lumine Environment"
echo "================================================"
echo ""

# PostgreSQL Password (32 karakter random)
echo "1. PostgreSQL Password:"
DB_PASSWORD=$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)
echo "$DB_PASSWORD" | md5sum | cut -c1-32
read -p "Copy password atau generate baru? [y/n]: " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    DB_PASSWORD="lumine-admin-2026!"
fi
echo "   Result: $DB_PASSWORD"
echo ""

# HMAC Secret Key (64 karakter hex)
echo "2. HMAC Secret Key:"
HMAC_SECRET_KEY=$(openssl rand -hex 32)
echo "   Generated: $HMAC_SECRET_KEY"
echo ""

# 9router API Key (UUID format)
echo "3. 9router API Key:"
LLM_GATEWAY_API_KEY=$(cat /proc/sys/kernel/random/uuid)
echo "   Generated: $LLM_GATEWAY_API_KEY"
echo ""

# Session Secret for Authelia (64 characters hex)
echo "4. Authelia Session Secret:"
AUTH_SESSION_SECRET=$(openssl rand -hex 32)
echo "   Generated: $AUTH_SESSION_SECRET"
echo ""

# Storage Encryption Key for Authelia (32 base64 encoded)
echo "5. Authelia Storage Encryption Key:"
AUTH_STORAGE_KEY=$(openssl rand -base64 32 | tr -d '\n' | head -c 32)
echo "   Generated: $AUTH_STORAGE_KEY"
echo ""

# VNC Password for MT5 (minimal 6 chars)
echo "6. VNC Password for MT5:"
read -p "Enter VNC password (min 6 chars): " -s VNC_PASSWORD
echo ""
if [ ${#VNC_PASSWORD} -lt 6 ]; then
    echo "Warning: Password too short, using default..."
    VNC_PASSWORD="lumine-mt5-vnc-2026"
fi
echo "   Result: *** (hidden)"
echo ""

# GitHub Token for Backup (optional - personal access token with repo scope)
echo "7. GitHub Token for Backup:"
read -p "Enter GitHub Personal Access Token (optional, press enter to skip): " GITHUB_BACKUP_TOKEN
if [ -z "$GITHUB_BACKUP_TOKEN" ]; then
    GITHUB_BACKUP_TOKEN=""
    echo "   No backup token set"
else
    echo "   Token configured (first 8 chars): ${GITHUB_BACKUP_TOKEN:0:8}..."
fi
echo ""

# ============================================
# Write .env file
# ============================================
echo "================================================"
echo "Writing .env file to scripts/deploy/.env"
echo "================================================"

cat > .env << EOF
# =============================================================================
# Lumine Production Environment Configuration
# 
# WARNING: This file contains SECRET credentials!
# - DO NOT commit this file to git
# - DO not share this file
# - Use .env.sample as template only
# =============================================================================

# ── Target VPS ──────────────────────────────────────────────────────────────
VPS_HOST=166.88.227.177
VPS_USER=root
VPS_SSH_PORT=22

# ── Database ────────────────────────────────────────────────────────────────
# PostgreSQL credentials for backend services
DB_PASSWORD=${DB_PASSWORD}
DB_USER=lumine
DB_NAME=lumine

# ── API & Gateway ───────────────────────────────────────────────────────────
# Cryptographic secrets for API authentication and signing
HMAC_SECRET_KEY=${HMAC_SECRET_KEY}

# 9router LLM Gateway API key (for AI agent authentication)
LLM_GATEWAY_API_KEY=${LLM_GATEWAY_API_KEY}

# ── Authelia Configuration ──────────────────────────────────────────────────
# Two-factor authentication service for control plane dashboards
# Note: User 'admin' has password stored in Authelia config (not here)
# See: infrastructure/control-plane/authelia/configuration.yml
AUTHIALIZATION_DOMAINS=166.88.227.177
AUTHEDIA_REMEMBER_DOMAIN=166.88.227.177
AUTHEDIA_REMEMBER_FOR=5m
AUTHERIA_SESSION_SECRET=${AUTH_SESSION_SECRET}
AUTHERIA_STORAGE_ENCRYPTION_KEY=${AUTH_STORAGE_KEY}

# ── Git & Backup ────────────────────────────────────────────────────────────
# Repository configuration for code and backups
GITHUB_REPO=nabhanyuzqi1/lumine-hedge-fund
GITHUB_BACKUP_REPO=nabhanyuzqi1/lumine-backups
GITHUB_BACKUP_TOKEN=${GITHUB_BACKUP_TOKEN:-}

# Backup configuration
BACKUP_DIR=/root/lumine-backups
BACKUP_RETENTION_DAYS=7

# ── Optional Components ─────────────────────────────────────────────────────
# Set true/false to enable/disable specific services
INSTALL_9ROUTER=true
INSTALL_HERMES=true
INSTALL_OPENCLAUDE=true
INSTALL_LUMINE=true
INSTALL_DOCKER=true

# ── MT5 / VNC (Wine in Docker) ──────────────────────────────────────────────
# Password for noVNC browser + traditional VNC client access to MT5 desktop
# Minimum 6 characters required
VNC_PASSWORD=${VNC_PASSWORD}

# Display resolution for MT5 Wine container
RESOLUTION=1280x768x24

# ── Frontend Configuration ──────────────────────────────────────────────────
# Landing page deployment target
LANDING_DEPLOY_PATH=/var/www/lumine
EOF

chmod 600 .env

echo ""
echo "================================================"
echo "SUCCESS: .env file created at $(pwd)/.env"
echo "Permissions: 600 (owner read/write only)"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Review the values in $(pwd)/.env"
echo "2. Copy to scripts/deploy/ directory:"
echo "   cp .env scripts/deploy/"
echo "3. Test deployment:"
echo "   cd scripts/deploy && ./deploy-stack.sh"
echo ""
echo "IMPORTANT: NEVER commit .env to git!"
echo "The file is already added to .gitignore"
