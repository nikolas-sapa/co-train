"""Fresh -I -B sensitivity controls. In-memory helpers only, no source edits.

Run with the repository's already provisioned test interpreter. All receipts
and logs stay beside this driver; no provider, native runner or Docker.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[4]
SCRATCH = Path(__file__).resolve().parent
UNIT = REPO / "ptc/test_owned_program_runner.py"
SOURCES = [
    REPO / "ptc/harness.py", UNIT,
    REPO / "ptc/test_owned_program_runner_integration.py",
]
CASES = {
    "close": (
        "test_repeated_cancellation_joins_owned_close",
        "caller returned before owned close acknowledgment",
    ),
    "fatal": (
        "test_infrastructure_failure_has_no_next_request[unexpected]",
        "infrastructure failure dispatched a second policy request",
    ),
}


def _hashes():
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in SOURCES}


class Reports:
    def __init__(self):
        self.selected = []
        self.reports = []

    def pytest_collection_modifyitems(self, session, config, items):
        self.selected = [item.nodeid for item in items]

    def pytest_runtest_logreport(self, report):
        self.reports.append({
            "nodeid": report.nodeid, "when": report.when,
            "outcome": report.outcome, "longrepr": str(report.longrepr or ""),
        })


def _worker(case, *, bypass):
    sys.path.insert(0, str(REPO))
    import pytest
    import ptc.harness as harness

    name, intended = CASES[case]
    selected = str(UNIT) + "::" + name
    original_close = harness._close_program_runner
    original_execute = harness._execute_owned_program
    before = _hashes()
    reports = Reports()
    retained, hits = [], []

    async def unowned_close(runner):
        hits.append("close")
        # Deliberately wrong: launch returns without joining this task.
        # The selected test's finally releases/drains its retained fixture task.
        retained.append(asyncio.create_task(runner.aclose()))

    async def raw_execute(runner, code, timeout):
        hits.append("fatal")
        # Deliberately wrong: RuntimeError falls into legacy tool feedback.
        return await runner.run_program(code, timeout=timeout)

    try:
        if bypass:
            if case == "close":
                harness._close_program_runner = unowned_close
            else:
                harness._execute_owned_program = raw_execute
        exit_code = int(pytest.main([
            "-q", "-p", "no:cacheprovider", f"--rootdir={REPO}", selected,
        ], plugins=[reports]))
    finally:
        harness._close_program_runner = original_close
        harness._execute_owned_program = original_execute

    after = _hashes()
    calls = [report for report in reports.reports if report["when"] == "call"]
    failures = [
        report for report in reports.reports if report["outcome"] == "failed"
    ]
    expected_node = "ptc/test_owned_program_runner.py::" + name
    selection_ok = (
        len(reports.selected) == 1
        and reports.selected[0].endswith(expected_node)
        and len(calls) == 1
        and calls[0]["nodeid"] == reports.selected[0]
    )
    if bypass:
        valid = (
            selection_ok and exit_code == 1 and hits == [case]
            and len(failures) == 1 and failures[0]["when"] == "call"
            and intended in failures[0]["longrepr"]
            and "AssertionError" in failures[0]["longrepr"]
        )
    else:
        valid = (
            selection_ok and exit_code == 0 and hits == []
            and calls[0]["outcome"] == "passed" and failures == []
        )
    drained = all(task.done() for task in retained)
    for task in retained:
        if task.done() and not task.cancelled():
            task.exception()
    receipt = {
        "case": case, "bypass": bypass, "bypass_hits": len(hits),
        "selected": reports.selected, "reports": reports.reports,
        "pytest_exit": exit_code, "source_hashes_before": before,
        "source_hashes_after": after, "source_unchanged": before == after,
        "helpers_restored": (
            harness._close_program_runner is original_close
            and harness._execute_owned_program is original_execute
        ),
        "retained_fixture_tasks_drained": drained,
        "intended_failure": intended,
        "accepted": valid and before == after and drained,
    }
    destination = SCRATCH / (
        f"owned-runner-{case}-{'bypass' if bypass else 'positive'}.json"
    )
    destination.write_text(json.dumps(receipt, indent=2) + "\n")
    return 0 if receipt["accepted"] else 1


def main():
    global SCRATCH
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--worker", choices=CASES)
    parser.add_argument("--bypass", action="store_true")
    args = parser.parse_args()
    if not args.artifacts_dir.is_absolute():
        parser.error("--artifacts-dir must be absolute")
    SCRATCH = args.artifacts_dir.resolve()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    if args.worker:
        return _worker(args.worker, bypass=args.bypass)
    before = _hashes()
    runs = []
    # Each negative and restored positive has a fresh interpreter/module graph.
    for case in CASES:
        for bypass in (True, False):
            label = f"{case}-{'bypass' if bypass else 'positive'}"
            command = [
                sys.executable, "-I", "-B", str(Path(__file__).resolve()),
                "--artifacts-dir", str(SCRATCH), "--worker", case,
            ]
            if bypass:
                command.append("--bypass")
            try:
                result = subprocess.run(
                    command, cwd=REPO, capture_output=True, text=True,
                    timeout=20.0, check=False,
                )
                (SCRATCH / f"owned-runner-{label}.log").write_text(
                    result.stdout + result.stderr
                )
                runs.append({"case": label, "exit_code": result.returncode})
            except subprocess.TimeoutExpired as exc:
                runs.append({"case": label, "timeout": str(exc)})
    after = _hashes()
    accepted = (
        all(run.get("exit_code") == 0 for run in runs) and before == after
    )
    (SCRATCH / "owned-runner-controls.json").write_text(json.dumps({
        "accepted": accepted, "runs": runs,
        "source_hashes_before": before, "source_hashes_after": after,
    }, indent=2) + "\n")
    print("owned runner controls accepted" if accepted else
          "owned runner controls failed; inspect scratch receipts/logs")
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
