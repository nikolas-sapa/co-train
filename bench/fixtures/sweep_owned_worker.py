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


def _write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value))
    temporary.replace(path)


def _wait(path, until):
    while not path.exists():
        if time.monotonic() >= until:
            raise RuntimeError(f"fixture readiness missing: {path.name}")
        time.sleep(0.001)
    return json.loads(path.read_text())


def main():
    root, mode, bindir, result, startup_delay = sys.argv[1:6]
    root, bindir = Path(root), Path(bindir)
    control = root / f"ready-{bindir.name}"
    control.mkdir(exist_ok=True)
    identity = {"pid": os.getpid(), "pgid": os.getpgrp(),
                "sid": os.getsid(0), "owner": str(root)}
    _write(root / f"group-{os.getpid()}.json", identity)
    until = time.monotonic() + 5.0
    time.sleep(float(startup_delay))
    if mode in ("leader-exit", "finite"):
        # Real SQL/interpreter setup belongs to the <=5s readiness phase, not
        # the later leader-exit or task-binding trigger. No fabricated result.
        remaining = until - time.monotonic()
        assert remaining > 0, "fixture startup exhausted readiness budget"
        status = (subprocess.run(sys.argv[6:], check=False, timeout=remaining).returncode
                  if len(sys.argv) > 6 else 0)
    if mode == "finite":
        _write(control / "ready.json", [identity])
        _wait(control / "release.json", until)
        _write(control / "released.json", [identity])
        _wait(control / "go.json", until)
        return status
    if mode == "grandchild":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        _write(control / "child-ready.json", identity)
        released_at = _wait(control / "release.json", until)
        _write(control / "child-released.json", identity)
        _wait(control / "go.json", until)
        # Late effects are relative to release, never interpreter startup.
        time.sleep(max(0.0, released_at + 0.80 - time.monotonic()))
        (root / "late-marker").write_text("descendant executed after return")
        return 0
    if mode in ("slow", "binding", "leader-exit", "interrupt"):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        child = subprocess.Popen(
            [sys.executable, "-B", __file__, str(root), "grandchild",
             str(bindir), "-", startup_delay],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        # No published pair without a real descendant execution acknowledgment.
        acknowledged = _wait(control / "child-ready.json", until)
        assert acknowledged["pid"] == child.pid
        assert acknowledged["pgid"] == acknowledged["sid"] == os.getpid()
        _write(root / "pids.json", [os.getpid(), child.pid])
        _write(control / "ready.json", [identity, acknowledged])
        released_at = _wait(control / "release.json", until)
        assert _wait(control / "child-released.json", until) == acknowledged
        _write(control / "released.json", [identity, acknowledged])
        _wait(control / "go.json", until)
        if mode == "leader-exit":
            _write(control / "trigger.json", time.monotonic())
            return status
        if mode == "interrupt":
            # Interrupt only our supervising probe, after BOTH real processes
            # execute. The outer independent supervisor is a different process.
            _write(control / "trigger.json", time.monotonic())
            os.kill(os.getppid(), signal.SIGINT)
        if mode in ("slow", "binding", "interrupt"):
            time.sleep(max(0.0, released_at + 0.55 - time.monotonic()))
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
    status = (subprocess.run(sys.argv[6:], check=False, timeout=1.0).returncode
              if len(sys.argv) > 6 else 0)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
