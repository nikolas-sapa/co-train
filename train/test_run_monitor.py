"""Pure RUN criteria, synthetic telemetry only. No trainer or completion proof."""

from __future__ import annotations

import builtins
import importlib
import importlib.util
import inspect
import os
import pathlib
import socket

import pytest

from train import verdict as V


@pytest.fixture
def monitor_class():
    # Missing API must be an honest call-phase RED, not a collection failure.
    def construct():
        assert importlib.util.find_spec("train.run_monitor") is not None, (
            "RunMonitor API not implemented"
        )
        return importlib.import_module("train.run_monitor").RunMonitor()

    return construct


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    attempts = []

    def deny(*args, **kwargs):
        attempts.append((args, kwargs))
        raise AssertionError("pure monitor attempted network access")

    for name in ("socket", "create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, deny)
    yield
    assert attempts == []


def step(a=0.4, b=1.0, **extra):
    return {"loss": 0.01, V.ZERO_STD_KEY: a, V.LOGP_DIFF_KEY: b, **extra}


def replay(monitor_class, rows):
    monitor = monitor_class()
    results = [monitor.observe(row) for row in rows]
    return monitor, results


def test_healthy_12_continue_and_finalize(monitor_class):
    monitor, results = replay(monitor_class, [step() for _ in range(12)])
    assert results == [None] * 12
    assert monitor.aborted is None
    assert monitor.finalize() == V.run_verdict(monitor.rows) == (True, [])


@pytest.mark.parametrize("count", [0, 1, 9])
def test_short_live_is_not_final_healthy(monitor_class, count):
    monitor, results = replay(monitor_class, [step() for _ in range(count)])
    assert results == [None] * count
    assert monitor.aborted is None
    assert monitor.finalize() == V.run_verdict(monitor.rows)
    assert monitor.finalize()[0] is False


def test_a_nine_vs_ten_sustained(monitor_class):
    monitor, results = replay(monitor_class, [step(a=0.61) for _ in range(9)])
    assert results == [None] * 9
    reason = monitor.observe(step(a=0.61))
    assert reason is not None
    assert "steps 0-9" in reason and "10 consecutive" in reason
    assert reason in V.criterion_a_sustained(monitor.rows)


@pytest.mark.parametrize(
    "values",
    [[0.60] * 12, [0.4] * 5 + [0.9] + [0.4] * 6, [0.61] * 9 + [0.4] + [0.61] * 9],
    ids=["exact-ceiling", "single-spike", "dip-resets"],
)
def test_a_non_sustained_controls(monitor_class, values):
    monitor, results = replay(monitor_class, [step(a=a) for a in values])
    assert results == [None] * len(values)
    assert monitor.finalize() == (True, [])


def test_b_ten_strict_rises(monitor_class):
    monitor, results = replay(monitor_class, [step(b=1 + i / 100) for i in range(10)])
    assert results[:9] == [None] * 9
    assert results[9] is not None and "monotonically" in results[9]
    assert monitor.finalize()[0] is False


def test_b_twenty_flat_positive(monitor_class):
    monitor, results = replay(monitor_class, [step(b=50.0) for _ in range(20)])
    assert results == [None] * 20
    assert monitor.finalize() == (True, [])


@pytest.mark.parametrize("spike,abort", [(3.0, False), (3.01, True)])
@pytest.mark.parametrize("index", [0, 9, 10, 19])
def test_b_ratio_strict_fixed_first_ten(monitor_class, spike, abort, index):
    rows = [step() for _ in range(20)]
    rows[index][V.LOGP_DIFF_KEY] = spike
    monitor, results = replay(monitor_class, rows)
    first_possible = max(9, index)
    assert results[:first_possible] == [None] * first_possible
    assert (results[first_possible] is not None) is abort
    if abort:
        assert "median" in results[first_possible]
    assert monitor.finalize() == V.run_verdict(rows)
    assert monitor.finalize()[0] is not abort


@pytest.mark.parametrize("baseline", [0.0, -1.0])
def test_b_nonpositive_median_is_informational(monitor_class, baseline):
    rows = [step(b=baseline) for _ in range(10)] + [step(b=99.0)]
    monitor, results = replay(monitor_class, rows)
    assert results == [None] * 11
    assert monitor.finalize() == (True, [])
    assert any("non-positive" in note for note in V.criterion_b(rows)[1])


MISSING = object()
INVALID = [
    pytest.param(MISSING, id="missing"),
    pytest.param(None, id="none"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="positive-inf"),
    pytest.param(float("-inf"), id="negative-inf"),
    pytest.param(True, id="true"),
    pytest.param(False, id="false"),
]


@pytest.mark.parametrize("value", INVALID)
@pytest.mark.parametrize("key", [V.ZERO_STD_KEY, V.LOGP_DIFF_KEY], ids=["A", "B"])
@pytest.mark.parametrize("index", [0, 3, 9, 11])
def test_required_fault_immediate_even_early_b(monitor_class, value, key, index):
    rows = [step() for _ in range(12)]
    if value is MISSING:
        del rows[index][key]
    else:
        rows[index][key] = value
    monitor, results = replay(monitor_class, rows)
    assert results[:index] == [None] * index
    assert results[index] is not None
    assert key in results[index]
    assert all(result == results[index] for result in results[index:])
    assert monitor.finalize() == V.run_verdict(rows)
    assert monitor.finalize()[0] is False


def test_nonstep_rows_do_not_count_or_require_metrics(monitor_class):
    monitor = monitor_class()
    for i in range(9):
        assert monitor.observe({"train_loss": 0.01, V.ZERO_STD_KEY: True}) is None
        assert monitor.observe(step(a=0.61, step=1000 - i)) is None
        assert monitor.observe({"eval_loss": 0.01, V.LOGP_DIFF_KEY: None}) is None
    assert len(monitor.rows) == 27
    assert len(V.training_steps(monitor.rows)) == 9
    assert "steps 0-9" in monitor.observe(step(a=0.61, step=-99))


@pytest.mark.parametrize("key", [V.ZERO_STD_KEY, V.LOGP_DIFF_KEY], ids=["A", "B"])
def test_gap_preserves_logged_axis_and_first_ten(monitor_class, key):
    rows = [step(a=0.61, b=1 + i / 100) for i in range(11)]
    del rows[5][key]
    monitor, results = replay(monitor_class, rows)
    assert results[5] is not None and "step 5" in results[5]
    assert monitor.finalize() == V.run_verdict(rows)
    reasons = V.criterion_a_sustained(rows) if key == V.ZERO_STD_KEY else V.criterion_b(rows)[0]
    marker = "consecutive steps" if key == V.ZERO_STD_KEY else "monotonically"
    assert not any(marker in reason for reason in reasons)
    if key == V.LOGP_DIFF_KEY:
        assert any("first-10-step baseline" in reason for reason in reasons)


def test_b_baseline_gap_never_rebased_and_later_axis_stays_real(monitor_class):
    rows = [step()] + [step(b=1 + i / 100) for i in range(11)]
    del rows[0][V.LOGP_DIFF_KEY]
    rows += [step(b=4.0)]
    monitor, results = replay(monitor_class, rows)
    assert results[0] is not None
    ok, reasons = monitor.finalize()
    assert (ok, reasons) == V.run_verdict(rows)
    assert any("first-10-step baseline" in r for r in reasons)
    assert any("steps 1-10:" in r and "monotonically" in r for r in reasons)
    assert not any(" reached " in r for r in reasons)


COMPLETE = [
    pytest.param([step() for _ in range(12)], id="healthy"),
    pytest.param([step(a=0.61) for _ in range(10)], id="sustained-a"),
    pytest.param([step(a=0.60) for _ in range(12)], id="exact-a"),
    pytest.param([step(a=0.9)] + [step() for _ in range(11)], id="single-a"),
    pytest.param([step(a=0.61) for _ in range(9)] + [step()] +
                 [step(a=0.61) for _ in range(9)], id="reset-a"),
    pytest.param([step(b=1 + i / 100) for i in range(10)], id="rising-b"),
    pytest.param([step(b=50.0) for _ in range(20)], id="flat-b"),
    pytest.param([step() for _ in range(10)] + [step(b=3.0)], id="exact-ratio"),
    pytest.param([step() for _ in range(10)] + [step(b=3.01)], id="ratio"),
    pytest.param([step(b=3.01)] + [step() for _ in range(9)], id="baseline-spike"),
    pytest.param([step(b=0.0) for _ in range(10)], id="zero-baseline"),
    pytest.param([step(b=-1.0) for _ in range(10)], id="negative-baseline"),
]


@pytest.mark.parametrize("rows", COMPLETE)
def test_live_complete_parity_real_verdict(monitor_class, rows):
    monitor, _ = replay(monitor_class, rows)
    expected = V.run_verdict(rows)  # real function, never a mock
    assert monitor.finalize() == expected
    assert (monitor.aborted is None) is expected[0]
    if monitor.aborted is not None:
        assert monitor.aborted in expected[1]


def test_latch_and_defensive_history(monitor_class):
    monitor = monitor_class()
    row = step(extra={"nested": [1]})
    assert monitor.observe(row) is None
    row[V.ZERO_STD_KEY] = float("nan")
    row["extra"]["nested"].append(2)
    exported = monitor.rows
    exported[0][V.LOGP_DIFF_KEY] = None
    exported[0]["extra"]["nested"].append(3)
    exported.clear()
    assert monitor.rows == [step(extra={"nested": [1]})]
    for _ in range(9):
        assert monitor.observe(step()) is None
    assert monitor.finalize() == (True, [])
    reason = monitor.observe(step(b=None))
    assert reason is not None
    for row in (step(), {"eval_loss": 0.01}):
        assert monitor.observe(row) == reason
    for name, value in (("rows", []), ("aborted", None)):
        with pytest.raises(AttributeError):
            setattr(monitor, name, value)
    monitor.rows[-3][V.LOGP_DIFF_KEY] = 1.0
    assert monitor.aborted == reason
    assert monitor.finalize()[0] is False
    final_reasons = monitor.finalize()[1]
    final_reasons.clear()
    assert monitor.finalize()[0] is False


def test_pure_component_no_disk_or_framework_calls(monitor_class, monkeypatch):
    source = inspect.getsource(importlib.import_module("train.run_monitor"))
    calls = []
    original_import = builtins.__import__
    forbidden = {"torch", "transformers", "trl", "unsloth", "unsloth_zoo",
                 "verifiers", "datasets", "peft", "vllm", "observations",
                 "train.dead_group_probe", "train.native_training", "train.native_runtime"}

    def guarded_import(name, *args, **kwargs):
        assert name not in forbidden and name.split(".")[0] not in forbidden
        return original_import(name, *args, **kwargs)

    def deny(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("pure component attempted disk I/O")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(builtins, "open", deny)
    monkeypatch.setattr(os, "open", deny)
    monkeypatch.setattr(pathlib.Path, "open", deny)
    # Fresh module execution under guards, not a fake class or verdict.
    namespace = {"__name__": "train.run_monitor", "__package__": "train"}
    exec(compile(source, "<guarded-run-monitor>", "exec"), namespace)
    monitor = namespace["RunMonitor"]()
    for _ in range(12):
        assert monitor.observe(step()) is None
    assert monitor.finalize() == (True, [])
    assert monitor.observe(step(b=None)) is not None
    assert monitor.finalize()[0] is False
    assert calls == []
