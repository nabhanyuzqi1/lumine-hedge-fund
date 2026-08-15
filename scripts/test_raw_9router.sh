#!/bin/bash
# Raw response test — cek format 9router (JSON + SSE?)
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
cd /opt/lumine/backend
KEY=$(grep -E "^LLM_GATEWAY_API_KEY" .env | cut -d= -f2)
curl -s -m 60 http://127.0.0.1:20128/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"oc/deepseek-v4-flash-free\",\"messages\":[{\"role\":\"user\",\"content\":\"Balas hanya OK\"}],\"max_tokens\":50}" \
  -o /tmp/9r_raw.txt -w "HTTP %{http_code}, %{size_download} bytes\n"
echo "=== raw tail ==="
tail -c 400 /tmp/9r_raw.txt
echo
echo "=== valid JSON? ==="
python3 -c "
import json
raw = open('/tmp/9r_raw.txt').read()
try:
    j = json.loads(raw)
    print('VALID JSON, choices:', len(j.get('choices',[])))
    if j.get('choices'):
        m = j['choices'][0]['message']
        print('content:', repr((m.get('content') or '')[:100]))
        print('reasoning:', repr((m.get('reasoning_content') or '')[:100]))
except json.JSONDecodeError as e:
    print('INVALID JSON:', e)
    # coba split di data: [DONE]
    parts = raw.split('data: [DONE]')
    if len(parts) > 1:
        print('SSE DETECTED, JSON part:', parts[0][-200:])
"
'
