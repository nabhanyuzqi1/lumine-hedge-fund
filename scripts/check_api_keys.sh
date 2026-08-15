#!/bin/bash
# Cek key web-frontend di Redis; buat jika belum ada (pakai secret dari .env VITE_LUMINE_API_SECRET)
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
cd /opt/lumine/backend
SEC=$(grep -E "^VITE_LUMINE_API_SECRET" .env | cut -d= -f2)
KEY="web-frontend"
R=$(docker ps --format "{{.Names}}" | grep -i "redis" | grep -v http | head -1)
echo "redis container: $R"
echo "--- existing keys ---"
docker exec $R redis-cli KEYS "lumine:api_key:*"
if ! docker exec $R redis-cli EXISTS "lumine:api_key:$KEY" | grep -q 1; then
  echo "--- creating key $KEY ---"
  docker exec $R redis-cli HSET "lumine:api_key:$KEY" secret "$SEC" scopes "read,write" revoked 0
  echo "created"
fi
echo "--- verify ---"
docker exec $R redis-cli HGETALL "lumine:api_key:$KEY"
'
