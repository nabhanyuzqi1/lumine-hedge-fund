"""Strategy isolation supervisor (PRD v2.2 §5).

Satu strategi tidak boleh membuat seluruh trading engine gagal. Modul ini:

1. Menjalankan setiap decide() strategi di subprocess terisolasi
   (app/sandbox_child.py) dengan batas CPU, memory, wall-clock, file
   (RLIMIT_FSIZE=0 + Landlock), dan network (socket patch + Landlock net).
2. Strategy runtime tidak menerima db/broker credential: env kosong,
   `python -I -E`, fd warisan ditutup, FS dikunci sebelum decide().
3. Memvalidasi semua output terhadap schema OrderIntent (PRD 4.1):
   timeout / exception / malformed / NaN / Inf / volume tidak valid /
   tanpa SL -> reject.
4. Circuit breaker: ambang error beruntun -> breaker OPEN + lifecycle
   DEGRADED -> DISABLED (auto). Recovery lewat probe HALF_OPEN + owner.
5. Lifecycle (PRD 5.3) di tabel `strategies` (migrasi b002):
   DRAFT -> VALIDATING -> BACKTEST_APPROVED -> SHADOW -> PAPER ->
   LIVE_APPROVED -> LIVE -> DEGRADED -> DISABLED -> ARCHIVED.
   Transisi yang menaikkan privilege trading hanya owner/workflow
   (admin + 2FA di API); supervisor hanya auto: LIVE->DEGRADED,
   DEGRADED->DISABLED.
6. Semua crash & keputusan supervisor dicatat: system_events (source
   'supervisor') + signals (keluaran decide() tervalidasi, lintas mode).

Runner (paper/runner.py) memanggil supervisor.decide(); satu strategi
crash/timeout hanya menghasilkan reject untuk strategi itu — API dan
strategi lain tetap berjalan.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import resource
import signal
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .state_machine import fetchone

API_DIR = str(Path(__file__).resolve().parent.parent)   # api/
CHILD_PATH = str(Path(__file__).with_name("sandbox_child.py"))

# ── Konfigurasi (settings key 'strategy_supervisor', merge di atas default) ──
DEFAULT_CONFIG: dict = {
    "wall_timeout_s": 10.0,     # batas wall-clock per decide()
    "mem_limit_mb": 512,        # RLIMIT_AS
    "cpu_limit_s": 5,           # RLIMIT_CPU
    "breaker_threshold": 5,     # error beruntun sebelum breaker OPEN
    "breaker_cooldown_s": 300.0, # jeda sebelum probe HALF_OPEN
    "intent_ttl_s": 60,         # expires_at OrderIntent (PRD 4.1)
}
ACTIVE_STATUSES = {"SHADOW", "PAPER", "LIVE_APPROVED", "LIVE", "DEGRADED"}

# ── Lifecycle (PRD 5.3) ─────────────────────────────────────────────────────
LIFECYCLE_STATUSES = (
    "DRAFT", "VALIDATING", "BACKTEST_APPROVED", "SHADOW", "PAPER",
    "LIVE_APPROVED", "LIVE", "DEGRADED", "DISABLED", "ARCHIVED",
)

ALLOWED_LIFECYCLE: dict[str, set[str]] = {
    "DRAFT": {"VALIDATING", "ARCHIVED"},
    "VALIDATING": {"BACKTEST_APPROVED", "DRAFT", "ARCHIVED"},  # DRAFT = ditolak
    "BACKTEST_APPROVED": {"SHADOW", "ARCHIVED"},
    "SHADOW": {"PAPER", "DEGRADED", "ARCHIVED"},
    "PAPER": {"LIVE_APPROVED", "DEGRADED", "ARCHIVED"},
    "LIVE_APPROVED": {"LIVE", "DEGRADED", "ARCHIVED"},
    "LIVE": {"DEGRADED", "DISABLED", "ARCHIVED"},
    "DEGRADED": {"LIVE", "PAPER", "SHADOW", "DISABLED", "ARCHIVED"},
    "DISABLED": {"LIVE_APPROVED", "DEGRADED", "ARCHIVED"},
    "ARCHIVED": set(),
}

# Transisi yang menaikkan privilege trading: hanya owner / release workflow
# yang diotorisasi (PRD 5.3). API menegakkan admin + 2FA step-up.
OWNER_ONLY_TRANSITIONS = {
    ("VALIDATING", "BACKTEST_APPROVED"),
    ("BACKTEST_APPROVED", "SHADOW"),
    ("SHADOW", "PAPER"),
    ("PAPER", "LIVE_APPROVED"),
    ("LIVE_APPROVED", "LIVE"),
    ("DEGRADED", "LIVE"),
    ("DEGRADED", "PAPER"),
    ("DEGRADED", "SHADOW"),
    ("DISABLED", "LIVE_APPROVED"),
    ("DISABLED", "DEGRADED"),
}
# Satu-satunya transisi otomatis supervisor (jalur fault).
AUTO_TRANSITIONS = {
    ("LIVE", "DEGRADED"),
    ("DEGRADED", "DISABLED"),
}


# ── Fault & reject ──────────────────────────────────────────────────────────
class StrategyFault(Exception):
    """Kegagalan eksekusi/output strategi -> reject + breaker++."""
    reason_code = "FAULT"


class SandboxTimeout(StrategyFault):
    reason_code = "TIMEOUT"


class SandboxCrash(StrategyFault):
    reason_code = "CRASH"


class SandboxProtocol(StrategyFault):
    reason_code = "MALFORMED"


class SchemaInvalid(StrategyFault):
    reason_code = "SCHEMA_INVALID"


class LifecycleError(Exception):
    """Transisi status strategi tidak sah."""


# ── Sandbox subprocess ──────────────────────────────────────────────────────
def _preexec_limits(mem_bytes: int, cpu_s: int):
    """preexec_fn: rlimits + tutup fd warisan (async-signal-safe syscalls)."""

    def fn() -> None:
        try:
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
            resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except OSError:
            pass
        try:
            os.closerange(3, 4096)
        except OSError:
            pass

    return fn


def _kill_process_group(proc: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


async def run_sandbox(*, module: str, context: dict, params: dict,
                      wall_timeout_s: float, mem_limit_mb: int = 512,
                      cpu_limit_s: int = 5,
                      module_dir: str = API_DIR) -> dict:
    """Jalankan satu decide() di subprocess terisolasi. Return respons JSON.

    Raise SandboxTimeout / SandboxCrash / SandboxProtocol. Wall-clock
    divereg di sini (PRD 5.4: timeout tidak menahan order path).
    """
    request = json.dumps(
        {"module": module, "module_dir": module_dir,
         "context": context, "params": params},
        default=str, ensure_ascii=False,
    ).encode("utf-8")
    with tempfile.TemporaryDirectory(prefix="f2sandbox-") as sandbox_cwd:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-I", "-E", "-B", CHILD_PATH,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={},                      # 1: tanpa env secret apa pun
            cwd=sandbox_cwd,             # 4: cwd kosong
            start_new_session=True,      # 7: process group sendiri (killpg)
            preexec_fn=_preexec_limits(mem_limit_mb * 1024 * 1024, cpu_limit_s),
        )
        try:
            out, err = await asyncio.wait_for(
                proc.communicate(request), timeout=wall_timeout_s)
        except asyncio.TimeoutError:
            _kill_process_group(proc)
            await proc.wait()
            raise SandboxTimeout(
                f"strategy decide exceeded wall clock {wall_timeout_s}s")
        if proc.returncode != 0:
            tail = (err or b"")[-500:].decode("utf-8", "replace")
            raise SandboxCrash(
                f"strategy subprocess exited code={proc.returncode}: {tail}")
        return _parse_response(out)


def _parse_response(out: bytes) -> dict:
    if len(out) > 1 * 1024 * 1024:
        raise SandboxProtocol("sandbox response too large")
    lines = [ln for ln in out.decode("utf-8", "replace").splitlines() if ln.strip()]
    if not lines:
        raise SandboxProtocol("sandbox produced no output")
    try:
        resp = json.loads(lines[-1])
    except ValueError as exc:
        raise SandboxProtocol(f"malformed sandbox output: {exc}") from exc
    if not isinstance(resp, dict) or "ok" not in resp:
        raise SandboxProtocol("malformed sandbox response envelope")
    return resp


def load_config(settings: dict | None = None) -> dict:
    """Default + settings key 'strategy_supervisor' (subset apa pun)."""
    cfg = dict(DEFAULT_CONFIG)
    override = (settings or {}).get("strategy_supervisor") or {}
    if isinstance(override, dict):
        for key in cfg:
            if override.get(key) is not None:
                cfg[key] = override[key]
    return cfg


# ── Validasi schema (PRD 4.1 / 5.2) ────────────────────────────────────────
# Field yang boleh dikembalikan modul strategi (mirror OrderIntent dataclass
# di api/strategies/*). Field PRD lainnya (signal_id, client_order_id, dst.)
# diisi supervisor lewat finalize_intent — strategi tidak dipercaya mengisinya.
RAW_INTENT_KEYS = {
    "symbol", "side", "volume", "sl", "tp", "strategy", "reason",
    "sl_distance", "risk_usd",
}


def _finite(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _num(value) -> float | None:
    return float(value) if _finite(value) else None


def context_hash(context: dict) -> str:
    """Hash kanonik context (immutable untuk satu decide, PRD 4.2)."""
    canonical = json.dumps(context, sort_keys=True, default=str,
                           ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_raw_output(raw, *, strategy_id: str, symbol: str) -> dict:
    """Validasi keluaran mentah decide() sebelum di-finalize.

    Reject: bukan dict, key tak dikenal, symbol/side salah, volume <= 0 atau
    NaN/Inf, SL kosong/NaN/Inf, reason bukan string. Raise SchemaInvalid.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise SchemaInvalid(
            f"output must be OrderIntent dict or None, got {type(raw).__name__}")
    unknown = set(raw) - RAW_INTENT_KEYS
    if unknown:
        raise SchemaInvalid(f"unknown output fields: {sorted(unknown)}")

    def need_finite(key: str, *, positive: bool) -> float:
        value = raw.get(key)
        num = _num(value)
        if num is None:
            raise SchemaInvalid(f"{key} must be a finite number "
                                f"(NaN/Inf/missing rejected), got {value!r}")
        if positive and num <= 0:
            raise SchemaInvalid(f"{key} must be > 0, got {num}")
        return num

    sym = raw.get("symbol")
    if not isinstance(sym, str) or not sym or sym != symbol:
        raise SchemaInvalid(f"symbol mismatch: got {sym!r}, expected {symbol!r}")
    side = raw.get("side")
    if side not in ("BUY", "SELL"):
        raise SchemaInvalid(f"side must be BUY|SELL, got {side!r}")
    strategy = raw.get("strategy")
    if strategy != strategy_id:
        raise SchemaInvalid(
            f"strategy identity mismatch: got {strategy!r}, expected {strategy_id!r}")
    need_finite("volume", positive=True)
    need_finite("sl", positive=True)          # PRD 4.1: order tanpa SL ditolak
    if raw.get("tp") is not None:
        need_finite("tp", positive=True)
    reason = raw.get("reason", "")
    if reason is None:
        reason = ""
    if not isinstance(reason, str) or len(reason) > 500:
        raise SchemaInvalid("reason must be a string <= 500 chars")
    for key in ("sl_distance", "risk_usd"):
        if raw.get(key) is not None:
            num = _num(raw[key])
            if num is None or num < 0:
                raise SchemaInvalid(f"{key} must be a finite number >= 0")
    return raw


def finalize_intent(raw: dict, *, strategy_id: str, strategy_version: str,
                    ctx_hash: str, now: datetime, ttl_s: float) -> dict:
    """Lengkapi OrderIntent sesuai kontrak PRD 4.1 (field identitas + expiry).

    client_order_id deterministik (idempotent per context): hash dari
    strategy_id + context_hash. created_at/expires_at UTC (PRD 4.3).
    """
    return {
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "signal_id": uuid.uuid4().hex,
        "client_order_id": hashlib.sha256(
            f"{strategy_id}|{ctx_hash}".encode("utf-8")).hexdigest()[:32],
        "symbol": raw["symbol"],
        "side": raw["side"],
        "order_type": "MARKET",
        "volume": float(raw["volume"]),
        "requested_price": None,
        "stop_loss": float(raw["sl"]),
        "take_profit": (float(raw["tp"]) if raw.get("tp") is not None else None),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=ttl_s)).isoformat(),
        "reason_code": "STRATEGY_SIGNAL",
        "reason": raw.get("reason") or "",
        "context_hash": ctx_hash,
        "sl_distance": (float(raw["sl_distance"])
                        if raw.get("sl_distance") is not None else None),
        "risk_usd": (float(raw["risk_usd"])
                     if raw.get("risk_usd") is not None else None),
    }


def validate_order_intent(intent: dict) -> None:
    """Validasi OrderIntent final terhadap kontrak PRD 4.1. Raise SchemaInvalid."""
    mandatory = (
        "strategy_id", "strategy_version", "signal_id", "client_order_id",
        "symbol", "side", "order_type", "volume", "stop_loss",
        "created_at", "expires_at", "reason_code", "context_hash",
    )
    missing = [k for k in mandatory if intent.get(k) is None]
    if missing:
        raise SchemaInvalid(f"OrderIntent missing mandatory fields: {missing}")
    if intent["side"] not in ("BUY", "SELL"):
        raise SchemaInvalid("side must be BUY|SELL")
    if intent["order_type"] != "MARKET":
        raise SchemaInvalid("order_type must be MARKET (runtime v2.2)")
    if not _finite(intent["volume"]) or intent["volume"] <= 0:
        raise SchemaInvalid("volume must be finite > 0")
    if not _finite(intent["stop_loss"]) or intent["stop_loss"] <= 0:
        raise SchemaInvalid("stop_loss must be finite > 0 (PRD 4.1)")
    if intent.get("take_profit") is not None:
        if not _finite(intent["take_profit"]) or intent["take_profit"] <= 0:
            raise SchemaInvalid("take_profit must be finite > 0")
    for key in ("created_at", "expires_at"):
        if not isinstance(intent[key], str):
            raise SchemaInvalid(f"{key} must be ISO8601 string")
    try:
        created = datetime.fromisoformat(intent["created_at"])
        expires = datetime.fromisoformat(intent["expires_at"])
    except ValueError as exc:
        raise SchemaInvalid(f"bad timestamp: {exc}") from exc
    if expires <= created:
        raise SchemaInvalid("expires_at must be after created_at (PRD 4.1)")


# ── State DB: lifecycle, breaker, events, signals ───────────────────────────
BREAKER_DEFAULTS: dict = {
    "state": "CLOSED",           # CLOSED | OPEN | HALF_OPEN
    "consecutive_errors": 0,
    "opened_at": None,
    "last_error": None,
}


@dataclass
class SupervisedDecision:
    """Hasil satu siklus decide() ter-supervisi."""

    strategy_id: str
    status: str
    intent: dict | None = None        # OrderIntent tervalidasi (PRD 4.1)
    rejected: bool = False
    reason: str | None = None
    reason_code: str | None = None
    breaker: dict = field(default_factory=dict)
    signal_id: str | None = None

    @property
    def ok(self) -> bool:
        return not self.rejected


def _parse_breaker(raw) -> dict:
    breaker = dict(BREAKER_DEFAULTS)
    if isinstance(raw, dict):
        for key in breaker:
            if raw.get(key) is not None:
                breaker[key] = raw[key]
    breaker["consecutive_errors"] = int(breaker["consecutive_errors"])
    return breaker


async def _ensure_strategy_row(conn, *, strategy_id: str,
                               strategy_version: str,
                               seed_status: str = "DRAFT") -> None:
    """Daftarkan strategi bila belum ada (seed status: legacy import PAPER,
    strategi baru DRAFT). Tidak pernah menimpa status yang sudah ada."""
    if seed_status not in LIFECYCLE_STATUSES:
        raise LifecycleError(f"invalid seed status {seed_status!r}")
    enabled = seed_status in ACTIVE_STATUSES
    await conn.execute(
        """
        INSERT INTO strategies (strategy_id, name, status, environment,
                                config, current_version, enabled)
        VALUES (%s, %s, %s, 'dev', '{}'::jsonb, %s, %s)
        ON CONFLICT (strategy_id) DO NOTHING
        """,
        (strategy_id, strategy_id, seed_status, strategy_version, enabled),
    )


async def get_strategy_state(conn, strategy_id: str) -> dict | None:
    row = await fetchone(
        conn,
        "SELECT strategy_id, status, enabled, current_version, circuit_breaker "
        "FROM strategies WHERE strategy_id = %s",
        (strategy_id,),
    )
    return dict(row) if row else None


async def record_event(conn, strategy_id: str, event_type: str, message: str,
                       *, severity: str = "INFO", details: dict | None = None,
                       correlation_id: str | None = None) -> None:
    """Catat keputusan/crash supervisor ke system_events (PRD 5.2, append-only)."""
    await conn.execute(
        """
        INSERT INTO system_events (event_type, severity, source, actor,
                                   message, details, correlation_id)
        VALUES (%s, %s, 'supervisor', %s, %s, %s, %s)
        """,
        (event_type, severity, strategy_id, message,
         json.dumps(details or {}, default=str), correlation_id),
    )


async def _write_signal(conn, *, strategy_id: str, strategy_version: str,
                        symbol: str, timeframe: str, side: str | None,
                        intent: dict | None, reason: str, source: str,
                        status: str, reject_reason: str | None = None) -> str | None:
    """Catat keluaran decide() tervalidasi ke signals (PRD 5.2/9.2)."""
    signal_id = (intent or {}).get("signal_id") or uuid.uuid4().hex
    await conn.execute(
        """
        INSERT INTO signals (strategy_id, strategy_version, symbol, timeframe,
                             side, order_intent, reason, source, status,
                             reject_reason)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (strategy_id, strategy_version, symbol, timeframe, side,
         json.dumps(intent, default=str) if intent else None, reason, source,
         status, reject_reason),
    )
    return signal_id


async def transition_strategy(conn, strategy_id: str, target: str, *,
                              actor: str, reason: str = "",
                              actor_role: str = "system") -> dict:
    """Transisi lifecycle strategi (PRD 5.3) + event append-only.

    actor_role: 'owner' | 'workflow' -> boleh owner-only transitions;
    'system' -> hanya AUTO_TRANSITIONS (fault path supervisor).
    """
    if target not in LIFECYCLE_STATUSES:
        raise LifecycleError(f"unknown status {target!r}")
    async with conn.transaction():
        row = await fetchone(
            conn, "SELECT status FROM strategies WHERE strategy_id = %s FOR UPDATE",
            (strategy_id,),
        )
        if row is None:
            raise LifecycleError(f"strategy {strategy_id!r} not registered")
        source = row["status"]
        if target not in ALLOWED_LIFECYCLE.get(source, set()):
            raise LifecycleError(
                f"illegal transition {source} -> {target} (PRD 5.3)")
        if (source, target) in OWNER_ONLY_TRANSITIONS and actor_role not in (
                "owner", "workflow"):
            raise LifecycleError(
                f"transition {source} -> {target} butuh owner/release workflow "
                f"(actor_role={actor_role!r})")
        if (source, target) in AUTO_TRANSITIONS and actor_role == "system":
            pass  # jalur fault supervisor
        # `enabled` = flag eksplisit owner (PRD 5.2: restart tidak auto-enable).
        # Supervisor TIDAK pernah men-enable: hanya mematikan saat DISABLED/
        # ARCHIVED; transisi lain tidak mengubah flag.
        if target in ("DISABLED", "ARCHIVED"):
            await conn.execute(
                """
                UPDATE strategies SET status = %s, enabled = false, updated_at = now()
                WHERE strategy_id = %s
                """,
                (target, strategy_id),
            )
        else:
            await conn.execute(
                """
                UPDATE strategies SET status = %s, updated_at = now()
                WHERE strategy_id = %s
                """,
                (target, strategy_id),
            )
        await record_event(
            conn, strategy_id, "STRATEGY_STATUS",
            f"lifecycle {source} -> {target}" + (f": {reason}" if reason else ""),
            severity="WARN" if target in ("DEGRADED", "DISABLED") else "INFO",
            details={"from": source, "to": target, "actor": actor,
                     "actor_role": actor_role, "reason": reason},
        )
    return {"strategy_id": strategy_id, "from": source, "to": target}


# ── Circuit breaker + jalur decide() ────────────────────────────────────────
async def _persist_breaker(conn, strategy_id: str, breaker: dict) -> None:
    await conn.execute(
        """
        UPDATE strategies SET circuit_breaker = %s, updated_at = now()
        WHERE strategy_id = %s
        """,
        (json.dumps(breaker, default=str), strategy_id),
    )


async def _register_failure(conn, *, strategy_id: str, state: dict,
                            breaker: dict, fault: StrategyFault,
                            cfg: dict, symbol: str, timeframe: str,
                            source: str, ctx_hash: str | None) -> SupervisedDecision:
    """Catat fault: breaker++, signal REJECTED, system_events, dan eskalasi
    lifecycle otomatis (aktif -> DEGRADED -> DISABLED) saat ambang terlampaui."""
    now = datetime.now(timezone.utc)
    breaker["consecutive_errors"] = int(breaker["consecutive_errors"]) + 1
    breaker["last_error"] = str(fault)[:500]
    was_half_open = breaker["state"] == "HALF_OPEN"
    escalated_to: str | None = None

    if was_half_open or breaker["consecutive_errors"] >= cfg["breaker_threshold"]:
        breaker["state"] = "OPEN"
        breaker["opened_at"] = now.isoformat()
        status = state["status"]
        if status == "DEGRADED":
            escalated_to = "DISABLED"
        elif status in ("SHADOW", "PAPER", "LIVE_APPROVED", "LIVE"):
            escalated_to = "DEGRADED"

    await _persist_breaker(conn, strategy_id, breaker)
    if escalated_to is not None:
        await transition_strategy(
            conn, strategy_id, escalated_to, actor="supervisor:breaker",
            reason=f"circuit breaker: {fault}", actor_role="system")
    signal_id = await _write_signal(
        conn, strategy_id=strategy_id,
        strategy_version=state.get("current_version") or "",
        symbol=symbol, timeframe=timeframe, side=None, intent=None,
        reason=f"rejected: {fault}", source=source, status="REJECTED",
        reject_reason=fault.reason_code)
    await record_event(
        conn, strategy_id, "STRATEGY_FAULT",
        f"fault rejected: {fault}",
        severity="CRITICAL" if escalated_to else "WARN",
        details={"reason_code": fault.reason_code,
                 "consecutive_errors": breaker["consecutive_errors"],
                 "breaker_state": breaker["state"],
                 "escalated_to": escalated_to,
                 "context_hash": ctx_hash},
    )
    return SupervisedDecision(
        strategy_id=strategy_id, status=state["status"], intent=None,
        rejected=True, reason=str(fault), reason_code=fault.reason_code,
        breaker=dict(breaker), signal_id=signal_id,
    )


async def decide(conn, *, strategy_id: str, strategy_version: str,
                 module: str, context: dict, params: dict, symbol: str,
                 timeframe: str, source: str = "PAPER",
                 settings: dict | None = None, seed_status: str = "DRAFT",
                 timeout_s: float | None = None,
                 module_dir: str = API_DIR) -> SupervisedDecision:
    """Jalankan satu decide() strategi di sandbox terisolasi (PRD v2.2 §5).

    Urutan: status gate -> breaker gate -> subprocess sandbox -> validasi
    schema -> finalize OrderIntent (PRD 4.1) -> signal EMITTED. Setiap
    kegagalan dicatat dan dihitung circuit breaker; strategi lain tidak
    terpengaruh (crash terjadi di subprocess, error di sini ditangkap caller).
    """
    cfg = load_config(settings)
    wall_s = float(timeout_s or cfg["wall_timeout_s"])
    await _ensure_strategy_row(conn, strategy_id=strategy_id,
                               strategy_version=strategy_version,
                               seed_status=seed_status)
    state = await get_strategy_state(conn, strategy_id)
    assert state is not None
    status = state["status"]
    breaker = _parse_breaker(state.get("circuit_breaker"))
    now = datetime.now(timezone.utc)
    ctx_hash = context_hash(context)

    # 1. Status gate: hanya strategi aktif yang boleh menghasilkan sinyal.
    #    Steady-state (bukan keputusan per-call): tanpa baris signal/event
    #    agar tabel tidak ter-spam; status terlihat via lifecycle.
    if status not in ACTIVE_STATUSES:
        return SupervisedDecision(
            strategy_id=strategy_id, status=status, intent=None, rejected=True,
            reason=f"status {status} bukan strategi aktif (PRD 5.3)",
            reason_code="STATUS_INACTIVE", breaker=breaker)

    # 2. Breaker gate: OPEN -> tolak cepat tanpa spawn; cooldown lewat ->
    #    HALF_OPEN (satu probe diizinkan).
    if breaker["state"] == "OPEN":
        opened_at = breaker.get("opened_at")
        elapsed = None
        if opened_at:
            try:
                elapsed = (now - datetime.fromisoformat(opened_at)).total_seconds()
            except ValueError:
                elapsed = None
        if elapsed is not None and elapsed >= cfg["breaker_cooldown_s"]:
            breaker["state"] = "HALF_OPEN"
            await _persist_breaker(conn, strategy_id, breaker)
            await record_event(
                conn, strategy_id, "CIRCUIT_BREAKER",
                "cooldown terlampaui; probe HALF_OPEN diizinkan",
                severity="INFO", details={"state": "HALF_OPEN"})
        else:
            # Throttle steady-state: tanpa baris per-call (state breaker
            # terlihat di lifecycle + system_events saat transisi).
            return SupervisedDecision(
                strategy_id=strategy_id, status=status, intent=None,
                rejected=True, reason="circuit breaker OPEN",
                reason_code="BREAKER_OPEN", breaker=breaker)

    # 3. Sandbox subprocess: crash/timeout strategi tidak menyentuh proses ini.
    try:
        resp = await run_sandbox(
            module=module, context=context, params=params,
            wall_timeout_s=wall_s, mem_limit_mb=int(cfg["mem_limit_mb"]),
            cpu_limit_s=int(cfg["cpu_limit_s"]), module_dir=module_dir)
        if not resp.get("ok"):
            raise SandboxProtocol(str(resp.get("error") or "unknown child error"))
        raw = resp.get("intent")
        if raw is not None:
            validate_raw_output(raw, strategy_id=strategy_id, symbol=symbol)
    except StrategyFault as fault:
        return await _register_failure(
            conn, strategy_id=strategy_id, state=state, breaker=breaker,
            fault=fault, cfg=cfg, symbol=symbol, timeframe=timeframe,
            source=source, ctx_hash=ctx_hash)

    # 4. Sukses: reset breaker (probe HALF_OPEN -> CLOSED = recovery).
    if breaker["state"] != "CLOSED" or breaker["consecutive_errors"]:
        await record_event(
            conn, strategy_id, "CIRCUIT_BREAKER",
            "probe sukses; breaker kembali CLOSED",
            severity="INFO",
            details={"was": breaker["state"],
                     "consecutive_errors": breaker["consecutive_errors"]})
    breaker.update({"state": "CLOSED", "consecutive_errors": 0,
                    "opened_at": None, "last_error": None})
    await _persist_breaker(conn, strategy_id, breaker)

    # 5. None = tidak ada entry; output valid tanpa order. Bukan sinyal:
    #    tidak menulis baris (menjaga tabel signals bermakna).
    if raw is None:
        return SupervisedDecision(
            strategy_id=strategy_id, status=status, intent=None,
            rejected=False, breaker=breaker)

    # 6. Finalize + validasi kontrak penuh PRD 4.1.
    intent = finalize_intent(raw, strategy_id=strategy_id,
                             strategy_version=state.get("current_version")
                             or strategy_version,
                             ctx_hash=ctx_hash, now=now,
                             ttl_s=float(cfg["intent_ttl_s"]))
    validate_order_intent(intent)
    signal_id = await _write_signal(
        conn, strategy_id=strategy_id,
        strategy_version=state.get("current_version") or strategy_version,
        symbol=symbol, timeframe=timeframe, side=intent["side"],
        intent=intent, reason=intent["reason"] or "signal", source=source,
        status="EMITTED")
    return SupervisedDecision(
        strategy_id=strategy_id, status=status, intent=intent,
        rejected=False, breaker=breaker, signal_id=signal_id)


# ── Read helpers untuk API ──────────────────────────────────────────────────
async def supervisor_states(conn) -> list[dict]:
    """Semua strategi terdaftar: lifecycle + breaker + enabled (UI monitoring)."""
    rows = await fetchone(
        conn,
        "SELECT COALESCE(json_agg(t ORDER BY t.strategy_id), '[]'::json) AS data "
        "FROM (SELECT strategy_id, name, status, enabled, current_version, "
        "circuit_breaker, updated_at FROM strategies) t",
    )
    states = (rows or {}).get("data") or []
    for item in states:
        item["circuit_breaker"] = _parse_breaker(item.get("circuit_breaker"))
    return states


async def recent_events(conn, strategy_id: str, limit: int = 20) -> list[dict]:
    """Event supervisor terbaru untuk satu strategi (crash, breaker, status)."""
    rows = await fetchone(
        conn,
        """
        SELECT COALESCE(json_agg(t), '[]'::json) AS data FROM (
            SELECT event_type, severity, message, details, created_at
            FROM system_events
            WHERE source = 'supervisor' AND actor = %s
            ORDER BY id DESC LIMIT %s
        ) t
        """,
        (strategy_id, limit),
    )
    return (rows or {}).get("data") or []



