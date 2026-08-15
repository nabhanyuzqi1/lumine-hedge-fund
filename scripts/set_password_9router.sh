#!/bin/bash
# Set password baru via CLI token + login + setup provider
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
MID=$(cat /var/lib/docker/volumes/backend_9router_data/_data/machine-id)
CSEC=$(cat /var/lib/docker/volumes/backend_9router_data/_data/auth/cli-secret)
TOKEN=$(printf "%s" "${MID}9r-cli-auth${CSEC}" | sha256sum | cut -c1-16)
echo "token: $TOKEN"

echo "=== SETTINGS GET (cek struktur) ==="
curl -s -b /tmp/9r.cookies -H "x-9r-cli-token: $TOKEN" http://127.0.0.1:20128/api/settings | head -c 400
echo
echo "=== Coba login lagi ==="
curl -s -c /tmp/9r.cookies -X POST http://127.0.0.1:20128/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"password\":\"123456\"}" | head -c 400
echo
'
