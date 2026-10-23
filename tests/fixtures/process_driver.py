"""Independent supervisor target; reports results, never cleans up for tests."""

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

repo, directory, target, mode, exception_name, code = sys.argv[1:]
root = Path(directory)
sys.path.insert(0, repo)
payload = Path(__file__).with_name("process_payload.py")
suite_timeout = 1.0 if mode == "normal" else 0.15
if target == "helper":
    import process_watchdog as module
else:
    spec = importlib.util.spec_from_file_location(
        "runner_under_test", Path(repo) / target / "mutate.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SUITE_TIMEOUT = suite_timeout
    module.PY = sys.executable

real_popen = subprocess.Popen
processes = []


class FixturePopen(real_popen):
    def __init__(self, args, **kwargs):
        argv = [sys.executable, str(payload), mode, directory, code]
        super().__init__(argv, **kwargs)
        processes.append(self)
        self.injected = False
        self.wait_injected = False
        if mode != "normal":
            deadline = time.monotonic() + 0.8
            while not (root / "grandchild.pid").exists() and time.monotonic() < deadline:
                time.sleep(0.005)
            if not (root / "grandchild.pid").exists():
                raise RuntimeError("fixture did not start before the test deadline")

    def communicate(self, *args, **kwargs):
        if exception_name in {"KeyboardInterrupt", "SystemExit"} and not self.injected:
            self.injected = True
            if exception_name == "KeyboardInterrupt":
                raise KeyboardInterrupt("fixture interrupt")
            raise SystemExit(7)
        return super().communicate(*args, **kwargs)

    def wait(self, *args, **kwargs):
        if exception_name == "wait-interrupt" and not self.wait_injected:
            self.wait_injected = True
            raise KeyboardInterrupt("fixture TERM-wait interrupt")
        return super().wait(*args, **kwargs)


subprocess.Popen = FixturePopen
started = time.monotonic()
try:
    if target == "helper":
        result = module.run_bounded(["fixture"], cwd=root, timeout=suite_timeout)
    elif target == "ptc":
        result = module.run(root, "ptc")
    else:
        result = module.run(root)
    report = {
        "returncode": result.returncode, "stdout": result.stdout,
        "stderr": result.stderr,
    }
except BaseException as exc:
    report = {
        "exception": type(exc).__name__, "code": getattr(exc, "code", None),
        "stdout": getattr(exc, "stdout", None),
        "stderr": getattr(exc, "stderr", None),
        "notes": getattr(exc, "__notes__", []),
    }
report["elapsed"] = time.monotonic() - started
report["leader_reaped"] = all(process.returncode is not None for process in processes)
report["streams_closed"] = all(
    process.stdout.closed and process.stderr.closed for process in processes
)
(root / "report.json").write_text(json.dumps(report))
