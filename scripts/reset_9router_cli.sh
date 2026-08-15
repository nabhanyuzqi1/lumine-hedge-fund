#!/bin/bash
# Reset password 9router via CLI token → login → setup
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
# Ambil machine-id + cli-secret dari volume
MID=$(cat /var/lib/docker/volumes/backend_9router_data/_data/machine-id)
CSEC=$(cat /var/lib/docker/volumes/backend_9router_data/_data/auth/cli-secret)
echo "machine-id: $MID"
echo "cli-secret: $CSEC"

# Token = sha256(machineId + "9r-cli-auth" + cliSecret).substring(0,16)
TOKEN=$(printf "%s" "${MID}9r-cli-auth${CSEC}" | sha256sum | cut -c1-16)
echo "token: $TOKEN"

echo "=== RESET PASSWORD ==="
curl -s -X POST http://127.0.0.1:20128/api/auth/reset-password \
  -H "Content-Type: application/json" \
  -H "x-9r-cli-token: $TOKEN" \
  -d "{\"password\":null}" | head -c 300
echo
echo "=== LOGIN (default 123456) ==="
curl -s -c /tmp/9r.cookies -X POST http://127.0.0.1:20128/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"password\":\"123456\"}" | head -c 300
echo
'
