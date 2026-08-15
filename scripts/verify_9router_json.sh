#!/bin/bash
# Verifikasi response JSON valid dengan Accept header
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 'cd /opt/lumine/backend
KEY=$(grep -E "^LLM_GATEWAY_API_KEY" .env | cut -d= -f2)
curl -s -m 60 http://127.0.0.1:20128/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d "{\"model\":\"oc/deepseek-v4-flash-free\",\"messages\":[{\"role\":\"user\",\"content\":\"Balas hanya dengan kata OK\"}],\"max_tokens\":100}" \
  -o /tmp/9r_resp.txt -w "HTTP %{http_code}\n"
python3 -c "
import json
j = json.loads(open(\"/tmp/9r_resp.txt\").read())
print(\"VALID JSON\")
print(\"model:\", j.get(\"model\"))
print(\"choices:\", len(j.get(\"choices\", [])))
if j.get(\"choices\"):
    m = j[\"choices\"][0][\"message\"]
    print(\"content:\", repr((m.get(\"content\") or \"\")[:120]))
    print(\"finish:\", j[\"choices\"][0].get(\"finish_reason\"))
"
'
