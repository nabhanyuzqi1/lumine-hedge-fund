#!/bin/bash
# Extract AI_PROVIDERS dari chunks — cari pola provider keys
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 "docker exec 9router node -e '
const {execSync} = require(\"child_process\");
const files = execSync(\"ls /app/.next/server/chunks/*.js 2>/dev/null\").toString().trim().split(\"\n\");
const target = [\"opencode\", \"openrouter\", \"openai\", \"deepseek\", \"google\", \"anthropic\"];
for (const f of files) {
  const s = require(\"fs\").readFileSync(f, \"utf8\");
  const found = target.filter(t => s.includes(JSON.stringify(t)));
  if (found.length >= 3) {
    console.log(\"=== \", f, \"len\", s.length, \"found:\", found.join(\",\"));
  }
}
'"