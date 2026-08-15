#!/bin/bash
# Test dengan stream:false eksplisit + Accept header
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 'cd /opt/lumine/backend
KEY=$(grep -E "^LLM_GATEWAY_API_KEY" .env | cut -d= -f2)
for BODY in "{\"model\":\"oc/deepseek-v4-flash-free\",\"messages\":[{\"role\":\"user\",\"content\":\"Balas hanya OK\"}],\"max_tokens\":50,\"stream\":false}" "{\"model\":\"oc/deepseek-v4-flash-free\",\"messages\":[{\"role\":\"user\",\"content\":\"Balas hanya OK\"}],\"max_tokens\":50}"; do
  echo "=== body: ${BODY:0:60}... ==="
  curl -s -m 60 http://127.0.0.1:20128/v1/chat/completions \
    -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d "$BODY" -o /tmp/9r_resp.txt -w "HTTP %{http_code}\n"
  python3 -c "
raw = open(\"/tmp/9r_resp.txt\").read()
print(\"ends with [DONE]:\", raw.rstrip().endswith(\"data: [DONE]\"))
print(\"len:\", len(raw))
"
done
'
