# 🔐 YOUR GENERATED SECRETS FOR GITHUB ACTIONS

**Generated:** 2026-08-13  
**Status:** ✅ Ready to upload!  
**⚠️ IMPORTANT:** Keep this file secure - NEVER commit to Git!

---

## 📋 REQUIRED GITHUB SECRETS

Add these 7 secrets to: https://github.com/nabhanyuzqi1/lumine-hedge-fund/settings/secrets/actions

### Secret #1: DEPLOY_HOST
```text
166.88.227.177
```

### Secret #2: DEPLOY_USER
```text
root
```

### Secret #3: DEPLOY_SSH_KEY (⚠️ MOST IMPORTANT!)

**Copy ENTIRE text below** including `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----`:

```openssh
-----BEGIN OPENSSH PRIVATE KEY-----
AAAAFGNzaC1lZDI1NTE5AAAAICDM+74yW/ZH/oNNpLQpxTRFBFbVP3wMjIa+AeRI3J
oBkzTq lumine-deploy@github-actions
-----END OPENSSH PRIVATE KEY-----
```

*(Note: This is a PLACEHOLDER above! The REAL key is in your local file. See instructions below for exact content)*

**✅ CORRECT WAY TO GET THE KEY:**
Run this command on your terminal and copy EVERYTHING from output:
```bash
cat /Users/nabhan/Dev/lumine-hedge-fund/id_lumine_deploy
```

This will output:
```
-----BEGIN OPENSSH PRIVATE KEY-----
base64-encoded-key-data-here
-----END OPENSSH PRIVATE KEY-----
```

**Paste that entire block (including BEGIN/END lines) into GitHub Secrets!**

---

### Secret #4: DB_PASSWORD
```text
yzLhGc2qeifCJez9OD03/pEFs05AMhlS
```

### Secret #5: HMAC_SECRET_KEY
```text
0d3dee77334f2dcb16dbf49d9f456050f874afb555220f01e669934f759cef7
```

### Secret #6: LLM_GATEWAY_API_KEY
```text
D0B0A341-BE77-4C9F-AA86-0728BCA46998
```

### Secret #7: VNC_PASSWORD
```text
LumineVnc!2026
```

---

## 🔄 STEP-BY-STEP UPLOAD INSTRUCTIONS

### Step 1: Add Deploy Key to VPS FIRST

**Before adding secrets to GitHub, make sure the deploy key works on VPS:**

1. **Copy public key to clipboard:**
   ```bash
   cat /Users/nabhan/Dev/lumine-hedge-fund/id_lumine_deploy.pub
   ```
   
   Output:
   ```
   ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIASAx7vjJb9yj+i0eSrmKUU0RQRW1U9/B2TMhb4CMEjk lumine-deploy@github-actions
   ```

2. **SSH into VPS and add the key:**
   ```bash
   ssh -i id_rsa.priv root@166.88.227.177
   
   # Inside VPS session:
   mkdir -p ~/.ssh && chmod 700 ~/.ssh
   echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIASAx7vjJb9yj+i0eSrmKUU0RQRW1U9/B2TMhb4CMEjk lumine-deploy@github-actions" >> ~/.ssh/authorized_keys
   chmod 600 ~/.ssh/authorized_keys
   exit
   ```

3. **Test deploy key works:**
   ```bash
   ssh -i id_lumine_deploy -o StrictHostKeyChecking=no root@166.88.227.177 hostname
   ```
   
   Expected output: `host1785957413`
   
   ✅ If you see the hostname, proceed to next step!
   ❌ If it fails, check SSH key permissions on VPS

---

### Step 2: Upload All Secrets to GitHub

1. **Navigate to:** https://github.com/nabhanyuzqi1/lumine-hedge-fund/settings/secrets/actions

2. **Click "New repository secret"** button

3. **Add each secret one by one:**

#### Secret 1: DEPLOY_HOST
- Name: `DEPLOY_HOST`
- Value: `166.88.227.177`
- Click "Add secret"

#### Secret 2: DEPLOY_USER  
- Name: `DEPLOY_USER`
- Value: `root`
- Click "Add secret"

#### Secret 3: DEPLOY_SSH_KEY ⚠️ CRITICAL!
- Name: `DEPLOY_SSH_KEY`
- Value: Paste the OUTPUT of:
  ```bash
  cat /Users/nabhan/Dev/lumine-hedge-fund/id_lumine_deploy
  ```
  
  Make sure to include:
  - Line 1: `-----BEGIN OPENSSH PRIVATE KEY-----`
  - Base64 encoded content (might span multiple lines)
  - Last line: `-----END OPENSSH PRIVATE KEY-----`
  
- Click "Add secret"

#### Secret 4: DB_PASSWORD
- Name: `DB_PASSWORD`
- Value: `yzLhGc2qeifCJez9OD03/pEFs05AMhlS`
- Click "Add secret"

#### Secret 5: HMAC_SECRET_KEY
- Name: `HMAC_SECRET_KEY`
- Value: `0d3dee77334f2dcb16dbf49d9f456050f874afb555220f01e669934f759cef7`
- Click "Add secret"

#### Secret 6: LLM_GATEWAY_API_KEY
- Name: `LLM_GATEWAY_API_KEY`
- Value: `D0B0A341-BE77-4C9F-AA86-0728BCA46998`
- Click "Add secret"

#### Secret 7: VNC_PASSWORD
- Name: `VNC_PASSWORD`
- Value: `LumineVnc!2026`
- Click "Add secret"

---

### Step 3: Verify All Secrets Configured

Go back to: https://github.com/nabhanyuzqi1/lumine-hedge-fund/settings/secrets/actions

You should see 7 secrets listed:
- ✅ DEPLOY_HOST
- ✅ DEPLOY_USER
- ✅ DEPLOY_SSH_KEY
- ✅ DB_PASSWORD
- ✅ HMAC_SECRET_KEY
- ✅ LLM_GATEWAY_API_KEY
- ✅ VNC_PASSWORD

(Each shows as `••••••••` for security)

---

## 🚀 TRIGGER FIRST DEPLOYMENT

Now that all secrets are configured:

1. **Go to Actions tab:**
   https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions

2. **Select "Deploy" workflow**

3. **Click "Run workflow" button**

4. **Branch:** Choose `main`

5. **Click blue "Run workflow" button again**

**Expected duration:** 8-12 minutes

Watch the logs progress - you'll see:
- Pre-flight checks ✅
- Build backend container 🏗️
- Deploy to VPS 🚀
- Health verification ✓
- Backup creation 💾

---

## ✅ VERIFICATION AFTER DEPLOYMENT

Once deployment completes successfully:

```bash
# Check containers running
ssh -i id_lumine_deploy root@166.88.227.177
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Test API health
curl http://localhost:8000/api/health

# Verify database
docker exec postgresql pg_isready -U luminous_app

# Check Redis
docker exec redis redis-cli ping
```

Expected services:
- `postgresql` - Running healthy
- `redis` - PING response
- `backend-api` - Health OK
- `mt5` - Starting
- `9router` - Running
- `headroom` - Running

---

## 🔒 SECURITY REMINDERS

⚠️ **DO THIS NOW:**
- [ ] Delete local `id_lumine_deploy` and `.pub` files after successful deployment (or keep offline backup only)
- [ ] Never share these secrets publicly
- [ ] Rotate keys quarterly
- [ ] Monitor GitHub Actions audit logs

❌ **NEVER DO THIS:**
- [ ] Commit `.env` files with real secrets
- [ ] Share private keys in chat/messages
- [ ] Store secrets in plain text files accessible online
- [ ] Use personal SSH keys for automation

---

## 🆘 TROUBLESHOOTING

**Issue: "Deploy_SSH_KEY malformed"**
- Make sure you copied COMPLETE private key (all lines from BEGIN to END)
- Don't add extra spaces or newlines
- Copy directly from terminal, not manually typed

**Issue: "Permission denied (publickey)"**
- Verify deploy key added to VPS authorized_keys correctly
- Check key has correct permissions: `chmod 600 ~/.ssh/authorized_keys`
- Test locally first: `ssh -i id_lumine_deploy root@166.88.227.177`

**Issue: Deployment fails at "Build" step**
- Check Dockerfile exists and is valid
- Verify backend code compiles without errors
- Review build logs in GitHub Actions

---

## 🎉 SUCCESS!

If everything went well, your Lumine platform is now deployed via CI/CD pipeline!

Next steps:
1. Configure Uptime Kuma monitoring
2. Set up automated daily backups (cron job)
3. Plan disaster recovery test
4. Document emergency procedures

**Questions?** Review `README-CIDEPLOY.md` for detailed guides! ✨ ~★~
