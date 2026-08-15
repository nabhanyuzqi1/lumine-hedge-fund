#!/bin/bash
# Reset password 9router → default → login → setup provider
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
echo "=== RESET PASSWORD ==="
curl -s -X POST http://127.0.0.1:20128/api/auth/reset-password \
  -H "Content-Type: application/json" \
  -d "{\"password\":null}" | head -c 300
echo
echo "=== LOGIN (default 123456) ==="
curl -s -c /tmp/9r.cookies -X POST http://127.0.0.1:20128/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"password\":\"123456\"}" | head -c 300
echo
echo "=== AUTH STATUS ==="
curl -s -b /tmp/9r.cookies http://127.0.0.1:20128/api/auth/status | head -c 200
echo
'
