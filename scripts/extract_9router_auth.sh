#!/bin/bash
# Extract CLI token check logic dari 9router middleware
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 "docker exec 9router node -e '
const s = require(\"fs\").readFileSync(\"/app/.next/server/middleware.js\",\"utf8\");
const i = s.indexOf(\"cli-secret\");
console.log(\"=== around cli-secret ===\");
console.log(s.slice(Math.max(0,i-400), i+400));
const j = s.indexOf(\"aT=\");
console.log(\"=== aT def ===\");
console.log(s.slice(j, j+400));
'"
