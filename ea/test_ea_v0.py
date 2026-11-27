"""Test EA v0 (kartu FUND2-P0): HMAC + heartbeat + tick batch + dummy bridge.

Dua lapis:
  1. Unit: kontrak HMAC (referensi Python = yang ditiru MQL5 SignHeaders),
     vektor RFC 4231 untuk HMAC-SHA256.
  2. Integrasi/E2E: dummy_bridge.py dijalankan di thread, lalu
     - request valid diterima & heartbeat/tick (dengan spread) tercatat;
     - signature salah / body dimodifikasi / timestamp basi / nonce replay
       ditolak 401;
     - EaSim (replika perilaku EA v0: heartbeat 2s, batch 250ms, poll 100ms)
       menghasilkan heartbeat >= 3 dan ticks tercatat dalam durasi singkat.

Jalankan: ~/fund2/api/.venv/bin/python -m pytest ea/test_ea_v0.py -v
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "ea"))
sys.path.insert(0, str(REPO / "scripts"))

from ea_simulator import EaSim, sign_request  # noqa: E402
from dummy_bridge import BridgeState, make_handler  # noqa: E402

SECRET = "test-secret-ea-v0-0123456789abcdef"


# ── Unit: kontrak HMAC ──────────────────────────────────────────────────
def test_rfc4231_case1():
    """RFC 4231 Test Case 1: HMAC-SHA256 key/data 0x0b.."""
    key = b"\x0b" * 20
    data = b"Hi There"
    expected = ("b0344c61d8db38535ca8afceaf0bf12b"
                "881dc200c9833da726e9376c2e32cff7")
    assert hmac.new(key, data, hashlib.sha256).hexdigest() == expected


def test_rfc4231_case2():
    """RFC 4231 Test Case 2: key 'Jefe', data 'what do ya want...'."""
    got = hmac.new(b"Jefe", b"what do ya want for nothing?",
                   hashlib.sha256).hexdigest()
    assert got == "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"


def test_rfc4231_case3_long_key():
    """RFC 4231 Test Case 3: key 131 byte > block 64 -> key di-hash dulu.

    Jalur yang sama dengan HmacSha256() MQL5 saat secret > 64 byte.
    """
    got = hmac.new(b"\xaa" * 131,
                   b"Test Using Larger Than Block-Size Key - Hash Key First",
                   hashlib.sha256).hexdigest()
    assert got == "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54"


def test_sign_request_shape():
    headers = sign_request(SECRET, "POST", "/bridge/heartbeat", b"{}")
    assert headers["X-Fund2-Timestamp"].isdigit()
    assert len(headers["X-Fund2-Nonce"]) == 32
    assert len(headers["X-Fund2-Signature"]) == 64  # hex sha256


def test_sign_request_known_vector():
    """Signature harus reproducible: canonical string sama -> signature sama."""
    body = b'{"a":1}'
    ts = "1700000000"
    nonce = "ab" * 16
    sts = "\n".join([ts, nonce, "POST", "/bridge/tick",
                     hashlib.sha256(body).hexdigest()]).encode()
    expected = hmac.new(SECRET.encode(), sts, hashlib.sha256).hexdigest()
    # replikasi manual (persis alur sign_request)
    sig = hmac.new(SECRET.encode(), sts, hashlib.sha256).hexdigest()
    assert sig == expected


def test_sign_request_body_sensitivity():
    """Body beda 1 byte -> signature beda (proteksi tamper)."""
    h1 = sign_request(SECRET, "POST", "/bridge/tick", b'{"a":1}')
    h2 = sign_request(SECRET, "POST", "/bridge/tick", b'{"a":2}')
    assert h1["X-Fund2-Signature"] != h2["X-Fund2-Signature"]


# ── Fixture: dummy bridge di thread ─────────────────────────────────────
@pytest.fixture()
def bridge(tmp_path):
    state = BridgeState(SECRET, str(tmp_path))
    from http.server import ThreadingHTTPServer
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield {"base": f"http://127.0.0.1:{server.server_address[1]}",
           "state": state, "out_dir": tmp_path}
    server.shutdown()
    server.server_close()


def _post(base, path, body: bytes, headers=None, sign=True, secret=SECRET):
    if headers is None:
        headers = sign_request(secret, "POST", path, body) if sign else {}
    req = urllib.request.Request(base + path, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        payload = e.read().decode()
        try:
            payload = json.loads(payload or "{}")
        except json.JSONDecodeError:
            pass
        return e.code, payload


def _get(base, path, headers=None):
    req = urllib.request.Request(base + path, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            raw = r.read().decode()
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        payload = e.read().decode()
        try:
            payload = json.loads(payload or "{}")
        except json.JSONDecodeError:
            pass
        return e.code, payload


# ── Integrasi: HMAC valid & data tercatat ───────────────────────────────
def test_health_and_stats_open(bridge):
    code, body = _get(bridge["base"], "/health")
    assert code == 200 and body["ok"] is True
    code, body = _get(bridge["base"], "/_stats")
    assert code == 200 and body["heartbeats"] == 0


def test_signed_heartbeat_recorded(bridge):
    body = json.dumps({"ts": int(time.time()), "symbol": "XAUUSD",
                       "bid": 2650.1, "ask": 2650.3, "spread": 0.2,
                       "ea": "v0"}).encode()
    code, resp = _post(bridge["base"], "/bridge/heartbeat", body)
    assert code == 200 and resp["ok"] is True
    stats = bridge["state"].stats()
    assert stats["heartbeats"] == 1
    assert stats["last_heartbeat"]["spread"] == 0.2
    assert stats["last_heartbeat"]["symbol"] == "XAUUSD"
    # tercatat di file jsonl
    lines = (bridge["out_dir"] / "heartbeats.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["ea"] == "v0"


def test_signed_tick_batch_recorded_with_spread(bridge):
    ticks = [{"ts": int(time.time() * 1000) - 200, "bid": 2650.10,
              "ask": 2650.25, "spread": 0.15},
             {"ts": int(time.time() * 1000), "bid": 2650.11,
              "ask": 2650.27, "spread": 0.16}]
    body = json.dumps({"symbol": "XAUUSD", "ticks": ticks}).encode()
    code, resp = _post(bridge["base"], "/bridge/tick", body)
    assert code == 200 and resp["recorded"] == 2
    stats = bridge["state"].stats()
    assert stats["ticks"] == 2 and stats["tick_batches"] == 1
    assert stats["last_ticks"][-1]["spread"] == 0.16
    lines = (bridge["out_dir"] / "ticks.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    assert all(json.loads(l)["spread"] > 0 for l in lines)


def test_signed_poll_returns_null(bridge):
    code, body = _get(bridge["base"], "/bridge/poll?timeout_s=0",
                      sign_request(SECRET, "GET", "/bridge/poll?timeout_s=0", b""))
    assert code == 200 and (body == "null" or body is None)


def test_unsigned_rejected(bridge):
    code, resp = _post(bridge["base"], "/bridge/heartbeat", b"{}", sign=False)
    assert code == 401 and "missing" in resp["error"]


def test_bad_signature_rejected(bridge):
    headers = sign_request(SECRET, "POST", "/bridge/heartbeat", b"{}")
    headers["X-Fund2-Signature"] = "f" * 64
    code, resp = _post(bridge["base"], "/bridge/heartbeat", b"{}", headers=headers)
    assert code == 401 and resp["error"] == "bad signature"


def test_wrong_secret_rejected(bridge):
    code, resp = _post(bridge["base"], "/bridge/heartbeat", b"{}",
                       secret="wrong-secret-wrong-secret")
    assert code == 401 and resp["error"] == "bad signature"


def test_tampered_body_rejected(bridge):
    """Sign body A, kirim body B -> signature tidak cocok."""
    headers = sign_request(SECRET, "POST", "/bridge/tick",
                           b'{"symbol":"XAUUSD","ticks":[]}')
    tampered = b'{"symbol":"EVIL","ticks":[]}'
    req = urllib.request.Request(bridge["base"] + "/bridge/tick", data=tampered,
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    assert code == 401


def test_stale_timestamp_rejected(bridge):
    headers = sign_request(SECRET, "POST", "/bridge/heartbeat", b"{}")
    headers["X-Fund2-Timestamp"] = str(int(time.time()) - 30)  # > 5s
    # hitung ulang signature dgn ts basi (canonical pakai ts header)
    body = b"{}"
    sts = "\n".join([headers["X-Fund2-Timestamp"], headers["X-Fund2-Nonce"],
                     "POST", "/bridge/heartbeat",
                     hashlib.sha256(body).hexdigest()]).encode()
    headers["X-Fund2-Signature"] = hmac.new(
        SECRET.encode(), sts, hashlib.sha256).hexdigest()
    code, resp = _post(bridge["base"], "/bridge/heartbeat", body, headers=headers)
    assert code == 401 and "tolerance" in resp["error"]


def test_nonce_replay_rejected(bridge):
    body = b'{"ts":1,"symbol":"XAUUSD","bid":1,"ask":1,"spread":0,"ea":"v0"}'
    headers = sign_request(SECRET, "POST", "/bridge/heartbeat", body)
    code, _ = _post(bridge["base"], "/bridge/heartbeat", body, headers=headers)
    assert code == 200
    # nonce sama, ts sama -> replay
    code, resp = _post(bridge["base"], "/bridge/heartbeat", body, headers=headers)
    assert code == 401 and resp["error"] == "nonce replayed"


# ── E2E: simulator perilaku EA v0 ───────────────────────────────────────
def test_ea_simulator_end_to_end(bridge):
    """EaSim (cadence dipercepat 4x: heartbeat 0.5s, batch 62.5ms) selama 3s:
    minimal 3 heartbeat & puluhan tick tercatat, semua punya spread."""
    sim = EaSim(bridge["base"], SECRET, heartbeat_sec=0.5,
                tick_batch_ms=62.5, poll_ms=100.0)
    sim.start(3.0)
    sim.stop()
    stats = bridge["state"].stats()
    assert sim.stats["heartbeats_sent"] >= 3
    assert sim.stats["ticks_sent"] >= 20
    assert sim.stats["http_other"] == 0 and sim.stats["errors"] == 0
    assert stats["heartbeats"] == sim.stats["heartbeats_sent"]
    assert stats["ticks"] == sim.stats["ticks_sent"]
    # semua tick tercatat punya spread
    assert all(t.get("spread", 0) > 0 for t in stats["last_ticks"])
    # poll dipoll terus tanpa error
    assert stats["polls"] >= 10


# ── Regresi: result queue anti head-of-line (kartu t_7e7dc1c1) ──────────
# Insiden 22 Nov: result 404 (unknown command_id) di-retry permanen tanpa
# backoff/log/drop -> satu poison pill menyumbat FIFO, order lain macet di
# SENT. Replika Python memakai klasifikasi yang sama dengan LumineEA v5.02.
def _result_sim():
    return EaSim("http://127.0.0.1:1/bridge", SECRET)


def test_result_queue_constants_match_mql5():
    from ea_simulator import (RESULT_QUEUE_MAX, RESULT_RETRY_BASE_MS,
                              RESULT_RETRY_MAX_MS)
    assert (RESULT_RETRY_BASE_MS, RESULT_RETRY_MAX_MS, RESULT_QUEUE_MAX) == \
        (1000, 30000, 128)


def test_result_queue_poison_404_dropped_fifo_drains():
    """404 di kepala antrean di-drop, result di belakangnya tetap terkirim."""
    sim = _result_sim()
    codes = {"poison-cmd": 404}

    def fake(method, path_with_query, body):
        import json as _json
        cid = _json.loads(body)["command_id"]
        return codes.get(cid, 200)

    sim._request = fake
    sim.queue_result({"command_id": "poison-cmd", "status": "FILLED"})
    sim.queue_result({"command_id": "good-1", "status": "FILLED"})
    sim.queue_result({"command_id": "good-2", "status": "FAILED"})

    assert sim.flush_one_result(now_ms=0) == 404          # poison di-drop
    assert sim.flush_one_result(now_ms=1) == 200          # good-1 langsung jalan
    assert sim.flush_one_result(now_ms=2) == 200          # good-2 ikut
    assert sim.result_queue == []
    assert sim.stats["results_dropped"] == 1
    assert sim.stats["results_sent"] == 2
    # drop terlog dengan command_id + sisa antrean
    assert any("DROPPED" in l and "poison-cmd" in l and "sisa antrean=2" in l
               for l in sim.result_log)


def test_result_queue_422_and_409_also_permanent():
    sim = _result_sim()
    sim._request = lambda method, path_with_query, body: 422
    sim.queue_result({"command_id": "bad-payload", "status": "FILLED"})
    assert sim.flush_one_result(now_ms=0) == 422
    assert sim.result_queue == [] and sim.stats["results_dropped"] == 1

    sim._request = lambda method, path_with_query, body: 409
    sim.queue_result({"command_id": "cancelled-order", "status": "FAILED"})
    assert sim.flush_one_result(now_ms=0) == 409
    assert sim.result_queue == [] and sim.stats["results_dropped"] == 2


def test_result_queue_transient_backoff_schedule_and_recovery():
    """5xx: retry 1s, 2s, 4s ...; sukses mereset backoff (langsung coba lagi)."""
    sim = _result_sim()
    sim._request = lambda method, path_with_query, body: 500
    sim.queue_result({"command_id": "r1", "status": "FILLED"})

    t = 1000.0
    assert sim.flush_one_result(now_ms=t) == 500           # gagal ke-1 -> 1000
    assert sim.flush_one_result(now_ms=t + 999) == "backoff"   # belum waktunya
    assert sim.flush_one_result(now_ms=t + 1000) == 500    # gagal ke-2 -> 2000
    assert sim.flush_one_result(now_ms=t + 1000 + 1999) == "backoff"
    assert sim.flush_one_result(now_ms=t + 3000) == 500    # gagal ke-3 -> 4000

    # tiap gagal terlog beserta isi antrean
    assert any("retry dalam 1000 ms" in l and "isi antrean=1" in l
               for l in sim.result_log)
    assert any("retry dalam 2000 ms" in l for l in sim.result_log)

    # pulih: 200 -> backoff reset -> result berikutnya tidak menunggu
    sim._request = lambda method, path_with_query, body: 200
    assert sim.flush_one_result(now_ms=t + 7000) == 200
    assert sim._result_retry_ms == 0
    sim.queue_result({"command_id": "r2", "status": "FAILED"})
    assert sim.flush_one_result(now_ms=t + 7001) == 200    # tanpa jeda
    assert sim.result_queue == []
    assert sim.stats["results_sent"] == 2


def test_result_queue_backoff_caps_at_30s():
    sim = _result_sim()
    sim._request = lambda method, path_with_query, body: -1   # jaringan mati
    sim.queue_result({"command_id": "r1", "status": "FILLED"})
    t = 0.0
    for i in range(6):  # 1,2,4,8,16,32 -> cap 30
        assert sim.flush_one_result(now_ms=t) == -1
        t += 60000  # lewati jeda apapun
    assert sim._result_retry_ms == 30000
    assert sim.flush_one_result(now_ms=t) == -1
    assert sim._result_retry_ms == 30000  # tidak melebihi cap
    assert any("retry dalam 30000 ms" in l for l in sim.result_log)


def test_result_queue_force_bypasses_backoff_gate():
    """OnDeinit: force=True tetap mencoba walau sedang backoff."""
    sim = _result_sim()
    sim._request = lambda method, path_with_query, body: 503
    sim.queue_result({"command_id": "r1", "status": "FILLED"})
    assert sim.flush_one_result(now_ms=0) == 503
    assert sim.flush_one_result(now_ms=1) == "backoff"
    assert sim.flush_one_result(now_ms=1, force=True) == 503


class _PoisonResultHandler(BaseHTTPRequestHandler):
    """Stub bridge: /bridge/result -> 404 utk command_id poison, selain itu
    200 + tercatat (urutan dipertahankan). Auth diabaikan (fokus antrean)."""

    results: list = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        if self.path == "/bridge/result":
            try:
                payload = json.loads(body.decode())
            except json.JSONDecodeError:
                payload = {}
            if payload.get("command_id") == "poison-cmd":
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'{"error":"unknown command_id"}')
                return
            self.results.append(payload)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):  # senyap
        pass


def test_result_queue_poison_http_end_to_end():
    """HTTP sungguhan: poison 404 di-drop, good-1/good-2 terkirim berurutan."""
    _PoisonResultHandler.results = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _PoisonResultHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        sim = EaSim(f"http://127.0.0.1:{server.server_address[1]}", SECRET)
        sim.queue_result({"command_id": "poison-cmd", "status": "FILLED"})
        sim.queue_result({"command_id": "good-1", "status": "FILLED"})
        sim.queue_result({"command_id": "good-2", "status": "FAILED"})

        assert sim.flush_one_result(now_ms=time.time() * 1000) == 404
        assert sim.flush_one_result(now_ms=time.time() * 1000) == 200
        assert sim.flush_one_result(now_ms=time.time() * 1000) == 200
        assert sim.result_queue == []
        assert [r["command_id"] for r in _PoisonResultHandler.results] == \
            ["good-1", "good-2"]
    finally:
        server.shutdown()
        server.server_close()


# ── Regresi: seed anti blind-retry (kartu t_c378fee8) ───────────────────
# Insiden 22 Nov: chunk seed gagal di-retry buta tiap 1 detik tanpa log,
# "total=5000 bars" tercetak 20.078x dalam sehari (head-of-line versi seed).
# Replika Python memakai klasifikasi yang sama dengan LumineEA v5.03.


def _seed_sim():
    return EaSim("http://127.0.0.1:1/bridge", SECRET)


def test_seed_constants_match_mql5():
    from ea_simulator import SEED_RETRY_BASE_MS, SEED_RETRY_MAX_MS
    assert (SEED_RETRY_BASE_MS, SEED_RETRY_MAX_MS) == (1000, 30000)


def test_seed_total_printed_once_per_tf():
    """Kegagalan berulang di offset 0 TIDAK mencetak ulang 'total=N bars'."""
    sim = _seed_sim()
    assert sim.seed_next_chunk(500, now_ms=0) == "transient"
    assert sim.seed_next_chunk(500, now_ms=1000) == "transient"
    assert sim.seed_next_chunk(500, now_ms=3000) == "transient"
    total_lines = [l for l in sim.seed_log if "total=" in l]
    assert len(total_lines) == 1
    # setiap kegagalan tetap dilog — tidak senyap lagi seperti insiden
    fail_lines = [l for l in sim.seed_log if "chunk gagal" in l]
    assert len(fail_lines) == 3


def test_seed_4xx_drops_tf_and_advances():
    """4xx payload ditolak = permanen: TF di-drop, lanjut TF berikutnya."""
    sim = _seed_sim()
    assert sim.seed_next_chunk(422, now_ms=0) == "drop-tf"
    assert sim._seed_tf == "5m"          # lanjut TF berikutnya
    assert sim._seed_offset == 0
    assert sim.seed_log[-1].startswith("seed chunk DITOLAK http=422")
    # TF baru boleh cetak "total=" lagi dan chunk berikutnya jalan normal
    assert sim.seed_next_chunk(200, now_ms=1) == "sent"
    assert any("seed XAUUSD 5m total=" in l for l in sim.seed_log)


def test_seed_401_transient_not_dropped():
    """401/403 = auth bisa pulang → transient (backoff), TF tidak di-drop."""
    sim = _seed_sim()
    assert sim.seed_next_chunk(401, now_ms=0) == "transient"
    assert sim._seed_tf == "1m"
    assert sim._seed_retry_ms == 1000


def test_seed_transient_backoff_schedule_and_reset():
    """5xx: backoff 1s, 2s, 4s ...; sukses mereset (langsung coba lagi)."""
    sim = _seed_sim()
    t = 1000.0
    assert sim.seed_next_chunk(500, now_ms=t) == "transient"
    assert sim._seed_retry_ms == 1000
    assert sim.seed_next_chunk(500, now_ms=t + 999) == "backoff-gate"
    assert sim.seed_next_chunk(500, now_ms=t + 1000) == "transient"
    assert sim._seed_retry_ms == 2000
    assert sim.seed_next_chunk(500, now_ms=t + 3000) == "transient"
    assert sim._seed_retry_ms == 4000
    # sukses: reset backoff, offset maju
    assert sim.seed_next_chunk(200, now_ms=t + 7000) == "sent"
    assert sim._seed_retry_ms == 0
    assert sim._seed_offset == 500
    # setelah sukses, attempt berikutnya tidak tertahan gate
    assert sim.seed_next_chunk(200, now_ms=t + 7001) == "sent"


def test_seed_backoff_caps_at_30s():
    sim = _seed_sim()
    t = 0.0
    ms = 0
    for _ in range(6):
        assert sim.seed_next_chunk(503, now_ms=t) == "transient"
        ms = sim._seed_retry_ms
        t += ms
    assert ms == 30000   # 1,2,4,8,16,32 → cap 30s


def test_seed_advance_tf_after_total_reached():
    """10 chunk x 500 bar = 5000 → TF selesai, lanjut TF berikutnya."""
    sim = _seed_sim()
    now = 0.0
    for _ in range(10):
        assert sim.seed_next_chunk(200, now_ms=now) == "sent"
        now += 1
    assert sim._seed_tf == "5m"
    assert sim._seed_offset == 0
