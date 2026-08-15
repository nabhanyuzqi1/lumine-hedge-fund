#!/bin/bash
# List semua model 9router + test completion dengan model pertama
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
cd /opt/lumine/backend
KEY=$(grep -E "^LLM_GATEWAY_API_KEY" .env | cut -d= -f2)
echo "=== semua model ==="
curl -s -m 10 http://127.0.0.1:20128/v1/models -H "Authorization: Bearer $KEY" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for m in d.get(\"data\",[]): print(m[\"id\"])"
echo "=== test completion qwen3.5-plus ==="
curl -s -m 60 http://127.0.0.1:20128/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"alicode-intl/qwen3.5-plus\",\"messages\":[{\"role\":\"user\",\"content\":\"Balas: OK\"}],\"max_tokens\":10}" | head -c 600
echo
'
