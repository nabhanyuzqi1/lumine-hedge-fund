"""E2E smoke: signed requests against the live backend (port 8010).

Mirrors the frontend signing scheme (frontend/src/lib/api/auth.ts) so this
proves the exact payload the browser will send.
"""
import hashlib
import hmac
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8010"
SECRET = "bootstrap-secret-e2e"
KEY = "bootstrap"

_last_ts = {"v": 0}


def sign(method, path, body=b""):
    ts = max(int(time.time()), _last_ts["v"] + 1)
    _last_ts["v"] = ts
    body_hash = hashlib.sha256(body).hexdigest()
    payload = f"{method}\n{path}\n{ts}\n{body_hash}".encode()
    sig = hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return str(ts), sig


def request(method, path, body=None, signed=True):
    data = None if body is None else json.dumps(body).encode()
    headers = {}
    if signed:
        ts, sig = sign(method, path, data or b"")
        headers = {
            "X-Lumine-API-Key": KEY,
            "X-Lumine-Timestamp": ts,
            "X-Lumine-Signature": sig,
            "Content-Type": "application/json",
        }
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, {"raw": raw.decode(errors="replace")[:300]}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw.decode(errors="replace")[:300]}


def main():
    results = []

    # 1. unsigned -> 401
    status, body = request("GET", "/api/v1/portfolio/summary", signed=False)
    results.append(("unsigned request -> 401", status == 401 and body["error"]["code"] == "MISSING_AUTH", f"status={status} code={body.get('error', {}).get('code')}"))

    # 2. market cluster
    status, body = request("GET", "/api/v1/market/quote/XAUUSD")
    q = body["data"]
    results.append(("GET market/quote/XAUUSD", status == 200 and q["symbol"] == "XAUUSD" and float(q["bid"]) < float(q["ask"]), f"bid={q['bid']} ask={q['ask']}"))

    status, body = request("GET", "/api/v1/market/quotes?symbols=XAUUSD&symbols=EURUSD")
    results.append(("GET market/quotes (batch)", status == 200 and set(body["data"]) == {"XAUUSD", "EURUSD"}, f"keys={list(body['data'])}"))

    status, body = request("GET", "/api/v1/market/ohlcv/XAUUSD?timeframe=1h&limit=3")
    bars = body["data"]
    results.append(("GET market/ohlcv", status == 200 and len(bars) == 3 and bars[0]["symbol"] == "XAUUSD", f"bars={len(bars)}"))

    status, body = request("GET", "/api/v1/market/symbol/XAUUSD")
    results.append(("GET market/symbol/XAUUSD", status == 200 and body["data"]["tick_size"] == "0.01", f"tick={body['data']['tick_size']}"))

    status, body = request("GET", "/api/v1/market/symbols")
    results.append(("GET market/symbols", status == 200 and len(body["data"]) >= 2, f"count={len(body['data'])}"))

    status, body = request("GET", "/api/v1/market/volatility/XAUUSD?window=14")
    results.append(("GET market/volatility", status == 200 and 0 < body["data"]["volatility"] < 1, f"vol={body['data']['volatility']}"))

    status, body = request("GET", "/api/v1/market/correlation?symbols=XAUUSD&symbols=EURUSD")
    m = body["data"]
    results.append(("GET market/correlation", status == 200 and m["XAUUSD"]["XAUUSD"] == 1.0 and m["EURUSD"]["XAUUSD"] == m["XAUUSD"]["EURUSD"], f"sym={m['EURUSD']['XAUUSD']==m['XAUUSD']['EURUSD']}"))

    status, body = request("GET", "/api/v1/market/spread/XAUUSD?period=60")
    s = body["data"]
    results.append(("GET market/spread", status == 200 and float(s["min_spread"]) <= float(s["avg_spread"]) <= float(s["max_spread"]), f"spread={s['avg_spread']}"))

    status, body = request("GET", "/api/v1/market/session/XAUUSD")
    results.append(("GET market/session", status == 200 and body["data"]["current_session"] in {"asian", "european", "american", "off"}, f"session={body['data']['current_session']}"))

    status, body = request("GET", "/api/v1/market/features/XAUUSD")
    results.append(("GET market/features", status == 200 and "rsi_14" in body["data"]["features"], f"keys={list(body['data']['features'])[:3]}"))

    # 3. PATCH order (ModifyOrderDialog)
    status, body = request("PATCH", "/api/v1/orders/12345678-1234-5678-1234-567812345678", {"price": "2450.00"})
    d = body["data"]
    results.append(("PATCH orders/{id} modify", status == 200 and d["price"] == "2450.00" and d["status"] == "pending", f"price={d['price']} status={d['status']}"))

    # 4. simulate
    status, body = request("POST", "/api/v1/portfolio/default/simulate", {"symbol": "XAUUSD", "side": "buy", "volume": "0.40", "price": "2420.00"})
    results.append(("POST portfolio/simulate", status == 200 and float(body["data"]["margin_required"]) > 0, f"nav={body['data']['projected_nav']} margin={body['data']['margin_required']}"))

    # 5. kill-switch with tier
    status, body = request("POST", "/api/v1/admin/kill-switch", {"reason": "e2e smoke", "armed": True, "tier": "book"})
    results.append(("POST admin/kill-switch tier", status == 200 and body["data"]["tier"] == "book" and body["data"]["armed"] is True, f"armed={body['data']['armed']} tier={body['data']['tier']}"))

    status, body = request("GET", "/api/v1/admin/kill-switch")
    results.append(("GET admin/kill-switch persisted", status == 200 and body["data"]["tier"] == "book", f"tier={body['data']['tier']}"))

    # 6. invalid signature -> 401
    bad_ts, _ = sign("GET", "/api/v1/portfolio/summary", b"")
    req = urllib.request.Request(
        BASE + "/api/v1/portfolio/summary",
        headers={"X-Lumine-API-Key": KEY, "X-Lumine-Timestamp": bad_ts, "X-Lumine-Signature": "f" * 64},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        results.append(("bad signature -> 401", False, "unexpected 200"))
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        results.append(("bad signature -> 401", e.code == 401 and body["error"]["code"] == "INVALID_SIGNATURE", f"status={e.code} code={body['error']['code']}"))

    failed = [r for r in results if not r[1]]
    print(f"{'PASS' if not failed else 'FAIL'}  {len(results) - len(failed)}/{len(results)} checks")
    for name, ok, detail in results:
        print(f"  [{'✓' if ok else '✗'}] {name}  ({detail})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
