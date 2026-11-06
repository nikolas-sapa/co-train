"""Adversarial SQL trainer wrapper boundaries; construction only."""

from __future__ import annotations

import builtins
import copy
import importlib.util
import inspect
import os
from pathlib import Path
import sys

import pytest

from train import verdict as V
from train.run_monitor import RunMonitor

WORKSPACE = Path(__file__).resolve().parents[1]
FRAMEWORKS = {
    "torch", "transformers", "trl", "unsloth", "unsloth_zoo", "vllm",
    "datasets", "peft", "accelerate", "bitsandbytes", "verifiers",
}
FORBIDDEN_TRAINER_METHODS = {
    "train", "save_model", "save_state", "resume", "resume_from_checkpoint",
    "push_to_hub",
}


def _load_api(monkeypatch):
    path = Path(os.environ.get(
        "TASK8A_MODULE", WORKSPACE / "train/sql_training_run.py"
    ))
    spec = importlib.util.spec_from_file_location("train.sql_training_run", path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def api(monkeypatch):
    return _load_api(monkeypatch)


class _Trainer:
    def __init__(self, events):
        self.events = events
        self.callbacks = []
        self.forbidden = []

    def __getattribute__(self, name):
        if name in FORBIDDEN_TRAINER_METHODS:
            object.__getattribute__(self, "forbidden").append(name)
            raise AssertionError(f"forbidden trainer operation: {name}")
        return object.__getattribute__(self, name)

    def add_callback(self, callback):
        self.events.append("attach")
        self.callbacks.append(callback)


class _PoisonPath:
    def __init__(self, name, attempts):
        self.name = name
        self.attempts = attempts

    def __fspath__(self):
        self.attempts.append(self.name)
        raise AssertionError(f"forbidden path access: {self.name}")


def _step(a=0.4, b=1.0):
    return {"loss": 0.01, V.ZERO_STD_KEY: a, V.LOGP_DIFF_KEY: b}


@pytest.mark.parametrize(
    ("invalid", "message"),
    [
        ("model_revision", "model_revision must be a full 40-hex revision"),
        ("max_seq_length", "max_seq_length must be a positive integer"),
        ("steps", "steps must be a positive integer"),
    ],
)
def test_native_input_refusal_precedes_wrapper_and_path_work(
    api, monkeypatch, invalid, message
):
    native = api.native_training
    events = []
    path_attempts = []

    class PoisonTasks:
        def __iter__(self):
            events.append("task-iteration")
            raise AssertionError("tasks enumerated")

    tasks = PoisonTasks()
    db_root = _PoisonPath("db_root", path_attempts)
    output_dir = _PoisonPath("output_dir", path_attempts)
    model_dir = _PoisonPath("model_dir", path_attempts)
    root = _PoisonPath("root", path_attempts)
    values = {
        "model_revision": "a" * 40,
        "max_seq_length": 8192,
        "steps": 200,
    }
    values[invalid] = {
        "model_revision": "main",
        "max_seq_length": True,
        "steps": 0,
    }[invalid]
    original_builder = native.build_sql_trainer
    calls = []
    failures = []

    def delegated(*args, **kwargs):
        calls.append((args, kwargs))
        try:
            return original_builder(*args, **kwargs)
        except ValueError as exc:
            failures.append(exc)
            raise

    def forbidden(*args, **kwargs):
        events.append("forbidden-operation")
        raise AssertionError("wrapper continued after native input refusal")

    monkeypatch.setattr(native, "build_sql_trainer", delegated)
    monkeypatch.setattr(api, "RunMonitor", forbidden)
    monkeypatch.setattr(api, "_make_callback", forbidden)
    monkeypatch.setattr(native, "_load_runtime", forbidden)
    monkeypatch.setattr(native.native_model, "verify_local_model", forbidden)
    monkeypatch.setattr(native.sql_bridge, "prepare_sql_training", forbidden)

    import_attempts = []
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.split(".")[0] in FRAMEWORKS:
            import_attempts.append(name)
            raise AssertionError(f"forbidden framework import: {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with pytest.raises(ValueError) as caught:
        api.build_monitored_sql_trainer(
            tasks,
            db_root,
            output_dir=output_dir,
            model_dir=model_dir,
            model_revision=values["model_revision"],
            max_seq_length=values["max_seq_length"],
            steps=values["steps"],
            root=root,
        )

    assert len(calls) == 1
    assert len(failures) == 1 and caught.value is failures[0]
    assert str(caught.value) == message
    assert calls[0][0][0] is tasks and calls[0][0][1] is db_root
    assert calls[0][1]["output_dir"] is output_dir
    assert calls[0][1]["model_dir"] is model_dir
    assert calls[0][1]["root"] is root
    assert events == []
    assert path_attempts == []
    assert import_attempts == []


def test_default_forwarding_consumes_tasks_only_inside_delegate(api, monkeypatch):
    native = api.native_training
    default_root = inspect.signature(native.build_sql_trainer).parameters["root"].default
    events = []
    state = {"builder_active": False, "iterations": 0}
    yielded = [object(), object()]
    db_root = object()
    sentinels = {
        name: object()
        for name in ("output_dir", "model_dir", "model_revision", "max_seq_length")
    }
    trainer = _Trainer(events)

    class SingleUseTasks:
        def __iter__(self):
            state["iterations"] += 1
            events.append("iter")
            assert state["builder_active"], "tasks enumerated outside builder"
            assert state["iterations"] == 1, "tasks enumerated more than once"
            for index, item in enumerate(yielded, 1):
                events.append(f"yield-{index}")
                yield item
            events.append("exhausted")

    tasks = SingleUseTasks()
    calls = []

    def wiring_builder(*args, **kwargs):
        events.append("builder-start")
        state["builder_active"] = True
        calls.append((args, kwargs))
        consumed = list(args[0])
        assert consumed == yielded
        state["builder_active"] = False
        events.append("builder-return")
        return trainer

    real_monitor_factory = RunMonitor

    def monitor_factory():
        assert events[-1] == "builder-return"
        events.append("monitor")
        return real_monitor_factory()

    callback = object()

    def callback_factory(monitor):
        assert type(monitor) is RunMonitor
        events.append("callback")
        return callback

    monkeypatch.setattr(native, "build_sql_trainer", wiring_builder)
    monkeypatch.setattr(api, "RunMonitor", monitor_factory)
    monkeypatch.setattr(api, "_make_callback", callback_factory)
    result = api.build_monitored_sql_trainer(
        tasks, db_root, **sentinels
    )

    assert result.trainer is trainer
    assert type(result.monitor) is RunMonitor
    assert trainer.callbacks == [callback]
    assert trainer.forbidden == []
    assert state["iterations"] == 1
    assert events == [
        "builder-start", "iter", "yield-1", "yield-2", "exhausted",
        "builder-return", "monitor", "callback", "attach",
    ]
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] is tasks and args[1] is db_root
    assert kwargs.keys() == sentinels.keys() | {"steps", "root"}
    assert all(kwargs[name] is value for name, value in sentinels.items())
    assert kwargs["steps"] == 200
    assert kwargs["root"] is default_root


def test_task_iteration_failure_has_no_wrapper_tail(api, monkeypatch):
    events = []
    failure = RuntimeError("synthetic iteration failure")
    item = object()
    state = {"iterations": 0}
    trainer = _Trainer(events)

    class FailingTasks:
        def __iter__(self):
            state["iterations"] += 1
            events.append("iter")
            assert state["iterations"] == 1
            yield item
            events.append("raise")
            raise failure

    tasks = FailingTasks()
    yielded = []
    db_root = object()
    calls = []
    failures = []

    def wiring_builder(*args, **kwargs):
        events.append("builder-start")
        calls.append((args, kwargs))
        try:
            for task in args[0]:
                yielded.append(task)
        except RuntimeError as exc:
            failures.append(exc)
            raise
        return trainer

    def forbidden_tail(*args, **kwargs):
        events.append("wrapper-tail")
        raise AssertionError("wrapper continued after task iteration failed")

    monkeypatch.setattr(api.native_training, "build_sql_trainer", wiring_builder)
    monkeypatch.setattr(api, "RunMonitor", forbidden_tail)
    monkeypatch.setattr(api, "_make_callback", forbidden_tail)
    with pytest.raises(RuntimeError) as caught:
        api.build_monitored_sql_trainer(
            tasks,
            db_root,
            output_dir=object(),
            model_dir=object(),
            model_revision=object(),
            max_seq_length=object(),
        )

    assert len(calls) == 1
    assert calls[0][0][0] is tasks and calls[0][0][1] is db_root
    assert yielded == [item]
    assert len(failures) == 1 and caught.value is failures[0] is failure
    assert state["iterations"] == 1
    assert events == ["builder-start", "iter", "raise"]
    assert trainer.callbacks == []
    assert trainer.forbidden == []


def test_constructed_callbacks_have_isolated_defensive_histories(api, monkeypatch):
    from transformers.trainer_callback import (
        TrainerCallback,
        TrainerControl,
        TrainerState,
    )

    events = []
    trainers = [_Trainer(events), _Trainer(events)]
    calls = []

    def wiring_builder(*args, **kwargs):
        calls.append((args, kwargs))
        return trainers[len(calls) - 1]

    monkeypatch.setattr(api.native_training, "build_sql_trainer", wiring_builder)
    kwargs = {
        "output_dir": object(),
        "model_dir": object(),
        "model_revision": object(),
        "max_seq_length": object(),
    }
    first = api.build_monitored_sql_trainer(object(), object(), **kwargs)
    second = api.build_monitored_sql_trainer(object(), object(), **kwargs)
    callback_a, callback_b = (trainer.callbacks[0] for trainer in trainers)

    assert len(calls) == 2
    assert len(trainers[0].callbacks) == len(trainers[1].callbacks) == 1
    assert isinstance(callback_a, TrainerCallback)
    assert isinstance(callback_b, TrainerCallback)
    assert type(callback_a).__bases__ == (TrainerCallback,)
    assert type(callback_b).__bases__ == (TrainerCallback,)
    assert type(first.monitor) is type(second.monitor) is RunMonitor
    assert first.monitor is not second.monitor

    control_a, control_b = TrainerControl(), TrainerControl()
    state = TrainerState()
    healthy = {
        **_step(),
        "extra": {"nested": [1]},
    }
    original_healthy = copy.deepcopy(healthy)
    assert callback_a.on_log(None, state, control_a, logs=healthy) is control_a
    assert healthy == original_healthy
    assert control_a.should_training_stop is False
    healthy["extra"]["nested"].append(2)
    healthy[V.ZERO_STD_KEY] = 0.99
    exported = first.monitor.rows
    assert exported == [original_healthy]
    exported[0]["extra"]["nested"].append(3)
    exported[0][V.LOGP_DIFF_KEY] = 4.0
    exported.clear()
    assert first.monitor.rows == [original_healthy]
    assert second.monitor.rows == []

    fault = {"loss": 0.01}
    fault_copy = copy.deepcopy(fault)
    assert callback_a.on_log(None, state, control_a, logs=fault) is control_a
    assert fault == fault_copy
    assert first.monitor.aborted is not None
    assert V.ZERO_STD_KEY in first.monitor.aborted
    assert control_a.should_training_stop is True

    healthy_b = _step()
    assert callback_b.on_log(None, state, control_b, logs=healthy_b) is control_b
    assert second.monitor.aborted is None
    assert control_b.should_training_stop is False
    assert control_a.should_training_stop is True


def test_latched_abort_stops_each_fresh_control(api):
    from transformers.trainer_callback import TrainerControl, TrainerState

    monitor = RunMonitor()
    callback = api._make_callback(monitor)
    state = TrainerState()
    initial_control = TrainerControl()
    fault = {"loss": 0.01, V.ZERO_STD_KEY: 0.4, V.LOGP_DIFF_KEY: None}
    assert callback.on_log(None, state, initial_control, logs=fault) is initial_control
    reason = monitor.aborted
    assert reason is not None and V.LOGP_DIFF_KEY in reason
    assert monitor.rows == [fault]

    healthy = _step()
    later_fault = {"loss": 0.01}
    for logs in (None, healthy, later_fault):
        control = TrainerControl()
        assert control.should_training_stop is False
        assert callback.on_log(None, state, control, logs=logs) is control
        assert monitor.aborted == reason
        assert control.should_training_stop, (
            "fresh control after logs=None did not receive latched stop "
            "(negative-control target)"
        )

    assert monitor.rows == [fault, healthy, later_fault]
    assert len(monitor.rows) == 3


def test_nonstep_telemetry_preserves_callback_step_axis(api):
    from transformers.trainer_callback import TrainerControl, TrainerState

    monitor = RunMonitor()
    callback = api._make_callback(monitor)
    control = TrainerControl()
    state = TrainerState()

    for _ in range(9):
        for logs in (
            None,
            {"train_loss": 0.01, V.ZERO_STD_KEY: True, V.LOGP_DIFF_KEY: None},
            {"eval_loss": 0.01, V.ZERO_STD_KEY: True, V.LOGP_DIFF_KEY: None},
            _step(a=0.61),
        ):
            before = copy.deepcopy(logs)
            assert callback.on_log(None, state, control, logs=logs) is control
            assert logs == before
            assert monitor.aborted is None
            assert control.should_training_stop is False

    assert len(monitor.rows) == 27
    assert len(V.training_steps(monitor.rows)) == 9
    tenth = _step(a=0.61)
    assert callback.on_log(None, state, control, logs=tenth) is control
    assert monitor.aborted == V.criterion_a_sustained(monitor.rows)[0]
    assert "steps 0-9" in monitor.aborted
    assert "10 consecutive" in monitor.aborted
    assert control.should_training_stop is True
    assert len(monitor.rows) == 28
    assert len(V.training_steps(monitor.rows)) == 10


def test_callback_import_failure_propagates_after_builder(api, monkeypatch):
    events = []
    trainer = _Trainer(events)
    failure = ImportError("synthetic callback import failure")

    def wiring_builder(*args, **kwargs):
        events.append("builder")
        return trainer

    real_monitor_factory = RunMonitor

    def monitor_factory():
        events.append("monitor")
        return real_monitor_factory()

    monkeypatch.setattr(api.native_training, "build_sql_trainer", wiring_builder)
    monkeypatch.setattr(api, "RunMonitor", monitor_factory)
    original_import = builtins.__import__

    def intercept_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "transformers.trainer_callback":
            events.append("import")
            raise failure
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", intercept_import)
    with pytest.raises(ImportError) as caught:
        api.build_monitored_sql_trainer(
            object(),
            object(),
            output_dir=object(),
            model_dir=object(),
            model_revision=object(),
            max_seq_length=object(),
        )

    assert caught.value is failure
    assert events == ["builder", "monitor", "import"]
    assert trainer.callbacks == []
    assert trainer.forbidden == []
