"""One in-memory timeout-preflight bypass, not a production selector."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
import pytest
from ptc import harness

path = ROOT / "ptc/harness.py"
before = hashlib.sha256(path.read_bytes()).hexdigest()
original = harness._validate_program_runner_timeout
hits = []


def bypass(runner, timeout):
    hits.append(timeout)


output = io.StringIO()
try:
    harness._validate_program_runner_timeout = bypass
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        status = pytest.main([
            "-p", "no:cacheprovider", "-q",
            str(ROOT / "ptc/test_owned_program_timeout.py")
            + "::test_preflight_exception_is_fatal_not_tool_feedback[ValueError]",
        ])
finally:
    harness._validate_program_runner_timeout = original
message = "intended pre-model refusal dispatched a policy request"
assert status == 1 and len(hits) == 1 and message in output.getvalue(), output.getvalue()
assert hashlib.sha256(path.read_bytes()).hexdigest() == before
print(json.dumps({
    "pytest_exit": int(status),
    "bypass_hits": len(hits),
    "intended_assertion": message,
    "source_unchanged": True,
    "production_helper_restored": harness._validate_program_runner_timeout is original,
}))
