#!/usr/bin/env python3
"""Launch supervisor latensi P5 sebagai daemon double-fork (lepas dari sesi).

Supervisor dan driver harus bertahan bila sesi Hermes worker crash, karena
run latensi butuh ~2-3 jam. Double-fork + setsid menggantung daemon ke init.
"""
import os
import sys

SUPERVISOR = "/home/tekka/fund2/scripts/_p5_latency_supervisor.sh"

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
        os.execv("/bin/bash", ["bash", SUPERVISOR])
        os._exit(127)
    os._exit(0)
os.waitpid(pid, 0)
print("daemon launched")
