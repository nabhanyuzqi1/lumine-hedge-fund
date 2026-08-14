"""Live RPC decision-cycle test against the VPS (signed, web-frontend key)."""

import hashlib
import hmac
import json
import os
import time
import urllib.request

BASE = os.environ.get("BASE_URL", "http://166.88.227.177")
KEY = os.environ.get("KEY", "web-frontend")
SECRET = os.environ["HMAC_SECRET_KEY"]

_last = {"ts": 0}


def _ts() -> str:
    now = max(int(time.time()), _last["ts"] + 1)
    _last["ts"] = now
    return str(now)


def _signed(method: str, path: str, body: dict | None) -> dict:
    data = json.dumps(body).encode() if body is not None else b""
    ts = _ts()
    payload = f"{method}\n{path}\n{ts}\n{hashlib.sha256(data).hexdigest()}"
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        BASE + path,
        data=data or None,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Lumine-API-Key": KEY,
            "X-Lumine-Timestamp": ts,
            "X-Lumine-Signature": sig,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> None:
    print("== enqueue run-decision-cycle ==")
    envelope = _signed("POST", "/api/v1/rpc/run-decision-cycle", None)
    receipt = envelope["data"]
    command_id = receipt["command_id"]
    print("receipt:", receipt["command"], receipt["status"], command_id)

    for _ in range(10):
        time.sleep(2)
        status_envelope = _signed("GET", f"/api/v1/rpc/commands/{command_id}", None)
        result = status_envelope["data"]
        print(f"  poll: {result['status']}")
        if result["status"] in ("completed", "failed"):
            print("== result ==")
            print(json.dumps(result, indent=2)[:600])
            return
    raise SystemExit("TIMEOUT waiting for worker result")


if __name__ == "__main__":
    main()
