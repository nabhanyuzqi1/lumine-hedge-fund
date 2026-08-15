#!/bin/bash
# Eksplorasi API 9router — GET providers + POST connection
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
APIKEY="sk-fc7$(docker exec 9router sh -c "ls /app/data 2>/dev/null; cat /app/data/.env 2>/dev/null" 2>/dev/null | head -1)"
# Ambil API key dari .env backend (LLM_GATEWAY_API_KEY)
KEY=$(grep -E "^LLM_GATEWAY_API_KEY" /opt/lumine/backend/.env | cut -d= -f2)
echo "=== GET /api/providers (existing connections) ==="
curl -s -b "apikey=$KEY" http://127.0.0.1:20128/api/providers | head -c 500
echo
echo "=== GET /api/providers/client (provider list + auth modes) ==="
curl -s -b "apikey=$KEY" http://127.0.0.1:20128/api/providers/client | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    provs = d.get(\"providers\", d) if isinstance(d, dict) else d
    if isinstance(provs, list):
        print(\"providers:\", len(provs))
        for p in provs[:30]: print(\" \", p.get(\"id\"), \"|\", p.get(\"name\"), \"|\", p.get(\"authModes\") or p.get(\"authType\"))
    else:
        print(str(d)[:800])
except Exception as e:
    print(\"parse err:\", e)
"
'
