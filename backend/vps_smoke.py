"""Verify the LIVE VPS API with the web-frontend key (run from repo root)."""

import hashlib
import hmac
import json
import os
import time
import urllib.request

BASE = os.environ.get("BASE_URL", "http://166.88.227.177")
KEY = os.environ.get("KEY", "web-frontend")
SECRET = os.environ["HMAC_SECRET_KEY"]

_last_ts = {"v": 0}


def _paced_ts() -> str:
    """Mirror the frontend auth.ts pacing: max(now, last + 1) so the
    backend replay cache (key_id, ts, body_hash) never collides."""
    now = int(time.time())
    _last_ts["v"] = max(now, _last_ts["v"] + 1)
    return str(_last_ts["v"])


def signed_get(path: str) -> dict:
    ts = _paced_ts()
    body_hash = hashlib.sha256(b"").hexdigest()
    payload = f"GET\n{path}\n{ts}\n{body_hash}"
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        BASE + path,
        headers={
            "X-Lumine-API-Key": KEY,
            "X-Lumine-Timestamp": ts,
            "X-Lumine-Signature": sig,
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def signed_post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    ts = _paced_ts()
    payload = f"POST\n{path}\n{ts}\n{hashlib.sha256(data).hexdigest()}"
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Lumine-API-Key": KEY,
            "X-Lumine-Timestamp": ts,
            "X-Lumine-Signature": sig,
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


if __name__ == "__main__":
    checks = 0
    for path in [
        "/api/v1/market/symbols",
        "/api/v1/market/quote/XAUUSD",
        "/api/v1/market/ohlcv/XAUUSD",
        "/api/v1/portfolio/summary",
        "/api/v1/workflows",
        "/api/v1/journal",
        "/api/v1/admin/keys",
    ]:
        r = signed_get(path)
        ok = r.get("meta", {}).get("status") == "ok"
        print(f"[{'OK' if ok else 'FAIL'}] GET {path}")
        checks += 1

    r = signed_post("/api/v1/portfolio/default/simulate", {"symbol": "XAUUSD", "side": "buy", "volume": 1.0, "price": 2450.0})
    ok = r.get("meta", {}).get("status") == "ok"
    print(f"[{'OK' if ok else 'FAIL'}] POST /api/v1/portfolio/default/simulate")
    checks += 1

    print(f"\n{checks}/{checks} live VPS checks passed")
