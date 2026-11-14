#!/usr/bin/env python3
"""Warm up the fingers-demo herdr session deterministically.

Creates session `fingers-demo`, waits for the user's shell prompt, dismisses
any init dialog, drops into a clean zsh, seeds a known-safe clipboard, and
prints the demo content. Leaves the session running for the vhs tape.
"""

import fcntl
import os
import pty
import re
import select
import struct
import sys
import termios
import time

SESSION = "fingers-demo"
env = {k: v for k, v in os.environ.items() if not k.startswith("HERDR_")}

pid, fd = pty.fork()
if pid == 0:
    os.execvpe("herdr", ["herdr", "--session", SESSION], env)
    os._exit(1)
fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 110, 0, 0))

collected = b""


def read_until(markers, timeout, settle=1.2):
    """Read until one of `markers` (strs) appears, then let output settle."""
    global collected
    buf = b""
    deadline = time.time() + timeout
    hit = False
    while time.time() < deadline:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            if not hit and any(m.encode() in buf for m in markers):
                hit = True
                deadline = min(deadline, time.time() + settle)
    collected += buf
    return buf


def send(line, wait=0.6):
    for chunk_start in range(0, len(line), 16):
        os.write(fd, line[chunk_start : chunk_start + 16].encode())
        time.sleep(0.05)
    os.write(fd, b"\r")
    time.sleep(wait)


# 1) Attach; the user's powerlevel10k may show an instant-prompt dialog.
read_until([">"], 30)

# 2) Dismiss the dialog if present; a plain prompt redraws either way.
send("", wait=1.0)
read_until([">"], 10)

# 3) Clean shell (prompt marker becomes '%').
send("/bin/zsh -f", wait=0.8)
read_until(["%"], 10)

# 4) Nice prompt, clean screen, safe clipboard, demo content.
send("export PS1='%F{063}\u276f%f '", wait=0.5)
send("printf 'demo' | pbcopy", wait=0.6)
send("clear", wait=0.6)
send("python3 demo/demo-content.py", wait=1.8)
read_until(["PROJ-1042"], 15, settle=1.5)

plain = re.sub(
    r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07\x1b]*(\x07|\x1b\\)",
    "",
    collected.decode("utf-8", "replace"),
)
checks = ["docs", "PROJ-1042", "herdr.dev", "next steps", "traceback"]
missing = [c for c in checks if c not in plain]
if missing:
    print(f"SETUP INCOMPLETE, missing: {missing}", file=sys.stderr)
    print(plain[-600:], file=sys.stderr)
    sys.exit(1)
print("session warmed OK")
