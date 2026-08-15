#!/bin/bash
# Cari AI_PROVIDERS definition di semua chunks
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 "docker exec 9router node -e '
const {execSync} = require(\"child_process\");
const files = execSync(\"ls /app/.next/server/chunks/*.js 2>/dev/null\").toString().trim().split(\"\n\");
for (const f of files.slice(0, 200)) {
  const s = require(\"fs\").readFileSync(f, \"utf8\");
  // cari pola provider registry: authModes / baseUrl / apiBase
  if (s.includes(\"authModes\") || s.includes(\"apiBase\") || s.includes(\"providerAlias\")) {
    console.log(\"=== \", f, \"len\", s.length);
    const i = s.indexOf(\"authModes\");
    if (i !== -1) console.log(s.slice(Math.max(0,i-300), i+300).replace(/\n/g,\" \").slice(0,500));
    break;
  }
}
'"