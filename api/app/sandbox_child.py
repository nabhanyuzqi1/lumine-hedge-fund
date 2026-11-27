"""Sandbox child: eksekusi decide() strategi di subprocess terisolasi (PRD v2.2 §5).

Dijalankan supervisor (app/supervisor.py) sebagai:

    python -I -E -B app/sandbox_child.py

Protokol (satu baris JSON per arah, UTF-8):

    stdin  : {"module": "strategies.london_breakout", "module_dir": "<dir>",
              "context": {...}, "params": {...}}
    stdout : {"ok": true, "intent": {...}|null}
           | {"ok": false, "error": "<tipe>: <pesan>"}

Lapisan isolasi (defence in depth, tanpa root):

1. `python -I -E` + env kosong dari parent : tidak ada env secret (DB/broker).
2. closerange fd 3..N di preexec          : tidak ada fd warisan (koneksi DB).
3. rlimits (parent): RLIMIT_AS (memory), RLIMIT_CPU, RLIMIT_FSIZE=0 (anti
   tulis file), RLIMIT_CORE=0.
4. cwd sandbox kosong dari parent; stdout HANYA untuk satu baris hasil.
5. Modul socket dinetralkan SEBELUM import strategi: socket.create_connection,
   socket.socket, getaddrinfo, dst. semuanya raise OSError.
6. Landlock (deny-all FS + TCP bind/connect) di-enforce SETELAH import
   selesai, TEPAT sebelum decide(): strategi tidak bisa membaca file secret,
   menulis, men-exec binary, atau membuka koneksi TCP. Best-effort: bila
   kernel tidak mendukung, lapisan 1-5 tetap aktif dan stderr diberi catatan.
7. Wall-clock + killpg oleh parent; SIGXCPU/SIGXFSZ/SIGKILL dari rlimits.

Strategi adalah modul murni: decide(context, params) -> OrderIntent | None.
Modul yang melakukan I/O, jam, atau RNG melanggar kontrak strategies/README.md
dan akan gagal di sini (itu perilaku yang benar: fault -> reject).
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import NoReturn

MAX_REQUEST_BYTES = 8 * 1024 * 1024   # context candle 300 bar ~ puluhan KB
MAX_RESPONSE_BYTES = 1 * 1024 * 1024

_MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
_DIR_RE = re.compile(r"^/")


def _fail(message: str) -> NoReturn:
    """Tulis error terstruktur lalu exit 0 (fault terkontrol, bukan crash)."""
    body = json.dumps({"ok": False, "error": message}, ensure_ascii=False)
    sys.stdout.buffer.write(body.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()
    sys.exit(0)


# ── 5. netralisasi network (language level) ────────────────────────────────
def _block_socket() -> None:
    import socket

    def _blocked(*_a, **_k):
        raise OSError("sandbox: network access is blocked (PRD v2.2 §5)")

    class _BlockedSocket(socket.socket):
        def __init__(self, family=-1, type=-1, proto=-1, fileno=None):
            raise OSError("sandbox: socket() is blocked (PRD v2.2 §5)")

    socket.socket = _BlockedSocket
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked
    socket.gethostbyname = _blocked
    socket.gethostbyname_ex = _blocked
    socket.gethostbyaddr = _blocked
    socket.socketpair = _blocked
    socket.fromfd = _blocked


# ── 6. Landlock (kernel level, best-effort) ────────────────────────────────
_LL_CREATE_RULESET = 444
_LL_RESTRICT_SELF = 446
_PR_SET_NO_NEW_PRIVS = 38

_LL_FS_ALL = (
    (1 << 0)   # EXECUTE
    | (1 << 1)  # WRITE_FILE
    | (1 << 2)  # READ_FILE
    | (1 << 3)  # READ_DIR
    | (1 << 4)  # REMOVE_DIR
    | (1 << 5)  # REMOVE_FILE
    | (1 << 6)  # MAKE_CHAR
    | (1 << 7)  # MAKE_DIR
    | (1 << 8)  # MAKE_REG
    | (1 << 9)  # MAKE_SOCK
    | (1 << 10)  # MAKE_FIFO
    | (1 << 11)  # MAKE_BLOCK
    | (1 << 12)  # MAKE_SYM
    | (1 << 13)  # REFER
    | (1 << 14)  # TRUNCATE
)
_LL_NET_BIND_TCP = 1 << 0
_LL_NET_CONNECT_TCP = 1 << 1


def _enforce_landlock() -> str:
    """Deny-all FS + TCP. Return keterangan untuk stderr (best-effort)."""
    import ctypes
    import ctypes.util

    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)

        class _RulesetAttr(ctypes.Structure):
            _fields_ = [("handled_access_fs", ctypes.c_uint64),
                        ("handled_access_net", ctypes.c_uint64)]

        def _sys(call, *args):
            ctypes.set_errno(0)
            res = libc.syscall(ctypes.c_long(call), *args)
            if res < 0:
                code = ctypes.get_errno()
                raise OSError(code, os.strerror(code))
            return res

        abi = _sys(_LL_CREATE_RULESET, None, 0, 1)  # LANDLOCK_CREATE_RULESET_VERSION
        handled_net = (_LL_NET_BIND_TCP | _LL_NET_CONNECT_TCP) if abi >= 4 else 0
        attr = _RulesetAttr(handled_access_fs=_LL_FS_ALL,
                            handled_access_net=handled_net)
        fd = _sys(_LL_CREATE_RULESET, ctypes.byref(attr), ctypes.sizeof(attr), 0)
        if libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "prctl(NO_NEW_PRIVS) failed")
        _sys(_LL_RESTRICT_SELF, fd, 0)
        return f"landlock enforced (abi={abi}, fs=deny-all, net={'deny-tcp' if handled_net else 'n/a'})"
    except Exception as exc:  # best-effort: lapisan 1-5 tetap aktif
        return f"landlock unavailable ({exc}); fallback socket-patch+rlimits only"


def _load_module(module: str, module_dir: str):
    import importlib

    sys.path.insert(0, module_dir)
    return importlib.import_module(module)


def _build_params(mod, params_raw: dict):
    """Rekonstruksi StrategyParams dataclass dari JSON (unknown keys dibuang)."""
    params_cls = getattr(mod, "StrategyParams", None)
    if params_cls is None or not hasattr(params_cls, "__dataclass_fields__"):
        return params_raw
    known = set(params_cls.__dataclass_fields__)
    return params_cls(**{k: v for k, v in params_raw.items() if k in known})


def _serialize(result):
    """None | dataclass | dict -> payload JSON-safe; selain itu malformed."""
    if result is None:
        return None
    if hasattr(result, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(result)
    if isinstance(result, dict):
        return dict(result)
    _fail(f"malformed output: decide() returned {type(result).__name__}, "
          "expected OrderIntent dataclass, dict, or None")


def main() -> None:
    raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        _fail("request too large")
    try:
        req = json.loads(raw)
    except Exception as exc:
        _fail(f"malformed request: {type(exc).__name__}: {exc}")
    if not isinstance(req, dict):
        _fail("malformed request: expected JSON object")

    module = str(req.get("module") or "")
    module_dir = str(req.get("module_dir") or "")
    if not _MODULE_RE.match(module):
        _fail(f"invalid module name: {module!r}")
    if not _DIR_RE.match(module_dir) or not os.path.isdir(module_dir):
        _fail(f"invalid module_dir: {module_dir!r}")

    # 5: socket mati sebelum kode strategi dimuat
    _block_socket()

    try:
        mod = _load_module(module, module_dir)
    except Exception as exc:
        _fail(f"import failed: {type(exc).__name__}: {exc}")

    context = req.get("context") or {}
    params_raw = req.get("params") or {}
    if not isinstance(context, dict) or not isinstance(params_raw, dict):
        _fail("malformed request: context/params must be objects")
    params = _build_params(mod, params_raw)

    # 6: kunci filesystem SETELAH semua import selesai, sebelum decide()
    note = _enforce_landlock()
    sys.stderr.write(f"[sandbox_child] {note}\n")
    sys.stderr.flush()

    try:
        result = mod.decide(context, params)
    except SystemExit as exc:
        _fail(f"decide called SystemExit({exc.code})")
    except BaseException as exc:  # termasuk KeyboardInterrupt-style exit
        _fail(f"decide failed: {type(exc).__name__}: {exc}")

    payload = _serialize(result)
    try:
        body = json.dumps({"ok": True, "intent": payload}, allow_nan=False,
                          ensure_ascii=False)
    except ValueError as exc:
        _fail(f"non-finite output (NaN/Inf): {exc}")
    encoded = body.encode("utf-8")
    if len(encoded) > MAX_RESPONSE_BYTES:
        _fail("response too large")
    sys.stdout.buffer.write(encoded + b"\n")
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
