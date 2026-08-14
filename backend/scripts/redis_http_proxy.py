#!/usr/bin/env python3
"""
redis_http_proxy.py — HTTP REST gateway untuk Redis (bypass MQL5 socket limitation).

EA polling:
  GET /commands?timeout=30 → BRPOP mt5:commands 30 → {id, action, ...}
  POST /results → PUBLISH mt5:results + LPUSH mt5:ticks

Bridge tetap pakai Redis raw (tidak berubah).
"""
import json
import os
import sys
from flask import Flask, request, jsonify
import redis

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
    """
    BRPOP mt5:commands dengan timeout (long-polling untuk EA).
    Query param: timeout=30 (default 30s).
    Return: {id, action, symbol, ...} atau {} jika timeout.
    """
    timeout = int(request.args.get("timeout", 30))
    try:
        result = r.brpop("mt5:commands", timeout=timeout)
        if result:
            _, payload = result
            return jsonify(json.loads(payload)), 200
        else:
            # Timeout — return empty
            return jsonify({}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/results", methods=["POST"])
def results():
    """
    PUBLISH mt5:results + LPUSH mt5:ticks (order result dari EA).
    Body: {id, status, ticket, ...}
    """
    try:
        data = request.get_json(force=True)
        payload = json.dumps(data)
        # PUBLISH ke SSE subscribers
        r.publish("mt5:results", payload)
        # LPUSH ke journal (batas 1000)
        r.lpush("mt5:ticks", payload)
        r.ltrim("mt5:ticks", 0, 999)
        return jsonify({{"status": "ok"}}), 200
    except Exception as e:
        return jsonify({{"error": str(e)}}), 500

@app.route("/ticks", methods=["POST"])
def ticks():
    """
    LPUSH mt5:ticks (tick data dari EA: bid, ask, timestamp).
    Body: {{symbol, bid, ask, timestamp}}
    """
    try:
        data = request.get_json(force=True)
        payload = json.dumps(data)
        # LPUSH ke journal (batas 1000)
        r.lpush("mt5:ticks", payload)
        r.ltrim("mt5:ticks", 0, 999)
        return jsonify({{"status": "ok"}}), 200
    except Exception as e:
        return jsonify({{"error": str(e)}}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    app.run(host="0.0.0.0", port=port, debug=False)
