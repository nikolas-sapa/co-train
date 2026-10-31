"""Finite, offline fidelity control for admitted database-record projection."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[4]
SOURCES = (REPO / "bench/prepare.py", REPO / "bench/test_validated_draw_databases.py")
GATE = "PROJECTED_DB_DIGEST_NOT_ADMITTED"
TARGET = (
    str(SOURCES[1])
    + "::test_projection_preserves_admitted_digest_and_original_denominator[shared]"
)


def _hashes():
    return {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in SOURCES}


class _Discard:
    def write(self, value):
        return len(value)

    def flush(self):
        pass

    def isatty(self):
        return False


def _worker(mode, temporary):
    sys.path.insert(0, str(REPO))
    import pytest
    from bench import prepare
    from bench import test_validated_draw_databases as tests

    before = _hashes()
    retained, counters, reports = [], [], []
    hits = 0
    original_load = prepare.load_validated_draw
    original_artifacts, original_sentries = tests._artifacts, tests._sentries

    def artifacts(*args, **kwargs):
        result = original_artifacts(*args, **kwargs)
        _, draw, draw_sha, supplement, supplement_sha = result
        retained.extend(((draw, draw_sha), (supplement, supplement_sha)))
        return result

    @contextmanager
    def sentries(*args, **kwargs):
        with original_sentries(*args, **kwargs) as observed:
            try:
                yield observed
            finally:
                counters.append(dict(observed))

    def load(*args, **kwargs):
        nonlocal hits
        result = original_load(*args, **kwargs)
        if mode == "negative":
            hits += 1
            first, *remaining = result.databases
            different = "0" * 64 if first.sha256 != "0" * 64 else "1" * 64
            return replace(result, databases=(
                replace(first, sha256=different), *remaining))
        return result

    class Report:
        def pytest_runtest_logreport(self, report):
            reports.append((report.when, report.outcome,
                            report.failed and GATE in report.longreprtext))

    with patch.object(tests, "_artifacts", artifacts), \
            patch.object(tests, "_sentries", sentries), \
            patch.object(prepare, "load_validated_draw", load), \
            redirect_stdout(_Discard()), redirect_stderr(_Discard()):
        code = pytest.main([
            "-p", "no:cacheprovider", "-q", "--basetemp",
            str(temporary / "pytest"), TARGET,
        ], plugins=[Report()])
    calls = [report for report in reports if report[0] == "call"]
    intended = mode == "negative"
    source_unchanged = before == _hashes()
    retained_unchanged = len(retained) == 2 and all(
        hashlib.sha256(path.read_bytes()).hexdigest() == digest
        for path, digest in retained)
    no_consumer_work = len(counters) == 1 and all(
        counters[0].get(key, 0) == 0
        for key in ("connects", "selects", "golds", "ex"))
    qualified = (
        code == (1 if intended else 0)
        and hits == (1 if intended else 0)
        and calls == [("call", "failed" if intended else "passed", intended)]
        and all(outcome == "passed" for when, outcome, _ in reports if when != "call")
        and source_unchanged and retained_unchanged and no_consumer_work
        and counters[0].get("loads") == 2
    )
    return {
        "mode": mode, "qualified": qualified, "pytest_exit": int(code),
        "substitution_hits": hits, "named_failure": bool(calls and calls[0][2]),
        "source_unchanged": source_unchanged, "retained_unchanged": retained_unchanged,
        "consumer_counters": counters, "source_sha256": before,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--worker", choices=("negative", "restored"))
    args = parser.parse_args()
    if not args.artifacts_dir.is_absolute():
        parser.error("--artifacts-dir must be absolute")
    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    if args.worker:
        with tempfile.TemporaryDirectory(
                prefix="projection-", dir=args.artifacts_dir) as directory:
            receipt = _worker(args.worker, Path(directory))
        print(json.dumps(receipt, sort_keys=True))
        return 0 if receipt["qualified"] else 1

    before, receipts = _hashes(), []
    for mode in ("negative", "restored"):
        # Only two fixed, direct finite children. No shell or process-group authority.
        result = subprocess.run([
            sys.executable, "-I", "-B", str(Path(__file__).resolve()),
            "--artifacts-dir", str(args.artifacts_dir), "--worker", mode,
        ], capture_output=True, timeout=30, check=False)
        if result.returncode or len(result.stdout) > 32768:
            raise RuntimeError("projection control child failed")
        receipt = json.loads(result.stdout)
        if not receipt.get("qualified") or receipt.get("mode") != mode:
            raise RuntimeError("projection control receipt refused")
        receipts.append(receipt)
    if before != _hashes():
        raise RuntimeError("projection control changed source bytes")
    (args.artifacts_dir / "controls.json").write_text(
        json.dumps({"qualified": True, "receipts": receipts}, indent=2) + "\n")
    print(json.dumps({"qualified": True, "children": 2,
                      "negative_hits": 1, "restored_hits": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
