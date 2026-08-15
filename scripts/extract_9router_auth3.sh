#!/bin/bash
# Extract 3000 chars setelah cli-secret def
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 "docker exec 9router node -e '
const s = require(\"fs\").readFileSync(\"/app/.next/server/middleware.js\",\"utf8\");
const i = s.indexOf(\"cli-secret\", 187338);
console.log(s.slice(i, i+3000));
'"
