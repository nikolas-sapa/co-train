"""Finite local workload for process ownership checks, never a training job."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

mode, directory, code = sys.argv[1:]
root = Path(directory)
if mode == "normal":
    print("FIXTURE_STDOUT", flush=True)
    print("FIXTURE_STDERR", file=sys.stderr, flush=True)
    raise SystemExit(int(code))

if mode == "grandchild":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    (root / "grandchild.pid").write_text(str(os.getpid()))
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        (root / "heartbeat").write_text(str(time.monotonic_ns()))
        time.sleep(0.02)
    raise SystemExit(0)

if mode == "ignore-term":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
(root / "leader.pid").write_text(str(os.getpid()))
options = {}
if mode == "closed-pipes":
    options.update(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
if mode == "escaped-pipe":
    options["start_new_session"] = True
subprocess.Popen(
    [sys.executable, __file__, "grandchild", directory, "0"], **options,
)
deadline = time.monotonic() + 1
while not (root / "grandchild.pid").exists() and time.monotonic() < deadline:
    time.sleep(0.005)
if not (root / "grandchild.pid").exists():
    raise RuntimeError("fixture grandchild did not become ready")
print("FIXTURE_STDOUT", flush=True)
print("FIXTURE_STDERR", file=sys.stderr, flush=True)
if mode in {"pipe-held", "closed-pipes", "escaped-pipe"}:
    raise SystemExit(0)
deadline = time.monotonic() + 5
while time.monotonic() < deadline:
    time.sleep(0.02)
