"""Synthetic local checks only. Parent must supply an external 30s cap."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from train import qualification_watchdog as watchdog


def _cleanup_all(*operations):
    errors = []
    for operation in operations:
        try:
            operation()
        except BaseException as error:
            errors.append(error)
    if errors:
        raise errors[0]


def _reap(process, *, wait_seconds=5):
    if process is None:
        return
    try:
        if process.returncode is None:
            try:
                process.wait(timeout=wait_seconds)
            except subprocess.TimeoutExpired:
                if process.returncode is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
        process.wait(timeout=2)
    finally:
        _cleanup_all(*(stream.close for stream in
                       (process.stdin, process.stdout, process.stderr)
                       if stream is not None))


def _reap_all(*processes):
    _cleanup_all(*(lambda process=process: _reap(process) for process in processes))


def _cleanup_watches(*instances, actors=()):
    watches = [instance for instance in instances if instance is not None]
    _cleanup_all(
        *(instance._channel.close for instance in watches),
        *(lambda process=process: _reap(process) for process in actors),
        *(lambda instance=instance: _reap(
            instance._process,
            wait_seconds=max(0, min(13, instance._deadline - time.monotonic() + 1)),
        ) for instance in watches),
    )


def _cleanup_watch(instance, *actors):
    _cleanup_watches(instance, actors=actors)


def _arm(**values):
    try:
        return watchdog.arm(**values)
    except watchdog.ArmError as primary:
        try:
            _cleanup_watch(primary.controller)
        except BaseException as secondary:
            primary.controller.cleanup_errors += (secondary,)
        raise


def _setup(tmp_path, *, mode="ok", lifetime=12.0, teardown_seconds=3.0):
    executable = tmp_path / "trusted-stop"
    audit = tmp_path / "requests"
    executable.write_text(
        "#!" + sys.executable + "\n"
        "import json, os, sys, time\n"
        "request = json.load(sys.stdin)\n"
        "with open(os.environ['AUDIT'], 'a') as stream:\n"
        "    stream.write(json.dumps({'request': request, "
        "'leaked': 'WATCHDOG_INHERITED_SECRET' in os.environ}) + '\\n')\n"
        "mode = os.environ['MODE']\n"
        "if mode == 'hang': time.sleep(60)\n"
        "if mode == 'flood':\n"
        "    os.write(1, b'EXPLICIT_SECRET' * 20000)\n"
        "    os.write(2, b'EXPLICIT_SECRET' * 20000)\n"
        "sys.exit(7 if mode == 'fail' else 0)\n",
        encoding="ascii",
    )
    executable.chmod(0o700)
    app_id = "ap-synthetic-" + tmp_path.name
    identity = SimpleNamespace(app_id=app_id)
    values = dict(
        custody=SimpleNamespace(app_identity=identity), app_identity=identity,
        app_id=app_id, deadline=time.monotonic() + lifetime,
        teardown=watchdog.TrustedTeardown(
            executable, {"AUDIT": str(audit), "MODE": mode,
                         "PRIVATE_VALUE": "EXPLICIT_SECRET"},
            explicitly_trusted=True,
        ),
        evidence_path=tmp_path / "retained.jsonl",
        teardown_seconds=teardown_seconds, arm_seconds=4.0,
    )
    return values, audit


def _records(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def _refused(monkeypatch, values, error=ValueError):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("subprocess reached on refused authority")

    monkeypatch.setattr(watchdog.subprocess, "Popen", forbidden)
    with pytest.raises(error):
        _arm(**values)
    assert calls == []


def test_contract_wrong_app_zero_calls(tmp_path, monkeypatch):
    values, audit = _setup(tmp_path)
    values["app_identity"] = object()
    _refused(monkeypatch, values)
    assert not audit.exists()
    assert not values["evidence_path"].exists()


def test_contract_missing_control_identity(tmp_path, monkeypatch):
    values, _ = _setup(tmp_path)
    values["app_id"] = ""
    _refused(monkeypatch, values)
    values["app_id"] = "ap-wrong-owned-resource"
    _refused(monkeypatch, values)


def test_contract_requires_explicit_trust(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(watchdog.subprocess, "Popen", lambda *a, **k: calls.append(1))
    with pytest.raises(ValueError):
        watchdog.TrustedTeardown(tmp_path / "stop", {}, explicitly_trusted=False)
    assert calls == []


def test_contract_relative_executable(tmp_path):
    with pytest.raises(ValueError):
        watchdog.TrustedTeardown(Path("stop"), {}, explicitly_trusted=True)


def test_contract_nonfinite_deadline(tmp_path, monkeypatch):
    values, _ = _setup(tmp_path)
    values["deadline"] = math.inf
    _refused(monkeypatch, values)


def test_contract_aggregate_deadline(tmp_path, monkeypatch):
    values, _ = _setup(tmp_path)
    values["deadline"] = time.monotonic() + 1801
    _refused(monkeypatch, values)


def test_contract_teardown_reserve(tmp_path, monkeypatch):
    values, _ = _setup(tmp_path)
    values["deadline"] = time.monotonic() + 0.1
    _refused(monkeypatch, values)


def test_contract_duplicate_reservation_retained(tmp_path, monkeypatch):
    values, _ = _setup(tmp_path)
    values["evidence_path"].write_text("AMBIGUOUS_EXISTING_EVIDENCE\n")
    _refused(monkeypatch, values, FileExistsError)
    assert values["evidence_path"].read_text() == "AMBIGUOUS_EXISTING_EVIDENCE\n"


def test_contract_no_signal_after_reap(monkeypatch):
    signals = []
    monkeypatch.setattr(watchdog.os, "killpg", lambda *args: signals.append(args))
    process = SimpleNamespace(pid=123456, returncode=0)
    assert watchdog._signal_owned_group(process) is False
    assert signals == []


def test_contract_all_cleanup_primary_identity(monkeypatch):
    instance = object.__new__(watchdog.Watchdog)
    instance.cleanup_errors = ()
    instance._run_lock = threading.Lock()
    instance._ran = instance._finished = False
    instance._deadline = time.monotonic() + 5
    instance._teardown_seconds = 0.3
    instance._process = SimpleNamespace(poll=lambda: None)
    primary = KeyboardInterrupt("primary")
    calls = []

    def fail(name):
        calls.append(name)
        raise RuntimeError(name)

    monkeypatch.setattr(watchdog.Watchdog, "finish", lambda self: fail("watchdog"))

    def callback():
        raise primary

    with pytest.raises(KeyboardInterrupt) as caught:
        instance.run(callback, cleanup=(lambda: fail("one"), lambda: fail("two")))
    assert caught.value is primary
    assert calls == ["watchdog", "one", "two"]
    assert len(instance.cleanup_errors) == 3


def test_local_ordinary_success(tmp_path):
    values, audit = _setup(tmp_path)
    instance = _arm(**values)
    result = object()
    try:
        observed = instance.run(lambda: result)
        report = instance.finish()
        assert observed is result
        assert report["teardown"]["returncode"] == 0
        assert report["remote"] == report["billing"] == "UNKNOWN"
        assert len(_records(audit)) == 1
        assert values["evidence_path"].exists()
        assert report["teardown"]["attempted"] is True
    finally:
        _cleanup_watch(instance)


def _owner_actor(instance, *, die):
    fd = instance._channel.fileno()
    actor = subprocess.Popen(
        [sys.executable, "-I", "-c",
         "import sys,time; sys.exit(4) if sys.argv[1]=='die' else time.sleep(60)",
         "die" if die else "hang"],
        pass_fds=(fd,), close_fds=True, env={},
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True,
    )
    # Controller is a child of this test, so even RED fallback can really reap it.
    instance._channel.close()
    return actor


def _wait_controller(instance):
    instance._process.wait(timeout=max(
        0.001, min(14, instance._deadline - time.monotonic() + 1),
    ))
    records = _records(instance.evidence_path)
    assert records[-1]["event"] == "result"
    return records[-1]


def test_local_owner_hang(tmp_path):
    values, audit = _setup(tmp_path, lifetime=9)
    instance = _arm(**values)
    actor = None
    try:
        actor = _owner_actor(instance, die=False)
        report = _wait_controller(instance)
        assert report["reason"] == "deadline"
        assert actor.poll() is None
        assert len(_records(audit)) == 1
    finally:
        _cleanup_watch(instance, actor)


def test_local_owner_death(tmp_path):
    values, audit = _setup(tmp_path)
    instance = _arm(**values)
    actor = None
    try:
        actor = _owner_actor(instance, die=True)
        actor.wait(timeout=5)
        report = _wait_controller(instance)
        assert report["reason"] == "owner_eof"
        assert len(_records(audit)) == 1
    finally:
        _cleanup_watch(instance, actor)


def test_local_absolute_deadline(tmp_path):
    values, audit = _setup(tmp_path, lifetime=9)
    instance = _arm(**values)
    try:
        report = _wait_controller(instance)
        assert time.monotonic() < values["deadline"] + 0.5
        assert report["reason"] == "deadline"
        assert len(_records(audit)) == 1
    finally:
        _cleanup_watch(instance)


def test_local_teardown_hang_bounded(tmp_path):
    values, audit = _setup(tmp_path, mode="hang")
    instance = _arm(**values)
    started = time.monotonic()
    try:
        with pytest.raises(RuntimeError, match="local teardown unconfirmed"):
            instance.run(lambda: None)
        report = instance.finish()
        assert time.monotonic() - started < 5
        assert report["teardown"]["timed_out"] is True
        assert report["teardown"]["leader_reaped"] is True
        assert report["remote"] == "UNKNOWN"
        assert len(instance.cleanup_errors) == 1
        assert len(_records(audit)) == 1
        assert values["evidence_path"].exists()
    finally:
        _cleanup_watch(instance)


def test_local_child_held_stdout(tmp_path, monkeypatch):
    values, _ = _setup(tmp_path)
    reader, writer = os.pipe()
    holder = None
    commands = []
    popen = subprocess.Popen
    try:
        holder = popen(
            [sys.executable, "-I", "-c", "import time; time.sleep(60)"],
            pass_fds=(writer,), env={}, start_new_session=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        def held_stdout(*args, **kwargs):
            kwargs["stdout"] = writer
            process = popen(*args, **kwargs)
            commands.append(process)
            process.stdout = os.fdopen(reader, "rb", buffering=0, closefd=False)
            return process

        monkeypatch.setattr(watchdog.subprocess, "Popen", held_stdout)
        started = time.monotonic()
        report = watchdog._bounded_command(
            values["teardown"], values["app_id"], 3, started + 5,
        )
        assert time.monotonic() - started < 5
        assert report["leader_reaped"] is True
        assert report["returncode"] == 0
        assert holder.poll() is None
    finally:
        try:
            _reap_all(*commands, holder)
        finally:
            _cleanup_all(lambda: os.close(reader), lambda: os.close(writer))


def test_local_cancellation_identity(tmp_path):
    values, audit = _setup(tmp_path)
    instance = _arm(**values)
    primary = KeyboardInterrupt("cancel")

    def cancel():
        raise primary

    try:
        with pytest.raises(KeyboardInterrupt) as caught:
            instance.run(cancel)
        assert caught.value is primary
        assert len(_records(audit)) == 1
    finally:
        _cleanup_watch(instance)


def test_local_error_identity_failed_teardown(tmp_path):
    values, audit = _setup(tmp_path, mode="fail")
    instance = _arm(**values)
    primary = RuntimeError("exact primary")

    def fail():
        raise primary

    try:
        with pytest.raises(RuntimeError) as caught:
            instance.run(fail)
        assert caught.value is primary
        report = instance.finish()
        assert report["teardown"]["returncode"] == 7
        assert report["remote"] == "UNKNOWN"
        assert len(_records(audit)) == 1
        assert _records(values["evidence_path"])[-1] == report
    finally:
        _cleanup_watch(instance)


def test_local_duplicate_arm_one_request(tmp_path):
    values, audit = _setup(tmp_path)
    instance = _arm(**values)
    duplicate = alternate_watch = None
    try:
        with pytest.raises(FileExistsError):
            duplicate = _arm(**values)
        alternate = dict(values, evidence_path=tmp_path / "second-marker")
        with pytest.raises(FileExistsError):
            alternate_watch = _arm(**alternate)
        result = object()
        assert instance.run(lambda: result) is result
        first = instance.finish()
        assert instance.finish() is first
        assert len(_records(audit)) == 1
        assert values["evidence_path"].exists()
        called = []
        with pytest.raises(RuntimeError):
            instance.run(lambda: called.append(True))
        assert called == []
    finally:
        _cleanup_watches(instance, duplicate, alternate_watch)


def test_local_bounded_sanitized_output(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHDOG_INHERITED_SECRET", "GLOBAL_SECRET")
    values, audit = _setup(tmp_path, mode="flood")
    instance = _arm(**values)
    try:
        report = instance.finish()
        encoded = json.dumps(report)
        assert len(encoded) <= 4096
        assert report["teardown"]["output_bytes"] <= 4096
        assert report["teardown"]["output_truncated"] is True
        assert _records(audit)[0]["leaked"] is False
        evidence = values["evidence_path"].read_text()
        assert "EXPLICIT_SECRET" not in evidence
        assert "GLOBAL_SECRET" not in evidence
        assert values["app_id"] not in evidence
        assert len(_records(audit)) == 1
    finally:
        _cleanup_watch(instance)


def test_local_controller_hang_unknown(tmp_path):
    values, audit = _setup(tmp_path)
    instance = _arm(**values)
    try:
        os.kill(instance._process.pid, signal.SIGSTOP)
        started = time.monotonic()
        report = instance.finish()
        assert time.monotonic() - started < 5
        assert report["reason"] == "controller_unknown"
        assert report["local_ok"] is False
        assert report["remote"] == report["billing"] == "UNKNOWN"
        assert values["evidence_path"].exists()
        assert not audit.exists()
    finally:
        try:
            if instance._process.returncode is None:
                os.kill(instance._process.pid, signal.SIGCONT)
        finally:
            _cleanup_watch(instance)


def test_local_concurrent_rejection_no_cleanup(tmp_path):
    values, audit = _setup(tmp_path)
    instance = _arm(**values)
    entered = threading.Event()
    release = threading.Event()
    calls = []
    outcomes = []
    errors = []
    result = object()

    def callback():
        entered.set()
        assert release.wait(timeout=5)
        return result

    def admitted():
        try:
            outcomes.append(instance.run(callback, cleanup=(lambda: calls.append("admitted"),)))
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=admitted, daemon=True)
    try:
        thread.start()
        assert entered.wait(timeout=5)
        previous_errors = instance.cleanup_errors
        with pytest.raises(RuntimeError, match="fresh live armed"):
            instance.run(lambda: calls.append("rejected_callback"),
                         cleanup=(lambda: calls.append("rejected_cleanup"),))
        assert calls == []
        assert _records(audit) == []
        assert instance._finished is False
        assert instance._report is None
        assert instance._channel.fileno() >= 0
        assert instance.cleanup_errors is previous_errors
        release.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert errors == []
        assert outcomes == [result]
        assert outcomes[0] is result
        assert calls == ["admitted"]
        assert len(_records(audit)) == 1
    finally:
        release.set()
        _cleanup_all(
            lambda: thread.join(timeout=5) if thread.ident is not None else None,
            lambda: _cleanup_watch(instance),
        )


def test_local_reentrant_rejection_no_cleanup(tmp_path):
    values, audit = _setup(tmp_path)
    instance = _arm(**values)
    calls = []
    result = object()

    def callback():
        previous_errors = instance.cleanup_errors
        with pytest.raises(RuntimeError, match="fresh live armed"):
            instance.run(lambda: calls.append("rejected_callback"),
                         cleanup=(lambda: calls.append("rejected_cleanup"),))
        assert calls == []
        assert _records(audit) == []
        assert instance._finished is False
        assert instance._report is None
        assert instance._channel.fileno() >= 0
        assert instance.cleanup_errors is previous_errors
        return result

    try:
        assert instance.run(callback, cleanup=(lambda: calls.append("admitted"),)) is result
        assert calls == ["admitted"]
        assert len(_records(audit)) == 1
    finally:
        _cleanup_watch(instance)


def test_local_arm_failure_reaped(tmp_path, monkeypatch):
    values, _ = _setup(tmp_path)
    primary = TimeoutError("synthetic readiness failure")
    failures = []
    arm = watchdog.arm

    def fail_readiness(self, *args, **kwargs):
        raise primary

    def retain_failure(**kwargs):
        try:
            return arm(**kwargs)
        except watchdog.ArmError as error:
            failures.append(error)
            raise

    monkeypatch.setattr(watchdog.socket.socket, "recv", fail_readiness)
    monkeypatch.setattr(watchdog, "arm", retain_failure)
    unexpected = None
    try:
        with pytest.raises(watchdog.ArmError) as caught:
            unexpected = _arm(**values)
        assert failures == [caught.value]
        assert caught.value is failures[0]
        assert caught.value.__cause__ is primary
        instance = caught.value.controller
        assert isinstance(instance._process, subprocess.Popen)
        assert instance._channel.fileno() == -1
        assert instance._process.returncode is not None
        assert instance.cleanup_errors == ()
        assert values["evidence_path"].exists()
    finally:
        _cleanup_watches(unexpected, *(error.controller for error in failures))


def test_local_delayed_controller_no_spawn(tmp_path):
    values, audit = _setup(tmp_path, lifetime=9)
    instance = _arm(**values)
    try:
        os.kill(instance._process.pid, signal.SIGSTOP)
        time.sleep(max(0, values["deadline"] - watchdog._REAP_SECONDS
                       + 0.1 - time.monotonic()))
        if instance._process.returncode is None:
            os.kill(instance._process.pid, signal.SIGCONT)
        report = _wait_controller(instance)
        assert report["teardown"]["attempted"] is False
        assert report["teardown"]["timed_out"] is True
        assert report["teardown"]["error"] == "local_deadline_exhausted"
        assert report["local_ok"] is False
        assert report["remote"] == report["billing"] == "UNKNOWN"
        assert _records(audit) == []
    finally:
        try:
            if instance._process.returncode is None:
                os.kill(instance._process.pid, signal.SIGCONT)
        finally:
            _cleanup_watch(instance)


def test_local_launch_overrun_unknown(tmp_path, monkeypatch):
    values, _ = _setup(tmp_path)
    commands = []
    popen = subprocess.Popen

    def delayed_launch(*args, **kwargs):
        process = popen(*args, **kwargs)
        commands.append(process)
        time.sleep(0.2)
        return process

    monkeypatch.setattr(watchdog.subprocess, "Popen", delayed_launch)
    try:
        started = time.monotonic()
        command = watchdog._bounded_command(
            values["teardown"], values["app_id"], 0.1, started + 5,
        )
        report = watchdog._result("finish", command)
        assert len(commands) == 1
        assert command["attempted"] is True
        assert command["launch_overrun"] is True
        assert command["timed_out"] is True
        assert command["error"] == "local_launch_deadline_unknown"
        assert command["leader_reaped"] is True
        assert report["local_ok"] is False
        assert report["remote"] == report["billing"] == "UNKNOWN"
    finally:
        _reap_all(*commands)
