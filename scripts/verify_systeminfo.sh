#!/bin/bash
# Verify system-info setelah deploy (docker socket mount)
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 'cd /opt/lumine/backend
KEY="web-frontend"
SEC=$(docker exec backend-redis-1 redis-cli HGET "lumine:api_key:$KEY" secret)
TS=$(date +%s)
PATHREQ="/api/v1/admin/system-info"
EMPTY=$(printf "" | sha256sum | cut -d" " -f1)
PAYLOAD=$(printf "GET\n%s\n%s\n%s" "$PATHREQ" "$TS" "$EMPTY")
SIG=$(printf "%s" "$PAYLOAD" | openssl dgst -sha256 -hmac "$SEC" | awk "{print \$2}")
CODE=$(curl -s -o /tmp/r.json -w "%{http_code}" -H "Host: lumine.biz.id" \
  -H "X-Lumine-Api-Key: $KEY" -H "X-Lumine-Timestamp: $TS" -H "X-Lumine-Signature: $SIG" \
  "http://127.0.0.1$PATHREQ")
echo "HTTP $CODE"
python3 -c "
import json
d=json.load(open(\"/tmp/r.json\"))
svcs=d.get(\"data\",{}).get(\"services\",[])
print(\"services:\", len(svcs))
for s in svcs[:20]: print(\" \", s[\"name\"], s[\"status\"], s[\"health\"], s[\"image\"])
"
'
