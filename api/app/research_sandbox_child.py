"""Sandbox child: komputasi backtest riset Hermes (PRD v2.2 §12.4).

Dijalankan parent (app/research_sandbox.py) sebagai:
    python -I -E -B app/research_sandbox_child.py

Protokol (satu baris JSON per arah, UTF-8):
    stdin  : {"module_dir": "<api dir>", "strategy_module": "strategies.x",
              "symbol", "tf_seconds", "candles", "params", "spread",
              "slippage", "equity0", "context_bars", "regime_filter",
              "contract_size"}
    stdout : {"ok": true, "metrics": {...}, "sandbox": {...}}
           | {"ok": false, "error": "<pesan>", "sandbox": {...}}

Isolasi dijelaskan di app/research_sandbox.py. Child TIDAK punya akses
DB (env kosong), jaringan (socket + Landlock), atau penulisan file
(RLIMIT_FSIZE=0). Import dilakukan SEBELUM Landlock; komputasi SETELAH.
"""
from __future__ import annotations

import json
import os
import sys
from typing import NoReturn

MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def _fail(message: str) -> NoReturn:
    body = json.dumps({"ok": False, "error": message}, ensure_ascii=False)
    sys.stdout.buffer.write(body.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()
    sys.exit(0)


# ── netralisasi network (language level) ────────────────────────────────────
def _block_socket() -> None:
    import socket

    def _blocked(*_a, **_k):
        raise OSError("sandbox: network access is blocked (PRD v2.2 §12.4)")

    class _BlockedSocket(socket.socket):
        def __init__(self, family=-1, type=-1, proto=-1, fileno=None):
            raise OSError("sandbox: socket() is blocked (PRD v2.2 §12.4)")

    socket.socket = _BlockedSocket
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked
    socket.gethostbyname = _blocked
    socket.gethostbyname_ex = _blocked
    socket.gethostbyaddr = _blocked
    socket.socketpair = _blocked
    socket.fromfd = _blocked


# ── Landlock (kernel level, best-effort) ────────────────────────────────────
_LL_CREATE_RULESET = 444
_LL_RESTRICT_SELF = 446
_PR_SET_NO_NEW_PRIVS = 38
_LL_FS_ALL = (1 << 15) - 1
_LL_NET_BIND_TCP = 1 << 0
_LL_NET_CONNECT_TCP = 1 << 1


def _enforce_landlock() -> str:
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

        abi = _sys(_LL_CREATE_RULESET, None, 0, 1)
        handled_net = (_LL_NET_BIND_TCP | _LL_NET_CONNECT_TCP) if abi >= 4 else 0
        attr = _RulesetAttr(handled_access_fs=_LL_FS_ALL,
                            handled_access_net=handled_net)
        fd = _sys(_LL_CREATE_RULESET, ctypes.byref(attr), ctypes.sizeof(attr), 0)
        if libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "prctl(NO_NEW_PRIVS) failed")
        _sys(_LL_RESTRICT_SELF, fd, 0)
        return f"landlock enforced (abi={abi}, fs=deny-all, net={'deny-tcp' if handled_net else 'n/a'})"
    except Exception as exc:
        return f"landlock unavailable ({exc}); fallback socket-patch+rlimits only"


def _parse_candles(raw: list[dict]) -> list[dict]:
    from datetime import datetime
    out = []
    for c in raw:
        out.append({
            "ts": datetime.fromisoformat(c["ts"]),
            "open": float(c["open"]), "high": float(c["high"]),
            "low": float(c["low"]), "close": float(c["close"]),
        })
    return out


def main() -> None:
    raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        _fail("request too large")
    try:
        request = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"request tidak valid: {exc}")

    module_dir = request.get("module_dir") or ""
    strategy_module = request.get("strategy_module") or ""
    if not module_dir or not os.path.isdir(module_dir):
        _fail("module_dir tidak valid")
    if not strategy_module or not strategy_module.replace(".", "").isidentifier():
        _fail("strategy_module tidak valid")
    candles = _parse_candles(request.get("candles") or [])
    if len(candles) < 2:
        _fail("candle tidak cukup")

    _block_socket()
    sys.path.insert(0, module_dir)
    try:
        import importlib

        from paper.backtest import run_backtest

        mod = importlib.import_module(strategy_module)
        params_raw = dict(request.get("params") or {})
        params_cls = getattr(mod, "StrategyParams")
        known = set(params_cls.__dataclass_fields__)
        params = params_cls(**{k: v for k, v in params_raw.items() if k in known})
        kwargs = {}
        if request.get("spread") is not None:
            kwargs["spread"] = float(request["spread"])
        if request.get("slippage") is not None:
            kwargs["slippage"] = float(request["slippage"])
        result = run_backtest(
            candles,
            tf_seconds=int(request["tf_seconds"]),
            equity0=float(request.get("equity0") or 10000.0),
            params=params,
            **kwargs,
            strategy=mod,
            symbol=str(request["symbol"]),
            contract_size=float(request.get("contract_size") or 100.0),
            context_bars=int(request.get("context_bars") or 0),
            regime_filter=bool(request.get("regime_filter")),
        )
    except Exception as exc:
        _fail(f"{type(exc).__name__}: {exc}")

    note = _enforce_landlock()   # setelah import, sebelum output
    result.pop("trades_detail", None)   # jaga ukuran output
    if len(result.get("curve") or []) > 5000:
        result.pop("curve", None)
    body = json.dumps({"ok": True, "metrics": result,
                       "sandbox": {"isolation": note}},
                      default=str, ensure_ascii=False)
    if len(body) > MAX_RESPONSE_BYTES:
        _fail("response too large")
    sys.stdout.buffer.write(body.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
