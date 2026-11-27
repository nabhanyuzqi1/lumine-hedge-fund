"""Guardrail risiko inti: PUT /admin/risk-settings (PRD §14, §18).

Kartu t_d3ab9839. Endpoint ini kanál resmi perubahan guardrail dari UI
admin: wajib sesi 2FA + konfirmasi ulang password akun + audit.
"""
from __future__ import annotations

import pytest

from app import db


@pytest.mark.asyncio
async def test_update_guardrails_ok(client_2fa):
    r = await client_2fa.put(
        "/admin/risk-settings",
        json={
            "password": "testpass",
            "max_volume": 0.10,
            "max_orders_per_min": 5,
            "max_daily_drawdown": 292.02,
            "max_tick_age_s": 3.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated"] == ["max_daily_drawdown", "max_orders_per_min",
                              "max_tick_age_s", "max_volume"]
    settings = await db.get_settings()
    assert settings["max_volume"] == 0.10
    assert settings["max_orders_per_min"] == 5
    assert settings["max_daily_drawdown"] == 292.02
    assert settings["max_tick_age_s"] == 3.0


@pytest.mark.asyncio
async def test_update_guardrails_audited(client_2fa):
    before = (await db.get_settings())["max_volume"]
    r = await client_2fa.put(
        "/admin/risk-settings", json={"password": "testpass", "max_volume": 0.10})
    assert r.status_code == 200, r.text
    async with db.pool().connection() as conn:
        audit = await (await conn.execute(
            "select action, object, details from audit_log "
            "where action = 'CONFIG_CHANGED' and object = 'risk_settings' "
            "order by id desc limit 1"
        )).fetchall()
        trail = await (await conn.execute(
            "select old_value, new_value from settings_audit "
            "where key = 'max_volume' order by id desc limit 1"
        )).fetchall()
    assert audit, "perubahan guardrail wajib tercatat di audit_log"
    assert audit[0]["details"]["previous"]["max_volume"] == before
    assert trail and trail[0]["new_value"] == 0.10


@pytest.mark.asyncio
async def test_update_guardrails_wrong_password(client_2fa):
    before = (await db.get_settings())["max_volume"]
    r = await client_2fa.put(
        "/admin/risk-settings", json={"password": "salah", "max_volume": 0.10})
    assert r.status_code == 403
    assert (await db.get_settings())["max_volume"] == before
    async with db.pool().connection() as conn:
        rows = await (await conn.execute(
            "select count(*) as n from audit_log "
            "where action = 'RISK_SETTINGS_REJECTED'"
        )).fetchall()
    assert rows[0]["n"] >= 1, "penolakan password wajib ter-audit"


@pytest.mark.asyncio
async def test_update_guardrails_requires_2fa(client):
    """Sesi admin tanpa step-up 2FA ditolak."""
    r = await client.put(
        "/admin/risk-settings", json={"password": "testpass", "max_volume": 0.10})
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_update_guardrails_range_check(client_2fa):
    r = await client_2fa.put(
        "/admin/risk-settings", json={"password": "testpass", "max_volume": 0})
    assert r.status_code == 422
    r = await client_2fa.put(
        "/admin/risk-settings", json={"password": "testpass", "max_orders_per_min": 0})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_update_portfolio_risk_merges(client_2fa):
    # Baris DB parsial (pola yang dipakai test_portfolio_risk) harus tetap
    # menghasilkan konfigurasi lengkap: default + baris lama + nilai baru.
    await db.set_setting("portfolio_risk", {"max_open_risk_pct": 0.1})
    r = await client_2fa.put(
        "/admin/risk-settings",
        json={"password": "testpass", "portfolio_risk": {"max_total_volume_lot": 0.30}},
    )
    assert r.status_code == 200, r.text
    after = (await db.get_settings())["portfolio_risk"]
    assert after["max_total_volume_lot"] == 0.30
    assert after["max_open_risk_pct"] == 0.1          # nilai lama dipertahankan
    assert after["max_risk_per_trade_pct"] == 0.5     # default tidak hilang
    assert after["stress"]["gap_pct"] == 0.5          # nested default utuh
