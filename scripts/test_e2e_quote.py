#!/usr/bin/env python
"""Test end-to-end: kirim tick via proxy (simulasi EA) → GET /market/quote."""
import hashlib
import hmac
import json
import time
import urllib.request

BASE = "http://lumine.biz.id"
API_KEY = "bootstrap"
SECRET = "HMAC_SECRET_KEY"


def signed_get(path: str, secret: str = SECRET) -> dict:
    ts = str(int(time.time()))
    body = b""
    payload = f"GET\n{path}\n{ts}\n{hashlib.sha256(body).hexdigest()}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(BASE + path)
    req.add_header("X-Lumine-Api-Key", API_KEY)
    req.add_header("X-Lumine-Timestamp", ts)
    req.add_header("X-Lumine-Signature", sig)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


# 1. Kirim tick (simulasi EA)
tick = {
    "symbol": "XAUUSD", "bid": 4301.25, "ask": 4301.45,
    "timestamp": int(time.time()),
    "equity": 10050.0, "balance": 10000.0, "margin": 432.0,
}
req = urllib.request.Request(
    BASE + "/mt5-proxy/ticks",
    data=json.dumps(tick).encode(),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=10) as resp:
    print("tick POST:", resp.status)

# 2. Baca quote (harus mid ~4301.35)
out = signed_get("/api/v1/market/quote?symbol=XAUUSD")
print("quote:", json.dumps(out, indent=2)[:600])
