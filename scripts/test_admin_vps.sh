#!/bin/bash
# Test admin/system-info + admin/system-config
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
cd /opt/lumine/backend
KEY="web-frontend"
SEC=$(docker exec backend-redis-1 redis-cli HGET "lumine:api_key:$KEY" secret)
TS=$(date +%s)
PATHREQ="/api/v1/admin/system-info"
EMPTY=$(printf "" | sha256sum | cut -d" " -f1)
PAYLOAD=$(printf "GET\n%s\n%s\n%s" "$PATHREQ" "$TS" "$EMPTY")
SIG=$(printf "%s" "$PAYLOAD" | openssl dgst -sha256 -hmac "$SEC" | awk "{print \$2}")
echo "--- system-info ---"
curl -s -o /tmp/r.json -w "HTTP %{http_code}\n" -H "Host: lumine.biz.id" \
  -H "X-Lumine-Api-Key: $KEY" -H "X-Lumine-Timestamp: $TS" -H "X-Lumine-Signature: $SIG" \
  "http://127.0.0.1$PATHREQ"
head -c 800 /tmp/r.json; echo
'
