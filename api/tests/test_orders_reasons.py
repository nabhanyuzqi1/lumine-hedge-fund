"""AUDIT-B: serialisasi event risk — reasons selalu list[str] terbaca manusia.

Latar: di History ada event risk dengan reason kosong dan
`portfolio=[object Object]`. Frontend merender `payload.reasons` via
`String(r)` dan `noteFromPayload` menggabungkan sisa key payload jadi
`key=value`; elemen non-string (dict/objek) di reasons dan objek portfolio
menjadi "[object Object]". Kontrak baru (keputusan desain CEO):

- Server memetakan semua reasons ke list[str]: string -> apa adanya;
  dict/objek -> `label: key=value; ...`; None/empty -> dibuang.
- Objek portfolio TIDAK pernah masuk reasons; tetap terstruktur di
  `payload.portfolio`.
- RISK_PASS boleh reasons kosong (frontend menampilkan label "Risk lolos",
  kartu UI terpisah). Semantik gate ok/rejected/halt tidak berubah.
"""

import json


async def _csrf(client) -> str:
    return (await client.get("/auth/me")).json()["csrf_token"]


def _body(**overrides):
    body = {"symbol": "XAUUSD", "side": "BUY", "volume": 0.1, "sl": 1998.0, "tp": 2005.0}
    body.update(overrides)
    return body


def _risk_events(order: dict) -> list[dict]:
    return [e for e in order["events"]
            if e["to_status"] in ("RISK_PASS", "FAILED", "RISK_FAIL")]


def _assert_reasons_all_str(order: dict) -> list[str]:
    """Semua event risk: payload.reasons ada, list[str], bebas [object Object]."""
    reasons: list[str] = []
    for e in _risk_events(order):
        payload = e["payload"]
        assert "reasons" in payload, f"event {e['to_status']} tanpa reasons"
        assert isinstance(payload["reasons"], list), \
            f"reasons bukan list: {type(payload['reasons'])}"
        for r in payload["reasons"]:
            assert isinstance(r, str), f"reason non-string: {r!r}"
            assert "[object Object]" not in r, f"reason tak terbaca: {r!r}"
            assert r.strip() != "", f"reason kosong: {r!r}"
            reasons.append(r)
    return reasons


# ── humanize helper (unit) ───────────────────────────────────────────────────

def test_humanize_string_passthrough():
    from app.routes import _humanize_reasons

    assert _humanize_reasons(["spread 0.60 exceeds max 0.50"]) == \
        ["spread 0.60 exceeds max 0.50"]
    # whitespace-only dibuang
    assert _humanize_reasons(["  ", "ok"]) == ["ok"]


def test_humanize_none_and_empty_dropped():
    from app.routes import _humanize_reasons

    assert _humanize_reasons([None, "", [], {}, "x"]) == ["x"]


def test_humanize_dict_uses_label_key_value():
    from app.routes import _humanize_reason

    out = _humanize_reason({"label": "auto lot", "risk_usd": 50.0, "equity": 10000.0})
    assert out == "auto lot: risk_usd=50.0; equity=10000.0"
    # tanpa label -> key=value saja
    out = _humanize_reason({"code": "E123", "symbol": "XAUUSD"})
    assert out == "E123: symbol=XAUUSD"
    # tanpa field label/reason/message/code -> key=value
    out = _humanize_reason({"a": 1, "b": "dua"})
    assert out == "a=1; b=dua"


def test_humanize_object_not_raw_repr():
    from app.routes import _humanize_reason

    class FakeDecision:
        def __str__(self):
            return "decision(ok=False)"

    out = _humanize_reason(FakeDecision())
    assert out == "decision(ok=False)"
    assert "object at" not in out


def test_humanize_nested_list():
    from app.routes import _humanize_reasons

    # list di dalam list = SATU reason multi-bagian -> digabung "a; b"
    assert _humanize_reasons([["a", None, "b"]]) == ["a; b"]
    # list pertama jadi "a", list kedua tetap elemen tersendiri
    assert _humanize_reasons([["a", None, ""], "b"]) == ["a", "b"]


# ── integrasi POST /orders ───────────────────────────────────────────────────

async def test_rejected_order_reasons_all_strings(client):
    """Order ditolak gate: semua elemen payload.reasons bertipe str, tanpa
    [object Object], dan rejected_reasons respons konsisten.

    Tanpa tick -> spread filter gagal -> order FAILED (pola sama dengan
    test_orders_api.test_order_risk_reject_recorded_as_failed).
    """
    resp = await client.post("/orders", json=_body(),
                             headers={"x-csrf-token": await _csrf(client)})
    assert resp.status_code == 422, resp.text
    order = (await client.get(f"/orders/{resp.json()['id']}")).json()
    assert order["status"] == "FAILED"

    reasons = _assert_reasons_all_str(order)
    assert reasons, "order ditolak harus punya reason terbaca"
    # respons HTTP juga list[str]
    rejected = resp.json()["rejected_reasons"]
    assert isinstance(rejected, list)
    assert all(isinstance(r, str) for r in rejected)
    assert "[object Object]" not in json.dumps(rejected)


async def test_rejected_order_with_dict_reason_becomes_readable(client):
    """Elemen reasons berupa dict (mis. dari gate masa depan) TIDAK sampai ke
    payload sebagai objek: dipetakan ke string label: key=value."""
    from app import risk

    orig = risk.risk_gate

    def gate_with_dict_reason(order, ctx):
        decision = orig(order, ctx)
        decision.reasons.append({"label": "stres uji", "risk_usd": 12.5})
        decision.ok = False
        return decision

    import app.routes as routes
    routes.risk_gate = gate_with_dict_reason
    try:
        resp = await client.post("/orders", json=_body(),
                                 headers={"x-csrf-token": await _csrf(client)})
    finally:
        routes.risk_gate = orig

    assert resp.status_code == 422, resp.text
    order = (await client.get(f"/orders/{resp.json()['id']}")).json()
    assert order["status"] == "FAILED"
    reasons = _assert_reasons_all_str(order)
    assert any("stres uji: risk_usd=12.5" == r for r in reasons), reasons


async def test_risk_pass_event_payload_structured(client, tick_2000):
    """Order lolos: event RISK_PASS punya payload terstruktur — reasons
    list[str], portfolio dict — tidak ada object ter-stringify."""
    resp = await client.post("/orders", json=_body(),
                             headers={"x-csrf-token": await _csrf(client)})
    assert resp.status_code == 201, resp.text
    order = (await client.get(f"/orders/{resp.json()['id']}")).json()
    assert order["status"] == "RISK_PASS"

    reasons = _assert_reasons_all_str(order)
    gate = [e for e in order["events"] if e["to_status"] == "RISK_PASS"]
    assert len(gate) == 1
    payload = gate[0]["payload"]
    assert payload["risk"] == "pass"
    # RISK_PASS boleh reasons kosong (frontend menampilkan "Risk lolos")
    assert isinstance(payload["reasons"], list)
    assert all(isinstance(r, str) for r in reasons)
    # portfolio tetap objek terstruktur, BUKAN string "[object Object]"
    assert isinstance(payload["portfolio"], dict)
    assert "limits" in payload["portfolio"]
    assert "[object Object]" not in json.dumps(payload)


async def test_failed_order_event_payload_still_has_portfolio_dict(client):
    """Order gagal gate: portfolio snapshot tetap terstruktur di payload
    (tidak digabung ke reasons), reasons list[str]."""
    resp = await client.post("/orders", json=_body(),
                             headers={"x-csrf-token": await _csrf(client)})
    assert resp.status_code == 422, resp.text
    order = (await client.get(f"/orders/{resp.json()['id']}")).json()
    assert order["status"] == "FAILED"
    gate = [e for e in order["events"] if e["to_status"] == "FAILED"]
    assert len(gate) == 1
    payload = gate[0]["payload"]
    assert payload["risk"] == "rejected"
    assert isinstance(payload["reasons"], list) and payload["reasons"]
    assert all(isinstance(r, str) for r in payload["reasons"])
    assert isinstance(payload["portfolio"], dict)
    assert "[object Object]" not in json.dumps(payload)
