"""Versioning, approval & rollback (PRD v2.2 §11, t_f2v22a6).

Cover acceptance criteria §11.4:
- artifact versi disetujui tidak bisa diubah (API 409 + trigger DB);
- setiap strategi punya versi jelas (current_version + stamp sinyal);
- rollback diuji di staging: sinyal versi bermasalah berhenti, posisi
  terbuka TIDAK ditutup, rollback tercatat sebagai event + rekonsiliasi
  POST_ROLLBACK;
- tidak ada auto-promotion (status hanya berubah lewat keputusan eksplisit;
  AUTO_TRANSITIONS supervisor hanya jalur fault).
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import time

import pytest
from httpx import ASGITransport, AsyncClient

from app import db, supervisor, totp, versioning
from app.auth import hash_password
from app.main import app

MODULE = "sbx_strategies.probe"
MODULE_DIR = str(pathlib.Path(__file__).resolve().parent)

REPORT = {"sharpe": 1.8, "max_dd": 0.12, "trades": 120, "source": "backtest"}
WF_REPORT = {"wf_sharpe": 1.4, "folds": 6, "source": "walkforward"}
RISK = {"max_risk_per_trade": 0.005, "max_daily_drawdown": 100.0}


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _exec(query, params=()):
    async with db.pool().connection() as conn:
        await conn.execute(query, params)


async def _one(query, params=()):
    async with db.pool().connection() as conn:
        cur = await conn.execute(query, params)
        row = await cur.fetchone()
    return dict(row) if row else None


async def _register(client, sid="mean_reversion", version="1.0.0",
                    params=None, **kw):
    body = {"version": version, "params": params or {"num_std": 2.0},
            "backtest_report": REPORT, "walkforward_report": WF_REPORT,
            "risk_profile": RISK, "change_reason": "rilis uji versioning",
            "data_version": "candles-2026-11", **kw}
    return await client.post(f"/strategies/{sid}/versions", json=body)


async def _submit(client, sid="mean_reversion", version="1.0.0"):
    return await client.post(f"/strategies/{sid}/versions/{version}/submit",
                             json={"evidence": {"note": "uji"}})


async def _review(client, sid, version, stage, decision="APPROVED",
                  rationale="setuju"):
    return await client.post(f"/strategies/{sid}/versions/{version}/review",
                             json={"stage": stage, "decision": decision,
                                   "rationale": rationale})


async def _promote_to_owner(client, sid="mean_reversion", version="1.0.0"):
    """submit + 4 stage approval sampai OWNER_APPROVAL (versi jadi APPROVED)."""
    r = await _submit(client, sid, version)
    assert r.status_code == 200, r.text
    for stage in ("BACKTEST_REVIEW", "SHADOW_REVIEW", "PAPER_REVIEW",
                  "OWNER_APPROVAL"):
        r = await _review(client, sid, version, stage)
        assert r.status_code == 200, r.text
    return r


@pytest.fixture(autouse=True)
async def owner_env(_clean_db):
    """owner_username = 'tester' (user fixture) selama test versioning."""
    await db.set_setting("owner_username", "tester")
    yield
    await _exec("DELETE FROM settings WHERE key = 'owner_username'")


async def _second_admin():
    """Admin non-owner (username beda dari owner_username)."""
    await _exec(
        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'admin')",
        ("colleague", hash_password("colleaguepass")))
    c = _client()
    r = await c.post("/auth/login", json={"username": "colleague",
                                          "password": "colleaguepass"})
    assert r.status_code == 200, r.text
    c.headers["x-csrf-token"] = r.json()["csrf_token"]
    secret = (await c.post("/auth/2fa/setup")).json()["secret"]
    r = await c.post("/auth/2fa/enable", json={"code": totp.totp_at(secret)})
    assert r.status_code == 200, r.text
    r = await c.post("/auth/2fa/challenge",
                     json={"code": totp.totp_at(secret, time.time() + 30)})
    assert r.status_code == 200, r.text
    return c


# ── Registrasi & immutability (PRD 11.1) ────────────────────────────────────
async def test_register_version_stores_immutable_release_fields(client_2fa):
    r = await _register(client_2fa, params={"num_std": 2.5, "sl_atr": 1.1})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["version"] == "1.0.0"
    assert v["status"] == "DRAFT"
    assert v["code_commit_hash"]  # default git HEAD saat registrasi
    assert v["config_hash"] == versioning.config_hash(
        {"num_std": 2.5, "sl_atr": 1.1})
    assert v["data_version"] == "candles-2026-11"
    assert v["backtest_report"]["sharpe"] == 1.8
    assert v["walkforward_report"]["folds"] == 6
    assert v["risk_profile"]["max_risk_per_trade"] == 0.005
    assert v["change_reason"] == "rilis uji versioning"
    # strategi terdaftar: DRAFT, disabled, belum ada versi aktif (PRD 5.2)
    strat = await _one("SELECT * FROM strategies WHERE strategy_id='mean_reversion'")
    assert strat["status"] == "DRAFT" and strat["enabled"] is False
    assert strat["current_version"] is None
    # event registrasi tercatat
    ev = await _one("SELECT event_type FROM system_events WHERE "
                    "event_type='STRATEGY_VERSION_REGISTERED'")
    assert ev is not None


async def test_duplicate_version_rejected(client_2fa):
    assert (await _register(client_2fa)).status_code == 200
    r = await _register(client_2fa)
    assert r.status_code == 409
    assert "tidak boleh ditimpa" in r.json()["detail"]


async def test_artifacts_editable_only_in_draft(client_2fa):
    await _register(client_2fa)
    r = await client_2fa.post(
        "/strategies/mean_reversion/versions/1.0.0/artifacts",
        json={"fields": {"shadow_report": {"days": 5}}})
    assert r.status_code == 200, r.text
    assert r.json()["shadow_report"]["days"] == 5
    # submit -> REVIEW: artifact dibekukan di level API
    assert (await _submit(client_2fa)).status_code == 200
    r = await client_2fa.post(
        "/strategies/mean_reversion/versions/1.0.0/artifacts",
        json={"fields": {"paper_report": {"days": 2}}})
    assert r.status_code == 409


async def test_approved_version_immutable_api_and_db(client_2fa):
    """DoD inti: artifact versi disetujui tidak bisa diubah (PRD 11.4)."""
    await _register(client_2fa)
    await _promote_to_owner(client_2fa)
    v = await _one("SELECT * FROM strategy_versions WHERE "
                   "strategy_id='mean_reversion' AND version='1.0.0'")
    assert v["status"] == "APPROVED"
    # API menolak perubahan
    r = await client_2fa.post(
        "/strategies/mean_reversion/versions/1.0.0/artifacts",
        json={"fields": {"params": {"num_std": 9.9}}})
    assert r.status_code == 409
    # DB trigger menolak UPDATE dan DELETE (lapis kedua, PRD 11.1)
    with pytest.raises(Exception, match="immutable"):
        await _exec("UPDATE strategy_versions SET params = %s WHERE id = %s",
                    (json.dumps({"num_std": 9.9}), v["id"]))
    with pytest.raises(Exception, match="immutable"):
        await _exec("DELETE FROM strategy_versions WHERE id = %s", (v["id"],))
    # config_hash tidak berubah setelah semua percobaan
    v2 = await _one("SELECT config_hash, params FROM strategy_versions "
                    "WHERE id = %s", (v["id"],))
    assert v2["config_hash"] == v["config_hash"]
    assert v2["params"] == v["params"]


# ── Promotion workflow (PRD 11.2) ───────────────────────────────────────────
async def test_stage_order_enforced(client_2fa):
    await _register(client_2fa)
    await _submit(client_2fa)
    r = await _review(client_2fa, "mean_reversion", "1.0.0", "OWNER_APPROVAL")
    assert r.status_code == 409
    assert "urutan" in r.json()["detail"].lower() or "butuh" in r.json()["detail"].lower()
    # stage yang sama tidak boleh diputuskan dua kali
    assert (await _review(client_2fa, "mean_reversion", "1.0.0",
                          "BACKTEST_REVIEW")).status_code == 200
    r = await _review(client_2fa, "mean_reversion", "1.0.0", "BACKTEST_REVIEW")
    assert r.status_code == 409
    assert "append-only" in r.json()["detail"]


async def test_rejection_freezes_version(client_2fa):
    await _register(client_2fa)
    await _submit(client_2fa)
    r = await _review(client_2fa, "mean_reversion", "1.0.0", "BACKTEST_REVIEW",
                      decision="REJECTED", rationale="walk-forward bocor")
    assert r.status_code == 200, r.text
    v = await _one("SELECT status FROM strategy_versions WHERE "
                   "strategy_id='mean_reversion' AND version='1.0.0'")
    assert v["status"] == "REJECTED"
    r = await _review(client_2fa, "mean_reversion", "1.0.0", "SHADOW_REVIEW")
    assert r.status_code == 409  # versi final, keputusan baru ditolak
    # versi ditolak juga immutable di DB
    row = await _one("SELECT id FROM strategy_versions WHERE "
                     "strategy_id='mean_reversion' AND version='1.0.0'")
    with pytest.raises(Exception, match="immutable"):
        await _exec("UPDATE strategy_versions SET change_reason = 'x' "
                    "WHERE id = %s", (row["id"],))


async def test_owner_stage_requires_owner_username(client_2fa):
    await _register(client_2fa)
    await _submit(client_2fa)
    for stage in ("BACKTEST_REVIEW", "SHADOW_REVIEW", "PAPER_REVIEW"):
        assert (await _review(client_2fa, "mean_reversion", "1.0.0",
                              stage)).status_code == 200
    # admin sah tapi bukan owner -> 403 di stage OWNER_APPROVAL
    other = await _second_admin()
    r = await _review(other, "mean_reversion", "1.0.0", "OWNER_APPROVAL")
    assert r.status_code == 403
    assert "owner" in r.json()["detail"].lower()
    # rollback juga owner-only
    r = await other.post("/strategies/mean_reversion/rollback",
                         json={"reason": "uji", "to_version": None})
    assert r.status_code == 403


# ── Aktivasi (PRD 11.2/11.4) ────────────────────────────────────────────────
async def test_activate_paper_requires_paper_review(client_2fa):
    await _register(client_2fa)
    await _submit(client_2fa)
    assert (await _review(client_2fa, "mean_reversion", "1.0.0",
                          "BACKTEST_REVIEW")).status_code == 200
    r = await client_2fa.post(
        "/strategies/mean_reversion/versions/1.0.0/activate",
        json={"mode": "paper", "reason": "naik ke paper"})
    assert r.status_code == 409
    assert "PAPER_REVIEW" in r.json()["detail"]


async def test_activate_live_requires_owner_and_live_approval(client_2fa):
    await _register(client_2fa)
    assert (await _submit(client_2fa)).status_code == 200
    for stage in ("BACKTEST_REVIEW", "SHADOW_REVIEW", "PAPER_REVIEW"):
        assert (await _review(client_2fa, "mean_reversion", "1.0.0",
                              stage)).status_code == 200
    # OWNER_APPROVAL belum -> live ditolak
    r = await client_2fa.post(
        "/strategies/mean_reversion/versions/1.0.0/activate",
        json={"mode": "live", "reason": "naik live"})
    assert r.status_code == 409
    assert (await _review(client_2fa, "mean_reversion", "1.0.0",
                          "OWNER_APPROVAL")).status_code == 200
    # OWNER sudah, LIVE_APPROVAL belum -> live masih ditolak
    r = await client_2fa.post(
        "/strategies/mean_reversion/versions/1.0.0/activate",
        json={"mode": "live", "reason": "naik live"})
    assert r.status_code == 409
    assert "LIVE_APPROVAL" in r.json()["detail"]
    assert (await _review(client_2fa, "mean_reversion", "1.0.0",
                          "LIVE_APPROVAL")).status_code == 200
    r = await client_2fa.post(
        "/strategies/mean_reversion/versions/1.0.0/activate",
        json={"mode": "live", "reason": "canary live"})
    assert r.status_code == 200, r.text
    strat = await _one("SELECT current_version, enabled FROM strategies "
                       "WHERE strategy_id='mean_reversion'")
    assert strat["current_version"] == "1.0.0" and strat["enabled"] is True


async def test_full_promotion_paper_activation_records_evidence(client_2fa):
    """PRD 11.2: DRAFT->...->PAPER dengan bukti + aktor di tiap transisi."""
    await _register(client_2fa)
    await _promote_to_owner(client_2fa)
    strat = await _one("SELECT status FROM strategies WHERE "
                       "strategy_id='mean_reversion'")
    assert strat["status"] == "LIVE_APPROVED"
    v = await _one("SELECT status FROM strategy_versions WHERE "
                   "strategy_id='mean_reversion' AND version='1.0.0'")
    assert v["status"] == "APPROVED"
    r = await client_2fa.post(
        "/strategies/mean_reversion/versions/1.0.0/activate",
        json={"mode": "paper", "reason": "promosi ke paper"})
    assert r.status_code == 200, r.text
    strat = await _one("SELECT current_version, enabled FROM strategies "
                       "WHERE strategy_id='mean_reversion'")
    assert strat["current_version"] == "1.0.0" and strat["enabled"] is True
    settings = await db.get_settings()
    assert settings["strategy_mode_mean_reversion"] == "paper"
    assert settings["strategy_params_mean_reversion"] == {"num_std": 2.0}
    # approval ACTIVATE + deployment_records + audit settings tercatat
    act = await _one("SELECT stage, reviewer, evidence FROM strategy_approvals "
                     "WHERE stage='ACTIVATE'")
    assert act is not None and act["reviewer"] == "tester"
    assert act["evidence"]["mode"] == "paper"
    assert act["evidence"]["previous_version"] is None
    dep = await _one("SELECT service, version, deploy_type, details FROM "
                     "deployment_records WHERE details->>'action'='ACTIVATE'")
    assert dep is not None and dep["version"] == "1.0.0"
    assert dep["deploy_type"] == "CONFIG"
    audit = await _one("SELECT key, new_value, changed_by FROM settings_audit "
                       "WHERE key='strategy_mode_mean_reversion' "
                       "ORDER BY id DESC LIMIT 1")
    assert audit is not None and audit["changed_by"] == "tester"


# ── Rollback (PRD 11.3) ─────────────────────────────────────────────────────
async def _seed_open_positions(sid="mean_reversion"):
    """Posisi terbuka live + paper; rollback TIDAK boleh menutupnya."""
    # live: orders.strategy -> positions.order_id (skema a001)
    row = await _one(
        """
        INSERT INTO orders (symbol, side, volume, sl, tp, strategy, action,
                            status, ticket, price_filled)
        VALUES ('XAUUSD', 'BUY', 0.01, 1990.0, 2020.0, %s, 'OPEN',
                'FILLED', 900001, 2000.0)
        RETURNING id
        """,
        (sid,))
    await _exec(
        """
        INSERT INTO positions (ticket, order_id, symbol, side, volume,
                               open_price, open_time, sl, tp, status)
        VALUES (900001, %s, 'XAUUSD', 'BUY', 0.01, 2000.0, now(),
                1990.0, 2020.0, 'OPEN')
        """,
        (row["id"],))
    await _exec(
        """
        INSERT INTO paper_orders (mode, strategy, symbol, side, volume, sl, tp,
                                  entry_price, status, opened_at)
        VALUES ('PAPER', %s, 'XAUUSD', 'SELL', 0.02, 2010.0, 1990.0,
                2005.0, 'OPEN', now())
        """,
        (sid,))
    await _exec(
        """
        INSERT INTO paper_state (key, value, updated_at) VALUES (%s, %s, now())
        """,
        (f"runner_{sid}",
         json.dumps({"balance": 10000.0, "position": {
             "order_id": "1", "side": "SELL", "volume": 0.02,
             "entry_price": 2005.0, "sl": 2010.0, "tp": 1990.0}})))


async def _open_live_count(sid="mean_reversion") -> int:
    row = await _one(
        """
        SELECT count(*) AS n FROM positions p
        JOIN orders o ON o.id = p.order_id
        WHERE p.status = 'OPEN' AND o.strategy = %s
        """,
        (sid,))
    return int(row["n"])


async def _two_active_versions(client, sid="mean_reversion"):
    """v1.0.0 dan v1.1.0 sama-sama ter-approve + aktif di paper."""
    await _register(client, sid, "1.0.0", params={"num_std": 2.0})
    await _promote_to_owner(client, sid, "1.0.0")
    await client.post(f"/strategies/{sid}/versions/1.0.0/activate",
                      json={"mode": "paper", "reason": "baseline"})
    await _register(client, sid, "1.1.0", params={"num_std": 3.0},
                    change_reason="kalibrasi ulang")
    await _promote_to_owner(client, sid, "1.1.0")
    await client.post(f"/strategies/{sid}/versions/1.1.0/activate",
                      json={"mode": "paper", "reason": "versi baru"})
    strat = await _one("SELECT current_version FROM strategies WHERE "
                       f"strategy_id='{sid}'")
    assert strat["current_version"] == "1.1.0"


async def test_rollback_restores_last_approved_keeps_positions(client_2fa):
    """DoD staging: rollback berhenti di sinyal versi bermasalah, posisi
    terbuka tidak ditutup, rollback + rekonsiliasi tercatat (PRD 11.3)."""
    await _seed_open_positions()
    await _two_active_versions(client_2fa)
    # posisi terbuka tercatat sebelum rollback
    pre = await _open_live_count()
    assert pre == 1
    r = await client_2fa.post("/strategies/mean_reversion/rollback", json={
        "reason": "sharpe versi 1.1.0 runtuh di live",
        "position_policy": "MANAGE_AS_IS"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["from_version"] == "1.1.0"
    assert body["to_version"] == "1.0.0"  # versi terakhir yang disetujui
    # 1. current_version kembali ke versi lama (sinyal versi bermasalah stop)
    strat = await _one("SELECT current_version, enabled FROM strategies "
                       "WHERE strategy_id='mean_reversion'")
    assert strat["current_version"] == "1.0.0"
    # 2. params versi lama dipulihkan (ter-audit)
    settings = await db.get_settings()
    assert settings["strategy_params_mean_reversion"] == {"num_std": 2.0}
    # 3. posisi terbuka TIDAK disentuh
    post = await _open_live_count()
    assert post == pre
    po = await _one("SELECT status FROM paper_orders WHERE "
                    "strategy='mean_reversion' ORDER BY id DESC LIMIT 1")
    assert po["status"] == "OPEN"
    # 4. rollback tercatat sebagai event (3 kanal audit)
    rb = await _one("SELECT stage, reviewer, rationale, evidence FROM "
                    "strategy_approvals WHERE stage='ROLLBACK'")
    assert rb is not None and rb["reviewer"] == "tester"
    assert rb["evidence"]["from_version"] == "1.1.0"
    assert rb["evidence"]["open_positions_touched"] is False
    ev = await _one("SELECT event_type, severity, details FROM system_events "
                    "WHERE event_type='STRATEGY_ROLLBACK'")
    assert ev is not None and ev["severity"] == "WARN"
    assert ev["details"]["to_version"] == "1.0.0"
    dep = await _one("SELECT details FROM deployment_records "
                     "WHERE details->>'action'='ROLLBACK'")
    assert dep is not None
    # 5. rekonsiliasi pasca-rollback tercatat dengan posisi terbuka
    rec = await _one("SELECT * FROM reconciliation_runs "
                     "WHERE trigger_source='POST_ROLLBACK'")
    assert rec is not None
    assert rec["status"] == "COMPLETED"
    assert rec["ledger_summary"]["live_open_positions"] == 1
    assert rec["ledger_summary"]["paper_open_positions"] == 1
    assert "tidak diotomatis tutup" in rec["ledger_summary"]["note"]
    assert body["reconciliation_run_id"] == str(rec["run_id"])


async def test_rollback_default_picks_last_activated_not_current(client_2fa):
    """Tanpa to_version: target = versi terakhir diaktifkan selain sekarang."""
    await _two_active_versions(client_2fa)
    r = await client_2fa.post("/strategies/mean_reversion/rollback",
                              json={"reason": "balik ke baseline"})
    assert r.status_code == 200, r.text
    assert r.json()["to_version"] == "1.0.0"


async def test_rollback_rejects_unapproved_and_same_version(client_2fa):
    await _two_active_versions(client_2fa)
    # rollback ke versi yang sama -> 409
    r = await client_2fa.post("/strategies/mean_reversion/rollback",
                              json={"reason": "x", "to_version": "1.1.0"})
    assert r.status_code == 409
    # rollback ke versi yang belum disetujui -> 409
    await _register(client_2fa, "mean_reversion", "1.2.0")
    r = await client_2fa.post("/strategies/mean_reversion/rollback",
                              json={"reason": "x", "to_version": "1.2.0"})
    assert r.status_code == 409
    assert "disetujui" in r.json()["detail"]
    # tanpa alasan -> 409 (audit wajib)
    r = await client_2fa.post("/strategies/mean_reversion/rollback",
                              json={"reason": "  "})
    assert r.status_code == 409


async def test_rollback_without_active_version_409(client_2fa):
    await _register(client_2fa)
    await _promote_to_owner(client_2fa)
    r = await client_2fa.post("/strategies/mean_reversion/rollback",
                              json={"reason": "belum ada yang aktif"})
    assert r.status_code == 409
    assert "belum punya versi aktif" in r.json()["detail"]


# ── Versi jelas pada sinyal (PRD 11.4) + no auto-promotion ─────────────────
def _ctx(behavior: str) -> dict:
    """Context sandbox sama pola dengan BASE_CONTEXT test_supervisor."""
    now = "2026-11-24T00:00:00+00:00"
    return {"symbol": "XAUUSD", "now": now,
            "candles": [{"ts": "2026-11-23T23:55:00+00:00", "open": 2000,
                         "high": 2001, "low": 1999, "close": 2000.5,
                         "volume": 0}],
            "liquidity": {"ts": now, "bid": 1999.9, "ask": 2000.1,
                          "spread": 0.2, "spread_median_15m": 0.2,
                          "fresh": True},
            "positions": [], "trades_today": 0,
            "risk": {"equity": 10000.0, "risk_per_trade": 0.005,
                     "max_volume": 0.1, "max_spread": 0.5},
            "behavior": behavior}


async def _decide(conn, behavior="ok", strategy_id="sbx_probe"):
    return await supervisor.decide(
        conn, strategy_id=strategy_id, strategy_version="0.0.1",
        module=MODULE, context=_ctx(behavior), params={},
        symbol="XAUUSD", timeframe="M5", source="PAPER", settings={},
        seed_status="PAPER", module_dir=MODULE_DIR)


async def test_signals_carry_registry_version_and_rollback_switches(client_2fa):
    """Sinyal men-stamp versi registry aktif; setelah rollback sinyal baru
    membawa versi lama -> sinyal versi bermasalah berhenti (PRD 11.3/11.4)."""
    async with db.pool().connection() as conn:
        d1 = await _decide(conn)
        assert not d1.rejected
    row = await _one("SELECT strategy_version, current_version FROM signals "
                     "s JOIN strategies st ON st.strategy_id = s.strategy_id "
                     "WHERE s.strategy_id='sbx_probe' ORDER BY s.id DESC LIMIT 1")
    assert row["strategy_version"] == "0.0.1"  # seed legacy = versi modul
    # daftarkan + promosikan + aktifkan v0.1.0 lalu v0.2.0 untuk sbx_probe
    await _register(client_2fa, "sbx_probe", "0.1.0", params={})
    await _promote_to_owner(client_2fa, "sbx_probe", "0.1.0")
    r = await client_2fa.post(
        "/strategies/sbx_probe/versions/0.1.0/activate",
        json={"mode": "paper", "reason": "baseline registry"})
    assert r.status_code == 200, r.text
    await _register(client_2fa, "sbx_probe", "0.2.0", params={})
    await _promote_to_owner(client_2fa, "sbx_probe", "0.2.0")
    r = await client_2fa.post(
        "/strategies/sbx_probe/versions/0.2.0/activate",
        json={"mode": "paper", "reason": "uji stamp versi"})
    assert r.status_code == 200, r.text
    async with db.pool().connection() as conn:
        d2 = await _decide(conn)
        assert not d2.rejected
    row = await _one("SELECT strategy_version FROM signals WHERE "
                     "strategy_id='sbx_probe' ORDER BY id DESC LIMIT 1")
    assert row["strategy_version"] == "0.2.0"  # stamp versi registry
    # rollback -> sinyal berikutnya men-stamp versi baseline 0.1.0 lagi
    r = await client_2fa.post("/strategies/sbx_probe/rollback",
                              json={"reason": "versi 0.2.0 bermasalah"})
    assert r.status_code == 200, r.text
    assert r.json()["to_version"] == "0.1.0"
    async with db.pool().connection() as conn:
        d3 = await _decide(conn)
        assert not d3.rejected
    row = await _one("SELECT strategy_version FROM signals WHERE "
                     "strategy_id='sbx_probe' ORDER BY id DESC LIMIT 1")
    assert row["strategy_version"] == "0.1.0"


async def test_no_auto_promotion(client_2fa):
    """Tidak ada auto-promotion (PRD 11.4): registrasi tidak mengubah status;
    transisi otomatis supervisor hanya jalur fault, tidak pernah promosi."""
    await _register(client_2fa)
    # tidak ada keputusan eksplisit -> tidak ada perubahan status/approval
    v = await _one("SELECT status FROM strategy_versions WHERE "
                   "strategy_id='mean_reversion' AND version='1.0.0'")
    assert v["status"] == "DRAFT"
    n = await _one("SELECT count(*) AS n FROM strategy_approvals")
    assert n["n"] == 0
    strat = await _one("SELECT status, enabled FROM strategies WHERE "
                       "strategy_id='mean_reversion'")
    assert strat["status"] == "DRAFT" and strat["enabled"] is False
    # AUTO_TRANSITIONS hanya turun (fault), tidak ada yang naik privilege
    for src, dst in supervisor.AUTO_TRANSITIONS:
        assert dst in ("DEGRADED", "DISABLED"), (src, dst)
    # semua transisi kenaikan privilege owner-only (PRD 5.3/11.2)
    promotions = {("VALIDATING", "BACKTEST_APPROVED"),
                  ("BACKTEST_APPROVED", "SHADOW"), ("SHADOW", "PAPER"),
                  ("PAPER", "LIVE_APPROVED"), ("LIVE_APPROVED", "LIVE")}
    assert promotions <= supervisor.OWNER_ONLY_TRANSITIONS


async def test_versions_listing_shows_current_history_and_drift(client_2fa):
    await _two_active_versions(client_2fa)
    r = await client_2fa.get("/strategies/mean_reversion/versions")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["strategy"]["current_version"] == "1.1.0"
    versions = {v["version"]: v for v in data["versions"]}
    assert versions["1.0.0"]["is_current"] is False
    assert versions["1.1.0"]["is_current"] is True
    assert versions["1.0.0"]["status"] == "APPROVED"
    stages = [a["stage"] for a in versions["1.1.0"]["approvals"]]
    assert stages.count("ACTIVATE") == 1
    assert "BACKTEST_REVIEW" in stages and "OWNER_APPROVAL" in stages
    # drift: versi modul (kode jalan) vs versi registry aktif terlihat
    assert versions["1.1.0"]["module_version"] is not None
    assert versions["1.1.0"]["version_drift"] is True
    # detail satu versi
    r = await client_2fa.get("/strategies/mean_reversion/versions/1.0.0")
    assert r.status_code == 200
    assert r.json()["config_hash"] == versioning.config_hash({"num_std": 2.0})
