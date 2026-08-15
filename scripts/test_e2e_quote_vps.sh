#!/bin/bash
# E2E: tick → MarketService → quote API dengan kredensial .env asli
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 '
cd /opt/lumine/backend
KEY=$(grep -E "^VITE_LUMINE_API_KEY" .env | cut -d= -f2)
SEC=$(grep -E "^HMAC_SECRET_KEY" .env | cut -d= -f2)
python3 - "$KEY" "$SEC" <<"PYEOF"
import hashlib, hmac, json, sys, time, urllib.request

BASE = "http://127.0.0.1"
API_KEY = sys.argv[1]
SECRET = sys.argv[2]
EMPTY = hashlib.sha256(b"").hexdigest()
HOST = {"Host": "lumine.biz.id"}

def signed_get(path):
    ts = str(int(time.time()))
    payload = "GET\n" + path + "\n" + ts + "\n" + EMPTY
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(BASE + path, headers=HOST)
    req.add_header("X-Lumine-Api-Key", API_KEY)
    req.add_header("X-Lumine-Timestamp", ts)
    req.add_header("X-Lumine-Signature", sig)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())

try:
    print("quote:", json.dumps(signed_get("/api/v1/market/quote/XAUUSD"))[:400])
except Exception as e:
    print("quote err:", e)
try:
    print("ohlcv-4h:", json.dumps(signed_get("/api/v1/market/ohlcv/XAUUSD?timeframe=4h&limit=3"))[:400])
except Exception as e:
    print("ohlcv err:", e)
PYEOF'
