# ✅ CI/CD SETUP CHECKLIST - LUMINE PLATFORM

**Status:** ⏳ Ready to deploy  
**Time estimate:** 20-30 minutes  
**Difficulty:** 🟢 Beginner-friendly (follow steps in order!)

---

## 📋 PRE-REQUISITES

Before starting, make sure you have:
- [ ] Terminal/Ssh client installed on your computer
- [ ] Git repository: https://github.com/nabhanyuzqi1/lumine-hedge-fund
- [ ] VPS accessible at: `166.88.227.177`
- [ ] Personal SSH key working (`id_rsa.priv`)

---

## 🎯 STEP-BY-STEP CHECKLIST

### Phase 1: Prepare Deploy Keys (5 min)

#### Step 1.1: Generate Deploy Key
Execute this command in terminal:
```bash
cd /Users/nabhan/Dev/lumine-hedge-fund
ssh-keygen -t ed25519 -f id_lumine_deploy -C "lumine-deploy@github-actions" -N ""
```

**Expected output:**
```
Generating public/private ed25519 key pair.
Your identification has been saved in id_lumine_deploy
Your public key has been saved in id_lumine_deploy.pub
```

✅ **Check:** Run `ls -lh id_lumine*` and verify both files exist

---

#### Step 1.2: Copy Public Key
```bash
cat id_lumine_deploy.pub
```

**Action:** Select and copy the ENTIRE output line (starts with `ssh-ed25519`)

✅ **Check:** You should see something like:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5... lumine-deploy@github-actions
```

---

#### Step 1.3: Add to VPS
1. SSH into VPS:
   ```bash
   ssh -i id_rsa.priv root@166.88.227.177
   ```

2. Inside VPS, run these commands:
   ```bash
   mkdir -p ~/.ssh && chmod 700 ~/.ssh
   echo "PASTE_PUBLIC_KEY_HERE" >> ~/.ssh/authorized_keys
   chmod 600 ~/.ssh/authorized_keys
   exit
   ```
   
   Replace `"PASTE_PUBLIC_KEY_HERE"` with the actual key you copied above!

3. Test deploy key works:
   ```bash
   ssh -i id_lumine_deploy -o StrictHostKeyChecking=no root@166.88.227.177 hostname
   ```
   
   Expected output: `host1785957413`

✅ **Check:** If you see the hostname, deploy key is configured correctly!

---

### Phase 2: Upload Secrets to GitHub (10 min)

#### Step 2.1: Navigate to Settings
1. Open browser
2. Go to: https://github.com/nabhanyuzqi1/lumine-hedge-fund/settings/secrets/actions

#### Step 2.2: Add First Secret - DEPLOY_HOST

**Click "New repository secret":**
| Field | Value |
|-------|-------|
| Name | `DEPLOY_HOST` |
| Secret | `166.88.227.177` |

✅ Click **"Add secret"**

---

#### Step 2.3: Add Second Secret - DEPLOY_USER

**Click "New repository secret":**
| Field | Value |
|-------|-------|
| Name | `DEPLOY_USER` |
| Secret | `root` |

✅ Click **"Add secret"**

---

#### Step 2.4: Add Third Secret - DEPLOY_SSH_KEY ⚠️ CRITICAL!

**This is the most important step!**

1. In terminal, run:
   ```bash
   cat id_lumine_deploy
   ```

2. You'll see output spanning multiple lines:
   ```
   -----BEGIN OPENSSH PRIVATE KEY-----
   ...base64 data...
   -----END OPENSSH PRIVATE KEY-----
   ```

3. **Select and copy EVERYTHING** from BEGIN to END (all lines!)

4. In GitHub, click "New repository secret":
   | Field | Value |
   |-------|-------|
   | Name | `DEPLOY_SSH_KEY` |
   | Secret | **[PASTE YOUR COMPLETE KEY HERE]** |

5. ✅ Click **"Add secret"**

⚠️ **WARNING:** Make sure you copied ALL lines, not just part of it!

---

#### Step 2.5: Add DB_PASSWORD

**Click "New repository secret":**
| Field | Value |
|-------|-------|
| Name | `DB_PASSWORD` |
| Secret | `yzLhGc2qeifCJez9OD03/pEFs05AMhlS` |

✅ Click **"Add secret"**

---

#### Step 2.6: Add HMAC_SECRET_KEY

**Click "New repository secret":**
| Field | Value |
|-------|-------|
| Name | `HMAC_SECRET_KEY` |
| Secret | `0d3dee77334f2dcb16dbf49d9f456050f874afb555220f01e669934f759cef7` |

✅ Click **"Add secret"**

---

#### Step 2.7: Add LLM_GATEWAY_API_KEY

**Click "New repository secret":**
| Field | Value |
|-------|-------|
| Name | `LLM_GATEWAY_API_KEY` |
| Secret | `D0B0A341-BE77-4C9F-AA86-0728BCA46998` |

✅ Click **"Add secret"**

---

#### Step 2.8: Add VNC_PASSWORD

**Click "New repository secret":**
| Field | Value |
|-------|-------|
| Name | `VNC_PASSWORD` |
| Secret | `LumineVnc!2026` |

✅ Click **"Add secret"**

---

#### Step 2.9: Verify All Secrets

Go back to Secrets page and confirm you see:
- [ ] DEPLOY_HOST ••••••
- [ ] DEPLOY_USER ••••••
- [ ] DEPLOY_SSH_KEY ••••••
- [ ] DB_PASSWORD ••••••
- [ ] HMAC_SECRET_KEY ••••••
- [ ] LLM_GATEWAY_API_KEY ••••••
- [ ] VNC_PASSWORD ••••••

✅ All 7 secrets should be present!

---

### Phase 3: Trigger Deployment (5-10 min)

#### Step 3.1: Go to Actions Tab
1. Navigate to: https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions

#### Step 3.2: Select Deploy Workflow
- Find **"Deploy"** workflow in Recent workflows list
- Click **"Run workflow"** button

#### Step 3.3: Configure Workflow
- Dropdown "Branch": Keep as `main`
- Click blue **"Run workflow"** button again

---

#### Step 3.4: Watch Logs Progress

Workflow will take ~8-12 minutes. Watch progress:

**Phase 1:** Pre-flight checks ✅ (~30 sec)
**Phase 2:** Build backend container 🏗️ (~3-5 min)
**Phase 3:** Deploy to VPS 🚀 (~3-5 min)
**Phase 4:** Backup creation 💾 (~1-2 min)

**Successful completion shows:** ✅ SUCCESS (green checkmark)

---

### Phase 4: Verify Deployment Success (5 min)

#### Step 4.1: SSH into VPS
```bash
ssh -i id_lumine_deploy root@166.88.227.177
```

#### Step 4.2: Check Containers Running
```bash
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Expected output:
```
NAME            STATUS             PORTS
postgresql      Up (healthy)       5432/tcp
redis           Up (healthy)       6379/tcp
backend-api     Up (healthy)       127.0.0.1:8000->8000/tcp
mt5             Up                 127.0.0.1:5900->5900/tcp, 127.0.0.1:6901->6901/tcp
9router         Up                 0.0.0.0:20128->20128/tcp
headroom        Up
```

✅ **Check:** At least 4-6 containers running healthy

---

#### Step 4.3: Test Backend API
```bash
curl http://localhost:8000/api/health
```

Expected JSON response:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "..."
}
```

✅ **Check:** Returns 200 status with health OK

---

#### Step 4.4: Verify Database
```bash
docker exec postgresql pg_isready -U luminous_app
```

Expected: `accepting connections`

✅ **Check:** Database reachable

---

#### Step 4.5: Verify Redis
```bash
docker exec redis redis-cli ping
```

Expected: `PONG`

✅ **Check:** Redis responsive

---

## 🎉 SUCCESS INDICATORS

If you completed all phases successfully:

✅ Deploy key added to VPS  
✅ All 7 GitHub secrets configured  
✅ Workflow completed with SUCCESS  
✅ Containers running healthy  
✅ API responding to health checks  
✅ Database accepting connections  
✅ Redis responding to PING  

**🎊 Your Lumine platform is deployed via GitOps CI/CD pipeline!**

---

## 🔒 POST-DEPLOYMENT SECURITY

After successful deployment:

- [ ] Delete `id_lumine_deploy` and `.pub` files locally (or keep offline backup only)
- [ ] Monitor GitHub Actions audit logs weekly
- [ ] Schedule quarterly key rotation
- [ ] Review access permissions on VPS
- [ ] Document emergency procedures

---

## 🆘 COMMON ISSUES & FIXES

### Issue 1: "Permission denied" during deployment

**Cause:** Deploy key not matching or wrong format in GitHub

**Fix:**
1. Delete `DEPLOY_SSH_KEY` secret
2. Re-run: `cat id_lumine_deploy` 
3. Copy ENTIRE output (all lines)
4. Create new secret with exact same content
5. Retry deployment

---

### Issue 2: "Database connection failed"

**Cause:** Wrong password or database not ready yet

**Fix:**
```bash
# Wait 2-3 more minutes for database initialization
# Then check logs:
ssh -i id_lumine_deploy root@166.88.227.177
docker logs postgresql --tail 30
```

---

### Issue 3: Backend starts but API returns 500

**Cause:** Migration not applied or environment issue

**Fix:**
```bash
# SSH and apply migrations manually:
docker exec backend-api python -m alembic upgrade head
docker restart backend-api
```

---

## 📚 HELPFUL DOCUMENTATION

For detailed guides:
- `README-CIDEPLOY.md` - Complete CI/CD pipeline documentation
- `VPS-GITOPS-SETUP.md` - Security best practices
- `GITHUB-SECRETS-SETUP.md` - Detailed step-by-step guide
- `vps-deployment-plan.md` - Infrastructure architecture

---

## ✨ NEXT STEPS AFTER SUCCESS

Once deployment verified:
1. Set up automated daily backups (cron job)
2. Configure Uptime Kuma monitoring dashboard
3. Plan disaster recovery test
4. Document emergency contact procedures
5. Establish key rotation schedule

---

**Questions?** Check other documentation files before proceeding!  
**Ready?** Start from Step 1.1 above! 🚀 ✨
