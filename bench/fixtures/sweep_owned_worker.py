"""Finite adversarial worker used only by sweep regression probes.

No SQL, pickle or arbitrary callable enters argv. Any trailing argv is the real
sweep's diagnostic child command, which this fixture runs without modification.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def main():
    root, mode, bindir, result = sys.argv[1:5]
    root, bindir = Path(root), Path(bindir)
    (root / f"group-{os.getpid()}.json").write_text(json.dumps(
        {"pid": os.getpid(), "pgid": os.getpgrp()}))
    if mode == "grandchild":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        (root / "grandchild-ready").write_text(str(os.getpid()))
        time.sleep(0.80)
        (root / "late-marker").write_text("descendant executed after return")
        return 0
    if mode in ("slow", "binding", "leader-exit", "interrupt"):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        child = subprocess.Popen(
            [sys.executable, "-B", __file__, str(root), "grandchild",
             str(bindir), "-"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        # Readiness is evidence the descendant executed, not just a Popen PID.
        until = time.monotonic() + 0.3
        while not (root / "grandchild-ready").exists() and time.monotonic() < until:
            time.sleep(0.001)
        (root / "pids.json").write_text(json.dumps([os.getpid(), child.pid]))
        if mode == "interrupt":
            # Interrupt only our supervising probe, after BOTH real processes
            # execute. The outer independent supervisor is a different process.
            os.kill(os.getppid(), signal.SIGINT)
        if mode in ("slow", "binding", "interrupt"):
            time.sleep(0.55)
            # A late wrapper replacement is an actual file side effect. Never
            # recreate a parent-deleted private directory.
            if bindir.is_dir():
                from ptc.sql_arms import install_wrapper
                install_wrapper(bindir, str(root / "task-17.sqlite"), 10)
    if mode == "exit7":
        return 7
    if mode == "absent":
        return 0
    if mode == "malformed":
        if result != "-":
            Path(result).write_text("{not-json")
        return 0
    if len(sys.argv) > 5:
        return subprocess.run(sys.argv[5:], check=False, timeout=1.0).returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
