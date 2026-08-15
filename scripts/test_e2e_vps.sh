#!/bin/bash
# E2E tick→quote test dari dalam VPS (port 80 langsung ke caddy)
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 'python3 - <<"PYEOF"
import hashlib, hmac, json, time, urllib.request

BASE = "http://127.0.0.1"
API_KEY = "bootstrap"
SECRET = "HMAC_SECRET_KEY"
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

tick = {"symbol":"XAUUSD","bid":4301.25,"ask":4301.45,"timestamp":int(time.time()),"equity":10050.0,"balance":10000.0,"margin":432.0}
req = urllib.request.Request(BASE+"/mt5-proxy/ticks", data=json.dumps(tick).encode(), headers={"Content-Type":"application/json", **HOST})
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        print("tick POST:", resp.status)
except Exception as e:
    print("tick POST err:", e)

try:
    print("quote:", json.dumps(signed_get("/api/v1/market/quote/XAUUSD"))[:400])
except Exception as e:
    print("quote err:", e)
PYEOF'
