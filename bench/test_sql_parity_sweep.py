"""Real, finite subprocess regressions for sweep-owned work.

The legacy adapter below deliberately runs the SAME executable fixture through the
old callable boundary. Thus baseline RED means live work escaped a deadline, not a
missing proposed API. The replacement boundary is `_worker_command(request, result)`;
the fixture wraps that command without knowing or replacing its JSON protocol.
"""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from bench import sql_parity_sweep as sweep
from bench.task import SqlTask
from process_watchdog import ProcessCleanupError, run_bounded
from ptc.sql_diff import differential

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).with_name("fixtures") / "sweep_owned_worker.py"


def _task(tmp_path: Path, number: int) -> SqlTask:
    database = tmp_path / f"task-{number}.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE fixture(value INTEGER)")
        connection.execute("INSERT INTO fixture VALUES (?)", (number,))
    return SqlTask(
        name=f"fixture-{number}", question="Read the value", evidence="",
        gold_sql=f"SELECT value FROM fixture WHERE value = {number}",
        db_id=f"fixture-{number}", db_path=str(database), tier="simple",
        tier_source="annotated", shape="select", coarse_shape="select",
        source="fixture",
    )


def _projection(task, result):
    return {
        "name": task.name, "db_id": task.db_id,
        "question_id": int(task.name.rsplit("-", 1)[1]),
        "agreed": result.agreed, "capped": result.capped,
        "bash_outcome": result.bash.outcome, "ptc_outcome": result.ptc.outcome,
        "bash_rows": result.bash.n_rows, "ptc_rows": result.ptc.n_rows,
        "delivery_causes": list(result.delivery_causes),
        "render_causes": list(result.render_causes), "note": result.note,
    }


def _without_elapsed(row):
    return {key: value for key, value in row.items() if key != "elapsed_s"}


def _executing(pid):
    status = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True,
        text=True, check=False, timeout=0.2,
    )
    return status.returncode == 0 and bool(status.stdout.strip()) and not (
        status.stdout.strip().startswith("Z")
    )


def _already_reaped(pid):
    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return True
    return False


def _probe(mode, root):
    """Runs inside an independent <3s supervisor, never in pytest's process."""
    import process_watchdog

    first, second = _task(root, 17), _task(root, 29)
    parent = root / "worker"
    parent.mkdir()
    sentinel = parent / "unrelated"
    sentinel.write_text("preserve")
    directories, allowances, commands = [], [], []
    state = {"mode": mode, "timeout": 0.10 if mode in ("slow", "binding") else 1.0}
    original_run = process_watchdog.run_bounded
    original_command = getattr(sweep, "_worker_command", None)
    original_deadline = getattr(sweep, "_with_deadline", None)

    def fixture_command(bindir, command=(), result=None):
        directories.append(Path(bindir))
        return [
            sys.executable, str(FIXTURE), str(root), state["mode"],
            str(bindir), str(result or "-"), *map(str, command),
        ]

    def bounded(args, **kwargs):
        allowances.append(kwargs["timeout"])
        commands.append(list(args))
        kwargs["timeout"] = state["timeout"]
        return original_run(args, **kwargs)

    # New boundary keeps real child differential and serialization untouched.
    if original_command is not None:
        def command(request, result):
            return fixture_command(Path(request).parent,
                                   original_command(request, result), result)
        sweep._worker_command = command
        sweep.run_bounded = bounded
        process_watchdog.run_bounded = bounded
    else:
        # Baseline adapter is intentionally unowned, like its daemon computation.
        # Fixtures are finite even when cancellation is broken.
        def legacy(task, *, bindir, compare, max_rows):
            completed = subprocess.run(
                fixture_command(bindir), capture_output=True, text=True,
                timeout=1.5, check=False,
            )
            if completed.returncode:
                raise RuntimeError(f"worker exited {completed.returncode}")
            return differential(task, bindir=bindir, compare=compare,
                                max_rows=max_rows)

        def deadline(fn, timeout):
            allowances.append(timeout)
            return original_deadline(fn, state["timeout"])

        sweep.differential = legacy
        sweep._with_deadline = deadline

    started = time.monotonic()
    try:
        row = sweep._one(first, parent, "set", 10)
    except KeyboardInterrupt:
        if mode != "interrupt":
            raise
        row = {"interrupted": True}
    except ProcessCleanupError as error:
        if os.environ.get("SWEEP_TEST_DISABLE_TERMINATION") != "1":
            raise
        # The mutation can correctly fail loud at the reap gate. Still collect
        # independent liveness/side-effect evidence rather than treating that
        # cleanup exception itself as proof our liveness assertions are sensitive.
        row = {"agreed": False, "error": str(error),
               "delivery_causes": ["cleanup_failure"], "render_causes": []}
    returned = time.monotonic() - started
    returned_at = time.monotonic()
    private_at_return = [str(path) for path in directories if path.exists()]
    pids_path = root / "pids.json"
    pids = json.loads(pids_path.read_text()) if pids_path.exists() else []
    live_at_return = [pid for pid in pids if _executing(pid)]
    leader_reaped = bool(pids) and _already_reaped(pids[0])
    rows = []
    if mode == "binding":
        state.update(mode="finite", timeout=1.5)
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(lambda task: sweep._one(task, parent, "set", 10),
                                 (first, second)))
    # More than fixture's .80s marker delay; return-to-check remains <1s.
    # Protocol-error workers create no descendants, so need no late-marker wait.
    if pids:
        time.sleep(max(0.0, returned_at + 0.85 - time.monotonic()))
    return {
        "row": row, "rows": rows, "returned_s": returned,
        "pids": pids, "live_at_return": live_at_return,
        "leader_reaped": leader_reaped,
        "late_check_elapsed_s": time.monotonic() - returned_at,
        "live_after": [pid for pid in pids if _executing(pid)],
        "late_marker": (root / "late-marker").exists(),
        "private_at_return": private_at_return,
        "private_after": [str(path) for path in directories if path.exists()],
        "directories": [str(path) for path in directories],
        "sentinel": sentinel.read_text(), "allowances": allowances,
        "commands": commands,
    }


def _supervised(tmp_path, mode):
    """Independent supervisor: never call the production watchdog or its helpers."""
    started = time.monotonic()
    process = subprocess.Popen(
        [sys.executable, "-B", str(Path(__file__).resolve()),
         "--probe", mode, str(tmp_path)],
        cwd=ROOT, start_new_session=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1",
             "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
             "HF_DATASETS_OFFLINE": "1"},
    )
    try:
        stdout, stderr = process.communicate(timeout=2.5)
        assert process.returncode == 0, stderr
        report = json.loads(stdout)
    finally:
        # Probe has already captured return-time liveness and waited for markers.
        # Only now clean the supervisor's group and recorded original worker groups.
        groups = {process.pid}
        records = [json.loads(path.read_text()) for path in tmp_path.glob("group-*.json")]
        groups.update(owned["pgid"] for owned in records
                      if owned["pgid"] == owned["pid"])
        for pgid in groups:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                # Darwin can deny signals to a group containing only zombies.
                pids = tmp_path / "pids.json"
                assert pids.exists() and not any(
                    _executing(pid) for pid in json.loads(pids.read_text()))
        process.wait(timeout=0.15)
        process.stdout.close()
        process.stderr.close()
        assert all(owned["pgid"] in groups for owned in records)
    assert time.monotonic() - started < 3.0
    return report


def _assert_owned_stopped(report):
    assert len(report["pids"]) == 2, "worker AND grandchild must actually start"
    assert not report["live_at_return"], f"owned work still executing: {report}"
    assert report["leader_reaped"], "owned leader must already be reaped"
    assert not report["live_after"], report
    assert not report["late_marker"], "owned descendant produced a late side effect"
    assert report["late_check_elapsed_s"] < 1.0
    assert not report["private_at_return"], "parent must clean before returning"
    assert not report["private_after"]
    assert report["sentinel"] == "preserve"


def test_timeout_stops_owned_work(tmp_path):
    report = _supervised(tmp_path, "slow")
    assert report["row"]["delivery_causes"] == ["sweep_timeout"]
    assert not report["row"]["agreed"]
    assert report["returned_s"] < 1.0
    assert report["allowances"] == [45.0]
    _assert_owned_stopped(report)


def test_cleanup_after_normal_leader_exit(tmp_path):
    report = _supervised(tmp_path, "leader-exit")
    assert report["row"]["agreed"]
    assert report["row"]["bash_rows"] == report["row"]["ptc_rows"] == 1
    _assert_owned_stopped(report)


def test_task_binding_after_timeout(tmp_path):
    report = _supervised(tmp_path, "binding")
    assert report["row"]["delivery_causes"] == ["sweep_timeout"]
    assert [row["question_id"] for row in report["rows"]] == [17, 29]
    assert all(row["agreed"] and row["bash_rows"] == row["ptc_rows"] == 1
               for row in report["rows"])
    assert len(report["directories"]) == len(set(report["directories"])) == 3
    _assert_owned_stopped(report)


@pytest.mark.parametrize("compare", ["set", "multiset"])
@pytest.mark.parametrize(("sql", "cap", "capped", "render"), [
    ("SELECT value FROM fixture UNION ALL SELECT value FROM fixture", 10, False, None),
    ("SELECT value FROM fixture UNION ALL SELECT value FROM fixture", 1, True, None),
    ("SELECT NULL AS missing, value FROM fixture", 10, False, "null_rendering"),
    ("SELECT value AS repeated, value AS repeated FROM fixture", 10, False,
     "duplicate_columns"),
    ("SELECT NULL AS value UNION ALL SELECT value FROM fixture UNION ALL SELECT NULL",
     10, False, None),
])
def test_real_differential_output_unchanged(tmp_path, compare, sql, cap, capped, render):
    task = replace(_task(tmp_path, 17), gold_sql=sql)
    expected = differential(task, bindir=tmp_path / "direct",
                            compare=compare, max_rows=cap)
    trailing_nulls = sql.startswith("SELECT NULL AS value UNION")
    assert expected.agreed is (compare == "set" if trailing_nulls else True)
    assert expected.capped is capped
    if render:
        assert render in expected.render_causes
    row = sweep._one(task, tmp_path / "worker", compare, cap)
    assert _without_elapsed(row) == _projection(task, expected)
    assert sweep.summarise([row], compare=compare) == {
        "compare": compare, "n_total": 1, "n_agreed": int(expected.agreed),
        "n_diverged": int(not expected.agreed),
        "n_capped_both": int(capped),
        "n_compared_rowwise": int(expected.agreed) - int(capped),
        "n_agreed_with_render_cause": int(expected.agreed and
                                         bool(expected.render_causes)),
        "delivery_causes": {cause: 1 for cause in expected.delivery_causes},
        "render_causes": {cause: 1 for cause in expected.render_causes},
        "divergent_ids": [] if expected.agreed else [17],
        "render_ids": [17] if expected.render_causes else [],
        "timeouts": [],
    }


def test_each_differential_uses_fresh_json_worker(tmp_path, monkeypatch):
    task = _task(tmp_path, 17)
    parent = tmp_path / "worker"
    parent.mkdir()
    sentinel = parent / "unrelated"
    sentinel.write_text("preserve")
    calls = []

    def observed(args, **kwargs):
        assert task.gold_sql not in args, "SQL must not be a diagnostic CLI argument"
        assert "-I" in args and "-B" in args
        assert kwargs["timeout"] == 45.0
        json_paths = [Path(arg) for arg in args
                      if str(arg).endswith(".json") and Path(arg).is_file()]
        assert json_paths, "worker request must be an existing JSON file"
        request = json_paths[0]
        assert task.gold_sql in json.dumps(json.loads(request.read_text()))
        assert request.parent.parent == parent
        completed = run_bounded(args, **kwargs)
        calls.append((tuple(args), request.parent))
        return completed

    monkeypatch.setattr(sweep, "run_bounded", observed, raising=False)
    for _ in range(2):
        row = sweep._one(task, parent, "set", 10)
        assert row["agreed"]
    assert len(calls) == 2, "one fresh bounded subprocess per differential"
    assert calls[0][1] != calls[1][1]
    assert all(not directory.exists() for _, directory in calls)
    assert list(parent.iterdir()) == [sentinel]


def test_worker_ignores_pythonpath_startup_code(tmp_path, monkeypatch):
    task = _task(tmp_path, 17)
    poison = tmp_path / "untrusted-imports"
    poison.mkdir()
    marker = tmp_path / "startup-executed"
    (poison / "sitecustomize.py").write_text(
        f"from pathlib import Path; Path({str(marker)!r}).write_text('executed')\n")
    monkeypatch.setenv("PYTHONPATH", str(poison))
    monkeypatch.chdir(poison)
    row = sweep._one(task, tmp_path / "worker", "multiset", 10)
    assert row["agreed"]
    assert row["bash_rows"] == row["ptc_rows"] == 1
    assert not marker.exists()


def _valid_worker_payload():
    return {"result": {
        "agreed": True, "capped": False, "bash_outcome": "ok", "ptc_outcome": "ok",
        "bash_rows": 1, "ptc_rows": 1, "delivery_causes": [], "render_causes": [],
        "note": "",
    }}


@pytest.mark.parametrize(("field", "value"), [
    ("agreed", 1), ("agreed", False), ("capped", 0), ("capped", True),
    ("bash_outcome", "unknown"), ("ptc_outcome", []),
    ("bash_rows", True), ("ptc_rows", -1), ("bash_rows", 1.5),
    ("delivery_causes", "rows_differ"), ("delivery_causes", ["invented"]),
    ("render_causes", ["invented"]), ("render_causes", [None]), ("note", None),
    ("name", "forged-child-identity"),
    ("bash_outcome", "refused"),
])
def test_invalid_worker_projection_is_not_success(tmp_path, monkeypatch, field, value):
    task = _task(tmp_path, 17)
    payload = _valid_worker_payload()
    payload["result"][field] = value
    if field == "bash_outcome" and value == "refused":
        payload["result"]["bash_rows"] = 0

    def completed(args, **kwargs):
        Path(args[-1]).write_text(json.dumps(payload))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(sweep, "run_bounded", completed)
    row = sweep._one(task, tmp_path / "worker", "set", 10)
    assert row["delivery_causes"] == ["sweep_error"]
    assert not row["agreed"]
    assert row["name"] == task.name and row["question_id"] == 17
    assert list((tmp_path / "worker").iterdir()) == []


@pytest.mark.parametrize("payload", [None, [], {}, {"agreed": True},
                                    {"result": {}}, {"error": ""},
                                    {"error": 7}, {"result": {}, "error": "conflict"}])
def test_incomplete_worker_envelope_is_not_success(tmp_path, monkeypatch, payload):
    task = _task(tmp_path, 17)

    def completed(args, **kwargs):
        Path(args[-1]).write_text(json.dumps(payload))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(sweep, "run_bounded", completed)
    row = sweep._one(task, tmp_path / "worker", "set", 10)
    assert row["delivery_causes"] == ["sweep_error"]
    assert not row["agreed"]


def test_child_timeout_exception_is_not_supervisor_deadline(tmp_path, monkeypatch):
    task = _task(tmp_path, 17)

    def completed(args, **kwargs):
        Path(args[-1]).write_text(json.dumps({"error": "TimeoutError: child failure"}))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(sweep, "run_bounded", completed)
    row = sweep._one(task, tmp_path / "worker", "set", 10)
    assert row["error"] == "TimeoutError: child failure"
    assert row["delivery_causes"] == ["sweep_error"]


def test_non_timeout_failure_is_not_labeled_as_a_sweep_timeout(tmp_path):
    task = replace(_task(tmp_path, 17), gold_sql="")
    parent = tmp_path / "worker"
    parent.mkdir()
    sentinel = parent / "unrelated"
    sentinel.write_text("preserve")
    row = sweep._one(task, parent, "multiset", 10)
    assert row["error"] == "ValueError: task 'fixture-17' has no gold query to compare"
    assert row["delivery_causes"] == ["sweep_error"]
    assert row["render_causes"] == []
    assert not row["agreed"]
    assert sweep.summarise([row], compare="set")["timeouts"] == []
    assert list(parent.iterdir()) == [sentinel]


@pytest.mark.parametrize("mode", ["exit7", "absent", "malformed"])
def test_worker_failures_are_not_success(tmp_path, mode):
    report = _supervised(tmp_path, mode)
    assert not report["row"]["agreed"], f"{mode} worker became agreement"
    assert report["row"]["delivery_causes"] == ["sweep_error"]
    assert report["row"]["render_causes"] == []
    assert "error" in report["row"]
    assert not report["private_at_return"]
    assert report["sentinel"] == "preserve"


@pytest.mark.parametrize("error_type", [ProcessCleanupError, PermissionError, RuntimeError])
def test_cleanup_failure_stays_explicit(tmp_path, monkeypatch, error_type):
    task = _task(tmp_path, 17)
    calls = []

    def failed_cleanup(*args, **kwargs):
        calls.append(args)
        raise error_type("fixture could not reap owned leader")

    # Baseline has no subprocess boundary: patch with raising=False so RED is the
    # false success, never AttributeError/import failure.
    monkeypatch.setattr(sweep, "run_bounded", failed_cleanup, raising=False)
    with pytest.raises(error_type, match="could not reap"):
        for _ in range(2):
            sweep._one(task, tmp_path / "worker", "set", 10)
    assert len(calls) == 1, "cleanup failure must abort, not continue to another task"
    assert len(list((tmp_path / "worker").glob("query-*"))) == 1


def test_interruption_cleans_owned_work_and_propagates(tmp_path):
    report = _supervised(tmp_path, "interrupt")
    assert report["row"] == {"interrupted": True}
    assert report["returned_s"] < 1.0
    # An interrupted caller cannot assert cleanup succeeded. Preserve its private
    # directory, but the real watchdog must still stop/reap its executing work.
    assert len(report["private_at_return"]) == 1
    report = {**report, "private_at_return": [], "private_after": []}
    _assert_owned_stopped(report)


def test_main_keeps_sorted_membership_and_summary(tmp_path, monkeypatch, capsys):
    tasks = [_task(tmp_path, 29), _task(tmp_path, 17)]
    monkeypatch.setattr(sweep, "load_bird", lambda path: tasks)
    output = tmp_path / "out" / "sweep.json"
    assert sweep.main(["--out", str(output), "--jobs", "2", "--compare", "multiset",
                       "--max-rows", "1"]) == 0
    payload = json.loads(output.read_text())
    assert [row["question_id"] for row in payload["rows"]] == [17, 29]
    assert all(row["agreed"] and row["bash_rows"] == row["ptc_rows"] == 1
               for row in payload["rows"])
    assert payload["summary"] == sweep.summarise(payload["rows"], compare="multiset")
    assert payload["summary"]["n_total"] == payload["summary"]["n_agreed"] == 2
    assert payload["max_rows"] == 1
    assert list((output.parent / "bin").iterdir()) == []
    assert str(output) in capsys.readouterr().out


def test_main_ownership_failure_never_writes_success_summary(tmp_path, monkeypatch):
    task = _task(tmp_path, 17)
    monkeypatch.setattr(sweep, "load_bird", lambda path: [task])

    def failed_cleanup(*args, **kwargs):
        raise ProcessCleanupError("fixture main ownership failure")

    monkeypatch.setattr(sweep, "run_bounded", failed_cleanup)
    output = tmp_path / "out" / "sweep.json"
    with pytest.raises(ProcessCleanupError, match="main ownership failure"):
        sweep.main(["--out", str(output), "--jobs", "1"])
    assert not output.exists()
    assert len(list((output.parent / "bin").glob("query-*"))) == 1


def test_sweep_termination_guard_sensitivity(tmp_path, monkeypatch):
    # Isolated mutation: suppress ORIGINAL-group signals, not production edits.
    # The finite fixture is safe even if both cleanup escalation signals disappear.
    # Mutation affects only the probe's production watchdog, NEVER its supervisor.
    monkeypatch.setenv("SWEEP_TEST_DISABLE_TERMINATION", "1")
    report = _supervised(tmp_path, "slow")
    assert len(report["pids"]) == 2
    assert report["late_marker"], "negative control must produce a real late side effect"
    assert report["live_at_return"] or report["late_marker"]
    with pytest.raises(AssertionError, match="owned work still executing|late side effect"):
        _assert_owned_stopped({**report, "leader_reaped": True})


if __name__ == "__main__":
    if os.environ.get("SWEEP_TEST_DISABLE_TERMINATION") == "1":
        import process_watchdog
        process_watchdog._signal_group = lambda process, signum: None
    assert sys.argv[1] == "--probe"
    print(json.dumps(_probe(sys.argv[2], Path(sys.argv[3]))))
