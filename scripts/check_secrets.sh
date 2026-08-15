#!/bin/bash
# Bandingkan secret frontend vs Redis
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
cd /opt/lumine/backend
echo "--- .env VPS ---"
grep -E "^VITE_LUMINE_API_(KEY|SECRET)" .env | sed "s/\(=.\{8\}\).*/\1.../"
echo "--- container frontend ---"
docker exec backend-frontend-1 env 2>/dev/null | grep -E "VITE_LUMINE_API" | sed "s/\(=.\{8\}\).*/\1.../" || echo "(no env access)"
echo "--- container api ---"
docker exec backend-api-1 env 2>/dev/null | grep -iE "hmac" | sed "s/\(=.\{8\}\).*/\1.../" || echo "(no env access)"
'
