# 🚀 CI/CD DEPLOYMENT STARTER GUIDE

**Goal:** Deploy Lumine Hedge Fund Platform to VPS via GitHub Actions  
**Status:** ✅ All configuration files created  
**Next:** Follow steps below to configure & deploy!

---

## 📂 FILES CREATED

| File | Purpose | Status |
|------|---------|--------|
| `.github/workflows/deploy-v2.yml` | Main deployment workflow | ✅ Created |
| `infrastructure/control-plane/docker-compose.yml` | Control plane services | ✅ Created |
| `infrastructure/control-plane/caddy/Caddyfile` | Reverse proxy config | ✅ Created |
| `infrastructure/control-plane/authelia/config.yml` | Auth provider | ✅ Created |
| `infrastructure/control-plane/homepage/settings.yml` | Dashboard config | ✅ Created |
| `README-CIDEPLOY.md` | Complete CI/CD guide | ✅ Created |
| `VPS-GITOPS-SETUP.md` | Security setup guide | ✅ Created |

---

## ⚡ 3-STEP QUICK START

### Step 1: Generate Deploy Key (5 min)
```bash
cd /Users/nabhan/Dev/lumine-hedge-fund
ssh-keygen -t ed25519 -f id_lumine_deploy -C "lumine-deploy" -N ""
```

### Step 2: Add Key to VPS (5 min)
```bash
# Copy public key to clipboard
cat id_lumine_deploy.pub

# Then SSH into VPS and add it
ssh -i id_rsa.priv root@166.88.227.177
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "PASTE_PUBLIC_KEY_HERE" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
exit
```

### Step 3: Configure GitHub Secrets (5 min)
Go to: https://github.com/nabhanyuzqi1/lumine-hedge-fund/settings/secrets/actions

Add these 7 secrets:
1. `DEPLOY_HOST` = `166.88.227.177`
2. `DEPLOY_USER` = `root`
3. `DEPLOY_SSH_KEY` = Paste entire contents of `id_lumine_deploy` (BEGIN/END lines included!)
4. `DB_PASSWORD` = (generate secure password, see README-CIDEPLOY.md)
5. `HMAC_SECRET_KEY` = (generate 64-char hex string, see README-CIDEPLOY.md)
6. `LLM_GATEWAY_API_KEY` = (UUID format, see README-CIDEPLOY.md)
7. `VNC_PASSWORD` = `LumineVnc!2026`

---

## 🎯 TRIGGER FIRST DEPLOYMENT

After setting up secrets:

1. Go to: https://github.com/nabhanyuzqi1/lumine-hedge-fund/actions
2. Find **"Deploy"** workflow
3. Click **"Run workflow"** button
4. Choose branch: `main`
5. Click blue **"Run workflow"** again

**Expected duration:** 8-12 minutes  
**What happens:** Build → Test → Deploy → Verify → Backup

---

## ✅ VERIFICATION CHECKLIST

After deployment completes, check:

- [ ] Docker containers running (`docker ps`)
- [ ] Backend API responds at `/api/health`
- [ ] PostgreSQL accepting connections
- [ ] Redis responding to PING
- [ ] Uptime Kuma monitoring active
- [ ] Homepage dashboard accessible

---

## 🆘 TROUBLESHOOTING

**Issue:** Workflow fails immediately  
**Solution:** Check `DEPLOY_SSH_KEY` contains complete private key text

**Issue:** Containers won't start  
**Solution:** Verify environment variables are correct in GitHub Secrets

**Issue:** Can't access homepage  
**Solution:** Ensure Caddy certificate issued (wait 5-10 min for HTTPS)

---

## 📖 READ FULL DOCUMENTATION

For detailed instructions, see:
- **README-CIDEPLOY.md** - Complete CI/CD pipeline guide
- **VPS-GITOPS-SETUP.md** - Security best practices
- **vps-deployment-plan.md** - Infrastructure architecture
- **vps-reinstall-plan.md** - Safety checklist

---

## ✨ NEXT STEPS AFTER SUCCESS

Once deployment works:
1. Schedule automated daily backups (cron job on VPS)
2. Set up monitoring alerts (Slack integration via Uptime Kuma)
3. Plan DR test execution (quarterly requirement)
4. Document emergency procedures for team
5. Establish key rotation schedule

---

**🎉 Ready to deploy?** Start with Step 1 above!

Questions? Review documentation before proceeding~ ✨ ~★~
