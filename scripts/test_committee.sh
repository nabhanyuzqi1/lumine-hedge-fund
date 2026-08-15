#!/bin/bash
# Verify committee feed + trigger analyst workflow
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 'cd /opt/lumine/backend
KEY="web-frontend"
SEC=$(docker exec backend-redis-1 redis-cli HGET "lumine:api_key:$KEY" secret)
TS=$(date +%s)
sign() {
  local METHOD=$1 PATHREQ=$2
  local EMPTY=$(printf "" | sha256sum | cut -d" " -f1)
  local PAYLOAD=$(printf "%s\n%s\n%s\n%s" "$METHOD" "$PATHREQ" "$TS" "$EMPTY")
  printf "%s" "$PAYLOAD" | openssl dgst -sha256 -hmac "$SEC" | awk "{print \$2}"
}
echo "=== committee/feed ==="
SIG=$(sign "GET" "/api/v1/committee/feed")
curl -s -H "Host: lumine.biz.id" -H "X-Lumine-Api-Key: $KEY" -H "X-Lumine-Timestamp: $TS" -H "X-Lumine-Signature: $SIG" \
  "http://127.0.0.1/api/v1/committee/feed?limit=5" | head -c 400
echo
echo "=== workflow runs ==="
SIG=$(sign "GET" "/api/v1/workflows")
curl -s -H "Host: lumine.biz.id" -H "X-Lumine-Api-Key: $KEY" -H "X-Lumine-Timestamp: $TS" -H "X-Lumine-Signature: $SIG" \
  "http://127.0.0.1/api/v1/workflows?limit=3" | head -c 400
echo
'
