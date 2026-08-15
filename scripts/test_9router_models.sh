#!/bin/bash
# Test batch model 9router — cari provider dengan credentials aktif
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
cd /opt/lumine/backend
KEY=$(grep -E "^LLM_GATEWAY_API_KEY" .env | cut -d= -f2)
for M in "deepseek/deepseek-v4-flash" "deepseek/deepseek-chat" "openai/gpt-5.4-mini" "ag/gemini-3.7-flash-high" "tokenrouter/deepseek/deepseek-v4-flash" "qianfan/deepseek-v4-flash" "siliconflow/deepseek-ai/DeepSeek-V4-Flash" "glm-cn/glm-5.2"; do
  R=$(curl -s -m 30 http://127.0.0.1:20128/v1/chat/completions \
    -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -d "{\"model\":\"$M\",\"messages\":[{\"role\":\"user\",\"content\":\"Balas: OK\"}],\"max_tokens\":8}" | head -c 180)
  echo "$M → $R"
  echo
done
'
