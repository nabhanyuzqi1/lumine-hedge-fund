"""Ringkasan lifecycle + riwayat approval untuk Strategy Lab (PRD v2.2 §21.4, §11).

Cover kartu UI-D3a (read-only, tanpa mengubah endpoint versioning existing):
- GET /strategies/lifecycle-summary: ringkasan per strategi dalam SATU
  panggilan (versi aktif, jumlah versi, approval terakhir, flag
  walk-forward/shadow, status degradasi) agar UI tidak N+1 fetch;
- GET /strategies/{id}/approvals: riwayat approval append-only urut desc
  (default limit 50), 404 untuk strategi tak dikenal;
- kedua endpoint memakai get_current_user saja (auth required, tanpa 2FA).

Data uji di-seed via SQL langsung (endpoint yang diuji read-only; tabel
strategy_versions/strategy_approvals immutable hanya dibaca, INSERT tetap
sah untuk fixture).
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app import db
from app.main import app


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _exec(query, params=()):
    async with db.pool().connection() as conn:
        await conn.execute(query, params)


async def _seed_strategy(sid: str, name: str, status: str = "DRAFT",
                         current_version: str | None = None):
    await _exec(
        """
        INSERT INTO strategies (strategy_id, name, status, current_version,
                                enabled)
        VALUES (%s, %s, %s, %s, false)
        ON CONFLICT (strategy_id) DO UPDATE
            SET name = EXCLUDED.name, status = EXCLUDED.status,
                current_version = EXCLUDED.current_version
        """,
        (sid, name, status, current_version))


async def _seed_version(sid: str, version: str, *,
                        walkforward: dict | None = None,
                        shadow: dict | None = None,
                        status: str = "DRAFT") -> int:
    async with db.pool().connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO strategy_versions (strategy_id, version, params,
                                           config_hash, walkforward_report,
                                           shadow_report, status, created_by)
            VALUES (%s, %s, '{}'::jsonb, 'hash-' || %s, %s::jsonb, %s::jsonb,
                    %s, 'tester') RETURNING id
            """,
            (sid, version, version,
             __import__("json").dumps(walkforward) if walkforward else None,
             __import__("json").dumps(shadow) if shadow else None,
             status))
        return (await cur.fetchone())["id"]


async def _seed_approval(version_id: int, *, stage: str, decision: str,
                         age_minutes: int, reviewer: str = "tester",
                         rationale: str = "ok"):
    await _exec(
        """
        INSERT INTO strategy_approvals (strategy_version_id, stage, decision,
                                        reviewer, rationale, evidence,
                                        created_at)
        VALUES (%s, %s, %s, %s, %s, '{}'::jsonb,
                now() - (%s || ' minutes')::interval)
        """,
        (version_id, stage, decision, reviewer, rationale, age_minutes))


async def _seed_degradation(sid: str, status: str):
    await _exec(
        "INSERT INTO degradation_state (strategy_id, status) VALUES (%s, %s) "
        "ON CONFLICT (strategy_id) DO UPDATE SET status = EXCLUDED.status",
        (sid, status))


# ── GET /strategies/lifecycle-summary ────────────────────────────────────────
async def test_lifecycle_summary_two_strategies(client):
    """2 strategi dengan versi berbeda: ringkasan lengkap dalam 1 panggilan."""
    # strategi A: 2 versi, punya walk-forward + shadow, degradation DEGRADED,
    # sudah aktif versi 1.1.0 (lifecycle PAPER).
    await _seed_strategy("alpha", "Alpha Breakout", status="PAPER",
                         current_version="1.1.0")
    v1 = await _seed_version("alpha", "1.0.0",
                             walkforward={"wf_sharpe": 1.2},
                             shadow={"sharpe": 1.5}, status="SUPERSEDED")
    await _seed_version("alpha", "1.1.0",
                        walkforward={"wf_sharpe": 1.4}, status="APPROVED")
    await _seed_approval(v1, stage="BACKTEST_REVIEW", decision="APPROVED",
                         age_minutes=120)
    await _seed_approval(v1, stage="SHADOW_REVIEW", decision="APPROVED",
                         age_minutes=60, rationale="shadow oke")
    await _seed_degradation("alpha", "DEGRADED")
    # strategi B: tanpa versi sama sekali.
    await _seed_strategy("beta", "Beta Blank")

    r = await client.get("/strategies/lifecycle-summary")
    assert r.status_code == 200, r.text
    rows = {s["strategy_id"]: s for s in r.json()["strategies"]}
    assert set(rows) == {"alpha", "beta"}

    a = rows["alpha"]
    assert a["name"] == "Alpha Breakout"
    assert a["lifecycle_status"] == "PAPER"
    assert a["active_version"] == "1.1.0"
    assert a["version_count"] == 2
    assert a["last_approval_stage"] == "SHADOW_REVIEW"   # yang terakhir
    assert a["last_approval_decision"] == "APPROVED"
    assert a["has_walkforward"] is True
    assert a["has_shadow"] is True
    assert a["degradation_status"] == "DEGRADED"
    assert a["updated_at"]

    # strategi tanpa versi: version_count 0, active_version null (kontrak UI)
    b = rows["beta"]
    assert b["version_count"] == 0
    assert b["active_version"] is None
    assert b["last_approval_stage"] is None
    assert b["last_approval_decision"] is None
    assert b["has_walkforward"] is False
    assert b["has_shadow"] is False
    assert b["degradation_status"] == "NORMAL"  # default tanpa row state


async def test_lifecycle_summary_empty(client):
    r = await client.get("/strategies/lifecycle-summary")
    assert r.status_code == 200, r.text
    assert r.json() == {"strategies": []}


# ── GET /strategies/{id}/approvals ───────────────────────────────────────────
async def test_approvals_sorted_desc_across_versions(client):
    """Riwayat approval lintas versi urut created_at DESC (terbaru dulu)."""
    await _seed_strategy("gamma", "Gamma Flow")
    v1 = await _seed_version("gamma", "1.0.0", status="APPROVED")
    v2 = await _seed_version("gamma", "2.0.0")
    await _seed_approval(v1, stage="BACKTEST_REVIEW", decision="APPROVED",
                         age_minutes=180)
    await _seed_approval(v1, stage="ACTIVATE", decision="APPROVED",
                         age_minutes=120, rationale="aktifkan v1")
    await _seed_approval(v2, stage="BACKTEST_REVIEW", decision="REJECTED",
                         age_minutes=60, rationale="metrik di bawah ambang")
    await _seed_approval(v2, stage="BACKTEST_REVIEW", decision="APPROVED",
                         age_minutes=30)

    r = await client.get("/strategies/gamma/approvals")
    assert r.status_code == 200, r.text
    approvals = r.json()["approvals"]
    assert [a["stage"] for a in approvals] == [
        "BACKTEST_REVIEW", "BACKTEST_REVIEW", "ACTIVATE", "BACKTEST_REVIEW"]
    assert [a["decision"] for a in approvals] == [
        "APPROVED", "REJECTED", "APPROVED", "APPROVED"]
    # field kontrak UI + versi ter-join
    assert set(approvals[0]) == {"id", "version", "stage", "decision",
                                 "reviewer", "rationale", "evidence",
                                 "created_at"}
    assert approvals[0]["version"] == "2.0.0"
    assert approvals[-1]["version"] == "1.0.0"
    # rationale terbawa: keputusan REJECTED punya rationale eksplisit
    rejected = [a for a in approvals if a["decision"] == "REJECTED"]
    assert len(rejected) == 1
    assert rejected[0]["rationale"] == "metrik di bawah ambang"
    assert rejected[0]["version"] == "2.0.0"


async def test_approvals_limit_50_default(client):
    """Default limit 50 baris walau riwayat lebih panjang (append-only)."""
    await _seed_strategy("delta", "Delta Long")
    v = await _seed_version("delta", "1.0.0")
    await _exec(
        """
        INSERT INTO strategy_approvals (strategy_version_id, stage, decision,
                                        reviewer, evidence, created_at)
        SELECT %s, 'PAPER_REVIEW', 'APPROVED', 'tester', '{}'::jsonb,
               now() - (g || ' minutes')::interval
        FROM generate_series(1, 55) g
        """,
        (v,))
    r = await client.get("/strategies/delta/approvals")
    assert r.status_code == 200, r.text
    approvals = r.json()["approvals"]
    assert len(approvals) == 50
    created = [a["created_at"] for a in approvals]
    assert created == sorted(created, reverse=True)  # tetap urut desc
    r = await client.get("/strategies/delta/approvals", params={"limit": 5})
    assert r.status_code == 200, r.text
    assert len(r.json()["approvals"]) == 5


async def test_approvals_unknown_strategy_404(client):
    r = await client.get("/strategies/tidak-ada/approvals")
    assert r.status_code == 404, r.text
    assert "tidak-ada" in r.json()["detail"]


async def test_approvals_known_strategy_without_history_empty(client):
    await _seed_strategy("epsilon", "Epsilon Quiet")
    r = await client.get("/strategies/epsilon/approvals")
    assert r.status_code == 200, r.text
    assert r.json() == {"approvals": []}


# ── Auth (read-only: get_current_user tanpa 2FA) ─────────────────────────────
async def test_summary_and_approvals_require_auth():
    async with _client() as c:
        r = await c.get("/strategies/lifecycle-summary")
        assert r.status_code == 401, r.text
        r = await c.get("/strategies/alpha/approvals")
        assert r.status_code == 401, r.text


async def test_summary_and_approvals_read_only_no_2fa(client):
    """Client login biasa (tanpa 2FA challenge) tetap bisa akses read-only."""
    await _seed_strategy("alpha", "Alpha Breakout")
    r = await client.get("/strategies/lifecycle-summary")
    assert r.status_code == 200, r.text
    r = await client.get("/strategies/alpha/approvals")
    assert r.status_code == 200, r.text
