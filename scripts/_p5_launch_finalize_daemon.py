#!/usr/bin/env python3
"""Launch finalizer daemon run latensi P5 sebagai daemon double-fork."""
import os

TARGET = "/home/tekka/fund2/scripts/_p5_overnight_finalize_daemon.py"
PY = "/home/tekka/fund2/api/.venv/bin/python"

pid = os.fork()
if pid == 0:
    os.setsid()
    pid2 = os.fork()
    if pid2 == 0:
        os.close(0)
        os.close(1)
        os.close(2)
        os.open("/dev/null", os.O_RDONLY)
        os.open("/dev/null", os.O_WRONLY)
        os.open("/dev/null", os.O_WRONLY)
        os.execv(PY, [PY, TARGET])
        os._exit(127)
    os._exit(0)
os.waitpid(pid, 0)
print("finalizer daemon launched")
