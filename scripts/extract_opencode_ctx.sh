#!/bin/bash
# Extract provider ids dari chunk 235.js (AI_PROVIDERS)
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 "docker exec 9router node -e '
const s = require(\"fs\").readFileSync(\"/app/.next/server/chunks/235.js\",\"utf8\");
// Cari pola \"opencode\":{...} atau opencode:{
const i = s.indexOf(JSON.stringify(\"opencode\"));
console.log(\"context around opencode:\");
console.log(s.slice(Math.max(0,i-100), i+400).replace(/\n/g, \" \"));
'"