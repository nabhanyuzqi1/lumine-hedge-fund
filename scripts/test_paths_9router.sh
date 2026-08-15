#!/bin/bash
# Test path /api/v1 vs /v1 chat completions
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 'cd /opt/lumine/backend
KEY=$(grep -E "^LLM_GATEWAY_API_KEY" .env | cut -d= -f2)
for P in "/api/v1/chat/completions" "/v1/chat/completions"; do
  echo "=== $P ==="
  curl -s -m 60 "http://127.0.0.1:20128$P" \
    -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -d "{\"model\":\"oc/deepseek-v4-flash-free\",\"messages\":[{\"role\":\"user\",\"content\":\"Balas hanya OK\"}],\"max_tokens\":50}" \
    -o /tmp/9r_resp.txt -w "HTTP %{http_code}\n"
  python3 -c "
import json
raw = open(\"/tmp/9r_resp.txt\").read()
try:
    j = json.loads(raw)
    print(\"VALID JSON\")
    if j.get(\"choices\"):
        m = j[\"choices\"][0][\"message\"]
        print(\"content:\", repr((m.get(\"content\") or \"\")[:60]))
except json.JSONDecodeError:
    print(\"INVALID (SSE?)\", \"data: [DONE]\" in raw)
    print(raw[:150])
"
done
'
