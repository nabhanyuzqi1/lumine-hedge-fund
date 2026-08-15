#!/bin/bash
# Verifikasi system-info services status
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 'cd /opt/lumine/backend
KEY=web-frontend
SEC=$(docker exec backend-redis-1 redis-cli HGET "lumine:api_key:web-frontend" secret)
T=$(date +%s)
E=$(printf "" | sha256sum | cut -d" " -f1)
SIG=$(printf "GET\n/api/v1/admin/system-info\n%s\n%s" $T $E | openssl dgst -sha256 -hmac "$SEC" | awk "{print \$2}")
curl -s -H "Host: lumine.biz.id" -H "X-Lumine-Api-Key: $KEY" -H "X-Lumine-Timestamp: $T" -H "X-Lumine-Signature: $SIG" \
  "http://127.0.0.1/api/v1/admin/system-info" > /tmp/si.json
python3 -c "
import json
d = json.load(open(\"/tmp/si.json\"))
data = d.get(\"data\", {})
svcs = data.get(\"services\", [])
print(len(svcs), \"services total\")
healthy = [s for s in svcs if s.get(\"health\") == \"healthy\" or (s.get(\"status\") == \"running\" and not s.get(\"health\"))]
print(len(healthy), \"healthy (running tanpa health dihitung)\")
for s in svcs:
    print(\" \", s.get(\"name\"), \"|\", s.get(\"status\"), \"|\", s.get(\"health\"))
"'