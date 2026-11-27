"""Fault injection + isolation tests: strategy supervisor (PRD v2.2 §5).

DoD kartu t_f2v22a1, tiap butir dibuktikan test:
- crash satu strategi tidak menghentikan runner/API/strategi lain
  (test_runner_crash_isolation, Sandbox* tests)
- strategi tidak bisa akses jaringan/secret
  (test_sandbox_network_blocked, test_sandbox_secret_read_blocked,
  test_sandbox_env_has_no_secrets, test_sandbox_subprocess_escape_blocked)
- timeout/exception/malformed/NaN/Inf -> reject
  (test_sandbox_timeout_*, test_sandbox_crash_*, Schema tests)
- circuit breaker + recovery fault injection
  (test_circuit_breaker_*, test_degraded_failure_disables)
- lifecycle PRD 5.3 + owner gating (test_lifecycle_*)

Fixture strategi: tests/sbx_strategies/probe.py (perilaku via context).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import db, supervisor
from app.supervisor import (
    LifecycleError,
    SandboxCrash,
    SandboxTimeout,
    SchemaInvalid,
    StrategyFault,
    validate_order_intent,
    validate_raw_output,
)

TESTS_DIR = Path(__file__).resolve().parent
MODULE = "sbx_strategies.probe"
MODULE_DIR = str(TESTS_DIR)
SECRET_PATH = str(TESTS_DIR.parent / ".env")  # file secret nyata (api/.env)

NOW = datetime(2026, 11, 23, 9, 30, 30, tzinfo=timezone.utc)
BASE_CONTEXT: dict = {
    "symbol": "XAUUSD",
    "now": NOW.isoformat(),
    "candles": [{"ts": "2026-11-23T09:25:00+00:00", "open": 2000, "high": 2001,
                 "low": 1999, "close": 2000.5, "volume": 0}],
    "liquidity": {"ts": NOW.isoformat(), "bid": 1999.9, "ask": 2000.1,
                  "spread": 0.2, "spread_median_15m": 0.2, "fresh": True},
    "positions": [],
    "trades_today": 0,
    "risk": {"equity": 10000.0, "risk_per_trade": 0.005, "max_volume": 0.1,
             "max_spread": 0.5},
}


def ctx(behavior: str, **kw) -> dict:
    context = dict(BASE_CONTEXT)
    context["behavior"] = behavior
    context.update(kw)
    return context


async def _sandbox(behavior: str, *, wall: float = 10, cpu: int = 5,
                   params: dict | None = None, **kw) -> dict:
    return await supervisor.run_sandbox(
        module=MODULE, context=ctx(behavior, **kw), params=params or {},
        wall_timeout_s=wall, cpu_limit_s=cpu, module_dir=MODULE_DIR)


def _raw(**kw) -> dict:
    base = dict(symbol="XAUUSD", side="BUY", volume=0.01, sl=1.0, tp=2.0,
                strategy="sbx_probe")
    base.update(kw)
    return base


# ── Sandbox: kontrak normal ────────────────────────────────────────────────
async def test_sandbox_valid_intent_and_params_roundtrip():
    resp = await _sandbox("ok", params={"tf_seconds": 123, "unknown_key": 1})
    assert resp["ok"] is True
    intent = resp["intent"]
    assert intent["symbol"] == "XAUUSD"
    assert intent["side"] == "BUY"
    assert intent["volume"] == 0.01
    assert intent["sl"] == 1.0 and intent["tp"] == 2.0
    assert intent["strategy"] == "sbx_probe"
    assert intent["reason"] == "tf=123"  # params dataclass direkonstruksi


async def test_sandbox_none_is_valid_output():
    assert await _sandbox("none") == {"ok": True, "intent": None}


# ── Sandbox: timeout / crash / resource (PRD 5.2, 5.4) ─────────────────────
async def test_sandbox_timeout_killed_within_wall_clock():
    t0 = time.monotonic()
    with pytest.raises(SandboxTimeout):
        await _sandbox("sleep", wall=2)
    assert time.monotonic() - t0 < 8, "timeout tidak boleh menahan order path"


async def test_sandbox_sigkill_crash_reported():
    with pytest.raises(SandboxCrash) as exc_info:
        await _sandbox("crash")
    assert "code=-9" in str(exc_info.value)  # SIGKILL


async def test_sandbox_exit_crash_reported():
    with pytest.raises(SandboxCrash):
        await _sandbox("exit")


async def test_sandbox_cpu_limit_kills_busy_loop():
    t0 = time.monotonic()
    with pytest.raises(SandboxCrash):
        await _sandbox("spin_cpu", wall=15, cpu=1)
    assert time.monotonic() - t0 < 12


async def test_sandbox_memory_limit():
    resp = await _sandbox("huge_memory", wall=15)
    assert resp["ok"] is False
    assert "MemoryError" in resp["error"]


# ── Sandbox: output malformed / NaN / Inf (PRD 5.2) ────────────────────────
async def test_sandbox_malformed_outputs_rejected():
    for behavior in ("malformed_str", "malformed_list"):
        resp = await _sandbox(behavior)
        assert resp["ok"] is False, behavior
        assert "malformed" in resp["error"], behavior


async def test_sandbox_nan_inf_rejected_at_serialization():
    for behavior in ("nan_volume", "inf_sl"):
        resp = await _sandbox(behavior)
        assert resp["ok"] is False, behavior
        assert "non-finite" in resp["error"], behavior


# ── Sandbox: network & secret isolation (PRD 5.4) ──────────────────────────
async def test_sandbox_network_blocked():
    for behavior in ("net", "raw_socket"):
        resp = await _sandbox(behavior, wall=15)
        assert resp["ok"] is False, behavior
        assert "sandbox" in resp["error"] or "Permission" in resp["error"], behavior


async def test_sandbox_secret_read_blocked():
    resp = await _sandbox("secret", secret_path=SECRET_PATH)
    assert resp["ok"] is False
    assert "Permission denied" in resp["error"], resp["error"]


async def test_sandbox_etc_passwd_read_blocked():
    resp = await _sandbox("secret", secret_path="/etc/passwd")
    assert resp["ok"] is False
    assert "Permission denied" in resp["error"], resp["error"]


async def test_sandbox_env_has_no_secrets():
    """Child env kosong: tidak ada db/broker/telegram credential di sandbox."""
    resp = await _sandbox("env")
    assert resp["ok"] is True, resp
    assert resp["intent"]["reason"] == "env clean"


async def test_sandbox_subprocess_escape_blocked():
    """Landlock deny-all FS: exec binary / import modul baru setelah lockdown gagal."""
    resp = await _sandbox("subprocess_escape", wall=15)
    assert resp["ok"] is False


# ── Schema validation unit (PRD 4.1 / 5.2) ─────────────────────────────────
@pytest.mark.parametrize("field,value", [
    ("volume", float("nan")),
    ("volume", float("inf")),
    ("volume", 0),
    ("volume", -0.01),
    ("sl", float("nan")),
    ("sl", float("inf")),
    ("sl", 0),
    ("sl", None),
    ("tp", 0),
    ("tp", float("nan")),
])
def test_schema_rejects_bad_numbers(field, value):
    with pytest.raises(SchemaInvalid):
        validate_raw_output(_raw(**{field: value}), strategy_id="sbx_probe",
                            symbol="XAUUSD")


def test_schema_rejects_identity_mismatch():
    with pytest.raises(SchemaInvalid):
        validate_raw_output(_raw(strategy="other_strategy"),
                            strategy_id="sbx_probe", symbol="XAUUSD")
    with pytest.raises(SchemaInvalid):
        validate_raw_output(_raw(symbol="BTCUSD"),
                            strategy_id="sbx_probe", symbol="XAUUSD")


def test_schema_rejects_unknown_field_and_non_dict():
    with pytest.raises(SchemaInvalid):
        validate_raw_output(_raw(junk=1), strategy_id="sbx_probe", symbol="XAUUSD")
    with pytest.raises(SchemaInvalid):
        validate_raw_output([1, 2], strategy_id="sbx_probe", symbol="XAUUSD")
    with pytest.raises(SchemaInvalid):
        validate_raw_output("x", strategy_id="sbx_probe", symbol="XAUUSD")


def test_schema_rejects_bad_side():
    with pytest.raises(SchemaInvalid):
        validate_raw_output(_raw(side="buy"), strategy_id="sbx_probe",
                            symbol="XAUUSD")


def test_finalize_intent_full_prd_contract():
    ctx_hash = supervisor.context_hash(BASE_CONTEXT)
    intent = supervisor.finalize_intent(
        _raw(), strategy_id="sbx_probe", strategy_version="1.2.3",
        ctx_hash=ctx_hash, now=NOW, ttl_s=60)
    validate_order_intent(intent)  # tidak raise
    assert intent["strategy_id"] == "sbx_probe"
    assert intent["strategy_version"] == "1.2.3"
    assert intent["order_type"] == "MARKET"
    assert intent["stop_loss"] == 1.0 and intent["take_profit"] == 2.0
    assert intent["expires_at"] > intent["created_at"]
    # client_order_id idempotent per context (PRD 3.3 langkah 7)
    again = supervisor.finalize_intent(
        _raw(), strategy_id="sbx_probe", strategy_version="1.2.3",
        ctx_hash=ctx_hash, now=NOW, ttl_s=60)
    assert again["client_order_id"] == intent["client_order_id"]
    other = supervisor.finalize_intent(
        _raw(), strategy_id="sbx_probe", strategy_version="1.2.3",
        ctx_hash="different", now=NOW, ttl_s=60)
    assert other["client_order_id"] != intent["client_order_id"]


def test_validate_order_intent_rejects_missing_expiry_and_bad_ttl():
    intent = supervisor.finalize_intent(
        _raw(), strategy_id="sbx_probe", strategy_version="1.2.3",
        ctx_hash="h", now=NOW, ttl_s=60)
    broken = dict(intent, expires_at=None)
    with pytest.raises(SchemaInvalid):
        validate_order_intent(broken)
    expired = supervisor.finalize_intent(
        _raw(), strategy_id="sbx_probe", strategy_version="1.2.3",
        ctx_hash="h", now=NOW, ttl_s=-60)
    with pytest.raises(SchemaInvalid):
        validate_order_intent(expired)


# ── decide(): validasi + pencatatan (DB test) ───────────────────────────────
def _cfg(**overrides) -> dict:
    return {"strategy_supervisor": overrides}


async def _decide(conn, behavior: str, *, strategy_id: str = "sbx_probe",
                  settings: dict | None = None, seed: str = "PAPER", **kw):
    return await supervisor.decide(
        conn, strategy_id=strategy_id, strategy_version="0.0.1",
        module=MODULE, context=ctx(behavior, **kw), params={},
        symbol="XAUUSD", timeframe="M5", source="PAPER", settings=settings,
        seed_status=seed, module_dir=MODULE_DIR)


async def _signals(conn, strategy_id="sbx_probe") -> list[dict]:
    rows = await conn.execute(
        "SELECT * FROM signals WHERE strategy_id = %s ORDER BY id", (strategy_id,))
    return [dict(r) for r in await rows.fetchall()]


async def _events(conn, strategy_id="sbx_probe") -> list[dict]:
    rows = await conn.execute(
        "SELECT * FROM system_events WHERE source='supervisor' AND actor = %s "
        "ORDER BY id", (strategy_id,))
    return [dict(r) for r in await rows.fetchall()]


async def test_decide_valid_intent_enriched_prd4_1(_clean_db):
    async with db.pool().connection() as conn:
        decision = await _decide(conn, "ok")
        signals = await _signals(conn)
    assert not decision.rejected
    intent = decision.intent
    for key in ("strategy_id", "strategy_version", "signal_id",
                "client_order_id", "symbol", "side", "order_type", "volume",
                "stop_loss", "created_at", "expires_at", "reason_code",
                "context_hash"):
        assert intent.get(key) is not None, f"PRD 4.1: {key} wajib"
    assert intent["order_type"] == "MARKET"
    assert intent["side"] == "BUY"
    # signal EMITTED tercatat (PRD 5.2/9.2)
    assert len(signals) == 1 and signals[0]["status"] == "EMITTED"
    assert signals[0]["side"] == "BUY"
    assert decision.breaker["state"] == "CLOSED"


async def test_decide_none_writes_no_signal(_clean_db):
    async with db.pool().connection() as conn:
        decision = await _decide(conn, "none")
        signals = await _signals(conn)
    assert not decision.rejected and decision.intent is None
    # "no entry" bukan sinyal: tabel signals tidak ter-spam iterasi kosong
    assert signals == []


async def test_decide_malformed_rejected_and_recorded(_clean_db):
    async with db.pool().connection() as conn:
        decision = await _decide(conn, "malformed_str")
        signals = await _signals(conn)
        events = await _events(conn)
    assert decision.rejected
    assert decision.reason_code == "MALFORMED"
    assert signals[-1]["status"] == "REJECTED"
    assert signals[-1]["reject_reason"] == "MALFORMED"
    assert any(e["event_type"] == "STRATEGY_FAULT" for e in events)


async def test_decide_nan_inf_rejected(_clean_db):
    for behavior in ("nan_volume", "inf_sl"):
        async with db.pool().connection() as conn:
            decision = await _decide(conn, behavior)
        assert decision.rejected, behavior
        assert "non-finite" in decision.reason, behavior


async def test_decide_contract_violations_rejected(_clean_db):
    # PRD 4.1: order tanpa SL / volume tidak valid / identitas salah -> reject
    for behavior, code in (("no_sl", "SCHEMA_INVALID"),
                           ("zero_volume", "SCHEMA_INVALID"),
                           ("negative_volume", "SCHEMA_INVALID"),
                           ("wrong_strategy", "SCHEMA_INVALID"),
                           ("extra_field", "SCHEMA_INVALID")):
        async with db.pool().connection() as conn:
            decision = await _decide(conn, behavior)
        assert decision.rejected, behavior
        assert decision.reason_code == code, behavior


async def test_decide_network_blocked(_clean_db):
    for behavior in ("net", "raw_socket"):
        async with db.pool().connection() as conn:
            decision = await _decide(conn, behavior)
        assert decision.rejected, behavior
        assert ("sandbox" in decision.reason
                or "Permission" in decision.reason), decision.reason


async def test_decide_secret_read_blocked(_clean_db):
    async with db.pool().connection() as conn:
        decision = await _decide(conn, "secret", secret_path=SECRET_PATH)
    assert decision.rejected
    assert "Permission denied" in decision.reason


async def test_decide_env_has_no_secrets(_clean_db):
    async with db.pool().connection() as conn:
        decision = await _decide(conn, "env")
    assert not decision.rejected, decision.reason
    assert decision.intent["reason"] == "env clean"


async def test_decide_status_gate_blocks_inactive(_clean_db):
    async with db.pool().connection() as conn:
        decision = await _decide(conn, "ok", seed="DRAFT")  # DRAFT tidak aktif
        signals = await _signals(conn)
    assert decision.rejected
    assert decision.reason_code == "STATUS_INACTIVE"
    assert "DRAFT" in decision.reason
    # steady-state gate: tanpa spam signal
    assert signals == []


# ── Circuit breaker fault injection (PRD 5.2) ───────────────────────────────
async def test_circuit_breaker_opens_after_threshold_and_throttles(_clean_db):
    settings = _cfg(breaker_threshold=3)
    async with db.pool().connection() as conn:
        for _ in range(3):
            decision = await _decide(conn, "malformed_str", settings=settings)
            assert decision.rejected
        state = await supervisor.get_strategy_state(conn, "sbx_probe")
        # eskalasi otomatis: PAPER -> DEGRADED saat ambang terlampaui
        assert state["status"] == "DEGRADED"
        assert state["circuit_breaker"]["state"] == "OPEN"
        # panggilan berikut: throttle cepat TANPA spawn subprocess dan TANPA
        # baris signal baru (steady-state, anti-spam)
        signals_before = len(await _signals(conn))
        t0 = time.monotonic()
        decision = await _decide(conn, "ok", settings=settings)
        elapsed = time.monotonic() - t0
        signals_after = await _signals(conn)
    assert decision.reason_code == "BREAKER_OPEN"
    assert decision.rejected
    assert elapsed < 1.0, "breaker OPEN harus tolak cepat tanpa subprocess"
    assert len(signals_after) == signals_before == 3  # hanya 3 fault terekam


async def test_circuit_breaker_recovery_half_open_probe(_clean_db):
    settings = _cfg(breaker_threshold=2, breaker_cooldown_s=0)
    async with db.pool().connection() as conn:
        for _ in range(2):
            await _decide(conn, "malformed_str", settings=settings)
        state = await supervisor.get_strategy_state(conn, "sbx_probe")
        assert state["circuit_breaker"]["state"] == "OPEN"
        # cooldown lewat -> probe HALF_OPEN; probe sukses -> breaker CLOSED
        decision = await _decide(conn, "ok", settings=settings)
        state = await supervisor.get_strategy_state(conn, "sbx_probe")
    assert not decision.rejected
    assert decision.breaker["state"] == "CLOSED"
    assert state["circuit_breaker"]["consecutive_errors"] == 0
    # status tetap DEGRADED: pemulihan privilege hanya owner (PRD 5.3)
    assert state["status"] == "DEGRADED"


async def test_circuit_breaker_half_open_probe_failure_reopens(_clean_db):
    settings = _cfg(breaker_threshold=1, breaker_cooldown_s=0)
    async with db.pool().connection() as conn:
        await _decide(conn, "malformed_str", settings=settings)  # -> DEGRADED, OPEN
        # probe gagal -> breaker OPEN lagi
        decision = await _decide(conn, "malformed_str", settings=settings)
        state = await supervisor.get_strategy_state(conn, "sbx_probe")
    assert decision.rejected
    assert state["circuit_breaker"]["state"] == "OPEN"


async def test_degraded_failure_disables_strategy(_clean_db):
    """Eskalasi dua tingkat: aktif -> DEGRADED -> DISABLED (auto, PRD 5.2)."""
    settings = _cfg(breaker_threshold=1, breaker_cooldown_s=0)
    async with db.pool().connection() as conn:
        await _decide(conn, "malformed_str", settings=settings)  # PAPER -> DEGRADED
        state = await supervisor.get_strategy_state(conn, "sbx_probe")
        assert state["status"] == "DEGRADED"
        await _decide(conn, "malformed_str", settings=settings)  # probe gagal
        state = await supervisor.get_strategy_state(conn, "sbx_probe")
        assert state["status"] == "DISABLED"
        assert state["enabled"] is False
        # DISABLED: decide ditolak status gate, tidak spawn
        decision = await _decide(conn, "ok", settings=settings)
    assert decision.reason_code == "STATUS_INACTIVE"


async def test_events_record_crash_and_breaker(_clean_db):
    settings = _cfg(breaker_threshold=2)
    async with db.pool().connection() as conn:
        await _decide(conn, "crash")
        await _decide(conn, "malformed_str", settings=settings)
        events = await _events(conn)
    kinds = [e["event_type"] for e in events]
    assert "STRATEGY_FAULT" in kinds  # crash tercatat (PRD 5.2)
    assert any("CRITICAL" == e["severity"] or "WARN" == e["severity"]
               for e in events if e["event_type"] == "STRATEGY_FAULT")


# ── Lifecycle transitions + owner gating (PRD 5.3) ──────────────────────────
async def test_lifecycle_chain_and_owner_gating(_clean_db):
    async with db.pool().connection() as conn:
        await _decide(conn, "none")  # seed sbx_probe PAPER
        # owner-only transition ditolak untuk role system
        with pytest.raises(LifecycleError):
            await supervisor.transition_strategy(
                conn, "sbx_probe", "LIVE_APPROVED", actor="supervisor",
                actor_role="system")
        # chain valid lewat owner/workflow
        path = ["LIVE_APPROVED", "LIVE"]
        for target in path:
            res = await supervisor.transition_strategy(
                conn, "sbx_probe", target, actor="owner",
                actor_role="owner")
            assert res["to"] == target
        # transisi ilegal: lompatan status
        with pytest.raises(LifecycleError):
            await supervisor.transition_strategy(
                conn, "sbx_probe", "PAPER", actor="owner", actor_role="owner")
        # auto transitions supervisor (jalur fault)
        await supervisor.transition_strategy(
            conn, "sbx_probe", "DEGRADED", actor="supervisor",
            actor_role="system")
        await supervisor.transition_strategy(
            conn, "sbx_probe", "DISABLED", actor="supervisor",
            actor_role="system")
        state = await supervisor.get_strategy_state(conn, "sbx_probe")
        assert state["enabled"] is False


async def test_lifecycle_full_prd_path(_clean_db):
    """DRAFT -> ... -> LIVE penuh via owner; DRAFT -> ARCHIVED via workflow."""
    async with db.pool().connection() as conn:
        await supervisor._ensure_strategy_row(
            conn, strategy_id="new_strategy", strategy_version="1.0.0",
            seed_status="DRAFT")
        for target in ("VALIDATING", "BACKTEST_APPROVED", "SHADOW", "PAPER",
                       "LIVE_APPROVED", "LIVE"):
            await supervisor.transition_strategy(
                conn, "new_strategy", target, actor="release-workflow",
                actor_role="workflow")
        state = await supervisor.get_strategy_state(conn, "new_strategy")
        assert state["status"] == "LIVE"


async def test_unknown_strategy_rejected(_clean_db):
    async with db.pool().connection() as conn:
        with pytest.raises(LifecycleError):
            await supervisor.transition_strategy(
                conn, "not_registered", "LIVE", actor="owner",
                actor_role="owner")


# ── API endpoints (monitoring + transisi owner-gated) ──────────────────────
async def test_api_supervisor_status_and_events(client, _clean_db):
    assert (await client.get("/strategies/supervisor")).json() == {"strategies": []}
    async with db.pool().connection() as conn:
        await _decide(conn, "none")  # seed sbx_probe PAPER
    resp = await client.get("/strategies/supervisor")
    assert resp.status_code == 200
    data = resp.json()["strategies"]
    assert len(data) == 1
    assert data[0]["strategy_id"] == "sbx_probe"
    assert data[0]["status"] == "PAPER"
    assert data[0]["circuit_breaker"]["state"] == "CLOSED"
    resp = await client.get("/strategies/sbx_probe/supervisor/events")
    assert resp.status_code == 200
    assert isinstance(resp.json()["events"], list)


async def test_api_lifecycle_transition_guards(client, _clean_db):
    async with db.pool().connection() as conn:
        await _decide(conn, "none")  # seed PAPER
    # owner-only transition tanpa step-up 2FA -> 403
    resp = await client.post("/strategies/sbx_probe/lifecycle",
                             json={"to_status": "LIVE_APPROVED", "reason": "t"})
    assert resp.status_code == 403, resp.text
    # target tak dikenal -> 422
    resp = await client.post("/strategies/sbx_probe/lifecycle",
                             json={"to_status": "JUNK"})
    assert resp.status_code == 422
    # transisi non-owner-only (PAPER -> ARCHIVED) boleh tanpa 2FA
    resp = await client.post("/strategies/sbx_probe/lifecycle",
                             json={"to_status": "ARCHIVED", "reason": "retire"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["to"] == "ARCHIVED"
    # transisi ilegal dari ARCHIVED -> 409
    resp = await client.post("/strategies/sbx_probe/lifecycle",
                             json={"to_status": "LIVE"})
    assert resp.status_code == 409
    # strategi tidak terdaftar -> 404
    resp = await client.post("/strategies/ghost/lifecycle",
                             json={"to_status": "ARCHIVED"})
    assert resp.status_code == 404


async def test_api_lifecycle_owner_gated_with_2fa(client_2fa, _clean_db):
    async with db.pool().connection() as conn:
        await _decide(conn, "none")  # seed PAPER
    resp = await client_2fa.post("/strategies/sbx_probe/lifecycle",
                                 json={"to_status": "LIVE_APPROVED",
                                       "reason": "owner approval (PRD 5.3)"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["to"] == "LIVE_APPROVED"


# ── Isolasi runner: crash satu strategi, lain tetap jalan (PRD 5.4) ─────────
async def test_runner_crash_isolation(_clean_db):
    from paper import runner as paper_runner
    from paper.store import DEFAULT_STATE
    from strategies.mean_reversion import (
        STRATEGY_ID as MR_ID,
        OrderIntent as MRIntent,
        StrategyParams as MRParams,
    )

    tick = {"bid": 1999.85, "ask": 2000.15, "spread": 0.30, "ts_utc": NOW}
    good_intent = MRIntent(symbol="XAUUSD", side="BUY", volume=0.04,
                           sl=1990.0, tp=2015.0, strategy=MR_ID, reason="iso")
    spec_crash = paper_runner.StrategySpec(
        id="sbx_probe", state_key="runner_iso_crash", params_cls=None,
        decide=None, module=MODULE, version="0.0.1")
    spec_good = paper_runner.StrategySpec(
        id=MR_ID, state_key="runner_iso_good", params_cls=MRParams,
        decide=lambda context, params: good_intent)  # legacy in-process

    async with db.pool().connection() as conn:
        settings = await db.get_settings()
        state_a = dict(DEFAULT_STATE)
        state_b = dict(DEFAULT_STATE)
        # Strategi A crash di subprocess -> ditampung jadi reject, no raise
        logs_a = await paper_runner.run_iteration(
            conn, state_a, spec=spec_crash, mode="PAPER", settings=settings,
            params=MRParams(), tick=tick, candles=[], spread_median=0.25,
            now=NOW, allow_entry=True)
        # Strategi B tetap berjalan normal (DoD PRD 5.4)
        logs_b = await paper_runner.run_iteration(
            conn, state_b, spec=spec_good, mode="PAPER", settings=settings,
            params=MRParams(), tick=tick, candles=[], spread_median=0.25,
            now=NOW, allow_entry=True)

    assert any("REJECTED by supervisor" in line for line in logs_a), logs_a
    assert "position" not in state_a or not state_a.get("position")
    assert any(line.startswith("ENTRY BUY") for line in logs_b), logs_b
    assert state_b["position"] is not None



