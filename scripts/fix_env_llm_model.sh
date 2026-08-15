#!/bin/bash
# Fix .env: pisahkan LLM_DEFAULT_MODEL dari baris ADMIN_PASSWORD
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 'cd /opt/lumine/backend
python3 - <<"PYEOF"
lines = open(".env").read().split("\n")
fixed = []
for l in lines:
    if l.startswith("ADMIN_PASSWORD=") and "LLM_DEFAULT_MODEL=" in l:
        # pisahkan: ADMIN_PASSWORD=...|LLM_DEFAULT_MODEL=...
        idx = l.index("LLM_DEFAULT_MODEL=")
        fixed.append(l[:idx].rstrip())
        fixed.append(l[idx:])
    else:
        fixed.append(l)
open(".env", "w").write("\n".join(fixed) + "\n")
print("OK")
PYEOF
echo "=== hasil ==="
grep -nE "^ADMIN_PASSWORD|^LLM_DEFAULT_MODEL" .env | sed "s/\(PASSWORD=.\{6\}\).*/\1.../"
'