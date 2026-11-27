"""Test regresi t_afd7fe4e: pre-flight gate + fail_reason wajib + anggaran latensi.

Tiga butir kartu diuji di sini:

A. Gate pre-flight deterministik sebelum LLM (sesi pasar dari tabel, EA offline,
   tick basi, spread, kill-switch/drawdown) — logika murni + endpoint API
   (yang juga mencatat event `CYCLE_SKIPPED`).
B. `fail_reason` WAJIB + terstruktur (`fail_detail`) untuk setiap FAILED, dan
   constraint DB `orders_failed_requires_reason` menolak FAILED tanpa alasan.
C. Anggaran latensi: `max_tokens` per tahap + prompt statis-dulu (prefix cache)
   + ringkasan p95 terhadap target 35 s.

Semua test memakai DB test per-sesi dari `conftest.py`; tidak ada akses DB live.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app import (db, fail_reason, kill_switch, llm_budget, market,
                 market_sessions, preflight)


def _wib(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=market_sessions.WIB)


# ── A1. Sesi pasar dari tabel ────────────────────────────────────────────────
def _xau_rows():
    return [
        {"symbol": "XAUUSD", "weekday": wd, "open_minute": 360,
         "close_minute": 299, "timezone": "Asia/Jakarta", "enabled": True}
        for wd in range(0, 5)
    ]


def _btc_rows():
    return [
        {"symbol": "BTCUSD", "weekday": wd, "open_minute": 0,
         "close_minute": 1440, "timezone": "Asia/Jakarta", "enabled": True}
        for wd in range(0, 7)
    ]


def test_session_xauusd_buka_dan_jeda_harian():
    rows = _xau_rows()
    # Rabu 26 Nov 2026 07:30 WIB -> bursa buka.
    assert market_sessions.session_open(rows, _wib(2026, 11, 26, 7, 30))[0] is True
    # Jeda harian 04:59-06:00 WIB -> tutup (tidak ada jendela yang memuatnya).
    open_, reason = market_sessions.session_open(rows, _wib(2026, 11, 26, 5, 30))
    assert open_ is False
    assert reason.startswith(market_sessions.CODE_CLOSED)
    # Sabtu 06:00 WIB -> akhir pekan, tutup.
    assert market_sessions.session_open(rows, _wib(2026, 11, 28, 6, 30))[0] is False


def test_session_xauusd_jendela_lewat_tengah_malam():
    """Jumat 06:00 -> Sabtu 04:59: Sabtu 03:00 masih buka (baris Jumat)."""
    rows = _xau_rows()
    assert market_sessions.session_open(rows, _wib(2026, 11, 28, 3, 0))[0] is True
    assert market_sessions.session_open(rows, _wib(2026, 11, 28, 5, 30))[0] is False


def test_session_btcusd_24_7():
    rows = _btc_rows()
    for moment in (_wib(2026, 11, 26, 7, 30), _wib(2026, 11, 28, 3, 0),
                   _wib(2026, 11, 29, 23, 59)):
        assert market_sessions.session_open(rows, moment)[0] is True


def test_session_tanpa_baris_fail_closed():
    open_, reason = market_sessions.session_open([], _wib(2026, 11, 26, 7, 30))
    assert open_ is False
    assert reason == market_sessions.CODE_MISSING


def test_session_disabled_fail_closed():
    rows = [dict(r, enabled=False) for r in _btc_rows()]
    open_, reason = market_sessions.session_open(rows, _wib(2026, 11, 26, 7, 30))
    assert open_ is False
    assert reason == market_sessions.CODE_DISABLED


def test_seed_migrasi_menyediakan_sesi_untuk_simbol_trading():
    """Simbol yang diizinkan owner harus punya baris sesi (kalau tidak: blok).

    Bukti bahwa seed migrasi o015 benar-benar ada di DB (bukan hardcode kode).
    """
    import asyncio

    async def run():
        settings = await db.get_settings()
        symbols = [s for s in settings.get("allowed_symbols") or [] if s]
        async with db.pool().connection() as conn:
            return await market_sessions.load_rows(conn, symbols)

    rows = asyncio.run(run())
    assert rows, "allowed_symbols kosong: tidak ada yang bisa diuji"
    for symbol, list_rows in rows.items():
        assert list_rows, f"{symbol} tidak punya baris market_sessions (seed o015 hilang)"


# ── A2. Rantai pre-flight (murni) ───────────────────────────────────────────
def _settings(**over):
    base = {
        "allowed_symbols": ["XAUUSD"],
        "max_tick_age_s": 3.0,
        "max_spread": 0.5,
        "symbol_specs": {"XAUUSD": {"contract_size": 100.0, "sl_min_usd": 100.0,
                                    "sl_max_usd": 5000.0, "vol_max_lot": 0.5,
                                    "spread_abs_max_usd": 0.5}},
    }
    base.update(over)
    return base


def _tick(age_s=0.5, spread=0.2, trade_enabled=None):
    import time
    return {"bid": 2000.0, "ask": 2000.0 + spread, "spread": spread,
            "ts": time.time() - age_s, "trade_enabled": trade_enabled}


def test_preflight_lolos_saat_semua_baik():
    result = preflight.evaluate(
        settings=_settings(), symbols=["XAUUSD"],
        sessions={"XAUUSD": _xau_rows()}, ticks={"XAUUSD": _tick()},
        ea_age_s=1.0, drawdown_pct=0.1, now=_wib(2026, 11, 26, 7, 30))
    assert result["ok"] is True
    assert result["allowed"] == ["XAUUSD"]
    assert result["blocked"] == []
    assert result["reason"] is None


@pytest.mark.parametrize("case,expected", [
    ("market_closed", preflight.CODE_SESSION),
    ("ea_offline", preflight.CODE_EA_OFFLINE),
    ("stale_tick", preflight.CODE_STALE_TICK),
    ("wide_spread", preflight.CODE_SPREAD),
    ("no_tick", preflight.CODE_NO_TICK),
])
def test_preflight_menolak_dengan_kode_stabil(case, expected):
    now = _wib(2026, 11, 26, 7, 30)
    kwargs: dict = {"settings": _settings(), "symbols": ["XAUUSD"],
                    "sessions": {"XAUUSD": _xau_rows()},
                    "ticks": {"XAUUSD": _tick()},
                    "ea_age_s": 1.0, "drawdown_pct": 0.1, "now": now}
    if case == "market_closed":
        kwargs["now"] = _wib(2026, 11, 26, 5, 30)
    elif case == "ea_offline":
        kwargs["ea_age_s"] = 999.0
    elif case == "stale_tick":
        kwargs["ticks"] = {"XAUUSD": _tick(age_s=30.0)}
    elif case == "wide_spread":
        kwargs["ticks"] = {"XAUUSD": _tick(spread=5.0)}
    elif case == "no_tick":
        kwargs["ticks"] = {"XAUUSD": None}
    result = preflight.evaluate(**kwargs)
    assert result["ok"] is False
    assert result["allowed"] == []
    assert result["blocked"][0]["code"] == expected
    assert result["reason"].startswith("preflight_blocked:")
    # Tiap simbol wajib punya alasan terstruktur (audit + UI).
    assert result["blocked"][0]["stage"] in {
        preflight.STAGE_SESSION, preflight.STAGE_EA, preflight.STAGE_DATA}


def test_preflight_spread_ambang_per_simbol():
    """BTCUSD spread ~30 USD tidak boleh diblok ambang global 0.5."""
    settings = _settings(symbol_specs={
        "BTCUSD": {"contract_size": 1.0, "sl_min_usd": 100.0, "sl_max_usd": 5000.0,
                   "vol_max_lot": 0.5, "spread_abs_max_usd": 60.0}})
    result = preflight.evaluate(
        settings=settings, symbols=["BTCUSD"], sessions={"BTCUSD": _btc_rows()},
        ticks={"BTCUSD": {"bid": 90000.0, "ask": 90030.0, "spread": 30.0,
                          "ts": __import__("time").time()}},
        ea_age_s=1.0, drawdown_pct=0.1, now=_wib(2026, 11, 26, 7, 30))
    assert result["ok"] is True


def test_preflight_ea_trade_disabled_memblok():
    result = preflight.evaluate(
        settings=_settings(), symbols=["XAUUSD"], sessions={"XAUUSD": _xau_rows()},
        ticks={"XAUUSD": _tick(trade_enabled=False)}, ea_age_s=1.0,
        drawdown_pct=0.1, now=_wib(2026, 11, 26, 7, 30))
    assert result["ok"] is False
    assert result["blocked"][0]["code"] == preflight.CODE_SYMBOL_DISABLED


def test_preflight_kill_switch_dan_drawdown_memblok():
    now = _wib(2026, 11, 26, 7, 30)
    halted = preflight.evaluate(
        settings=_settings(kill_switch={"active": True, "mode": "GLOBAL_HALT",
                                        "reason": "test"}),
        symbols=["XAUUSD"], sessions={"XAUUSD": _xau_rows()},
        ticks={"XAUUSD": _tick()}, ea_age_s=1.0, drawdown_pct=0.1, now=now)
    assert halted["ok"] is False
    assert halted["blocked"][0]["code"] == preflight.CODE_KILL_SWITCH

    # Drawdown tak terbaca = fail-closed (bukan dianggap 0%).
    unknown = preflight.evaluate(
        settings=_settings(max_daily_drawdown=3.0), symbols=["XAUUSD"],
        sessions={"XAUUSD": _xau_rows()}, ticks={"XAUUSD": _tick()},
        ea_age_s=1.0, drawdown_pct=None, now=now)
    assert unknown["ok"] is False
    assert unknown["blocked"][0]["code"] == preflight.CODE_DRAWDOWN




# ── A3. Endpoint API: siklus diblok dicatat sebagai CYCLE_SKIPPED ───────────
@pytest.mark.asyncio
async def test_endpoint_preflight_memblok_dan_mencatat_event(client, _clean_db):
    """Pasar tutup -> tidak ada yang allowed + satu event CYCLE_SKIPPED.

    Event inilah bukti DoD#1 ("tidak ada pemanggilan LLM saat pasar tutup"):
    tanpa baris ini siklus yang dilewati tidak terlihat di audit mana pun.
    """
    # Penghalang deterministik: EA belum pernah heartbeat (`ea_never_seen`).
    # Sengaja TIDAK memakai "pasar tutup" supaya test tetap bermakna pada jam
    # bursa buka (jalur blok yang sama, kode alasan berbeda).
    from app.state_machine import fetchall

    market.update_tick("XAUUSD", 2000.0, 2000.2, trade_enabled=True)

    r = await client.post("/llm-agent/preflight",
                          json={"cycle_id": "cycle-test-0001", "symbols": ["XAUUSD"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "allowed" in body and "blocked" in body
    assert body["allowed"] == []
    assert body["reason"].startswith("preflight_blocked:")
    codes = {b["code"] for b in body["blocked"]}
    assert preflight.CODE_EA_NEVER_SEEN in codes or preflight.CODE_EA_OFFLINE in codes

    async with db.pool().connection() as conn:
        rows = await fetchall(
            conn,
            "SELECT payload, decision FROM order_events WHERE to_status = 'CYCLE_SKIPPED'",
        )
    assert len(rows) == 1
    payload = rows[0]["payload"]
    decision = rows[0]["decision"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(decision, str):
        decision = json.loads(decision)
    assert payload["cycle_id"] == "cycle-test-0001"
    assert decision["kind"] == "cycle_skipped"
    # Bentuk decision wajib memenuhi CHECK order_events_decision_shape_check.
    for key in ("kind", "reasoning", "confidence", "model", "prompt_version"):
        assert key in decision


# ── B. fail_reason wajib + terstruktur ──────────────────────────────────────
def test_fail_reason_render_dan_from_reasons():
    d = fail_reason.from_reasons(
        ["spread_too_wide: spread 0.61 > 0.50", "volume too large"],
        stage=fail_reason.STAGE_RISK_GATE)
    assert d["code"] == "spread_too_wide"
    assert d["stage"] == "risk_gate"
    assert "volume too large" in d["message"]
    text = fail_reason.render(d)
    assert text.startswith("spread_too_wide: ")
    assert text.endswith("(stage=risk_gate)")


def test_fail_reason_dari_pesan_ea_memakai_retcode():
    d = fail_reason.from_text("OrderSend failed retcode=10018 (market closed)",
                              stage=fail_reason.STAGE_BRIDGE_RESULT)
    assert d["code"] == "retcode_10018"
    assert d["stage"] == "bridge_result"


def test_fail_reason_pesan_kosong_tetap_terisi():
    d = fail_reason.from_text(None, stage=fail_reason.STAGE_RECONCILER)
    assert d["code"] == "failed"
    assert d["message"]


@pytest.mark.asyncio
async def test_order_ditolak_gate_punya_fail_reason_dan_detail(client, _clean_db):
    """Order yang ditolak gate: fail_reason TEXT + fail_detail JSONB terisi."""
    from app.state_machine import fetchone

    await db.set_setting("max_volume", 0.01)
    r = await client.post("/orders", json={
        "symbol": "XAUUSD", "side": "BUY", "volume": 0.5,
        "sl": 1990.0, "tp": 2010.0,
    })
    assert r.status_code == 422, r.text
    order_id = r.json()["id"]
    async with db.pool().connection() as conn:
        row = await fetchone(
            conn,
            "SELECT status, fail_reason, fail_detail FROM orders WHERE id = %s",
            (order_id,),
        )
    assert row["status"] == "FAILED"
    assert row["fail_reason"], "FAILED wajib punya fail_reason"
    detail = row["fail_detail"]
    if isinstance(detail, str):
        detail = json.loads(detail)
    assert detail["stage"] == fail_reason.STAGE_RISK_GATE
    assert detail["code"]
    assert detail["message"]


@pytest.mark.asyncio
async def test_constraint_db_menolak_failed_tanpa_fail_reason(client, _clean_db):
    """Constraint `orders_failed_requires_reason` = jaring pengaman terakhir.

    Jalur kode baru yang lupa mengisi alasan harus gagal keras di DB, bukan
    diam-diam membuat baris FAILED tanpa penyebab (kelas bug 192 NULL).
    """
    from psycopg import errors

    from app.state_machine import fetchone

    async with db.pool().connection() as conn:
        with pytest.raises(errors.CheckViolation):
            await conn.execute(
                """
                INSERT INTO orders (symbol, side, volume, sl, tp, status)
                VALUES ('XAUUSD', 'BUY', 0.01, 1990, 2010, 'FAILED')
                """
            )
        await conn.rollback()
    # Insert yang sama DENGAN alasan harus lolos (constraint tidak terlalu ketat).
    async with db.pool().connection() as conn:
        await conn.execute(
            """
            INSERT INTO orders (symbol, side, volume, sl, tp, status, fail_reason)
            VALUES ('XAUUSD', 'BUY', 0.01, 1990, 2010, 'FAILED', 'probe: ok (stage=unknown)')
            """
        )


# ── C. Anggaran latensi + prompt cache ─────────────────────────────────────
def test_budget_default_membatasi_output_per_tahap():
    budget = llm_budget.resolve({})
    assert budget["target_p95_s"] == 35.0
    assert budget["max_tokens_specialist"] <= 600
    assert budget["max_tokens_synth"] <= 900
    assert budget["max_tokens_single"] <= 1500
    assert budget["reasoning_max_tokens"] <= 400


def test_budget_settings_owner_menimpa_dengan_batas_aman():
    budget = llm_budget.resolve({"llm_latency_budget": {
        "max_tokens_synch": 1, "max_tokens_synth": 99999, "target_p95_s": 20}})
    assert budget["max_tokens_synth"] == 2000      # dipotong ke batas keras
    assert budget["target_p95_s"] == 20.0
    assert budget["max_tokens_specialist"] == llm_budget.DEFAULT_BUDGET[
        "max_tokens_specialist"]                      # key asing diabaikan


def test_budget_urutan_konteks_statis_dulu():
    """`now_utc` + data volatil di belakang: prefix cache bisa hit."""
    ctx = {
        "now_utc": "2026-11-26T07:30:00Z",
        "symbols": {"XAUUSD": {"price": 2000.0, "candles": {
            "M5": [1], "H4": [2], "M15": [3], "H1": [4]}}},
        "session": {"weekend": False},
    }
    ordered = llm_budget.stable_context(ctx)
    keys = list(ordered)
    assert keys[0] == "symbols"
    assert list(ordered["symbols"]["XAUUSD"]["candles"]) == ["H4", "H1", "M15", "M5"]
    assert keys.index("now_utc") > keys.index("symbols")


def test_budget_cache_stats_berbagai_bentuk_usage():
    vllm = llm_budget.cache_stats(
        {"prompt_tokens": 1000, "prompt_cache_hit_tokens": 900,
         "prompt_cache_miss_tokens": 100})
    assert vllm == {"hit": 900, "miss": 100, "rate": 0.9}
    openai = llm_budget.cache_stats(
        {"prompt_tokens": 1000, "prompt_tokens_details": {"cached_tokens": 250}})
    assert openai["hit"] == 250 and openai["miss"] == 750
    assert llm_budget.cache_stats(None) == {"hit": None, "miss": None, "rate": None}


def test_budget_summarise_latency_p95():
    samples = [10.0, 12.0, 20.0, 30.0, 34.0, 40.0, 120.0]
    stats = llm_budget.summarise_latency(samples, 35.0)
    assert stats["n"] == 7
    assert stats["max_s"] == 120.0
    assert stats["p50_s"] == 30.0
    assert stats["within_budget"] is False   # p95 di atas target
    assert llm_budget.summarise_latency([5.0, 10.0], 35.0)["within_budget"] is True


def test_prompt_loop_memakai_aturan_reasoning_ringkas():
    from app import llm_agent_loop

    prompt = llm_agent_loop._build_user_prompt(
        {"now_utc": "2026-11-26T07:30:00Z", "symbols": {}}, llm_budget.resolve({}))
    assert "reasoning maksimal 400 token" in prompt
    assert prompt.index("<market_data>") == 0


# ── C2. Plafon thinking provider + deadline tahap + cache ordering ─────────
def test_budget_plafon_thinking_dikirim_per_tahap():
    """`max_tokens` tidak membatasi token reasoning: plafon harus eksplisit.

    Bukti produksi 26 Nov 2026: technical dengan max_tokens=450 tetap
    menghasilkan 1.496-2.351 token (reasoning ikut dihitung) = 26-32 s.
    """
    budget = llm_budget.resolve({})
    assert budget["specialist_reasoning"] == "off"
    assert llm_budget.thinking_param(budget, "specialist") == {
        "thinking": {"type": "disabled"}}
    assert llm_budget.thinking_param(budget, "synth") == {
        "thinking": {"type": "enabled", "budget_tokens": 400}}

    on = llm_budget.resolve({"llm_latency_budget": {
        "specialist_reasoning": "budget", "reasoning_max_tokens": 250}})
    assert llm_budget.thinking_param(on, "specialist") == {
        "thinking": {"type": "enabled", "budget_tokens": 250}}

    zero = llm_budget.resolve({"llm_latency_budget": {"synth_reasoning_tokens": 0}})
    assert llm_budget.thinking_param(zero, "synth") == {
        "thinking": {"type": "disabled"}}
    # Nilai asing untuk mode reasoning diabaikan, bukan mematikan siklus.
    weird = llm_budget.resolve({"llm_latency_budget": {"specialist_reasoning": "turbo"}})
    assert weird["specialist_reasoning"] == "off"


def test_budget_reorder_for_cache_volatil_di_belakang():
    payload = {
        "symbol": "XAUUSD",
        "now_utc": "2026-11-26T07:30:00Z",
        "symbols": {"XAUUSD": {
            "status": "ok", "price": 2000.0, "candle_age_min": 3,
            "timeframes": {"M5": {"close": 2000}},
            "structure": {"trend": "up"},
        }},
    }
    ordered = llm_budget.reorder_for_cache(payload)
    keys = list(ordered["symbols"]["XAUUSD"])
    assert keys[0] == "timeframes"           # blok besar stabil jadi prefix
    assert keys.index("structure") < keys.index("price")
    assert keys[-1] == "candle_age_min"      # paling volatil di belakang
    # Isi tidak boleh berubah, hanya urutan.
    assert ordered["symbols"]["XAUUSD"]["price"] == 2000.0
    assert llm_budget.reorder_for_cache("bukan dict") == "bukan dict"


async def test_specialist_deadline_membatalkan_dan_menandai_timeout():
    """Satu panggilan provider ekor tidak boleh meledakkan anggaran siklus."""
    import asyncio
    import time as _time

    from app import llm_specialists

    class SlowHttp:
        async def post(self, *args, **kwargs):
            await asyncio.sleep(30)

    started = _time.monotonic()
    result = await llm_specialists.run_specialists(
        SlowHttp(), {"symbols": {"XAUUSD": {}}}, symbol="XAUUSD",
        base="http://127.0.0.1:1", key="k", model="m",
        budget=llm_budget.resolve({}), deadline=_time.monotonic() + 0.3)
    elapsed = _time.monotonic() - started
    assert elapsed < 3.0, f"deadline tidak dipatuhi: {elapsed:.1f}s"
    assert set(result) == set(llm_specialists.ROLES)
    assert all(res["state"] == "timeout" for res in result.values())


async def test_chat_mengulang_tanpa_parameter_thinking_saat_ditolak():
    """Provider yang tidak mengenal `thinking` tidak boleh mematikan siklus."""
    from app import llm_specialists

    calls: list[dict] = []

    class _Resp:
        def __init__(self, code: int, body: dict):
            self.status_code = code
            self._body = body
            self.text = "err"

        def json(self):
            return self._body

    class Http:
        async def post(self, url, headers=None, json=None):
            calls.append(dict(json or {}))
            if "thinking" in (json or {}):
                return _Resp(400, {})
            return _Resp(200, {
                "choices": [{"message": {"content": '{"ok":1}'},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
                "model": "m"})

    res = await llm_specialists._chat(
        Http(), base="http://127.0.0.1:1", key="k", model="m",
        system="s", user="u", max_tokens=10, timeout_s=5,
        extra={"thinking": {"type": "disabled"}})
    assert res["data"] == {"ok": 1}
    assert len(calls) == 2
    assert "thinking" in calls[0] and "thinking" not in calls[1]
