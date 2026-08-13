# 🎯 STEP-BY-STEP GITHUB SECRETS SETUP

**Goal:** Upload all required secrets to GitHub Actions  
**Time:** ~10 minutes total  
**Status:** ✅ All values generated and ready!

---

## ⚠️ BEFORE YOU START

### IMPORTANT: Add Deploy Key to VPS FIRST!

**You MUST add the deploy public key to VPS before uploading secrets, or deployment will fail!**

### Step A: Copy Public Key to Clipboard

**In terminal:**
```bash
cat /Users/nabhan/Dev/lumine-hedge-fund/id_lumine_deploy.pub
```

**Output will be:**
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIASAx7vjJb9yj+i0eSrmKUU0RQRW1U9/B2TMhb4CMEjk lumine-deploy@github-actions
```

**Action:** Select and copy this ENTIRE line (from `ssh-ed25519` to `github-actions`)

### Step B: Add to VPS

**Option 1: Manual method (Recommended)**

1. SSH into VPS:
   ```bash
   ssh -i id_rsa.priv root@166.88.227.177
   ```

2. Inside VPS terminal, paste these commands:
   ```bash
   mkdir -p ~/.ssh && chmod 700 ~/.ssh
   echo "PASTE_PUBLIC_KEY_HERE" >> ~/.ssh/authorized_keys
   chmod 600 ~/.ssh/authorized_keys
   exit
   ```
   Replace `"PASTE_PUBLIC_KEY_HERE"` with the actual key you copied above.

3. **Verify it works:** Exit VPS, then test:
   ```bash
   ssh -i id_lumine_deploy -o StrictHostKeyChecking=no root@166.88.227.177 hostname
   ```
   
   Expected output: `host1785957413` ✅

---

## 🔧 UPLOAD GITHUB SECRETS

### Navigate to Settings

1. Open browser
2. Go to: https://github.com/nabhanyuzqi1/lumine-hedge-fund
3. Click **"Settings"** tab (top menu)
4. Scroll down to **"Secrets and variables"** → **"Actions"**
5. Click **"New repository secret"** button

---

### Secret #1: DEPLOY_HOST

**Click "New repository secret":**

| Field | Value |
|-------|-------|
| **Name** | `DEPLOY_HOST` |
| **Secret** | `166.88.227.177` |

✅ Click **"Add secret"**

---

### Secret #2: DEPLOY_USER

**Click "New repository secret":**

| Field | Value |
|-------|-------|
| **Name** | `DEPLOY_USER` |
| **Secret** | `root` |

✅ Click **"Add secret"**

---

### Secret #3: DEPLOY_SSH_KEY ⚠️ MOST CRITICAL!

This is where most people make mistakes! Follow carefully:

**Step 1:** Get your private key content

In terminal, run:
```bash
cat /Users/nabhan/Dev/lumine-hedge-fund/id_lumine_deploy
```

**What you'll see:**
```
-----BEGIN OPENSSH PRIVATE KEY-----
base64-encoded-private-key-data-here-that-spans-many-lines
-----END OPENSSH PRIVATE KEY-----
```

**Step 2:** Copy EVERYTHING from output

Select from `-----BEGIN` ALL the way through `-----END` including:
- The BEGIN line
- All base64 encoded lines (may span multiple lines!)
- The END line

**Step 3:** Paste into GitHub

| Field | Value |
|-------|-------|
| **Name** | `DEPLOY_SSH_KEY` |
| **Secret** | **[PASTE YOUR ENTIRE KEY HERE]** |

**⚠️ Common mistakes to avoid:**
- ❌ Don't type manually
- ❌ Don't miss any lines
- ❌ Don't include extra spaces
- ❌ Don't forget BEGIN/END lines

✅ Click **"Add secret"**

---

### Secret #4: DB_PASSWORD

| Field | Value |
|-------|-------|
| **Name** | `DB_PASSWORD` |
| **Secret** | `yzLhGc2qeifCJez9OD03/pEFs05AMhlS` |

✅ Click **"Add secret"**

---

### Secret #5: HMAC_SECRET_KEY

| Field | Value |
|-------|-------|
| **Name** | `HMAC_SECRET_KEY` |
| **Secret** | `0d3dee77334f2dcb16dbf49d9f456050f874afb555220f01e669934f759cef7` |

✅ Click **"Add secret"**

---

### Secret #6: LLM_GATEWAY_API_KEY

| Field | Value |
|-------|-------|
| **Name** | `LLM_GATEWAY_API_KEY` |
| **Secret** | `D0B0A341-BE77-4C9F-AA86-0728BCA46998` |

✅ Click **"Add secret"**

---

### Secret #7: VNC_PASSWORD

| Field | Value |
|-------|-------|
| **Name** | `VNC_PASSWORD` |
| **Secret** | `LumineVnc!2026` |

✅ Click **"Add secret"**

---

## ✅ VERIFICATION CHECKLIST

After adding all 7 secrets, go back to Secrets page:

You should see:
- [ ] DEPLOY_HOST ••••••
- [ ] DEPLOY_USER ••••••
- [ ] DEPLOY_SSH_KEY ••••••
- [ ] DB_PASSWORD ••••••
- [ ] HMAC_SECRET_KEY ••••••
- [ ] LLM_GATEWAY_API_KEY ••••••
- [ ] VNC_PASSWORD ••••••

(All show as bullet points for security - that's normal!)

---

## 🚀 TRIGGER FIRST DEPLOYMENT

Now you're ready to deploy!

### Option 1: Manual Trigger

1. Go to: https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions
2. Find **"Deploy"** workflow under Recent workflows
3. Click **"Run workflow"** button (right side)
4. Dropdown "Branch": Select `main`
5. Click blue **"Run workflow"** button again

**Wait time:** 8-12 minutes

Watch logs progress:
- ✅ Pre-flight checks
- 🏗️ Build backend container
- 🚀 Deploy to VPS
- ✓ Health verification
- 💾 Backup creation

### Option 2: Automatic (Push to main)

Just push a tiny change to trigger auto-deployment:

```bash
git add .
git commit -m "chore: update CI/CD configuration"
git push origin main
```

Workflow will auto-trigger on push to `main`.

---

## 📊 MONITORING DEPLOYMENT

While deploying, watch GitHub Actions:

1. Go to: https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions
2. Look for your latest workflow run
3. Click to view details
4. Expand each job to see logs

**Expected successful flow:**
1. `preflight-checks` → ✅ green checkmark
2. `build-backend` → ✅ green checkmark
3. `deploy` → ✅ green checkmark
4. `backup` → ✅ green checkmark
5. Overall workflow → ✅ SUCCESS

**If you see failures:**
- Red ❌ means job failed
- Click the red job to see detailed error
- Most common issue: Wrong SSH key format

---

## 🔍 VERIFY DEPLOYMENT SUCCESS

### Check GitHub Actions
- Workflow shows ✅ SUCCESS
- All jobs completed without errors

### SSH into VPS
```bash
ssh -i id_lumine_deploy root@166.88.227.177
```

### Verify services
```bash
# List all containers
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Expected running:
# postgresql   Up (healthy)
# redis        Up (healthy) 
# backend-api  Up (healthy)
# mt5          Up (starting)
# 9router      Up
# headroom     Up
```

### Test API health
```bash
curl http://localhost:8000/api/health
```

Expected response:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-08-13T..."
}
```

### Check database
```bash
docker exec postgresql pg_isready -U luminous_app
# Output: "accepting connections"
```

### Check Redis
```bash
docker exec redis redis-cli ping
# Output: PONG
```

---

## 🆘 TROUBLESHOOTING

### Issue: Workflow fails at "Setup SSH"

**Symptoms:** "Permission denied (publickey)"  
**Cause:** SSH key mismatch or wrong format  

**Fix:**
1. Delete `DEPLOY_SSH_KEY` secret
2. Re-run: `cat id_lumine_deploy` in terminal
3. Copy ENTIRE output (all lines from BEGIN to END)
4. Create new secret with exact same content
5. Retry deployment

### Issue: Containers won't start

**Symptoms:** `docker compose up` succeeds but services unhealthy  
**Cause:** Missing environment variables  

**Fix:**
1. Verify all 7 secrets are present in GitHub
2. Check secret values are correct (especially passwords)
3. View deployment logs: GitHub Actions → Run log → `deploy` job → `Create .env on VPS` step
4. Manually SSH and check `/opt/lumine/.env` file exists

### Issue: Backend API returns 500 error

**Symptoms:** Container starts but `/api/health` fails  
**Cause:** Database migration incomplete or connection refused  

**Fix:**
```bash
# SSH into VPS
ssh -i id_lumine_deploy root@166.88.227.177

# Check backend logs
cd /opt/lumine/backend
docker logs backend-api --tail 50

# Look for database connection errors
# If missing migrations:
docker exec postgresql psql -U luminous_app -d lumines -c "SELECT version();"

# Apply migrations manually
docker exec backend-api python -m alembic upgrade head
```

---

## ✨ SUCCESS!

If everything worked:

✅ Workflow completed successfully  
✅ All containers running healthy  
✅ API responding to health checks  
✅ Database accepting connections  
✅ Redis responding  

**Your Lumine platform is now deployed via GitOps CI/CD!** 🎉

Next steps:
1. Configure homepage dashboard
2. Set up monitoring alerts
3. Schedule automated backups
4. Plan DR test

**Need help?** Review other docs:
- `README-CIDEPLOY.md` - Complete guide
- `VPS-GITOPS-SETUP.md` - Security practices
- `START-HERE-CI-CD.md` - Quick reference

🌟 You've done it! ~★(◕‿◕)ノ ✨
