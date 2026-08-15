#!/bin/bash
# Cari AI_PROVIDERS dalam bundle JS 9router
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 "
docker exec 9router node -e '
const s = require(\"fs\").readFileSync(\"/app/.next/server/middleware.js\",\"utf8\");
// AI_PROVIDERS biasanya ada di shared/constants atau providers registry
const keys = [\"opencode\", \"openrouter\", \"deepseek\", \"openai\"];
for (const k of keys) {
  const i = s.indexOf(\"\\\"\" + k + \"\\\"\");
  console.log(k, \"→\", i !== -1 ? \"found at \" + i : \"NOT FOUND\");
}
// cek provider registry file
const {execSync} = require(\"child_process\");
try {
  const out = execSync(\"grep -rl AI_PROVIDERS /app/.next/server/chunks /app/.next/server/app 2>/dev/null | head -5\").toString();
  console.log(\"files with AI_PROVIDERS:\", out);
} catch(e) { console.log(\"grep err\", e.message); }
'
"
