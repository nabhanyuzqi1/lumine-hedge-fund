# Lumine Environment Setup Guide
## Quick Start untuk Generate .env File

### Opsi 1: Menggunakan Script Generator (Rekomended)

Script ini akan generate secure values otomatis dan create `.env` file siap pakai:

```bash
cd scripts/deploy
chmod +x generate-env.sh
./generate-env.sh
```

**Output:**
- Prompt interaktif untuk confirm/reject values yang di-generate
- Auto-create file `scripts/deploy/.env` dengan permissions 600 (hanya owner bisa baca)
- Semua secrets dibuat random dan aman

### Opsi 2: Manual Edit Template

Jika prefer manual control, edit template dan isi sendiri semua values:

```bash
cd scripts/deploy
cp .env.template .env
$EDITOR .env
```

**Kemudian replace semua placeholder `<...>` dengan values asli Anda:**

| Variable | Description | How to Generate |
|----------|-------------|-----------------|
| `DB_PASSWORD` | PostgreSQL admin password | `openssl rand -base64 32 \| tr -d '/+=' \| head -c 32` |
| `HMAC_SECRET_KEY` | API signing secret | `openssl rand -hex 32` (64 hex chars) |
| `LLM_GATEWAY_API_KEY` | 9router authentication | UUID format (`uuidgen` atau `/proc/sys/kernel/random/uuid`) |
| `AUTHERIA_SESSION_SECRET` | Authelia session cookie | `openssl rand -hex 32` |
| `AUTHERIA_STORAGE_ENCRYPTION_KEY` | Authelia database encryption | `openssl rand -base64 32` |
| `VNC_PASSWORD` | MT5 desktop access | Minimum 6 alphanumeric characters |
| `GITHUB_BACKUP_TOKEN` | Optional GitHub PAT | Create at github.com/settings/tokens |

---

## Security Checklist

### ✅ Values yang HARUS Secure
- [ ] `DB_PASSWORD` - Minimal 16 karakter random
- [ ] `HMAC_SECRET_KEY` - Gunakan `openssl rand -hex 32`
- [ ] `AUTHERIA_SESSION_SECRET` - 64 karakter hex random
- [ ] `AUTHERIA_STORAGE_ENCRYPTION_KEY` - Base64 random
- [ ] `LLM_GATEWAY_API_KEY` - UUID unik

### ⚠️ Values yang Perlu Diubah dari Default
- [ ] `VNC_PASSWORD` - **Jangan gunakan default!** Set strong password > 8 chars
- [ ] `ADMIN_PASSWORD` di `infrastructure/control-plane/authelia/configuration.yml` - Set unique password

### 🔒 Files yang TIDAK BOLEH Commit ke Git
❌ `scripts/deploy/.env`  
❌ `scripts/deploy/secrets.env`  
❌ Any files containing plaintext passwords or keys  

✅ `scripts/deploy/.env.template` (safe - all placeholders)  
✅ `scripts/deploy/.env.sample` (safe - example values only)

---

## Testing Your Configuration

Setelah buat `.env` file:

```bash
# Test connectivity ke VPS (jika SSH key configured)
ssh root@166.88.227.177 "hostname && date"

# Test Docker availability (jika Docker terinstall di VPS)
ssh root@166.88.227.177 "docker --version"

# Validate .env syntax (tidak commit apapun!)
bash -n .env && echo ".env syntax OK" || echo ".env has errors"

# Preview vars (tidak menampilkan sensitive data!)
grep -v PASSWORD .env | grep -v SECRET | grep -v TOKEN | head -20
```

---

## Next Steps

1. **Generate / Edit `.env`** sesuai guide di atas
2. **Test deployment scripts** locally dulu:
   ```bash
   ./bootstrap-vps.sh  # Simulate VPS setup (dry-run mode)
   ```
3. **Deploy to VPS**:
   ```bash
   ./deploy-stack.sh  # Full stack deployment
   ```
4. **Verify services**:
   ```bash
   ssh root@166.88.227.177 "docker compose -f /opt/lumine/backend/docker-compose.prod.yml ps"
   ```
5. **Access control plane**:
   - Landing page: `https://166.88.227.177/`
   - Dashboard via Authelia: `https://166.88.227.177/auth/`

---

## Troubleshooting

### Problem: "Password too weak" error during deploy
**Solution**: Use stronger password with more character types and length (> 16 chars)

### Problem: "Authelia configuration error"
**Solution**: Check `infrastructure/control-plane/authelia/configuration.yml`:
```yaml
theme: dark  # Ensure theme is set
authentication_backend:
  password:
    algorithm: argon2id
    # Verify user 'admin' password is properly hashed
    users:
      - user: "admin"
        password: "$argon2id$v=19$m=32000,t=3,p=4$..."  # Hashed password
```

### Problem: "MT5 connection timeout"
**Solution**: 
1. Verify `VNC_PASSWORD` matches what's in container env
2. Access via browser: `http://166.88.227.177:6901/vnc.html`
3. Check container logs: `docker compose logs mt5`

### Problem: "Backup fails on GitHub push"
**Solution**: 
- Verify `GITHUB_BACKUP_TOKEN` has `repo` scope
- Check repository exists: `git ls-remote https://github.com/nabhanyuzqi1/lumine-backups.git`
- Or remove token if using incremental-only backup

---

## Security Best Practices

### Password Generation Commands

```bash
# Strong password (random, safe chars)
echo "Secure Password:" && openssl rand -base64 32 | tr -d '/+=' | head -c 32

# HMAC Secret (hexadecimal)
echo "HMAC Secret:" && openssl rand -hex 32

# UUID for API keys
echo "UUID:" && cat /proc/sys/kernel/random/uuid

# VNC Password (manual entry, min 6 chars)
read -p "Enter VNC password: " -s VNC_PASS
echo ""
test ${#VNC_PASS} -ge 6 && echo "✓ Password meets minimum length" || echo "✗ Too short!"
```

### SSH Key Management

```bash
# Generate new ED25519 key pair
ssh-keygen -t ed25519 -f ~/.ssh/lumine_deploy -C "lumine-deployment"

# Copy public key to VPS (for CI/CD automation)
ssh-copy-id -i ~/.ssh/lumine_deploy.pub root@166.88.227.177

# Test connection
ssh -i ~/.ssh/lumine_deploy root@166.88.227.177 "whoami && docker --version"
```

### Git Protection

```bash
# Add to .gitignore (already included by default)
echo ".env" >> .gitignore
echo "*.pem" >> .gitignore
echo "*.key" >> .gitignore

# Verify no secrets committed
git log -p --all | grep -i password | grep -v "template\|sample\|#.*password" && echo "⚠ SECURITY WARNING: Secrets found in history!"
```

---

## Reference Documents

- **Main Documentation**: `docs/14-implementation/onboarding.md`
- **VPS Installation Guide**: `scripts/deploy/VPS-GUIDE.md`
- **Security Decisions**: `docs/adr/0047-cicd-github-actions-ghcr-ssh-deploy.md`
- **Backup Strategy**: `docs/11-infrastructure/backup-dr.md`

---

**Remember**: Keep all credentials offline! Never share `.env` files. Use Git history carefully when rotating secrets.
