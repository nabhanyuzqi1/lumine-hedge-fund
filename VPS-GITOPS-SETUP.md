# 🔒 VPS DEPLOYMENT CONFIGURATION GUIDE
**VPS:** 166.88.227.177  
**Date:** 2026-08-13  
**Status:** Preparing GitOps CI/CD Pipeline

---

## 📋 STEP-BY-STEP SETUP INSTRUCTIONS

### ⚠️ IMPORTANT SECURITY PRINCIPLES

1. **NEVER use your personal SSH key** (`id_rsa.priv`) for automated deployments
2. **Generate dedicated deploy key** with minimal permissions
3. **Use GitHub Secrets** for all sensitive data
4. **Rotate keys quarterly** or after personnel changes
5. **Document everything** in this guide

---

## 🔑 STEP 1: Generate Deploy SSH Key

**Execute locally** (NOT on VPS):

```bash
cd /Users/nabhan/Dev/lumine-hedge-fund

# Create dedicated deploy key
ssh-keygen -t ed25519 -f id_lumine_deploy -C "lumine-deploy@github-actions" -N ""

# This creates two files:
# - id_lumine_deploy (private key - will be stored in GitHub Secrets)
# - id_lumine_deploy.pub (public key - will be added to VPS)
```

**Expected output:**
```
Your identification has been saved in id_lumine_deploy
Your public key has been saved in id_lumine_deploy.pub
```

---

## 🖥️ STEP 2: Add Deploy Key to VPS

**Copy public key to VPS root user:**

```bash
# Method A: Copy to clipboard, then paste manually via SSH
cat /Users/nabhan/Dev/lumine-hedge-fund/id_lumine_deploy.pub
# Output: ssh-ed25519 AAAAC3NzaC1lZDI1NTE5... lumine-deploy@github-actions

# Then on VPS (manually):
ssh -i id_rsa.priv root@166.88.227.177
mkdir -p ~/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5..." >> ~/.ssh/authorized_keys
chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys
exit
```

**OR using one-liner:**
```bash
cat /Users/nabhan/Dev/lumine-hedge-fund/id_lumine_deploy.pub | ssh -i /Users/nabhan/Dev/lumine-hedge-fund/id_rsa.priv root@166.88.227.177 'mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys'
```

**Verify key works:**
```bash
# Test without password (will fail first time due to unknown host)
ssh -i /Users/nabhan/Dev/lumine-hedge-fund/id_lumine_deploy -o StrictHostKeyChecking=no root@166.88.227.177 hostname
# Expected output: host1785957413
```

---

## 🌐 STEP 3: Configure GitHub Repository Secrets

**Navigate to your repo:**
1. Go to: https://github.com/nabhanyuzqi1/lumine-hedge-fund
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret** for each item below

### Required Secrets:

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `DEPLOY_HOST` | `166.88.227.177` | VPS IP address |
| `DEPLOY_USER` | `root` | SSH username on VPS |
| `DEPLOY_SSH_KEY` | `(contents of id_lumine_deploy)` | Private deploy key (see below) |
| `DB_PASSWORD` | `(generate secure random)` | PostgreSQL password |
| `HMAC_SECRET_KEY` | `(generate random bytes)` | API authentication secret |
| `LLM_GATEWAY_API_KEY` | `(generate UUID)` | 9router gateway key |
| `VNC_PASSWORD` | `LumineVnc!2026` | MT5 desktop VNC password |

### How to get private key content:

```bash
# View private key contents
cat /Users/nabhan/Dev/lumine-hedge-fund/id_lumine_deploy

# Copy ENTIRE output including:
# -----BEGIN OPENSSH PRIVATE KEY-----
# ... base64 data ...
# -----END OPENSSH PRIVATE KEY-----
```

**PASTE into GitHub Secrets field** exactly as shown (preserve newlines!)

---

## 📝 STEP 4: Generate Environment Variables

### Option A: Use existing values (from previous deployment attempts)

Check if you have any `.env` file locally:
```bash
cd /Users/nabhan/Dev/lumine-hedge-fund
cat .env 2>/dev/null || echo "No .env file found"
```

If found, extract values and create GitHub Secrets.

### Option B: Generate new secure values

```bash
# PostgreSQL password (minimum 16 chars)
openssl rand -base64 24

# HMAC secret key (for API signing)
python3 -c "import secrets; print(secrets.token_hex(32))"

# LLM Gateway API Key (UUID format)
uuidgen

# VNC Password (already set as LumineVnc!2026 per plan)
echo "LumineVnc!2026"
```

**Example generated values:**
```bash
DB_PASSWORD=aB3$dE6$fG9$hJ2$kL5$mN8$pQ1$rS4
HMAC_SECRET_KEY=7f8e9d0c1b2a3f4e5d6c7b8a9f0e1d2c3b4a5f6e7d8c9b0a1f2e3d4c5b6a7f8e
LLM_GATEWAY_API_KEY=550e8400-e29b-41d4-a716-446655440000
VNC_PASSWORD=LumineVnc!2026
```

**⚠️ NEVER commit these to Git!** Only store in GitHub Secrets.

---

## 🏗️ STEP 5: Update .env.template File

**Create/update template file** at repository root:

```bash
cd /Users/nabhan/Dev/lumine-hedge-fund
nano .env.template
```

**Contents:**
```bash
# ============================================
# Lumine Hedge Fund Platform - Environment Template
# ============================================
# COPY THIS FILE TO .env AND FILL VALUES
# NEVER COMMIT REAL .env FILE TO GIT!

# --- Server Configuration ---
VPS_HOST=166.88.227.177
VPS_USER=root
VPS_SSH_PORT=22

# --- Database (PostgreSQL) ---
POSTGRES_DB=lumine
POSTGRES_USER=luminous_app
POSTGRES_PASSWORD=<GENERATE_SECURE_PASSWORD>
DB_HOST=postgresql
DB_PORT=5432

# --- Cache/Broker (Redis) ---
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=<OPTIONAL_SECURE_PASSWORD>

# --- API Security ---
HMAC_SECRET_KEY=<GENERATE_RANDOM_64_CHAR_HEX>
JWT_SECRET_KEY=<GENERATE_RANDOM_64_CHAR_HEX>
CORIS_ACCESS_TOKEN=<GENERATE_IF_USING_CORIS>

# --- LLM Gateway (9router) ---
LLM_GATEWAY_URL=https://api.9router.com/v1
LLM_GATEWAY_API_KEY=<GENERATE_UUID_OR_API_KEY>

# --- Application Settings ---
APP_NAME=Lumine Hedge Fund
APP_ENV=production
LOG_LEVEL=INFO

# --- MT5 Connection ---
MT5_SERVER=<YOUR_MT5_SERVER>
MT5_LOGIN=<YOUR_MT5_LOGIN>
MT5_PASSWORD=<YOUR_MT5_PASSWORD>
MT5_DOMAIN=<YOUR_MT5_DOMAIN>

# --- VNC Access for MT5 Desktop ---
VNC_PASSWORD=LumineVnc!2026

# --- Backup Configuration ---
BACKUP_DIR=/root/lumine-backups
BACKUP_RETENTION_DAYS=7
GITHUB_BACKUP_REPO=<OPTIONAL_GITHUB_REPO_URL>
GITHUB_BACKUP_TOKEN=<OPTIONAL_PERSONAL_ACCESS_TOKEN>

# --- Monitoring & Alerts ---
SLACK_WEBHOOK_URL=<OPTIONAL_SLACK_INCOMING_WEBHOOK>
PAGERDUTY_ROUTING_KEY=<OPTIONAL_PAGERDUTY_KEY>

# --- Feature Flags ---
INSTALL_9ROUTER=true
INSTALL_HERMES=true
INSTALL_OPENCLAUDE=false
INSTALL_LUMINE=true
INSTALL_DOCKER=true
```

**Save as:** `.env.template` (template with placeholders)  
**Do NOT save as:** `.env` (real secrets file - gitignored)

---

## 🔄 STEP 6: Push Configuration to Git

Now that all secrets are configured properly:

```bash
cd /Users/nabhan/Dev/lumine-hedge-fund

# Verify .gitignore includes sensitive files
grep -E "^\.env$|^id_\w+(_deploy)?$" .gitignore

# Add template file
git add .env.template

# Commit only non-sensitive changes
git commit -m "chore: add environment template for production deployment"

# Push to main branch
git push origin main
```

**✅ Verification Checklist:**
- [ ] `.env` file is in `.gitignore` (should never be committed)
- [ ] All secrets uploaded to GitHub Actions
- [ ] Deploy key tested successfully via SSH
- [ ] Template file matches current requirements

---

## 🚀 STEP 7: Trigger First Deployment

Once all secrets are configured:

**Option A: Manual Trigger via GitHub UI**
1. Go to: https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions
2. Select **"Deploy"** workflow
3. Click **"Run workflow"** button
4. Choose branch: `main`
5. Click **"Run workflow"** again to execute

**Option B: Automatic on Push**
- Workflow already configured to auto-deploy on push to `main` branch
- Simply push code changes and monitoring kicks in

---

## 🛡️ SECURITY AUDIT CHECKLIST

Before going live, verify:

- [ ] ✅ Deploy key separate from personal SSH keys
- [ ] ✅ Keys not hardcoded anywhere
- [ ] ✅ Only needed users have access to repo
- [ ] ✅ GitHub Actions audit logs reviewed
- [ ] ✅ Firewall allows only necessary ports
- [ ] ✅ SSH password authentication disabled on VPS
- [ ] ✅ Fail2Ban installed and running
- [ ] ✅ SSL/TLS certificates managed (via Caddy auto-HTTPS)
- [ ] ✅ Regular key rotation schedule established
- [ ] ✅ Emergency rollback procedure documented

---

## 🆘 EMERGENCY PROCEDURES

### Revoke Deploy Key (if compromised):
```bash
# Remove from VPS
ssh -i id_rsa.priv root@166.88.227.177
rm ~/.ssh/authorized_keys
# Regenerate new key and update GitHub Secrets
```

### Rollback Deployment:
```yaml
# In deploy.yml workflow file, add:
- name: Rollback on failure
  if: failure()
  run: |
    # Execute rollback script
    ./scripts/deploy/rollback.sh --to=previous-release
```

### Emergency Access:
Keep personal key (`id_rsa.priv`) accessible offline as backup!

---

## 📞 SUPPORT & DOCUMENTATION

- **GitHub Actions Docs:** https://docs.github.com/en/actions
- **SSH Key Management:** https://docs.github.com/en/authentication/connecting-to-github-with-ssh
- **Fail2Ban Guide:** https://www.fail2ban.org/wiki/index.php/Main_Page
- **Docker Security:** https://docs.docker.com/engine/security/

---

**NEXT STEPS:**
1. Generate deploy key (Step 1)
2. Upload secrets to GitHub (Steps 3-4)
3. Push template file (Step 6)
4. Trigger deployment (Step 7)

**Questions? Review documentation above before proceeding!** ✨ ~★~
