"""Monitored forwarding and real monitor behavior, never actual TRL training.

Shares only NEW-test private constructor fixtures. Callback base below is an
explicit lightweight double; production _make_callback/on_log and RunMonitor
remain real. Installed-framework callback interop belongs to existing tests.
"""

from __future__ import annotations

import builtins
import copy
import importlib
import inspect
from types import SimpleNamespace

import pytest

from train.test_native_training_reporting import (  # noqa: F401
    REVISION,
    assert_real_reporting,
    native_wiring,
    no_frameworks,
    sql_tasks,
)


@pytest.fixture
def api():
    return importlib.import_module("train.sql_training_run")


@pytest.fixture
def callback_base(monkeypatch, no_frameworks):
    """Fake base ONLY; do not import or claim installed Transformers interop."""
    state = SimpleNamespace(events=[], created=[])
    original = builtins.__import__

    class Base:
        def __init__(self):
            state.events.append("callback")
            state.created.append(self)

    def intercepted(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "transformers.trainer_callback":
            return SimpleNamespace(TrainerCallback=Base)
        return original(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", intercepted)
    return state


@pytest.fixture
def wrapper_wiring(api, callback_base, monkeypatch):
    """Delegation-only doubles, not the real native constructor or framework."""
    from train.run_monitor import RunMonitor

    state = SimpleNamespace(
        events=callback_base.events, calls=[], monitors=[], attached=[],
        failure=None, attach_failure=None,
    )

    class Trainer:
        def add_callback(self, callback):
            state.events.append("attach")
            state.attached.append(callback)
            if state.attach_failure is not None:
                raise state.attach_failure

        def __getattribute__(self, name):
            if name in {"train", "save_model", "save_state", "resume", "push_to_hub"}:
                raise AssertionError(f"wrapper attempted {name}")
            return object.__getattribute__(self, name)

    state.trainer = Trainer()

    def builder(*args, **kwargs):
        state.events.append("builder")
        state.calls.append((args, kwargs))
        if state.failure is not None:
            raise state.failure
        return state.trainer

    def monitor():
        state.events.append("monitor")
        instance = RunMonitor()
        state.monitors.append(instance)
        return instance

    monkeypatch.setattr(api.native_training, "build_sql_trainer", builder)
    monkeypatch.setattr(api, "RunMonitor", monitor)
    state.builder = builder
    state.api = api
    state.base = callback_base
    return state


def _ordinary_kwargs():
    # Identity-only delegation check; the real builder never receives these.
    return {key: object() for key in (
        "output_dir", "model_dir", "model_revision", "max_seq_length", "steps", "root",
    )}


def test_monitored_signature_remains_explicit_and_matches_native(api):
    actual = inspect.signature(api.build_monitored_sql_trainer)
    expected = inspect.signature(api.native_training.build_sql_trainer)
    assert list(actual.parameters) == list(expected.parameters)
    assert actual.parameters["reporting"].kind is inspect.Parameter.KEYWORD_ONLY
    assert actual.parameters["reporting"].default is None
    for name, parameter in expected.parameters.items():
        assert actual.parameters[name].kind == parameter.kind
        assert actual.parameters[name].default == parameter.default
        assert actual.parameters[name].annotation == parameter.annotation


@pytest.mark.parametrize("explicit_none", [False, True])
def test_defaults_delegate_once_to_old_signature_without_new_kwarg(
    wrapper_wiring, monkeypatch, explicit_none,
):
    state = wrapper_wiring
    tasks, db = object(), object()
    values = _ordinary_kwargs()
    before = dict(values)

    def old_signature(
        tasks, db_root, *, output_dir, model_dir, model_revision,
        max_seq_length, steps, root,
    ):
        return state.builder(
            tasks, db_root, output_dir=output_dir, model_dir=model_dir,
            model_revision=model_revision, max_seq_length=max_seq_length,
            steps=steps, root=root,
        )

    monkeypatch.setattr(state.api.native_training, "build_sql_trainer", old_signature)
    result = state.api.build_monitored_sql_trainer(
        tasks, db, **values, **({"reporting": None} if explicit_none else {}),
    )
    assert state.events == ["builder", "monitor", "callback", "attach"]
    assert len(state.calls) == len(state.attached) == len(state.monitors) == 1
    args, forwarded = state.calls[0]
    assert args[0] is tasks and args[1] is db
    assert forwarded.keys() == values.keys()
    assert all(forwarded[key] is value for key, value in values.items())
    assert values == before
    assert result.trainer is state.trainer
    assert result.monitor is state.monitors[0]


@pytest.mark.parametrize("malformed", [False, True])
def test_identical_option_forwarded_once_without_wrapper_validation(wrapper_wiring, malformed):
    from train.sql_reporting import ReportingConfig

    state = wrapper_wiring
    option = False if malformed else ReportingConfig(shortcut_ids=("fixture_shortcut",))

    class Tasks:
        def __iter__(self):
            raise AssertionError("wrapper enumerated caller tasks")

    tasks, db = Tasks(), object()
    kwargs = _ordinary_kwargs()
    result = state.api.build_monitored_sql_trainer(tasks, db, **kwargs, reporting=option)
    assert state.events == ["builder", "monitor", "callback", "attach"]
    assert len(state.calls) == len(state.attached) == 1
    args, forwarded = state.calls[0]
    assert args[0] is tasks and args[1] is db
    assert set(forwarded) == set(kwargs) | {"reporting"}
    assert forwarded["reporting"] is option
    assert all(forwarded[name] is value for name, value in kwargs.items())
    assert result.trainer is state.trainer and result.monitor is state.monitors[0]
    assert result.monitor.rows == [] and result.monitor.aborted is None


def test_builder_failure_preserves_identity_without_monitor_callback_attach(wrapper_wiring):
    from train.sql_reporting import ReportingConfig

    state = wrapper_wiring
    failure = RuntimeError("original builder failure")
    state.failure = failure
    with pytest.raises(RuntimeError) as caught:
        state.api.build_monitored_sql_trainer(
            object(), object(), **_ordinary_kwargs(), reporting=ReportingConfig(),
        )
    assert caught.value is failure
    assert state.events == ["builder"]
    assert len(state.calls) == 1
    assert state.monitors == state.base.created == state.attached == []


def test_attachment_failure_keeps_exact_exception_and_single_attach(wrapper_wiring):
    from train.sql_reporting import ReportingConfig

    state = wrapper_wiring
    failure = RuntimeError("original attachment failure")
    state.attach_failure = failure
    with pytest.raises(RuntimeError) as caught:
        state.api.build_monitored_sql_trainer(
            object(), object(), **_ordinary_kwargs(), reporting=ReportingConfig(),
        )
    assert caught.value is failure
    assert state.events == ["builder", "monitor", "callback", "attach"]
    assert len(state.attached) == 1


@pytest.mark.parametrize("malformed", [False, True])
def test_real_preflight_failure_propagates_before_all_monitored_work(
    api, monkeypatch, tmp_path, malformed,
):
    from train import grpo_ptc, guards, sql_reporting

    original_builder = api.native_training.build_sql_trainer
    calls, failures, attempted = [], [], []
    option = False if malformed else sql_reporting.ReportingConfig()
    with pytest.raises(guards.PreconditionUnmet) as expected:
        grpo_ptc.native_sql_preflight(root=guards.REPO_ROOT, steps=200)

    def delegated(*args, **kwargs):
        calls.append((args, kwargs))
        try:
            return original_builder(*args, **kwargs)
        except Exception as exc:
            failures.append(exc)
            raise

    def forbidden(*args, **kwargs):
        attempted.append("downstream")
        raise AssertionError("work before real closed preflight")

    monkeypatch.setattr(api.native_training, "build_sql_trainer", delegated)
    for owner, name in (
        (api, "RunMonitor"), (api, "_make_callback"),
        (api.native_training, "_load_runtime"),
        (api.native_training.native_model, "verify_local_model"),
        (api.native_training.sql_bridge, "prepare_sql_training"),
        (sql_reporting, "make_channel"), (sql_reporting, "validate_config"),
    ):
        monkeypatch.setattr(owner, name, forbidden)
    output = tmp_path / "never-created"
    with pytest.raises(guards.PreconditionUnmet) as caught:
        api.build_monitored_sql_trainer(
            object(), object(), output_dir=output,
            model_dir=tmp_path / "unread-model", model_revision=REVISION,
            max_seq_length=8192, reporting=option,
        )
    assert len(calls) == len(failures) == 1
    assert caught.value is failures[0]
    assert type(caught.value) is type(expected.value)
    assert str(caught.value) == str(expected.value)
    assert calls[0][1]["reporting"] is option
    tb = caught.value.__traceback__
    while tb.tb_next:
        tb = tb.tb_next
    assert tb.tb_frame.f_code is guards.require_frontier_taskset.__code__
    assert attempted == [] and not output.exists()


@pytest.mark.parametrize(
    "field,value,message",
    [("model_revision", "main", "model_revision must be a full 40-hex revision"),
     ("max_seq_length", True, "max_seq_length must be a positive integer"),
     ("steps", 0, "steps must be a positive integer")],
)
def test_monitored_invalid_argument_precedence(
    api, monkeypatch, tmp_path, field, value, message,
):
    from train import grpo_ptc, sql_reporting

    attempted = []

    def forbidden(*args, **kwargs):
        attempted.append("work")
        raise AssertionError("invalid arguments reached downstream work")

    for owner, name in (
        (api, "RunMonitor"), (api, "_make_callback"),
        (grpo_ptc, "native_sql_preflight"), (sql_reporting, "validate_config"),
    ):
        monkeypatch.setattr(owner, name, forbidden)
    kwargs = dict(
        output_dir=tmp_path / "output", model_dir=tmp_path / "model",
        model_revision=REVISION, max_seq_length=8192, steps=200, reporting=False,
    )
    kwargs[field] = value
    with pytest.raises(ValueError) as caught:
        api.build_monitored_sql_trainer(object(), object(), **kwargs)
    assert str(caught.value) == message
    assert attempted == []


def test_original_native_builder_real_bridge_and_original_callback_body(
    api, native_wiring, callback_base, monkeypatch,
):
    """Private constructor/base doubles, real bridge, callback body and monitor."""
    from train import sql_reporting, verdict as V
    from train.run_monitor import RunMonitor

    state = native_wiring
    callback_base.events = state.events
    monitors, delegates = [], []
    original_builder = api.native_training.build_sql_trainer

    def delegated(*args, **kwargs):
        state.events.append("delegate")
        delegates.append((args, kwargs))
        return original_builder(*args, **kwargs)

    def monitor():
        state.events.append("monitor")
        instance = RunMonitor()
        monitors.append(instance)
        return instance

    monkeypatch.setattr(api.native_training, "build_sql_trainer", delegated)
    monkeypatch.setattr(api, "RunMonitor", monitor)
    config = sql_reporting.ReportingConfig()
    result = api.build_monitored_sql_trainer(
        state.tasks, state.db_root, **state.kwargs, reporting=config,
    )
    assert state.events == [
        "delegate", "preflight", "verify_model", "prepare", "runtime", "dataset",
        "model", "peft", "config", "trainer", "suffix", "monitor", "callback", "attach",
    ]
    assert len(delegates) == len(monitors) == len(state.callbacks) == 1
    assert delegates[0][0][0] is state.tasks
    assert delegates[0][0][1] is state.db_root
    assert delegates[0][1]["reporting"] is config
    assert state.prepare_calls[0][2]["reporting"] is config
    assert result.trainer is state.trainers[0] and result.monitor is monitors[0]
    assert_real_reporting(result.trainer)
    callback = state.callbacks[0]
    assert callback is callback_base.created[0]
    logs = [
        {"loss": 0.01, V.ZERO_STD_KEY: 0.4, V.LOGP_DIFF_KEY: 1.0}
        for _ in range(12)
    ]
    before = copy.deepcopy(logs)
    expected = RunMonitor()
    control = SimpleNamespace(should_training_stop=False)
    for row in logs:
        expected.observe(row)
        assert callback.on_log(None, None, control, logs=row) is control
        assert control.should_training_stop is False
    assert result.monitor.rows == expected.rows == logs
    assert result.monitor.finalize() == expected.finalize() == (True, [])
    fault = {"loss": 0.01}
    fault_before = dict(fault)
    expected.observe(fault)
    assert callback.on_log(None, None, control, logs=fault) is control
    assert result.monitor.aborted == expected.aborted
    assert result.monitor.aborted is not None and control.should_training_stop is True
    reason = result.monitor.aborted
    for later in (None, logs[0]):
        assert callback.on_log(None, None, control, logs=later) is control
        assert result.monitor.aborted == reason and control.should_training_stop is True
    assert logs == before and fault == fault_before
    assert len(state.callbacks) == 1


def test_invalid_bridge_config_never_constructs_monitor(
    api, native_wiring, monkeypatch,
):
    state = native_wiring
    attempted = []

    def forbidden(*args, **kwargs):
        attempted.append("monitor/callback")
        raise AssertionError("failed native builder constructed monitoring")

    monkeypatch.setattr(api, "RunMonitor", forbidden)
    monkeypatch.setattr(api, "_make_callback", forbidden)
    with pytest.raises(TypeError) as caught:
        api.build_monitored_sql_trainer(
            state.tasks, state.db_root, **state.kwargs, reporting=False,
        )
    assert str(caught.value) == "expected an exact ReportingConfig"
    assert state.events == ["preflight", "verify_model", "prepare"]
    assert attempted == []


def test_monitored_forwarding_loss_canary_then_restored_positive(
    api, native_wiring, callback_base, monkeypatch,
):
    from train.sql_reporting import ReportingConfig

    state = native_wiring
    original_builder = api.native_training.build_sql_trainer
    config = ReportingConfig()

    def drop_reporting(*args, reporting=None, **kwargs):
        return original_builder(*args, **kwargs)

    with monkeypatch.context() as lost:
        lost.setattr(api.native_training, "build_sql_trainer", drop_reporting)
        result = api.build_monitored_sql_trainer(
            state.tasks, state.db_root, **state.kwargs, reporting=config,
        )
        assert len(state.callbacks) == 1  # Valid builder and callback setup.
        with pytest.raises(AssertionError) as caught:
            assert_real_reporting(
                result.trainer, message="monitored reporting snapshot missing after reset",
            )
        assert str(caught.value).splitlines()[0] == (
            "monitored reporting snapshot missing after reset"
        )
    result = api.build_monitored_sql_trainer(
        state.tasks, state.db_root, **state.kwargs, reporting=config,
    )
    assert_real_reporting(result.trainer)
    assert len(state.callbacks) == 2
