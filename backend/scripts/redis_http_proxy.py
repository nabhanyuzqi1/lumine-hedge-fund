#!/usr/bin/env python3
"""redis_http_proxy.py — HTTP REST gateway untuk Redis (bypass MQL5 socket limitation).

EA polling:
  GET /commands?timeout=30 → BRPOP mt5:commands 30 → {id, action, ...}
  POST /results → PUBLISH mt5:results
  POST /ticks → LPUSH mt5:ticks

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
    """BRPOP mt5:commands dengan timeout (long-polling untuk EA).
    Query param: timeout=30 (default 30s).
    Return: {id, action, symbol, ...} atau {} jika timeout.
    """
    timeout = int(request.args.get("timeout", 30))
    try:
        result = r.brpop("mt5:commands", timeout=timeout)
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
        # PUBLISH ke SSE subscribers
        r.publish("mt5:results", payload)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/ticks", methods=["POST"])
def ticks():
    """LPUSH mt5:ticks (tick data dari EA: bid, ask, timestamp).
    Body: {symbol, bid, ask, timestamp}
    """
    try:
        data = request.get_json(force=True)
        payload = json.dumps(data)
        # LPUSH ke journal (batas 1000)
        r.lpush("mt5:ticks", payload)
        r.ltrim("mt5:ticks", 0, 999)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/seed/bars", methods=["POST"])
def seed_bars():
    """LPUSH mt5:seed_bars (history bars dari EA: CopyRates chunk).
    Body: {symbol, timeframe, bars: [{ts, open, high, low, close, volume}]}
    Worker di API backend consume → insert bars_* table.
    """
    try:
        data = request.get_json(force=True)
        payload = json.dumps(data)
        r.lpush("mt5:seed_bars", payload)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/positions", methods=["POST"])
def positions():
    """LPUSH mt5:positions (snapshot open positions dari EA, tiap ~10s).
    Body: {snapshot_ts, positions: [{ticket, symbol, type, volume,
    price_open, sl, tp, profit, time}]}
    PositionSyncWorker di API backend consume → upsert tabel positions.
    """
    try:
        data = request.get_json(force=True)
        payload = json.dumps(data)
        r.lpush("mt5:positions", payload)
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
        r.lpush("mt5:deals", payload)
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
        r.hset("mt5:status", mapping={k: str(v) for k, v in data.items()})
        # TTL 90 detik — kalau EA mati, status otomatis kedaluwarsa
        r.expire("mt5:status", 90)
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
        r.lpush("mt5:logs", payload)
        r.ltrim("mt5:logs", 0, 199)
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
