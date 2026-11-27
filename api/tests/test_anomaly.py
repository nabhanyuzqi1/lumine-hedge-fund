"""Deteksi anomali harian (FUND2-P4, PRD 5.9; t_f2p4a2).

Tiga detektor murni (latensi, spread, rasio FAILED) diuji tanpa DB;
collect_anomalies diuji terhadap DB test (conftest: fund2_test_*, di-truncate
per test); jalur kirim Telegram diuji dengan fake_tg (tanpa jaringan).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app import anomaly, db

WIB = anomaly.WIB


# ---------------------------------------------------------------- util murni

def test_p95_median_kosong():
    assert anomaly._p95([]) is None
    assert anomaly._median([]) is None


def test_p95_sampel_tunggal():
    assert anomaly._p95([0.7]) == 0.7


def test_p95_ambil_persenil_95():
    # n=20: idx = ceil(0.95*20)-1 = 18 -> elemen ke-19 (nilai tertinggi kedua)
    vals = [0.01 * i for i in range(1, 21)]
    assert anomaly._p95(vals) == pytest.approx(0.19)


def test_median_genap_rata_tengah():
    assert anomaly._median([0.1, 0.2, 0.3, 0.4]) == pytest.approx(0.25)
    assert anomaly._median([0.3, 0.1, 0.2]) == pytest.approx(0.2)


def test_md_escape():
    assert anomaly._md_escape("XAU_USD") == "XAU\\_USD"
    assert anomaly._md_escape("a*b[c\\d") == "a\\*b\\[c\\\\d"


# ---------------------------------------------------------------- latensi

def test_latency_naik_terdeteksi():
    # p95 recent 500 ms >= 2x baseline 100 ms DAN > SLO 300 ms
    # p95 dari 3 sampel = elemen ke-3 (idx = ceil(0.95*3)-1 = 2)
    msg = anomaly.check_latency([0.5, 0.5, 0.5], [0.1] * 10)
    assert msg is not None
    assert "LATENSI ORDER NAIK" in msg
    assert "500 ms" in msg


def test_latency_naik_tapi_di_bawah_slo():
    # 2x baseline tapi masih < 300 ms -> sehat
    assert anomaly.check_latency([0.2, 0.2, 0.2], [0.05] * 10) is None


def test_latency_sehat():
    assert anomaly.check_latency([0.1, 0.12, 0.11], [0.1] * 10) is None


def test_latency_data_kurang():
    assert anomaly.check_latency([0.5, 0.5], [0.1] * 10) is None  # < 3 order


def test_latency_baseline_kosong():
    assert anomaly.check_latency([0.5, 0.5, 0.5], []) is None


# ---------------------------------------------------------------- spread

def test_spread_abnormal_rasio():
    msg = anomaly.check_spread("XAUUSD", [0.4] * 12, [0.1] * 12)
    assert msg is not None
    assert "SPREAD ABNORMAL" in msg
    assert "XAUUSD" in msg
    assert "4.0x" in msg


def test_spread_abnormal_absolut():
    # baseline tinggi (rasio < 2x) tapi di atas ambang absolut 0.50
    msg = anomaly.check_spread("XAUUSD", [0.6] * 12, [0.55] * 12)
    assert msg is not None
    assert "0.50 USD" in msg


def test_spread_sehat():
    assert anomaly.check_spread("XAUUSD", [0.2] * 12, [0.15] * 12) is None


def test_spread_sampel_kurang():
    assert anomaly.check_spread("XAUUSD", [0.9] * 11, [0.1] * 12) is None


def test_spread_baseline_kosong_pakai_absolut():
    msg = anomaly.check_spread("XAUUSD", [0.8] * 12, [])
    assert msg is not None
    assert "0.50 USD" in msg


def test_spread_absolut_bukan_simbol_terkalibrasi():
    # BTCUSD: spread 39 USD normal untuk skala harga BTC -> ambang absolut
    # 0.50 (kalibrasi XAUUSD) tidak berlaku, dan rasio vs baseline 1.0 sehat
    assert anomaly.check_spread("BTCUSD", [39.2] * 12, [39.2] * 12) is None


def test_spread_simbol_diescape():
    msg = anomaly.check_spread("XAU_USD", [0.8] * 12, [0.1] * 12)
    assert msg is not None
    assert "XAU\\_USD" in msg


# ---------------------------------------------------------------- rasio FAILED

def test_failed_ratio_tepat_ambang():
    statuses = ["FAILED"] + ["FILLED"] * 4  # 1/5 = 20%
    msg = anomaly.check_failed_ratio(statuses)
    assert msg is not None
    assert "RASIO FAILED TINGGI" in msg
    assert "1/5" in msg


def test_failed_ratio_di_bawah_ambang():
    assert anomaly.check_failed_ratio(["FAILED"] + ["FILLED"] * 9) is None


def test_failed_ratio_order_terminal_kurang():
    # hanya 4 order terminal -> belum bermakna
    assert anomaly.check_failed_ratio(["FAILED"] + ["FILLED"] * 3) is None


def test_failed_ratio_non_terminal_tidak_dihitung():
    # 100 order SENT (non-terminal) tidak masuk penyebut
    statuses = ["FAILED"] + ["FILLED"] * 3 + ["SENT"] * 100
    assert anomaly.check_failed_ratio(statuses) is None


def test_failed_ratio_dominan():
    statuses = ["FAILED"] * 3 + ["FILLED"] * 3  # 50%
    msg = anomaly.check_failed_ratio(statuses)
    assert msg is not None
    assert "3/6" in msg
    assert "50%" in msg


# ---------------------------------------------------------------- laporan

def test_build_report_dengan_anomali():
    text = anomaly.build_report(["⚠️ A", "⚠️ B"])
    assert "ANOMALI HARIAN" in text
    assert "⚠️ A" in text
    assert "⚠️ B" in text
    assert "Tidak ada anomali" not in text


def test_build_report_tanpa_anomali():
    text = anomaly.build_report([])
    assert "✅ Tidak ada anomali" in text


# ---------------------------------------------------------------- DB (collect)

async def _insert_order(*, status: str, created_at: datetime,
                        resolved_at: datetime | None = None,
                        symbol: str = "XAUUSD") -> None:
    async with db.pool().connection() as conn:
        await conn.execute(
            "INSERT INTO orders (symbol, side, volume, status, fail_reason, "
            "created_at, resolved_at) VALUES (%s, 'BUY', 0.01, %s, %s, %s, %s)",
            (symbol, status,
             "ea_no_result: fixture (stage=reconciler)" if status == "FAILED" else None,
             created_at, resolved_at),
        )


async def _insert_order_latency(*, created_at: datetime, latency_s: float,
                                symbol: str = "XAUUSD") -> None:
    """Order FILLED + event SENT ber-payload latency T0/T2 (PRD §6, t_4651d431).

    Patch latensi anomaly.py membaca T0→T2 dari order_events payload (mono_us),
    jadi fixture latensi harus menulis payload itu, bukan resolved_at.
    """
    async with db.pool().connection() as conn:
        row = await conn.execute(
            "INSERT INTO orders (symbol, side, volume, status, "
            "created_at, resolved_at) "
            "VALUES (%s, 'BUY', 0.01, 'FILLED', %s, %s) RETURNING id",
            (symbol, created_at, created_at + timedelta(seconds=latency_s)),
        )
        order_id = (await row.fetchone())["id"]
        t0_us = int(created_at.timestamp() * 1_000_000)
        await conn.execute(
            "INSERT INTO order_events (order_id, from_status, to_status, payload) "
            "VALUES (%s, 'RECEIVED', 'SENT', %s)",
            (order_id, json.dumps({
                "latency": {"T0": t0_us, "T2": t0_us + int(latency_s * 1_000_000)},
            })),
        )


async def _insert_spread(*, symbol: str, spread: float, window_start: datetime,
                         n: int = 12, session: str = "london") -> None:
    async with db.pool().connection() as conn:
        for i in range(n):
            await conn.execute(
                "INSERT INTO liquidity_samples (symbol, window_start, session, "
                "spread_avg, spread_min, spread_max, tick_count) "
                "VALUES (%s, %s, %s, %s, %s, %s, 5)",
                (symbol, window_start + timedelta(seconds=5 * i),
                 session, spread, spread, spread),
            )


async def test_collect_anomalies_deteksi_tiga_sekaligus():
    now = datetime.now(timezone.utc)
    # latensi: 3 order 24 jam dgn resolusi 500 ms; baseline 3 hari lalu 100 ms
    for _ in range(3):
        await _insert_order_latency(created_at=now - timedelta(hours=1), latency_s=0.5)
    for _ in range(5):
        await _insert_order_latency(created_at=now - timedelta(days=3), latency_s=0.1)
    # spread: XAUUSD recent 0.40 vs baseline 0.10 (4x)
    await _insert_spread(symbol="XAUUSD", spread=0.40,
                         window_start=now - timedelta(hours=1))
    await _insert_spread(symbol="XAUUSD", spread=0.10,
                         window_start=now - timedelta(days=3))
    # rasio FAILED: 5 order FAILED dalam 24 jam
    for _ in range(5):
        await _insert_order(status="FAILED", created_at=now - timedelta(hours=2))

    anomalies = await anomaly.collect_anomalies()
    joined = "\n".join(anomalies)
    assert "LATENSI ORDER NAIK" in joined
    assert "SPREAD ABNORMAL" in joined
    assert "RASIO FAILED TINGGI" in joined
    assert len(anomalies) == 3


async def test_collect_anomalies_sehat():
    now = datetime.now(timezone.utc)
    for _ in range(3):
        await _insert_order_latency(created_at=now - timedelta(hours=1), latency_s=0.1)
    for _ in range(5):
        await _insert_order_latency(created_at=now - timedelta(days=3), latency_s=0.1)
    await _insert_spread(symbol="XAUUSD", spread=0.20,
                         window_start=now - timedelta(hours=1))
    await _insert_spread(symbol="XAUUSD", spread=0.15,
                         window_start=now - timedelta(days=3))

    assert await anomaly.collect_anomalies() == []


async def test_collect_anomalies_db_kosong():
    assert await anomaly.collect_anomalies() == []


# ------------------------------------------------------------- exclude order QA

async def _insert_user(username: str, role: str) -> int:
    async with db.pool().connection() as conn:
        row = await conn.execute(
            "INSERT INTO users (username, password_hash, role) "
            "VALUES (%s, %s, %s) RETURNING id",
            (username, "uji-bukan-hash-asli", role),
        )
        return (await row.fetchone())["id"]


async def _insert_order_with_received(*, username: str | None, user_id: int | None,
                                      status: str, created_at: datetime,
                                      resolved_at: datetime | None = None) -> int:
    """Order + event RECEIVED ber-username pembuat (pola POST /orders, t_4651d431)."""
    async with db.pool().connection() as conn:
        row = await conn.execute(
            "INSERT INTO orders (user_id, symbol, side, volume, status, fail_reason, "
            "created_at, resolved_at) "
            "VALUES (%s, 'XAUUSD', 'BUY', 0.01, %s, %s, %s, %s) RETURNING id",
            (user_id, status,
             "ea_no_result: fixture (stage=reconciler)" if status == "FAILED" else None,
             created_at, resolved_at),
        )
        order_id = (await row.fetchone())["id"]
        await conn.execute(
            "INSERT INTO order_events (order_id, from_status, to_status, payload) "
            "VALUES (%s, NULL, 'RECEIVED', %s)",
            (order_id, json.dumps({"source": "api", "username": username})),
        )
        return order_id


async def _seed_latensi_failed_kontaminan(*, qa_username: str | None, qa_user_id: int | None):
    """3 order live sehat (24 jam + baseline) + 6 order kontaminan 175 s.

    Kalau order kontaminan ikut dihitung: p95 recent 175 s (>= 2x baseline
    100 ms DAN > SLO 300 ms) -> LATENSI ORDER NAIK, dan 5/9 terminal FAILED
    (55%) -> RASIO FAILED TINGGI. Persis profil insiden 25 Nov 2026.

    Mengembalikan list id order kontaminan (urutan seed) supaya test bisa
    mereatribusi order yang PASTI — created_at keenamnya identik, jadi
    ORDER BY created_at bersifat arbitrary (sumber flake).
    """
    now = datetime.now(timezone.utc)
    for _ in range(3):
        await _insert_order_latency(created_at=now - timedelta(hours=1), latency_s=0.1)
    for _ in range(5):
        await _insert_order_latency(created_at=now - timedelta(days=3), latency_s=0.1)
    contaminant_ids: list[str] = []
    for i in range(6):
        # tangkap order_id dari RETURNING (id UUID acak: ORDER BY id DESC
        # TIDAK menjamin order terakhir -> payload latensi bisa salah order,
        # bug flaky fixture lama)
        oid = await _insert_order_with_received(
            username=qa_username, user_id=qa_user_id,
            status="FAILED" if i < 5 else "FILLED",
            created_at=now - timedelta(hours=2),
            resolved_at=now - timedelta(hours=2) + timedelta(seconds=175),
        )
        contaminant_ids.append(oid)
        # kontaminan latensi: T0→T2 175 s (payload order_events, PRD §6)
        async with db.pool().connection() as conn:
            t0_us = int((now - timedelta(hours=2)).timestamp() * 1_000_000)
            await conn.execute(
                "INSERT INTO order_events (order_id, from_status, to_status, payload) "
                "VALUES (%s, 'RECEIVED', 'SENT', %s)",
                (oid, json.dumps({
                    "latency": {"T0": t0_us, "T2": t0_us + int(175 * 1_000_000)},
                })),
            )
    return contaminant_ids


async def test_collect_anomalies_order_qa_tidak_dihitung():
    """Regresi insiden 25 Nov 2026 (t_4651d431): order driver QA (user
    ber-role 'qa') tidak boleh masuk p95 latensi maupun rasio FAILED."""
    qa_id = await _insert_user("svc-qa-driver", "qa")
    await _seed_latensi_failed_kontaminan(qa_username="svc-qa-driver", qa_user_id=qa_id)
    assert await anomaly.collect_anomalies() == []


async def test_collect_anomalies_order_non_qa_tetap_dihitung():
    """Order buruk dari user non-QA tetap terdeteksi (exclude-nya spesifik
    role 'qa', bukan membuang semua order ber-username)."""
    admin_id = await _insert_user("tester-admin", "admin")
    await _seed_latensi_failed_kontaminan(qa_username="tester-admin", qa_user_id=admin_id)
    joined = "\n".join(await anomaly.collect_anomalies())
    assert "LATENSI ORDER NAIK" in joined
    assert "RASIO FAILED TINGGI" in joined


async def test_collect_anomalies_order_qa_reattributed_dikecualikan():
    """Order historis salah atribusi ke admin + compensating event
    QA_REATTRIBUTED -> user QA: keluar dari hitungan (append-only koreksi)."""
    await _insert_user("svc-qa-driver", "qa")
    await _insert_user("tester-admin", "admin")
    contaminant_ids = await _seed_latensi_failed_kontaminan(
        qa_username="tester-admin", qa_user_id=None)
    # koreksi: seluruh 6 order kontaminan diatribusikan ulang ke QA
    # (pakai id dari seed — created_at keenamnya identik, ORDER BY
    #  created_at bersifat arbitrary -> sumber flake)
    async with db.pool().connection() as conn:
        for oid in contaminant_ids:
            await conn.execute(
                "INSERT INTO order_events (order_id, from_status, to_status, payload) "
                "VALUES (%s, NULL, 'QA_REATTRIBUTED', %s)",
                (oid, json.dumps({"username": "svc-qa-driver", "task": "t_4651d431"})),
            )
    assert await anomaly.collect_anomalies() == []


async def test_collect_anomalies_failed_risk_rejected_tidak_dihitung():
    """Regresi t_3e43440c: order FAILED karena DITOLAK risk gate
    (payload risk=rejected) bukan gagal eksekusi — tidak boleh
    menyalakan RASIO FAILED TINGGI. Filosofi kill_switch:
    'ditolak risk gate, bukan gagal eksekusi'."""
    now = datetime.now(timezone.utc)
    async with db.pool().connection() as conn:
        # 5 order ditolak risk gate (insiden 25 Nov: portfolio/drawdown/kill-switch)
        for i in range(5):
            row = await conn.execute(
                "INSERT INTO orders (symbol, side, volume, status, fail_reason, "
                "created_at) VALUES ('XAUUSD', 'BUY', 0.01, 'FAILED', "
                "'ea_no_result: test (stage=reconciler)', %s) RETURNING id",
                (now - timedelta(hours=2),),
            )
            oid = (await row.fetchone())["id"]
            await conn.execute(
                "INSERT INTO order_events (order_id, from_status, to_status, payload) "
                "VALUES (%s, 'RECEIVED', 'FAILED', %s)",
                (oid, json.dumps({"risk": "rejected",
                                  "reasons": ["daily drawdown limit reached"]})),
            )
        # 5 order FILLED live
        for _ in range(5):
            await conn.execute(
                "INSERT INTO orders (symbol, side, volume, status, created_at) "
                "VALUES ('XAUUSD', 'BUY', 0.01, 'FILLED', %s)",
                (now - timedelta(hours=1),),
            )
    joined = "\n".join(await anomaly.collect_anomalies())
    assert "RASIO FAILED TINGGI" not in joined


async def test_collect_anomalies_failed_eksekusi_tetap_dihitung():
    """FAILED eksekusi pasar (tanpa payload risk=rejected) tetap memicu alert."""
    now = datetime.now(timezone.utc)
    async with db.pool().connection() as conn:
        for i in range(5):
            row = await conn.execute(
                "INSERT INTO orders (symbol, side, volume, status, fail_reason, "
                "created_at) VALUES ('XAUUSD', 'BUY', 0.01, 'FAILED', "
                "'ea_no_result: test (stage=reconciler)', %s) RETURNING id",
                (now - timedelta(hours=2),),
            )
            oid = (await row.fetchone())["id"]
            await conn.execute(
                "INSERT INTO order_events (order_id, from_status, to_status, payload) "
                "VALUES (%s, 'RECEIVED', 'FAILED', %s)",
                (oid, json.dumps({"reason": "OrderSend failed retcode=10018"})),
            )
    joined = "\n".join(await anomaly.collect_anomalies())
    assert "RASIO FAILED TINGGI" in joined


async def test_collect_anomalies_holding_time_tidak_dihitung_latensi():
    """Regresi t_3e43440c sumber #1: holding time posisi live (order di-close
    setelah menit-an) TIDAK termasuk sampel latensi T0→T2.

    Insiden 25 Nov: order FILLED_THEN_CLOSED di-hold hingga 3508 s; karena
    resolved_at diisi pada SEMUA status terminal, p95 'resolusi' 24 jam
    ~1950 s dan menyalakan LATENSI ORDER NAIK palsu (baseline 441 ms).
    Latensi kini dihitung dari payload T0→T2 order_events; order tanpa
    payload itu (instrumentasi lama) tidak dihitung sama sekali, dan
    resolved_at yang panjang tidak berpengaruh.
    """
    now = datetime.now(timezone.utc)
    # baseline sehat: 5 order 3 hari lalu, T0→T2 100 ms
    for _ in range(5):
        await _insert_order_latency(created_at=now - timedelta(days=3), latency_s=0.1)
    # 3 order live cepat 24 jam terakhir
    for _ in range(3):
        await _insert_order_latency(created_at=now - timedelta(hours=1), latency_s=0.1)
    # order live llm-agent di-close setelah hold 3508 s (insiden):
    # TANPA payload latency (instrumentasi lama) -> keluar dari sampel
    await _insert_order(
        status="FILLED_THEN_CLOSED",
        created_at=now - timedelta(hours=2),
        resolved_at=now - timedelta(hours=2) + timedelta(seconds=3508),
    )
    # order live dengan payload T0→T2 200 ms tapi hold 3508 s:
    # holding time diabaikan, T0→T2 yang dihitung (masih di bawah SLO)
    async with db.pool().connection() as conn:
        row = await conn.execute(
            "INSERT INTO orders (symbol, side, volume, status, created_at, resolved_at) "
            "VALUES ('XAUUSD', 'BUY', 0.01, 'FILLED_THEN_CLOSED', %s, %s) RETURNING id",
            (now - timedelta(hours=2),
             now - timedelta(hours=2) + timedelta(seconds=3508)),
        )
        order_id = (await row.fetchone())["id"]
        t0_us = int((now - timedelta(hours=2)).timestamp() * 1_000_000)
        await conn.execute(
            "INSERT INTO order_events (order_id, from_status, to_status, payload) "
            "VALUES (%s, 'RECEIVED', 'SENT', %s)",
            (order_id, json.dumps({
                "latency": {"T0": t0_us,
                            "T2": t0_us + int(0.2 * 1_000_000)},
            })),
        )
    assert await anomaly.collect_anomalies() == []


async def test_collect_anomalies_role_downgrade_akun_test():
    """Regresi t_3e43440c sumber #2: akun test lama ber-role 'admin' diturunkan
    ke 'qa' -> order historisnya keluar dari metrik anomaly (pola operasi live
    25 Nov: ui_d6_qa, llm3-e2e-agent, qac, qa_ops_ui, ui_d2_qa, tester).

    Kontras dalam satu test: sebelum downgrade order test ikut dihitung
    (alert menyala), sesudah downgrade collect_anomalies bersih.
    """
    await _insert_user("ui_d6_qa", "admin")  # kondisi awal: akun test masih admin
    await _seed_latensi_failed_kontaminan(
        qa_username="ui_d6_qa",
        qa_user_id=await _lookup_user_id("ui_d6_qa"),
    )
    joined = "\n".join(await anomaly.collect_anomalies())
    assert "LATENSI ORDER NAIK" in joined
    assert "RASIO FAILED TINGGI" in joined

    # operasi live t_3e43440c: turunkan role akun test menjadi 'qa'
    async with db.pool().connection() as conn:
        await conn.execute(
            "UPDATE users SET role = 'qa' WHERE username = 'ui_d6_qa'"
        )
    assert await anomaly.collect_anomalies() == []


async def _lookup_user_id(username: str) -> int:
    async with db.pool().connection() as conn:
        row = await (await conn.execute(
            "SELECT id FROM users WHERE username = %s", (username,),
        )).fetchone()
        return row["id"]


# ---------------------------------------------------------------- jalur kirim

async def test_send_path(fake_tg, monkeypatch):
    sent: list[str] = []

    async def fake_notify(text):
        sent.append(text)
        return True

    monkeypatch.setattr(anomaly, "notify_owner", fake_notify)
    text = anomaly.build_report(["⚠️ UJI"])
    assert await anomaly.notify_owner(text) is True
    assert sent == [text]
    assert "ANOMALI HARIAN" not in text or "UJI" in text


# ── 26 Nov 2026: kontaminasi harness sintetis + fixture QA ──────────────

async def test_collect_anomalies_harness_sintetis_tidak_dihitung():
    """Regresi alert SEV-3 26 Nov 2026 (T0→T2 p95 183 s, n=207).

    Harness latensi `p5-latency-gate-final` (mode 'harness-synthetic-ea')
    menulis order + event LATENCY ke DB dengan broker delay buatan 100-250 ms
    dan pace 6,8 s. Sampel itu bukan trafik broker dan tidak boleh membentuk
    p95 latensi live.
    """
    now = datetime.now(timezone.utc)
    # 3 order live normal (100 ms)
    for _ in range(3):
        await _insert_order_latency(created_at=now - timedelta(minutes=30), latency_s=0.1)
    # 20 order sintetis 183 s
    for _ in range(20):
        async with db.pool().connection() as conn:
            row = await conn.execute(
                "INSERT INTO orders (symbol, side, volume, status, created_at) "
                "VALUES ('XAUUSD', 'BUY', 0.01, 'FILLED', %s) RETURNING id",
                (now - timedelta(hours=1),),
            )
            oid = (await row.fetchone())["id"]
            t0_us = int((now - timedelta(hours=1)).timestamp() * 1_000_000)
            await conn.execute(
                "INSERT INTO order_events (order_id, from_status, to_status, payload) "
                "VALUES (%s, 'RECEIVED', 'SENT', %s)",
                (oid, json.dumps({
                    "latency": {"T0": t0_us, "T2": t0_us + 183_000_000,
                                "mode": "harness-synthetic-ea",
                                "run": "p5-latency-gate-final"},
                })),
            )
    joined = "\n".join(await anomaly.collect_anomalies())
    assert "LATENSI ORDER NAIK" not in joined


async def test_collect_anomalies_fixture_qa_tidak_dihitung_rasio():
    """Order ber-fail_reason 'qa-fixture' (driver menulis ke DB) bukan
    kegagalan eksekusi pasar: tidak boleh menaikkan rasio FAILED."""
    now = datetime.now(timezone.utc)
    async with db.pool().connection() as conn:
        for _ in range(6):
            await conn.execute(
                "INSERT INTO orders (symbol, side, volume, status, fail_reason, "
                "created_at) VALUES ('XAUUSD', 'BUY', 0.01, 'FAILED', "
                "'qa-fixture', %s)",
                (now - timedelta(hours=1),),
            )
        await conn.execute(
            "INSERT INTO orders (symbol, side, volume, status, created_at) "
            "VALUES ('XAUUSD', 'BUY', 0.01, 'FILLED', %s)",
            (now - timedelta(hours=1),),
        )
    joined = "\n".join(await anomaly.collect_anomalies())
    assert "RASIO FAILED TINGGI" not in joined


def test_check_failed_ratio_penyebut_semua_terminal():
    """Penolakan risk gate bukan kegagalan, tapi tetap masuk penyebut:
    3 gagal eksekusi dari 300 order terminal = 1%, bukan 3/3 = 100%."""
    dari = anomaly.check_failed_ratio
    rows = ([{"status": "FAILED", "gate": True}] * 297
            + [{"status": "FAILED", "gate": False}] * 3)
    assert dari(rows) is None
    rows_buruk = ([{"status": "FILLED", "gate": False}] * 5
                  + [{"status": "FAILED", "gate": False}] * 5)
    assert dari(rows_buruk) is not None
