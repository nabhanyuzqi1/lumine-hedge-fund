#!/usr/bin/env python3
"""redis_http_proxy.py — HTTP REST gateway untuk Redis (bypass MQL5 socket limitation).

EA polling:
  GET /commands?timeout=30 → BRPOP mt5:commands 30 → {id, action, ...}
  POST /results → PUBLISH mt5:results
  POST /ticks → LPUSH mt5:ticks

22 Aug 2026 — multi-instance (crypto):
  Header `X-Instance: crypto` (Caddy route /mt5-proxy-crypto set header)
  memisahkan STATUS/LOGS/RESULTS per-instance → key `mt5crypto:*`, sehingga
  instance Exness (BTCUSD 24/7) tidak menimpa status HFM.
  TICKS & SEED/BARS tetap shared (`mt5:ticks`, `mt5:seed_bars`) — MarketService
  dan bar builder sudah symbol-generic, BTCUSD otomatis masuk tanpa ubah backend.

Bridge tetap pakai Redis raw (tidak berubah).
"""
import json
import os

import redis
from flask import Flask, jsonify, request

app = Flask(__name__)

# Redis connection dari env
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=True)


def _ns() -> str:
    """Prefix key per-instance. Tanpa indikasi → `mt5:` (legacy/HFM).

    Instance lain → `mt5crypto:` — status/logs/results terisolasi.

    23 Aug 2026 — Caddy 2.11.4 TIDAK bisa menambah header/query request
    ke upstream (header_up/rewrite diabaikan). Deteksi dari Host header:
    - `lumine.biz.id` (domain) → HFM
    - `166.88.227.177` (IP langsung, EA crypto) → crypto
    """
    host = request.headers.get("Host", "")
    if "166.88.227.177" in host:
        return "mt5crypto:"
    # Fallback: query param atau X-Instance header (test internal)
    qinst = request.args.get("instance", "")
    if qinst:
        clean = "".join(ch for ch in qinst if ch.isalnum() or ch in "-_")
        return f"mt5{clean}:"
    inst = request.headers.get("X-Instance", "")
    if inst:
        clean = "".join(ch for ch in inst if ch.isalnum() or ch in "-_")
        return f"mt5{clean}:"
    return "mt5:"

@app.route("/health", methods=["GET"])
def health():
    """Health check."""
    try:
        r.ping()
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 503

@app.route("/commands", methods=["GET"])
def commands():
    """BRPOP mt5:commands / mt5crypto:commands dengan timeout (long-polling untuk EA).
    Query param: timeout=30 (default 30s).
    Return: {id, action, symbol, ...} atau {} jika timeout.

    23 Aug 2026 — per-instance: header X-Instance (Caddy route /mt5-proxy-crypto)
    memisahkan command queue sehingga EA HFM dan EA crypto TIDAK saling
    mengambil command milik instance lain.
    """
    timeout = int(request.args.get("timeout", 30))
    ns = _ns()
    key = f"{ns}commands"
    try:
        result = r.brpop(key, timeout=timeout)
        if result:
            _, payload = result
            return jsonify(json.loads(payload)), 200
        # Timeout — return empty
        return jsonify({}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/results", methods=["POST"])
def results():
    """PUBLISH mt5:results (order result dari EA).
    Body: {id, status, ticket, error, fill_price}
    """
    try:
        data = request.get_json(force=True)
        payload = json.dumps(data)
        # PUBLISH ke SSE subscribers: channel shared `mt5:results` (backend
        # bridge subscribe di sini) + channel per-instance (observability).
        ns = _ns()
        r.publish("mt5:results", payload)
        if ns != "mt5:":
            r.publish(f"{ns}results", payload)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/ticks", methods=["POST"])
def ticks():
    """LPUSH ke namespace instance (mt5:ticks HFM / mt5crypto:ticks crypto).
    Body: {symbol, bid, ask, timestamp}
    24 Aug 2026: + _ns() — sebelumnya SHARED mt5:ticks untuk semua EA
    (XAUUSD & BTCUSD campur 1 list; payload symbol menyelamatkan, tapi
    namespace harus terpisah per instance agar tidak konflik).
    """
    try:
        raw = request.get_data(cache=True)
        print(f"[TICKS-RAW] len={len(raw)} head={raw[:150]}", flush=True)
        data = request.get_json(force=True)
        payload = json.dumps(data)
        ns = _ns()
        r.lpush(f"{ns}ticks", payload)
        r.ltrim(f"{ns}ticks", 0, 999)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/seed/bars", methods=["POST"])
def seed_bars():
    """LPUSH ke namespace instance (mt5:seed_bars / mt5crypto:seed_bars).
    Body: {symbol, timeframe, bars: [{ts, open, high, low, close, volume}]}
    24 Aug 2026: + _ns() — sebelumnya SHARED.
    """
    try:
        raw = request.get_data(cache=True)
        print(f"[SEED/BARS] len={len(raw)} head={raw[:150]}", flush=True)
        data = request.get_json(force=True)
        payload = json.dumps(data)
        ns = _ns()
        r.lpush(f"{ns}seed_bars", payload)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        # 24 Aug 2026: log error detail — 500 silent membuat EA retry
        # selamanya (seed tidak pernah maju).
        import traceback

        traceback.print_exc()
        print(f"[SEED/BARS-ERR] {type(e).__name__}: {e}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route("/positions", methods=["POST"])
def positions():
    """LPUSH ke namespace instance (mt5:positions / mt5crypto:positions).
    Body: {snapshot_ts, positions: [{ticket, symbol, type, volume,
    price_open, sl, tp, profit, time}]}
    24 Aug 2026: + _ns() — sebelumnya SHARED.
    """
    try:
        data = request.get_json(force=True)
        payload = json.dumps(data)
        ns = _ns()
        r.lpush(f"{ns}positions", payload)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/deals", methods=["POST"])
def deals():
    """LPUSH mt5:deals (history deals dari EA: HistoryDealsGet chunk).
    Body: {symbol, deals: [{ticket, order, type, entry, volume, price,
    profit, commission, time}]}
    Backend consume → sinkronisasi fills / trade journal.
    """
    try:
        data = request.get_json(force=True)
        payload = json.dumps(data)
        ns = _ns()
        r.lpush(f"{ns}deals", payload)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/status", methods=["POST"])
def status():
    """HSET mt5:status (EA status: version, seed phase, ticks, spread,
    session H/L, account metrics). EA push tiap ~5 detik.
    Body: {ea_version, ea_build, seed_phase, ticks_sent, ...}
    """
    try:
        data = request.get_json(force=True)
        ns = _ns()
        key = f"{ns}status"
        r.hset(key, mapping={k: str(v) for k, v in data.items()})
        # TTL 90 detik — kalau EA mati, status otomatis kedaluwarsa
        r.expire(key, 90)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        # v4.12 (18 Aug): log BODY request saat parse gagal — EA kirim JSON
        # yang membuat werkzeug 400 (SendStatus 500). Body 500B pertama.
        raw = ""
        try:
            raw = request.get_data(as_text=True)[:500]
        except Exception:
            pass
        print(f"[STATUS] parse error: {e} | raw={raw}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route("/logs", methods=["POST"])
def logs():
    """LPUSH mt5:logs (EA log line untuk superadmin EA logs panel).
    Body: {ts, line}
    """
    try:
        data = request.get_json(force=True)
        payload = json.dumps(data)
        ns = _ns()
        key = f"{ns}logs"
        r.lpush(key, payload)
        r.ltrim(key, 0, 199)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    # PITFALL (18 Aug 2026): tanpa threaded=True Flask single-threaded —
    # GET /commands?timeout=1 (long-poll 1s) memblokir satu-satunya thread;
    # POST /status (dan lainnya) antri > EA WebRequest timeout 3s → socket
    # tertutup → 500. EA kirim 5 request/detik → race hampir konstan.
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
