"""Strategy versioning, approval & rollback (PRD v2.2 §11, t_f2v22a6).

Immutable release: setiap versi strategi menyimpan strategy ID/version,
commit hash, config hash, data hash, laporan backtest/walk-forward/shadow/
paper, risk profile, reviewer & approval, tanggal aktivasi/nonaktif, dan
alasan perubahan. Versi final (APPROVED/REJECTED/SUPERSEDED) tidak bisa
diubah: trigger DB `strategy_versions_immutable` (b002) menolak UPDATE/
DELETE, dan API ini menolaknya dengan 409.

Promotion workflow (PRD 11.2):
  DRAFT -> BACKTEST -> REVIEW -> SHADOW -> PAPER -> OWNER_APPROVAL ->
  CANARY/LOW_RISK_LIVE -> FULL_APPROVED_LIVE
Setiap transisi punya bukti + aktor sah, tercatat append-only di
strategy_approvals. Tidak ada auto-promotion: status versi hanya berubah
lewat decide_stage() eksplisit; supervisor.AUTO_TRANSITIONS hanya jalur
fault (LIVE->DEGRADED, DEGRADED->DISABLED), tidak pernah promosi.

Rollback (PRD 11.3): owner memilih versi terakhir yang disetujui; sinyal
baru dari versi bermasalah berhenti (strategies.current_version dipindah;
supervisor.decide men-stamp versi registry pada setiap sinyal/intent);
posisi terbuka TIDAK diotomatis tutup; rollback tercatat sebagai event
(system_events + strategy_approvals stage ROLLBACK) dan memicu run
rekonsiliasi reconciliation_runs trigger_source=POST_ROLLBACK.

Tanggal aktivasi/nonaktif per versi dicatat append-only sebagai baris
strategy_approvals stage ACTIVATE (created_at = waktu aktivasi, evidence
berisi versi sebelumnya + waktu nonaktifnya). strategy_versions bersifat
final-once sehingga penanggalan hidup di audit trail, bukan di row versi.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import uuid
from datetime import datetime, timezone

from . import db, supervisor
from .state_machine import fetchone

# Urutan stage promotion (PRD 11.2). stage sebelumnya wajib APPROVED.
STAGES = ("BACKTEST_REVIEW", "SHADOW_REVIEW", "PAPER_REVIEW",
          "OWNER_APPROVAL", "LIVE_APPROVAL")
# Stage yang keputusannya hanya boleh diambil owner (2FA + owner_username).
OWNER_STAGES = {"OWNER_APPROVAL", "LIVE_APPROVAL"}
# Transisi lifecycle strategies (PRD 5.3) saat stage di-APPROVE. Hanya
# dijalankan bila status strategi tepat di from_status (strategi legacy yang
# sudah PAPER/LIVE tidak dimundur; approval tetap tercatat).
STAGE_LIFECYCLE = {
    "BACKTEST_REVIEW": ("VALIDATING", "BACKTEST_APPROVED"),
    "SHADOW_REVIEW": ("BACKTEST_APPROVED", "SHADOW"),
    "PAPER_REVIEW": ("SHADOW", "PAPER"),
    "OWNER_APPROVAL": ("PAPER", "LIVE_APPROVAL_PLACEHOLDER"),
    "LIVE_APPROVAL": ("LIVE_APPROVED", "LIVE"),
}
STAGE_LIFECYCLE["OWNER_APPROVAL"] = ("PAPER", "LIVE_APPROVED")

FINAL_STATUSES = ("APPROVED", "REJECTED", "SUPERSEDED")
VERSION_STATUSES = ("DRAFT", "REVIEW", "APPROVED", "REJECTED", "SUPERSEDED")
ARTIFACT_FIELDS = ("code_commit_hash", "code_path", "params", "data_version",
                   "backtest_report", "walkforward_report", "shadow_report",
                   "paper_report", "risk_profile", "change_reason")
REPORT_FIELDS = ("backtest_report", "walkforward_report", "shadow_report",
                 "paper_report", "risk_profile")


class VersioningError(Exception):
    """Pelanggaran alur versioning -> HTTP 409."""


class VersionFrozen(VersioningError):
    """Versi final immutable (PRD 11.1) -> HTTP 409."""


def config_hash(params: dict | None) -> str:
    """SHA-256 params kanonik (sort_keys, separator rapat)."""
    canonical = json.dumps(params or {}, sort_keys=True,
                           separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(__import__("pathlib").Path(__file__).resolve().parents[2]),
            text=True, stderr=subprocess.DEVNULL).strip()[:12]
    except Exception:
        return None


def module_versions() -> dict[str, str]:
    """Map strategy_id -> STRATEGY_VERSION konstanta modul (info drift)."""
    out: dict[str, str] = {}
    for name in ("london_breakout", "mean_reversion", "btc_range_breakout"):
        try:
            mod = importlib.import_module(f"strategies.{name}")
            out[getattr(mod, "STRATEGY_ID", name)] = getattr(
                mod, "STRATEGY_VERSION", "")
        except Exception:
            continue
    return out


async def _event(conn, event_type: str, message: str, *, actor: str,
                 details: dict | None = None, severity: str = "INFO") -> None:
    await conn.execute(
        """
        INSERT INTO system_events (event_type, severity, source, actor,
                                   message, details)
        VALUES (%s, %s, 'versioning', %s, %s, %s)
        """,
        (event_type, severity, actor, message,
         json.dumps(details or {}, default=str)))


async def get_version(conn, strategy_id: str, version: str) -> dict | None:
    row = await fetchone(
        conn, "SELECT * FROM strategy_versions WHERE strategy_id = %s "
              "AND version = %s", (strategy_id, version))
    return dict(row) if row else None


async def _require_version(conn, strategy_id: str, version: str) -> dict:
    row = await get_version(conn, strategy_id, version)
    if row is None:
        raise KeyError(f"versi {strategy_id}/{version} tidak terdaftar")
    return row


async def _reload(strategy_id: str, version: str) -> dict:
    async with db.pool().connection() as conn:
        return await _require_version(conn, strategy_id, version)


async def approved_stages(conn, version_id: int) -> list[str]:
    rows = await fetchone(
        conn,
        "SELECT COALESCE(array_agg(stage ORDER BY id), '{}') AS stages "
        "FROM strategy_approvals WHERE strategy_version_id = %s "
        "AND decision = 'APPROVED' AND stage = ANY(%s)",
        (version_id, list(STAGES)))
    return list((rows or {}).get("stages") or [])


# ── Registrasi versi (PRD 11.1) ─────────────────────────────────────────────
async def register_version(strategy_id: str, *, version: str, params: dict,
                           name: str | None = None,
                           code_commit_hash: str | None = None,
                           code_path: str | None = None,
                           data_version: str | None = None,
                           backtest_report: dict | None = None,
                           walkforward_report: dict | None = None,
                           shadow_report: dict | None = None,
                           paper_report: dict | None = None,
                           risk_profile: dict | None = None,
                           change_reason: str | None = None,
                           created_by: str = "system") -> dict:
    """Daftarkan versi baru (status DRAFT). Versi lama tidak pernah ditimpa.

    config_hash dihitung dari params kanonik; code_commit_hash default git
    HEAD saat pendaftaran. Strategi belum terdaftar dibuat dengan status
    DRAFT + enabled=false (tidak auto-live, PRD 5.2).
    """
    if not (version or "").strip():
        raise VersioningError("version wajib diisi")
    async with db.pool().connection() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO strategies (strategy_id, name, description,
                                        status, environment, config,
                                        current_version, enabled)
                VALUES (%s, %s, NULL, 'DRAFT', 'dev', '{}'::jsonb, NULL, false)
                ON CONFLICT (strategy_id) DO NOTHING
                """,
                (strategy_id, name or strategy_id))
            try:
                row = await (await conn.execute(
                    """
                    INSERT INTO strategy_versions (strategy_id, version,
                        code_commit_hash, code_path, params, config_hash,
                        data_version, backtest_report, walkforward_report,
                        shadow_report, paper_report, risk_profile, status,
                        change_reason, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            'DRAFT', %s, %s)
                    RETURNING id
                    """,
                    (strategy_id, version,
                     code_commit_hash or _git_head(), code_path,
                     json.dumps(params or {}), config_hash(params),
                     data_version,
                     json.dumps(backtest_report) if backtest_report else None,
                     json.dumps(walkforward_report) if walkforward_report else None,
                     json.dumps(shadow_report) if shadow_report else None,
                     json.dumps(paper_report) if paper_report else None,
                     json.dumps(risk_profile) if risk_profile else None,
                     change_reason, created_by))).fetchone()
            except Exception as exc:  # unique_violation -> 409
                if "strategy_versions_strategy_id_version_key" in str(exc):
                    raise VersioningError(
                        f"versi {strategy_id}/{version} sudah ada; "
                        "versi live tidak boleh ditimpa (PRD 11.1)") from exc
                raise
            await _event(
                conn, "STRATEGY_VERSION_REGISTERED",
                f"versi {strategy_id}/{version} terdaftar (DRAFT)",
                actor=created_by,
                details={"version": version, "config_hash": config_hash(params),
                         "code_commit_hash": code_commit_hash or _git_head(),
                         "change_reason": change_reason})
    return await _reload(strategy_id, version)


async def attach_artifacts(strategy_id: str, version: str, *, actor: str,
                           **fields) -> dict:
    """Lengkapi artifact versi. Hanya saat DRAFT (sebelum submit review).

    Setelah REVIEW/APPROVED artifact dibekukan (PRD 11.4: artifact versi
    yang sudah disetujui tidak dapat diubah). Params baru menghitung ulang
    config_hash.
    """
    unknown = set(fields) - set(ARTIFACT_FIELDS)
    if unknown:
        raise VersioningError(f"field tidak dikenal: {sorted(unknown)}")
    async with db.pool().connection() as conn:
        async with conn.transaction():
            ver = await _require_version(conn, strategy_id, version)
            if ver["status"] != "DRAFT":
                raise VersionFrozen(
                    f"versi {strategy_id}/{version} status {ver['status']}: "
                    "artifact dibekukan (PRD 11.1/11.4); buat versi baru")
            sets, args = [], []
            for field in ARTIFACT_FIELDS:
                if field not in fields or fields[field] is None:
                    continue
                value = fields[field]
                if field in REPORT_FIELDS or field == "params":
                    value = json.dumps(value)
                sets.append(f"{field} = %s")
                args.append(value)
            if "params" in fields and fields["params"] is not None:
                sets.append("config_hash = %s")
                args.append(config_hash(fields["params"]))
            if not sets:
                raise VersioningError("tidak ada artifact yang diubah")
            args.extend([strategy_id, version])
            await conn.execute(
                f"UPDATE strategy_versions SET {', '.join(sets)} "
                "WHERE strategy_id = %s AND version = %s", tuple(args))
            await _event(
                conn, "STRATEGY_VERSION_ARTIFACT",
                f"artifact {strategy_id}/{version} diperbarui (DRAFT)",
                actor=actor, details={"fields": sorted(
                    k for k in fields if fields.get(k) is not None)})
    return await _reload(strategy_id, version)


# ── Keputusan stage (PRD 11.2) ──────────────────────────────────────────────
async def decide_stage(strategy_id: str, version: str, stage: str,
                       decision: str, *, reviewer: str,
                       rationale: str | None = None,
                       evidence: dict | None = None) -> dict:
    """Rekam keputusan stage promotion (append-only strategy_approvals).

    Aturan: versi harus status REVIEW; stage sebelumnya wajib sudah
    APPROVED (urutan PRD 11.2); satu stage satu keputusan; REJECTED
    membekukan versi (status REJECTED, final). OWNER_APPROVAL APPROVED
    membekukan versi sebagai APPROVED (immutable, PRD 11.1).
    """
    stage = (stage or "").strip().upper()
    decision = (decision or "").strip().upper()
    if stage not in STAGES:
        raise VersioningError(f"stage harus salah satu dari {list(STAGES)}")
    if decision not in ("APPROVED", "REJECTED"):
        raise VersioningError("decision harus APPROVED atau REJECTED")
    async with db.pool().connection() as conn:
        async with conn.transaction():
            ver = await _require_version(conn, strategy_id, version)
            # LIVE_APPROVAL diputuskan setelah OWNER_APPROVAL membekukan
            # versi (APPROVED): keputusan stage berikutnya tetap sah karena
            # hanya menambah baris approval append-only, artifact tidak
            # disentuh. REJECTED di stage ini tidak mengubah status versi
            # yang sudah final; gerbang aktivasi live tetap memblokir.
            allowed = ("REVIEW",) if stage != "LIVE_APPROVAL" else (
                "REVIEW", "APPROVED")
            if ver["status"] not in allowed:
                raise VersioningError(
                    f"versi {strategy_id}/{version} status {ver['status']}: "
                    f"keputusan {stage} hanya untuk versi "
                    f"{'/'.join(allowed)}")
            done = await approved_stages(conn, ver["id"])
            idx = STAGES.index(stage)
            missing = [s for s in STAGES[:idx] if s not in done]
            if missing:
                raise VersioningError(
                    f"stage {stage} butuh approval sebelumnya: {missing} "
                    "(urutan PRD 11.2)")
            dup = await fetchone(
                conn, "SELECT id FROM strategy_approvals "
                "WHERE strategy_version_id = %s AND stage = %s",
                (ver["id"], stage))
            if dup:
                raise VersioningError(
                    f"stage {stage} sudah diputuskan (append-only, PRD 18)")
            await conn.execute(
                """
                INSERT INTO strategy_approvals (strategy_version_id, stage,
                                                decision, reviewer,
                                                rationale, evidence)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (ver["id"], stage, decision, reviewer, rationale,
                 json.dumps(evidence or {}, default=str)))
            if decision == "REJECTED" and ver["status"] == "REVIEW":
                await conn.execute(
                    "UPDATE strategy_versions SET status = 'REJECTED' "
                    "WHERE id = %s", (ver["id"],))
                await _event(
                    conn, "STRATEGY_VERSION_REJECTED",
                    f"versi {strategy_id}/{version} ditolak di {stage}",
                    actor=reviewer, details={"stage": stage,
                                             "rationale": rationale},
                    severity="WARN")
            elif stage == "OWNER_APPROVAL":
                await conn.execute(
                    "UPDATE strategy_versions SET status = 'APPROVED' "
                    "WHERE id = %s", (ver["id"],))
                await _event(
                    conn, "STRATEGY_VERSION_APPROVED",
                    f"versi {strategy_id}/"
                    f"{version} APPROVED (immutable, PRD 11.1)",
                    actor=reviewer, details={"stage": stage})
            # Transisi lifecycle strategies (PRD 5.3) bila status strategi
            # tepat di from_status; strategi legacy yang sudah lebih jauh
            # tidak dimundur.
            src, dst = STAGE_LIFECYCLE[stage]
            strat = await fetchone(
                conn, "SELECT status FROM strategies WHERE strategy_id = %s "
                "FOR UPDATE", (strategy_id,))
            if decision == "APPROVED" and strat and strat["status"] == src:
                await supervisor.transition_strategy(
                    conn, strategy_id, dst, actor=reviewer,
                    reason=f"stage {stage} APPROVED: "
                           f"{rationale or ''}".strip(),
                    actor_role="owner" if stage in OWNER_STAGES else "workflow")
    return await _reload(strategy_id, version)


# ── Aktivasi versi (PRD 11.2/11.4) ──────────────────────────────────────────
async def activate_version(strategy_id: str, version: str, *, mode: str,
                           actor: str, reason: str | None = None) -> dict:
    """Aktifkan versi ter-approve untuk strategi (mode 'paper' | 'live').

    mode paper butuh PAPER_REVIEW APPROVED; mode live butuh OWNER_APPROVAL +
    LIVE_APPROVAL (dan versi status APPROVED). Mengisi strategies.current_version
    + enabled=true + settings mode/params (ter-audit), mencatat stage ACTIVATE
    append-only (tanggal aktivasi + versi nonaktif sebelumnya) dan
    deployment_records. Tidak ada auto-promotion: panggilan ini eksplisit.
    """
    mode = (mode or "").strip().lower()
    if mode not in ("paper", "live"):
        raise VersioningError("mode harus 'paper' atau 'live'")
    async with db.pool().connection() as conn:
        async with conn.transaction():
            ver = await _require_version(conn, strategy_id, version)
            done = await approved_stages(conn, ver["id"])
            if mode == "paper":
                if not ({"PAPER_REVIEW", "OWNER_APPROVAL",
                         "LIVE_APPROVAL"} & set(done)):
                    raise VersioningError(
                        "aktivasi paper butuh PAPER_REVIEW APPROVED (PRD 11.2)")
            else:
                if ver["status"] != "APPROVED":
                    raise VersioningError(
                        "aktivasi live butuh versi status APPROVED "
                        "(OWNER_APPROVAL, PRD 11.1)")
                if not {"OWNER_APPROVAL", "LIVE_APPROVAL"} <= set(done):
                    raise VersioningError(
                        "aktivasi live butuh OWNER_APPROVAL + LIVE_APPROVAL "
                        "APPROVED (PRD 11.2)")
            strat = await fetchone(
                conn, "SELECT current_version, environment FROM strategies "
                "WHERE strategy_id = %s FOR UPDATE", (strategy_id,))
            if strat is None:
                raise KeyError(f"strategi {strategy_id} tidak terdaftar")
            previous = strat["current_version"]
            now = datetime.now(timezone.utc)
            await conn.execute(
                "UPDATE strategies SET current_version = %s, enabled = true, "
                "updated_at = now() WHERE strategy_id = %s",
                (version, strategy_id))
            # Settings ter-audit (trigger settings_audit, atribusi app.actor).
            await conn.execute("SELECT set_config('app.actor', %s, true)",
                               (actor,))
            await conn.execute("SELECT set_config('app.source', 'versioning', true)")
            await conn.execute(
                """
                INSERT INTO settings (key, value, updated_at) VALUES (%s, %s, now())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,
                                                updated_at = now()
                """,
                (f"strategy_mode_{strategy_id}", json.dumps(mode)))
            await conn.execute(
                """
                INSERT INTO settings (key, value, updated_at) VALUES (%s, %s, now())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,
                                                updated_at = now()
                """,
                (f"strategy_params_{strategy_id}",
                 json.dumps(ver["params"] or {})))
            await conn.execute(
                """
                INSERT INTO strategy_approvals (strategy_version_id, stage,
                                                decision, reviewer,
                                                rationale, evidence)
                VALUES (%s, 'ACTIVATE', 'APPROVED', %s, %s, %s)
                """,
                (ver["id"], actor, reason,
                 json.dumps({"mode": mode, "previous_version": previous,
                             "activated_at": now.isoformat(),
                             "previous_deactivated_at": now.isoformat()
                             if previous else None,
                             "config_hash": ver["config_hash"]},
                            default=str)))
            await _event(
                conn, "STRATEGY_VERSION_ACTIVATED",
                f"versi {strategy_id}/{version} aktif (mode {mode})",
                actor=actor,
                details={"mode": mode, "previous_version": previous,
                         "reason": reason})
            await conn.execute(
                """
                INSERT INTO deployment_records (service, version, environment,
                                                deploy_type, deployed_by,
                                                status, details, finished_at)
                VALUES (%s, %s, %s, 'CONFIG', %s, 'SUCCESS', %s, now())
                """,
                (f"fund2-strategy-{strategy_id}", version,
                 strat["environment"] or "dev", actor,
                 json.dumps({"action": "ACTIVATE", "mode": mode,
                             "previous_version": previous},
                            default=str)))
    return await _reload(strategy_id, version)


async def submit_review(strategy_id: str, version: str, *, actor: str,
                        evidence: dict | None = None) -> dict:
    """DRAFT -> REVIEW: kunci artifact + mulai promotion workflow (PRD 11.2).

    Syarat bukti minimal: code_commit_hash + config_hash terisi dan salah
    satu laporan backtest/walk-forward ada. Strategi berstatus DRAFT naik
    ke VALIDATING (bukti masuk review).
    """
    async with db.pool().connection() as conn:
        async with conn.transaction():
            ver = await _require_version(conn, strategy_id, version)
            if ver["status"] != "DRAFT":
                raise VersioningError(
                    f"versi {strategy_id}/{version} status {ver['status']}, "
                    "submit hanya dari DRAFT")
            if not ver["code_commit_hash"] or not ver["config_hash"]:
                raise VersioningError(
                    "submit butuh code_commit_hash + config_hash (PRD 11.2)")
            if not ver["backtest_report"] and not ver["walkforward_report"]:
                raise VersioningError(
                    "submit butuh laporan backtest/walk-forward (PRD 11.2)")
            await conn.execute(
                "UPDATE strategy_versions SET status = 'REVIEW' "
                "WHERE id = %s", (ver["id"],))
            strat = await fetchone(
                conn, "SELECT status FROM strategies WHERE strategy_id = %s "
                "FOR UPDATE", (strategy_id,))
            if strat and strat["status"] == "DRAFT":
                await supervisor.transition_strategy(
                    conn, strategy_id, "VALIDATING", actor=actor,
                    reason=f"versi {version} masuk review",
                    actor_role="workflow")
            await _event(
                conn, "STRATEGY_VERSION_SUBMITTED",
                f"versi {strategy_id}/{version} masuk REVIEW",
                actor=actor, details={"evidence": evidence or {}})
    return await _reload(strategy_id, version)


# ── Rollback (PRD 11.3) ─────────────────────────────────────────────────────
async def resolve_rollback_target(conn, strategy_id: str, current: str,
                                  to_version: str | None) -> dict:
    """Versi tujuan rollback: eksplisit (harus ter-approve) atau otomatis
    versi terakhir yang pernah ACTIVATE dan bukan versi sekarang."""
    if to_version:
        target = await _require_version(conn, strategy_id, to_version)
        if target["version"] == current:
            raise VersioningError(
                f"versi {to_version} sudah menjadi versi aktif")
        done = await approved_stages(conn, target["id"])
        if target["status"] != "APPROVED" and not (
                {"PAPER_REVIEW", "OWNER_APPROVAL",
                 "LIVE_APPROVAL"} & set(done)):
            raise VersioningError(
                f"versi {to_version} belum disetujui (PRD 11.3: rollback ke "
                "versi terakhir yang disetujui)")
        return target
    row = await fetchone(
        conn,
        """
        SELECT sv.* FROM strategy_versions sv
        JOIN strategy_approvals sa ON sa.strategy_version_id = sv.id
        WHERE sv.strategy_id = %s AND sv.version <> %s
          AND sa.stage = 'ACTIVATE' AND sa.decision = 'APPROVED'
        ORDER BY sa.created_at DESC, sa.id DESC LIMIT 1
        """,
        (strategy_id, current))
    if row is None:
        raise VersioningError(
            "tidak ada versi teraktifasi untuk rollback; "
            "sebutkan to_version yang disetujui")
    return dict(row)


async def rollback_strategy(strategy_id: str, *, to_version: str | None,
                            actor: str, reason: str,
                            position_policy: str = "MANAGE_AS_IS") -> dict:
    """Rollback ke versi terakhir disetujui (PRD 11.3).

    - Sinyal baru dari versi bermasalah berhenti: strategies.current_version
      dipindah ke versi tujuan (supervisor.decide men-stamp versi registry
      pada setiap sinyal/intent).
    - Posisi terbuka TIDAK disentuh (tidak ada flatten/close otomatis);
      kebijakan exit-nya mengikuti position_policy dari owner, hanya
      dicatat sebagai evidence.
    - Rollback tercatat: strategy_approvals stage ROLLBACK (append-only),
      system_events STRATEGY_ROLLBACK, deployment_records, dan run
      rekonsiliasi reconciliation_runs trigger_source=POST_ROLLBACK.
    - Params versi tujuan dipulihkan ke settings (ter-audit settings_audit).
    """
    if not (reason or "").strip():
        raise VersioningError("alasan rollback wajib diisi (audit)")
    async with db.pool().connection() as conn:
        async with conn.transaction():
            strat = await fetchone(
                conn, "SELECT * FROM strategies WHERE strategy_id = %s "
                "FOR UPDATE", (strategy_id,))
            if strat is None:
                raise KeyError(f"strategi {strategy_id} tidak terdaftar")
            current = strat["current_version"]
            if not current:
                raise VersioningError(
                    f"strategi {strategy_id} belum punya versi aktif")
            target = await resolve_rollback_target(
                conn, strategy_id, current, to_version)
            now = datetime.now(timezone.utc)
            await conn.execute(
                "UPDATE strategies SET current_version = %s, updated_at = now() "
                "WHERE strategy_id = %s",
                (target["version"], strategy_id))
            await conn.execute("SELECT set_config('app.actor', %s, true)",
                               (actor,))
            await conn.execute("SELECT set_config('app.source', 'rollback', true)")
            await conn.execute(
                """
                INSERT INTO settings (key, value, updated_at) VALUES (%s, %s, now())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,
                                                updated_at = now()
                """,
                (f"strategy_params_{strategy_id}",
                 json.dumps(target["params"] or {})))
            await conn.execute(
                """
                INSERT INTO strategy_approvals (strategy_version_id, stage,
                                                decision, reviewer,
                                                rationale, evidence)
                VALUES (%s, 'ROLLBACK', 'APPROVED', %s, %s, %s)
                """,
                (target["id"], actor, reason,
                 json.dumps({"from_version": current,
                             "to_version": target["version"],
                             "position_policy": position_policy,
                             "open_positions_touched": False,
                             "rolled_back_at": now.isoformat()},
                            default=str)))
            await _event(
                conn, "STRATEGY_ROLLBACK",
                f"rollback {strategy_id}: {current} -> {target['version']}",
                actor=actor,
                details={"from_version": current,
                         "to_version": target["version"],
                         "position_policy": position_policy,
                         "reason": reason},
                severity="WARN")
            # Rekonsiliasi pasca-rollback: hitung posisi terbuka (live +
            # paper), TIDAK menutup apa pun (PRD 11.3). Posisi live terkait
            # strategi via orders.strategy (positions tidak punya kolom
            # strategy; join positions.order_id -> orders.id).
            live_open = await fetchone(
                conn,
                """
                SELECT count(*) AS n FROM positions p
                JOIN orders o ON o.id = p.order_id
                WHERE p.status = 'OPEN' AND o.strategy = %s
                """,
                (strategy_id,))
            paper_state = await fetchone(
                conn, "SELECT value FROM paper_state WHERE key = %s",
                (f"runner_{strategy_id}",))
            paper_open = 0
            if paper_state and (paper_state.get("value") or {}).get("position"):
                paper_open = 1
            run_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO reconciliation_runs (run_id, trigger_source,
                    status, broker_snapshot, ledger_summary, mismatches,
                    mismatch_count, critical_count, action_taken,
                    started_at, finished_at)
                VALUES (%s, 'POST_ROLLBACK', 'COMPLETED', '{}'::jsonb,
                        %s, '[]'::jsonb, 0, 0, 'NONE', now(), now())
                """,
                (run_id,
                 json.dumps({
                     "strategy_id": strategy_id,
                     "from_version": current,
                     "to_version": target["version"],
                     "live_open_positions": int((live_open or {})["n"]),
                     "paper_open_positions": paper_open,
                     "note": "posisi terbuka tidak diotomatis tutup "
                             "(PRD 11.3); exit mengikuti policy owner",
                     "position_policy": position_policy},
                     default=str)))
            await conn.execute(
                """
                INSERT INTO deployment_records (service, version, environment,
                                                deploy_type, deployed_by,
                                                status, details, finished_at)
                VALUES (%s, %s, %s, 'CONFIG', %s, 'SUCCESS', %s, now())
                """,
                (f"fund2-strategy-{strategy_id}", target["version"],
                 strat["environment"] or "dev", actor,
                 json.dumps({"action": "ROLLBACK", "from_version": current,
                             "to_version": target["version"],
                             "position_policy": position_policy,
                             "reconciliation_run_id": run_id},
                            default=str)))
    return {"strategy_id": strategy_id, "from_version": current,
            "to_version": target["version"],
            "position_policy": position_policy,
            "reconciliation_run_id": run_id,
            "note": "posisi terbuka tidak diubah (PRD 11.3)"}


# ── Read API ────────────────────────────────────────────────────────────────
async def list_versions(conn, strategy_id: str) -> dict:
    """Semua versi + approval + status aktif + drift versi modul (PRD 11.4)."""
    strat = await fetchone(
        conn, "SELECT strategy_id, name, status, environment, enabled, "
        "current_version FROM strategies WHERE strategy_id = %s",
        (strategy_id,))
    if strat is None:
        raise KeyError(f"strategi {strategy_id} tidak terdaftar")
    rows = await fetchone(
        conn,
        """
        SELECT COALESCE(json_agg(t ORDER BY t.created_at), '[]'::json) AS data
        FROM (SELECT id, version, code_commit_hash, code_path, params,
                     config_hash, data_version, backtest_report,
                     walkforward_report, shadow_report, paper_report,
                     risk_profile, status, change_reason, created_by,
                     created_at FROM strategy_versions
              WHERE strategy_id = %s) t
        """,
        (strategy_id,))
    versions = (rows or {}).get("data") or []
    mod_versions = module_versions()
    for v in versions:
        appr = await fetchone(
            conn,
            "SELECT COALESCE(json_agg(a ORDER BY a.created_at), '[]'::json) "
            "AS data FROM (SELECT stage, decision, reviewer, rationale, "
            "evidence, created_at FROM strategy_approvals "
            "WHERE strategy_version_id = %s) a", (v["id"],))
        v["approvals"] = (appr or {}).get("data") or []
        v["is_current"] = (v["version"] == strat["current_version"])
        v["module_version"] = mod_versions.get(strategy_id)
        v["version_drift"] = (
            mod_versions.get(strategy_id) is not None
            and strat["current_version"] is not None
            and mod_versions.get(strategy_id) != strat["current_version"])
    return {"strategy": dict(strat), "versions": versions}


# ── Ringkasan untuk Strategy Lab (PRD v2.2 §21.4, t_b61b39d0) ───────────────
async def get_strategy(conn, strategy_id: str) -> dict | None:
    """Satu baris strategies; None bila strategy_id tidak terdaftar."""
    row = await fetchone(
        conn, "SELECT * FROM strategies WHERE strategy_id = %s", (strategy_id,))
    return dict(row) if row else None


async def lifecycle_summary(conn) -> list[dict]:
    """Ringkasan lifecycle SEMUA strategi dalam satu query (anti N+1 UI).

    Sumber (read-only): strategies (lifecycle + versi aktif, supervisor
    state), strategy_versions (jumlah versi + flag laporan),
    strategy_approvals (keputusan terakhir), degradation_state (status
    degradasi; row absen = NORMAL, selaras degradation.DEFAULT_STATE).
    has_shadow juga true bila ada run di shadow_runs (registry run) meski
    shadow_report versi belum diisi. Strategi tanpa versi: version_count 0,
    active_version null, tanpa approval terakhir.
    """
    row = await fetchone(
        conn,
        """
        SELECT COALESCE(json_agg(t ORDER BY t.strategy_id), '[]'::json) AS data
        FROM (
            SELECT s.strategy_id, s.name,
                   s.status AS lifecycle_status,
                   s.current_version AS active_version,
                   COUNT(v.id)::int AS version_count,
                   COALESCE(BOOL_OR(v.walkforward_report IS NOT NULL), false)
                       AS has_walkforward,
                   COALESCE(BOOL_OR(v.shadow_report IS NOT NULL), false)
                       OR EXISTS (SELECT 1 FROM shadow_runs sr
                                  WHERE sr.strategy_id = s.strategy_id)
                       AS has_shadow,
                   (SELECT sa.stage FROM strategy_approvals sa
                    JOIN strategy_versions sv ON sv.id = sa.strategy_version_id
                    WHERE sv.strategy_id = s.strategy_id
                    ORDER BY sa.created_at DESC, sa.id DESC LIMIT 1)
                       AS last_approval_stage,
                   (SELECT sa.decision FROM strategy_approvals sa
                    JOIN strategy_versions sv ON sv.id = sa.strategy_version_id
                    WHERE sv.strategy_id = s.strategy_id
                    ORDER BY sa.created_at DESC, sa.id DESC LIMIT 1)
                       AS last_approval_decision,
                   COALESCE(dg.status, 'NORMAL') AS degradation_status,
                   s.updated_at
            FROM strategies s
            LEFT JOIN strategy_versions v ON v.strategy_id = s.strategy_id
            LEFT JOIN degradation_state dg ON dg.strategy_id = s.strategy_id
            GROUP BY s.strategy_id, s.name, s.status, s.current_version,
                     s.updated_at, dg.status
        ) t
        """)
    return (row or {}).get("data") or []


async def list_approvals(conn, strategy_id: str, limit: int = 50) -> list[dict]:
    """Riwayat approval strategi (append-only, PRD 11), urut terbaru.

    Gabungan approval semua versi strategi (join strategy_versions untuk
    label versi), ORDER BY created_at DESC (tie-break id DESC), dibatasi
    `limit` (default 50, di-clamp ke 1..200).
    """
    row = await fetchone(
        conn,
        """
        SELECT COALESCE(json_agg(t ORDER BY t.created_at DESC, t.id DESC),
                        '[]'::json) AS data
        FROM (SELECT sa.id, sv.version, sa.stage, sa.decision, sa.reviewer,
                     sa.rationale, sa.evidence, sa.created_at
              FROM strategy_approvals sa
              JOIN strategy_versions sv ON sv.id = sa.strategy_version_id
              WHERE sv.strategy_id = %s
              ORDER BY sa.created_at DESC, sa.id DESC
              LIMIT %s) t
        """,
        (strategy_id, max(1, min(int(limit), 200))))
    return (row or {}).get("data") or []
