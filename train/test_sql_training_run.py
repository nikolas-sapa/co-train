"""Constructor wiring spies and real installed callback behavior, never training."""
from __future__ import annotations

import builtins
import copy
import importlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import typing

import pytest

from train import verdict as V
from train.run_monitor import RunMonitor

WORKSPACE = Path(__file__).resolve().parents[1]
FRAMEWORKS = {
    "torch", "trl", "unsloth", "unsloth_zoo", "vllm", "datasets", "peft",
    "accelerate", "bitsandbytes", "verifiers",
}


def _api():
    path = Path(os.environ.get("TASK8A_MODULE", WORKSPACE / "train/sql_training_run.py"))
    spec = importlib.util.spec_from_file_location("train.sql_training_run", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _step(a=0.4, b=1.0):
    return {"loss": 0.01, V.ZERO_STD_KEY: a, V.LOGP_DIFF_KEY: b}


def _kwargs():
    return dict(output_dir=WORKSPACE / "never-output",
                model_dir=WORKSPACE / "unread-model",
                model_revision="a" * 40, max_seq_length=8192, root=WORKSPACE)


def _check(condition, message):
    # Active under -O too.
    if not condition:
        raise AssertionError(message)


def _guard(monkeypatch, *, callbacks):
    attempts = []
    original = builtins.__import__

    def deny(*args, **kwargs):
        attempts.append(("operation", repr(args)))
        raise AssertionError("forbidden model/training/network/process operation")

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in FRAMEWORKS | (set() if callbacks else {"transformers"}):
            attempts.append(("import", name))
            raise AssertionError(f"forbidden framework import: {name}")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)

    def audit(event, args):
        if event.startswith(("socket.", "subprocess.", "os.exec", "os.spawn")) or event in {
            "os.system", "os.fork", "os.posix_spawn", "os.remove", "os.rename",
            "os.mkdir", "os.rmdir", "os.truncate", "os.link", "os.symlink",
        }:
            deny(event, args)
        if event == "open":
            path, mode, flags = args
            if ((isinstance(mode, str) and any(c in mode for c in "wax+"))
                    or (isinstance(flags, int) and flags & (
                        os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
                    or (isinstance(path, (str, bytes)) and any(
                        s in os.fsdecode(path) for s in (
                            "unread-model", "never-output", ".safetensors", ".bin")))):
                deny(event, args)

    # Only fresh children use audit hooks, which cannot be removed.
    sys.addaudithook(audit)
    return attempts, deny


def _child(mode):
    from train import native_training as native
    from bench.task import SqlTask

    patch = pytest.MonkeyPatch()
    attempts, deny = _guard(patch, callbacks=mode == "interop")
    for owner, name in (
        (native, "_load_runtime"), (native.native_model, "verify_local_model"),
        (native.sql_bridge, "prepare_sql_training"),
    ):
        patch.setattr(owner, name, deny)

    if mode == "interop":
        from transformers.trainer_callback import TrainerCallback, TrainerControl, TrainerState
        api = _api()
        monitor = RunMonitor()
        callback = api._make_callback(monitor)
        control, state = TrainerControl(), TrainerState()
        _check(isinstance(callback, TrainerCallback), "not actual installed callback")
        _check(type(callback).__bases__ == (TrainerCallback,), "fake callback base")
        for _ in range(12):
            _check(callback.on_log(None, state, control, logs=_step()) is control,
                   "control identity changed")
            _check(not control.should_training_stop, "healthy stop")
        _check(len(monitor.rows) == 12 and monitor.finalize() == (True, []),
               "actual monitor did not receive twelve healthy rows")
        callback.on_log(None, state, control, logs={"loss": 0.01})
        reason = monitor.aborted
        _check(reason is not None and control.should_training_stop, "fault did not stop")
        for row in (_step(), None):
            _check(callback.on_log(None, state, control, logs=row) is control,
                   "latched control identity changed")
            _check(control.should_training_stop and monitor.aborted == reason, "stop cleared")
        _check(attempts == [], f"guard attempts: {attempts}")
        from importlib.metadata import version
        print(json.dumps({"mode": mode, "healthy_rows": 12, "same_control": 12,
                          "healthy_stop": False, "sticky_stop": True,
                          "transformers": version("transformers"),
                          "base_file": inspect.getfile(TrainerCallback),
                          "production_factory_file": inspect.getfile(api._make_callback),
                          "attempts": attempts}))
        return

    if mode == "inert":
        patch.setattr(native, "build_sql_trainer", deny)
        patch.setattr(importlib.import_module("train.run_monitor"), "RunMonitor", deny)
        _api()
        _check(attempts == [], f"import side effects: {attempts}")
        print(json.dumps({"mode": mode, "attempts": attempts}))
        return

    api = _api()
    patch.setattr(api, "RunMonitor", deny)
    patch.setattr(api, "_make_callback", deny)
    original = native.build_sql_trainer
    calls, exceptions = [], []

    def delegated(*args, **kwargs):
        calls.append((args, kwargs))
        try:
            return original(*args, **kwargs)
        except BaseException as exc:
            exceptions.append(exc)
            raise

    patch.setattr(native, "build_sql_trainer", delegated)
    status = native.guards.frontier_taskset_status(WORKSPACE)
    _check(not status.ok, "expected real frontier refusal absent")
    expected = (
        "the co-training pipeline is gated on spec §344 and the gate is shut:\n  - "
        + "\n  - ".join(status.reasons)
        + "\n\nThe dead-group probe (train/dead_group_probe.py) is NOT gated on "
        "this, and is the only GPU spend the spec authorises."
    )
    task = SqlTask("guard-only", "Not executed", "", "SELECT 1", "guard-only",
                   str(WORKSPACE / "unread-model/db.sqlite"), "simple", "derived",
                   "fixture", "fixture", "fixture")
    try:
        api.build_monitored_sql_trainer([task], WORKSPACE, **_kwargs())
    except native.guards.PreconditionUnmet as exc:
        _check(type(exc) is native.guards.PreconditionUnmet, "wrong exception class")
        _check(len(exceptions) == 1 and exc is exceptions[0], "original exception replaced")
        _check(str(exc) == expected, "wrong refusal reason")
        tb = exc.__traceback__
        while tb.tb_next:
            tb = tb.tb_next
        _check(tb.tb_frame.f_code is native.guards.require_frontier_taskset.__code__,
               "refusal did not originate in original frontier gate")
    else:
        raise AssertionError("real gate bypassed")
    _check(len(calls) == 1, "original delegation count")
    _check(attempts == [], f"side effects: {attempts}")
    _check(not _kwargs()["output_dir"].exists(), "output created")
    print(json.dumps({"mode": mode, "delegate": len(calls),
                      "class": "train.guards.PreconditionUnmet",
                      "source": "train.guards.require_frontier_taskset",
                      "reason": expected, "attempts": attempts}))


def _fresh(mode, optimized=False):
    command = [
        sys.executable, "-I", "-B", "-Werror",
    ] + (["-O"] if optimized else []) + [
        "-c", f"import sys; sys.path.insert(0, {str(WORKSPACE)!r}); "
              f"from train.test_sql_training_run import _child; _child({mode!r})",
    ]
    result = subprocess.run(command, cwd=WORKSPACE, env={
        **os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1",
    }, capture_output=True, text=True, timeout=12)
    print(json.dumps({"child_command": command, "exit": result.returncode,
                      "stdout": result.stdout, "stderr": result.stderr}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["attempts"] == []


@pytest.mark.parametrize("optimized", [False, True], ids=["normal", "optimized"])
def test_gate(optimized):
    _fresh("gate", optimized)


def test_import_inert():
    _fresh("inert")


def test_installed_callback():
    # Mandatory, no skip or replacement subclass.
    _fresh("interop")


@pytest.fixture
def api(monkeypatch):
    from train import native_training as native

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected native/model/preparation operation")

    for owner, name in ((native, "_load_runtime"),
                        (native.native_model, "verify_local_model"),
                        (native.sql_bridge, "prepare_sql_training")):
        monkeypatch.setattr(owner, name, forbidden)
    return _api()


@pytest.fixture
def wiring(api, monkeypatch):
    # Fake constructor and base prove forwarding only, not installed interop.
    events, callbacks = [], []
    error = RuntimeError("original exception identity")
    state = SimpleNamespace(failure=None, error=error, allow_events=False)

    class Trainer:
        def __getattribute__(self, name):
            if name in {"train", "save_model", "save_state", "resume", "push_to_hub"}:
                raise AssertionError(f"forbidden trainer operation {name}")
            if name == "add_callback" and state.failure == "lookup":
                events.append("lookup")
                raise error
            return object.__getattribute__(self, name)

        def add_callback(self, callback):
            events.append("attach")
            callbacks.append(callback)
            if state.failure == "call":
                raise error

    trainer = Trainer()

    class Base:
        def __init__(self):
            events.append("callback")

        def __getattribute__(self, name):
            if name.startswith("on_") and not state.allow_events:
                raise AssertionError(f"constructor invoked callback event {name}")
            return object.__getattribute__(self, name)

        def __getattr__(self, name):
            raise AssertionError(f"unexpected callback event {name}")

    original_import = builtins.__import__

    def imports(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "transformers.trainer_callback":
            return SimpleNamespace(TrainerCallback=Base)
        if name.split(".")[0] in FRAMEWORKS | {"transformers"}:
            raise AssertionError(f"unexpected heavyweight import {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", imports)
    calls = []

    def builder(*args, **kwargs):
        events.append("builder")
        calls.append((args, kwargs))
        if state.failure == "original":
            raise error
        return trainer

    def monitor():
        assert events == ["builder"], "monitor created without original delegation"
        events.append("monitor")
        return RunMonitor()

    monkeypatch.setattr(api.native_training, "build_sql_trainer", builder)
    monkeypatch.setattr(api, "RunMonitor", monitor)
    state.__dict__.update(api=api, trainer=trainer, events=events,
                          callbacks=callbacks, calls=calls)
    return state


@pytest.mark.parametrize("steps", [1, 17, 200])
def test_forwarding(wiring, steps):
    class Tasks:
        def __iter__(self):
            raise AssertionError("wrapper enumerated tasks")

    tasks, db = Tasks(), object()
    values = {name: object() for name in (
        "output_dir", "model_dir", "model_revision", "max_seq_length", "root")}
    values["steps"] = steps
    result = wiring.api.build_monitored_sql_trainer(tasks, db, **values)
    assert result.trainer is wiring.trainer
    assert wiring.events == ["builder", "monitor", "callback", "attach"]
    assert len(wiring.calls) == len(wiring.callbacks) == 1
    args, kwargs = wiring.calls[0]
    assert len(args) == 2 and args[0] is tasks and args[1] is db
    assert kwargs.keys() == values.keys()
    assert all(kwargs[k] is v for k, v in values.items())
    assert type(result.monitor) is RunMonitor
    assert result.monitor.rows == []  # no callback events during construction
    wiring.allow_events = True
    row, control = _step(), SimpleNamespace(should_training_stop=False)
    assert wiring.callbacks[0].on_log(None, None, control, logs=row) is control
    assert result.monitor.rows == [row]  # callback owns returned concrete monitor


def test_original_failure(wiring):
    wiring.failure = "original"
    with pytest.raises(RuntimeError) as caught:
        wiring.api.build_monitored_sql_trainer(object(), object(), **_kwargs())
    assert caught.value is wiring.error
    assert wiring.events == ["builder"] and len(wiring.calls) == 1
    assert wiring.callbacks == []


@pytest.mark.parametrize("stage", ["lookup", "call"])
def test_attachment_failure(wiring, stage):
    wiring.failure = stage
    with pytest.raises(RuntimeError) as caught:
        wiring.api.build_monitored_sql_trainer(object(), object(), **_kwargs())
    assert caught.value is wiring.error
    assert wiring.events == ["builder", "monitor", "callback",
                             "lookup" if stage == "lookup" else "attach"]
    assert len(wiring.calls) == 1
    assert len(wiring.callbacks) == (stage == "call")


@pytest.fixture
def callback(api):
    from transformers.trainer_callback import TrainerCallback, TrainerControl, TrainerState

    monitor = RunMonitor()
    cb = api._make_callback(monitor)
    assert isinstance(cb, TrainerCallback)
    return cb, monitor, TrainerControl(), TrainerState()


def _replay(callback, rows):
    cb, monitor, control, state = callback
    expected = RunMonitor()
    for row in rows:
        expected.observe(row)
        assert cb.on_log(None, state, control, logs=row) is control
        assert monitor.aborted == expected.aborted
        assert monitor.rows == expected.rows
        assert control.should_training_stop is (expected.aborted is not None)
    assert monitor.finalize() == expected.finalize() == V.run_verdict(rows)
    return monitor, control


@pytest.mark.parametrize("case", ["sustained", "ceiling"])
def test_callback_a(callback, case):
    rows = [_step(a=0.61 if case == "sustained" else 0.60)
            for _ in range(10 if case == "sustained" else 12)]
    monitor, control = _replay(callback, rows)
    assert control.should_training_stop is (case == "sustained")
    if case == "sustained":
        assert monitor.aborted == V.criterion_a_sustained(rows)[0]
        assert "10 consecutive" in monitor.aborted


@pytest.mark.parametrize("case", ["trend", "ratio-boundary", "ratio-breach"])
def test_callback_b(callback, case):
    if case == "trend":
        rows = [_step(b=1 + i / 100) for i in range(10)]
    else:
        rows = [_step() for _ in range(10)] + [
            _step(b=3.0 if case == "ratio-boundary" else 3.01)]
    monitor, control = _replay(callback, rows)
    assert control.should_training_stop is (case != "ratio-boundary")
    if monitor.aborted:
        assert monitor.aborted == V.criterion_b(rows, required=True)[0][0]


@pytest.mark.parametrize("key", [V.ZERO_STD_KEY, V.LOGP_DIFF_KEY], ids=["A", "B"])
@pytest.mark.parametrize("fault", ["missing", "nan", "posinf", "neginf"])
def test_callback_fault(callback, monkeypatch, key, fault):
    cb, monitor, control, state = callback
    row = _step()
    if fault == "missing":
        del row[key]
    else:
        row[key] = {"nan": float("nan"), "posinf": float("inf"),
                    "neginf": float("-inf")}[fault]
    before = copy.deepcopy(row)
    original, received = RunMonitor.observe, []

    def observe(self, log):
        if self is monitor:
            received.append(log)
        return original(self, log)

    monkeypatch.setattr(RunMonitor, "observe", observe)
    assert cb.on_log(None, state, control, logs=row) is control
    assert received == [row] and received[0] is row
    assert row.keys() == before.keys()
    assert all(row[k] is before[k] or row[k] == before[k] for k in row)
    reason = monitor.aborted
    assert reason and key in reason and control.should_training_stop
    expected = RunMonitor()
    assert original(expected, row) == reason
    for later in (_step(), {"eval_loss": 0.01}, None):
        assert cb.on_log(None, state, control, logs=later) is control
        assert monitor.aborted == reason and control.should_training_stop
    assert monitor.finalize() == V.run_verdict(monitor.rows)


def test_callback_nonstep(callback):
    cb, monitor, control, state = callback
    control.should_training_stop = True
    for row, size in ((None, 0), ({}, 1), ({"eval_loss": 0.01}, 2), (_step(), 3)):
        assert cb.on_log(None, state, control, logs=row) is control
        assert len(monitor.rows) == size and monitor.aborted is None
        assert control.should_training_stop
    assert len(V.training_steps(monitor.rows)) == 1
    cb.on_log(None, state, control, logs={"loss": 0.01})
    reason = monitor.aborted
    for row in (None, _step()):
        cb.on_log(None, state, control, logs=row)
        assert reason is not None and monitor.aborted == reason
        assert control.should_training_stop


def test_signature(api):
    from train.sql_reporting import ReportingConfig

    original = api.native_training.build_sql_trainer
    actual = inspect.signature(api.build_monitored_sql_trainer)
    expected = inspect.signature(original)
    assert list(actual.parameters) == list(expected.parameters)
    namespace = {"ReportingConfig": ReportingConfig}
    actual_types = typing.get_type_hints(api.build_monitored_sql_trainer, localns=namespace)
    expected_types = typing.get_type_hints(original, localns=namespace)
    for name, param in expected.parameters.items():
        mirrored = actual.parameters[name]
        assert mirrored.kind == param.kind
        assert mirrored.default == param.default
        assert actual_types[name] == expected_types[name]
    assert expected.parameters["steps"].default == 200
    assert actual_types["reporting"] == ReportingConfig | None
    assert api.MonitoredSqlTrainer._fields == ("trainer", "monitor")