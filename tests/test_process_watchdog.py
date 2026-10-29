"""Real finite process fixtures, protected by an independent outer supervisor."""

from __future__ import annotations

import importlib
import io
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
DRIVER = Path(__file__).with_name("fixtures") / "process_driver.py"
RUNNERS = ("ptc", "step2", "train")
pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX process-group contract")


def _running(pid):
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "stat="],
        capture_output=True, text=True, timeout=0.5, check=False,
    )
    if result.returncode == 1:
        return False
    assert result.returncode == 0, result.stderr
    return bool(result.stdout.strip()) and not result.stdout.lstrip().startswith("Z")


def _owned_pids(directory):
    return [
        int(path.read_text()) for path in
        (directory / "leader.pid", directory / "grandchild.pid") if path.exists()
    ]


def _exercise(tmp_path, target, mode, *, exception="none", code=0):
    """The code under test is never responsible for this final cleanup."""
    started = time.monotonic()
    supervisor = subprocess.Popen(
        [sys.executable, str(DRIVER), str(REPO), str(tmp_path),
         target, mode, exception, str(code)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True,
    )
    try:
        try:
            stdout, stderr = supervisor.communicate(timeout=2.5)
        except subprocess.TimeoutExpired:
            pytest.fail("runner exceeded independent 2.5-second outer deadline")
        assert supervisor.returncode == 0, (stdout, stderr)
        assert time.monotonic() - started < 3.0
        report = json.loads((tmp_path / "report.json").read_text())
        if mode != "normal":
            assert len(_owned_pids(tmp_path)) == 2
        if mode != "escaped-pipe":
            remaining = [pid for pid in _owned_pids(tmp_path) if _running(pid)]
            assert remaining == [], f"owned processes still running: {remaining}"
        assert report["leader_reaped"], report
        assert report["streams_closed"], report
        return report
    finally:
        # Old runners may share the supervisor's group; new ones own a child
        # group. The escaped fixture is intentionally outside both groups.
        for pid in [supervisor.pid, *_owned_pids(tmp_path)]:
            for kill in (os.killpg, os.kill):
                try:
                    kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        supervisor.communicate(timeout=1)


@pytest.mark.parametrize("target", RUNNERS)
@pytest.mark.parametrize("mode", ["leader-exit", "closed-pipes"])
def test_runner_cleanup_after_leader_exit(tmp_path, target, mode):
    report = _exercise(tmp_path, target, mode)
    assert report["returncode"] == (0 if mode == "closed-pipes" else 124), report


@pytest.mark.parametrize("target", ("helper", *RUNNERS))
@pytest.mark.parametrize("code", [0, 7, 124])
def test_watchdog_preserves_completed_result(tmp_path, target, code):
    report = _exercise(tmp_path, target, "normal", code=code)
    assert report["returncode"] == code
    assert report["stdout"] == "FIXTURE_STDOUT\n"
    assert report["stderr"] == "FIXTURE_STDERR\n"
    assert report["elapsed"] < 1.0


@pytest.mark.parametrize("target", ("helper", *RUNNERS))
@pytest.mark.parametrize("mode", ["ignore-term", "pipe-held"])
def test_watchdog_bounds_timeout_and_inherited_pipes(tmp_path, target, mode):
    report = _exercise(tmp_path, target, mode)
    if target == "helper":
        assert report["exception"] == "TimeoutExpired", report
    else:
        assert report["returncode"] == 124, report
    assert report["stdout"].count("FIXTURE_STDOUT") == 1
    assert report["stderr"].count("FIXTURE_STDERR") == 1


@pytest.mark.parametrize("target", ("helper", *RUNNERS))
@pytest.mark.parametrize("exception", ["KeyboardInterrupt", "SystemExit"])
def test_watchdog_propagates_baseexception_after_cleanup(tmp_path, target, exception):
    report = _exercise(tmp_path, target, "leader-exit", exception=exception)
    assert report["exception"] == exception
    assert report["code"] == (7 if exception == "SystemExit" else None)


@pytest.mark.parametrize("target", ("helper", *RUNNERS))
def test_watchdog_bounds_final_drain_for_escaped_pipe(tmp_path, target):
    report = _exercise(tmp_path, target, "escaped-pipe")
    if target == "helper":
        assert report["exception"] == "TimeoutExpired", report
        assert any("pipe" in note.lower() for note in report["notes"]), report
    else:
        assert report["returncode"] == 124, report
        assert "WATCHDOG: Output pipes remained open" in report["stderr"], report


@pytest.mark.parametrize("target", ("helper", *RUNNERS))
def test_interrupt_during_term_wait_still_finalizes(tmp_path, target):
    report = _exercise(tmp_path, target, "leader-exit", exception="wait-interrupt")
    assert report["exception"] == "KeyboardInterrupt", report


@pytest.mark.parametrize("parameter", ["timeout", "term_grace", "drain_grace", "reap_grace"])
@pytest.mark.parametrize("value", [0, -1, True, None, "1", float("inf"), float("nan")])
def test_watchdog_rejects_invalid_bounds_before_launch(parameter, value, monkeypatch):
    module = importlib.import_module("process_watchdog")

    def no_launch(*args, **kwargs):
        pytest.fail("invalid process bound reached Popen")

    monkeypatch.setattr(module.subprocess, "Popen", no_launch)
    with pytest.raises(ValueError, match="positive finite"):
        module.run_bounded(["never-launch"], **{parameter: value})


def test_empty_group_permission_error_reaps_then_retries_same_group(monkeypatch):
    module = importlib.import_module("process_watchdog")
    calls = []
    process = SimpleNamespace(pid=123456, poll=lambda: 0)

    def signal_group(group, signum):
        calls.append((group, signum))
        if len(calls) == 1:
            raise PermissionError("Darwin empty zombie group")
        raise ProcessLookupError("group gone after reap")

    monkeypatch.setattr(module.os, "killpg", signal_group)
    module._signal_group(process, signal.SIGTERM)
    assert calls == [(process.pid, signal.SIGTERM)] * 2


@pytest.mark.parametrize("status", [None, 0], ids=["live-leader", "reaped-leader"])
def test_real_permission_errors_are_not_silently_swallowed(status, monkeypatch):
    module = importlib.import_module("process_watchdog")
    process = SimpleNamespace(pid=123456, poll=lambda: status)

    def denied(*args):
        raise PermissionError("genuine permission failure")

    monkeypatch.setattr(module.os, "killpg", denied)
    with pytest.raises(PermissionError, match="genuine"):
        module._signal_group(process, signal.SIGTERM)


def test_failed_reap_is_infrastructure_not_a_suite_timeout(monkeypatch):
    module = importlib.import_module("process_watchdog")
    waits = iter([None, subprocess.TimeoutExpired("fixture", 0.2)])

    def wait(**kwargs):
        value = next(waits)
        if isinstance(value, Exception):
            raise value
        return value

    process = SimpleNamespace(
        pid=123456, wait=wait, stdout=io.StringIO(), stderr=io.StringIO(),
        communicate=lambda **kw: ("complete", ""),
    )
    monkeypatch.setattr(module, "_signal_group", lambda *args: None)
    with pytest.raises(RuntimeError, match="reap"):
        module._cleanup(process, term_grace=0.2, drain_grace=0.2, reap_grace=0.2)
    assert process.stdout.closed and process.stderr.closed


def test_signaling_failure_still_finalizes_and_preserves_first_error(monkeypatch):
    module = importlib.import_module("process_watchdog")
    waits = []
    process = SimpleNamespace(
        pid=123456, stdout=io.StringIO(), stderr=io.StringIO(),
        wait=lambda **kw: waits.append(kw),
    )

    def fail_signal(process, signum):
        if signum == signal.SIGTERM:
            raise PermissionError("first signal failure")
        raise RuntimeError("secondary KILL failure")

    monkeypatch.setattr(module, "_signal_group", fail_signal)
    with pytest.raises(PermissionError, match="first signal") as caught:
        module._cleanup(process, term_grace=0.2, drain_grace=0.2, reap_grace=0.2)
    assert process.stdout.closed and process.stderr.closed
    assert waits == [{"timeout": 0.2}]
    assert any("secondary KILL" in note for note in caught.value.__notes__)


def test_cleanup_preserves_interrupt_when_final_reap_also_fails(monkeypatch):
    module = importlib.import_module("process_watchdog")
    waits = iter([
        KeyboardInterrupt("original interrupt"), subprocess.TimeoutExpired("fixture", 0.2),
    ])

    def wait(**kwargs):
        raise next(waits)

    process = SimpleNamespace(
        pid=123456, wait=wait, stdout=io.StringIO(), stderr=io.StringIO(),
    )
    monkeypatch.setattr(module, "_signal_group", lambda *args: None)
    with pytest.raises(KeyboardInterrupt, match="original") as caught:
        module._cleanup(process, term_grace=0.2, drain_grace=0.2, reap_grace=0.2)
    assert process.stdout.closed and process.stderr.closed
    assert any("reap" in note for note in caught.value.__notes__)


@pytest.mark.parametrize("kind", ["KeyboardInterrupt", "SystemExit"])
def test_public_interrupt_keeps_all_secondary_cleanup_diagnostics(kind, monkeypatch):
    module = importlib.import_module("process_watchdog")
    original = KeyboardInterrupt("original") if kind == "KeyboardInterrupt" else SystemExit(7)

    def communicate(**kwargs):
        raise original

    def wait(**kwargs):
        raise subprocess.TimeoutExpired("fixture", 0.2)

    process = SimpleNamespace(
        communicate=communicate, wait=wait, stdout=io.StringIO(), stderr=io.StringIO(),
    )

    def fail_signal(process, signum):
        if signum == signal.SIGTERM:
            raise PermissionError("initial signal failure")
        raise RuntimeError("secondary KILL failure")

    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **kw: process)
    monkeypatch.setattr(module, "_signal_group", fail_signal)
    with pytest.raises(type(original)) as caught:
        module.run_bounded(["fixture"])
    assert caught.value is original
    assert process.stdout.closed and process.stderr.closed
    notes = "\n".join(caught.value.__notes__)
    assert "initial signal failure" in notes
    assert "secondary KILL failure" in notes
    assert "Failed to reap" in notes


def test_shared_interruption_notes_are_snapshotted_before_adding_details(monkeypatch):
    module = importlib.import_module("process_watchdog")

    class GuardedNotes(list):
        def __iter__(self):
            size = len(self)
            for note in super().__iter__():
                assert len(self) == size, "cleanup diagnostics mutated during iteration"
                yield note

    original = SystemExit(7)
    original.__notes__ = GuardedNotes(["initial context"])

    def interrupt(**kwargs):
        raise original

    process = SimpleNamespace(
        communicate=interrupt, wait=interrupt, stdout=io.StringIO(), stderr=io.StringIO(),
    )
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **kw: process)
    monkeypatch.setattr(module, "_signal_group", lambda *args: None)
    with pytest.raises(SystemExit) as caught:
        module.run_bounded(["fixture"])
    assert caught.value is original
    assert process.stdout.closed and process.stderr.closed
    assert any("initial context" in note for note in original.__notes__)
