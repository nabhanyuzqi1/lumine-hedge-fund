"""Endpoint tool Fibonacci chart (RISK-C, t_00db2872).

Level fib = ALAT BANTU. Modul ini tidak mengubah perilaku trading: tidak
menyentuh orders, bridge, kill-switch, maupun gate risk. Tujuannya hanya
menyimpan swing yang digambar user + level turunannya, supaya (a) chart bisa
menggambar ulang, dan (b) level itu opsional masuk konteks LLM.

Kontrak singkat:
- GET  /chart/fib/preview  -> hitung level tanpa menyimpan (validasi input).
- GET  /chart/fib/zones    -> daftar swing tersimpan untuk simbol (+TF opsional).
- POST /chart/fib/zones    -> simpan swing; level dihitung server (single source).
- DEL  /chart/fib/zones/id -> hapus; pembuat atau admin.

Semua mutasi wajib CSRF (require_csrf) dan tercatat di audit_log
(FIB_ZONE_CREATED / FIB_ZONE_DELETED). Simbol dibatasi whitelist chart yang
sama dengan /candles supaya UI tidak bisa menyimpan simbol liar.
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import db, fib_levels
from .auth import get_current_user, require_csrf
from .state_machine import fetchall, fetchone

router = APIRouter(prefix="/chart/fib")

#: Simbol chart (sama dengan CANDLE_SYMBOLS di routes.py).
CHART_SYMBOLS: tuple[str, ...] = ("XAUUSD", "BTCUSD")
CHART_TFS: tuple[str, ...] = ("M1", "M5", "M15")
MAX_ZONES = 50

#: Role yang boleh menulis swing/level. Sama dengan postur endpoint mutasi
#: lain: kredensial service 'agent' read-only, 'research' hanya riset, dan 'qa'
#: dipakai akun uji order. Ini bukan kontrol trading, jadi 'user' (operator
#: desk) ikut boleh; bacaan tetap terbuka untuk semua sesi login.
WRITE_ROLES = ("admin", "user")


def _require_writer(user: dict) -> None:
    if user.get("role") not in WRITE_ROLES:
        raise HTTPException(
            403, f"role {user.get('role')!r} read-only untuk tool fibonacci "
                 f"(butuh salah satu dari {', '.join(WRITE_ROLES)})")


class ZoneBody(BaseModel):
    symbol: str
    timeframe: str = "M5"
    direction: str
    swing_low: float
    swing_high: float
    note: str | None = Field(default=None, max_length=280)


def _clean_symbol(symbol: str) -> str:
    sym = (symbol or "").strip().upper()
    if sym not in CHART_SYMBOLS:
        raise HTTPException(
            400, f"symbol tidak didukung; salah satu dari {', '.join(CHART_SYMBOLS)}")
    return sym


def _clean_tf(timeframe: str | None, *, required: bool) -> str | None:
    if timeframe is None and not required:
        return None
    tf = (timeframe or "").strip().upper()
    if tf not in CHART_TFS:
        raise HTTPException(
            400, f"timeframe tidak didukung; salah satu dari {', '.join(CHART_TFS)}")
    return tf


def _levels_or_400(swing_low, swing_high, direction, digits) -> list[dict]:
    try:
        return fib_levels.compute_levels(swing_low, swing_high, direction, digits)
    except fib_levels.FibLevelError as exc:
        raise HTTPException(400, str(exc)) from None


def _zone_payload(row) -> dict:
    created = row["created_at"]
    return {
        "id": row["id"],
        "symbol": row["symbol"],
        "timeframe": row["timeframe"],
        "direction": row["direction"],
        "swing_low": float(row["swing_low"]),
        "swing_high": float(row["swing_high"]),
        "levels": row["levels"],
        "note": row["note"],
        "created_by": row["created_by_name"],
        "created_at": created.isoformat() if isinstance(created, datetime) else str(created),
    }


async def _audit(conn, user: dict, action: str, object_id: int,
                 details: dict, ip: str | None) -> None:
    await conn.execute(
        """
        INSERT INTO audit_log (actor, actor_role, action, object, details, ip)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (user.get("username") or "?", user.get("role"), action,
         f"fib_zone:{object_id}", json.dumps(details), ip),
    )


@router.get("/preview")
async def preview_levels(symbol: str,
                         direction: str,
                         swing_low: float,
                         swing_high: float,
                         timeframe: str | None = None,
                         user: dict = Depends(get_current_user)):
    """Hitung level tanpa menulis DB (dipakai chart saat user menarik swing)."""
    sym = _clean_symbol(symbol)
    tf = _clean_tf(timeframe, required=False)
    settings = await db.get_settings()
    digits = fib_levels.symbol_digits(sym, settings)
    levels = _levels_or_400(swing_low, swing_high, direction, digits)
    try:
        trend = fib_levels.normalize_direction(direction)
    except fib_levels.FibLevelError as exc:
        raise HTTPException(400, str(exc)) from None
    return {
        "symbol": sym,
        "timeframe": tf,
        "direction": trend,
        "swing_low": float(swing_low),
        "swing_high": float(swing_high),
        "digits": digits,
        "levels": levels,
        "informational_only": True,
    }


@router.get("/zones")
async def list_zones(symbol: str,
                     timeframe: str | None = None,
                     limit: int = 20,
                     user: dict = Depends(get_current_user)):
    sym = _clean_symbol(symbol)
    tf = _clean_tf(timeframe, required=False)
    if limit < 1 or limit > MAX_ZONES:
        raise HTTPException(400, f"limit harus 1..{MAX_ZONES}")
    sql = """
        SELECT f.*, u.username AS created_by_name
        FROM fib_levels f LEFT JOIN users u ON u.id = f.created_by
        WHERE f.symbol = %s
    """
    params: list = [sym]
    if tf is not None:
        sql += " AND f.timeframe = %s"
        params.append(tf)
    sql += " ORDER BY f.created_at DESC, f.id DESC LIMIT %s"
    params.append(limit)
    async with db.pool().connection() as conn:
        rows = await fetchall(conn, sql, tuple(params))
    return {"symbol": sym, "timeframe": tf, "count": len(rows),
            "zones": [_zone_payload(r) for r in rows]}


@router.post("/zones")
async def create_zone(body: ZoneBody, request: Request,
                      user: dict = Depends(require_csrf)):
    """Simpan satu swing + level hasil hitung server (deterministik).

    Retensi: per (symbol, timeframe) hanya MAX_ZONES swing terbaru yang
    disimpan; yang lebih lama dipangkas di transaksi yang sama supaya tabel
    tidak tumbuh tanpa batas karena klik UI (level lama tidak lagi relevan,
    chart hanya menampilkan yang terbaru).
    """
    _require_writer(user)
    sym = _clean_symbol(body.symbol)
    tf = _clean_tf(body.timeframe, required=True)
    settings = await db.get_settings()
    digits = fib_levels.symbol_digits(sym, settings)
    levels = _levels_or_400(body.swing_low, body.swing_high, body.direction, digits)
    try:
        trend = fib_levels.normalize_direction(body.direction)
        low, high = fib_levels.validate_swing(body.swing_low, body.swing_high)
    except fib_levels.FibLevelError as exc:
        raise HTTPException(400, str(exc)) from None
    note = (body.note or "").strip() or None
    ip = request.client.host if request.client else None
    async with db.pool().connection() as conn:
        async with conn.transaction():
            row = await fetchone(
                conn,
                """
                INSERT INTO fib_levels
                    (symbol, timeframe, direction, swing_low, swing_high,
                     levels, note, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (sym, tf, trend, low, high, json.dumps(levels), note,
                 user.get("user_id")),
            )
            await _audit(conn, user, "FIB_ZONE_CREATED", row["id"], {
                "symbol": sym, "timeframe": tf, "direction": trend,
                "swing_low": low, "swing_high": high, "digits": digits,
            }, ip)
            # Retensi: sisakan MAX_ZONES swing terbaru untuk (symbol, timeframe).
            await conn.execute(
                """
                DELETE FROM fib_levels
                WHERE symbol = %s AND timeframe = %s AND id NOT IN (
                    SELECT id FROM fib_levels
                    WHERE symbol = %s AND timeframe = %s
                    ORDER BY created_at DESC, id DESC LIMIT %s
                )
                """,
                (sym, tf, sym, tf, MAX_ZONES),
            )
    created = row["created_at"]
    return {
        "zone": {
            "id": row["id"], "symbol": row["symbol"], "timeframe": row["timeframe"],
            "direction": row["direction"], "swing_low": float(row["swing_low"]),
            "swing_high": float(row["swing_high"]), "levels": row["levels"],
            "note": row["note"], "created_by": user.get("username"),
            "created_at": created.isoformat() if isinstance(created, datetime)
            else str(created),
        },
        "informational_only": True,
    }


@router.delete("/zones/{zone_id}")
async def delete_zone(zone_id: int, request: Request,
                      user: dict = Depends(require_csrf)):
    """Hapus swing; hanya pembuat atau admin (shared desk, least privilege)."""
    _require_writer(user)
    ip = request.client.host if request.client else None
    async with db.pool().connection() as conn:
        async with conn.transaction():
            row = await fetchone(
                conn, "SELECT * FROM fib_levels WHERE id = %s FOR UPDATE", (zone_id,))
            if row is None:
                raise HTTPException(404, "fib zone tidak ditemukan")
            is_admin = user.get("role") == "admin"
            if not is_admin and row["created_by"] != user.get("user_id"):
                raise HTTPException(403, "hanya pembuat atau admin yang boleh menghapus")
            await conn.execute("DELETE FROM fib_levels WHERE id = %s", (zone_id,))
            await _audit(conn, user, "FIB_ZONE_DELETED", zone_id, {
                "symbol": row["symbol"], "timeframe": row["timeframe"],
                "direction": row["direction"],
                "swing_low": float(row["swing_low"]),
                "swing_high": float(row["swing_high"]),
            }, ip)
    return {"deleted": True, "id": zone_id}
