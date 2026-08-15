#!/bin/bash
# Test completion dengan oc/deepseek-v4-flash-free (noAuth provider)
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
cd /opt/lumine/backend
KEY=$(grep -E "^LLM_GATEWAY_API_KEY" .env | cut -d= -f2)
echo "=== oc/deepseek-v4-flash-free ==="
curl -s -m 60 http://127.0.0.1:20128/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"oc/deepseek-v4-flash-free\",\"messages\":[{\"role\":\"user\",\"content\":\"Balas hanya: OK\"}],\"max_tokens\":10}" | head -c 600
echo
'
