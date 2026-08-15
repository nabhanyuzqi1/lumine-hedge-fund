#!/bin/bash
# Login 9router + setup provider opencode
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
echo "=== LOGIN (password default 123456) ==="
R=$(curl -s -c /tmp/9r.cookies -X POST http://127.0.0.1:20128/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"password\":\"123456\"}")
echo "$R" | head -c 300
echo
echo "=== AUTH STATUS ==="
curl -s -b /tmp/9r.cookies http://127.0.0.1:20128/api/auth/status | head -c 300
echo
echo "=== GET /api/providers (connections) ==="
curl -s -b /tmp/9r.cookies http://127.0.0.1:20128/api/providers | head -c 400
echo
'
