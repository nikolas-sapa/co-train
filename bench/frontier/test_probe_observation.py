"""Synthetic observer plumbing, no policy/provider evidence."""

from __future__ import annotations

import dataclasses
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from bench import fixture
from bench.loader import load_bird
from bench.score import ExResult


def _probe():
    return importlib.import_module("bench.frontier.probe")


@pytest.fixture(scope="module")
def tasks(tmp_path_factory):
    return load_bird(fixture.materialize(tmp_path_factory.mktemp("observation")))


def test_original_scores(tasks, monkeypatch):
    api = _probe()
    original = api.execution_accuracy
    events, observations, scores = [], [], []

    def generate(task):
        events.append("generate")
        return f"```sql\n{task.gold_sql if len(scores) % 2 == 0 else 'SELECT -98765'}\n```"

    real_extract = api.extract_sql

    def extract(text):
        events.append("extract")
        return real_extract(text)

    def score(*args, **kwargs):
        events.append("score")
        result = original(*args, **kwargs)
        scores.append(result)
        return result

    def observe(value):
        events.append("observe")
        observations.append(value)

    monkeypatch.setattr(api, "extract_sql", extract)
    monkeypatch.setattr(api, "execution_accuracy", score)
    result = api.probe(tasks[:1], generate, policy="fixture", sample_observer=observe)
    assert events == ["generate", "extract", "score", "observe"] * 4
    assert [o.slot_index for o in observations] == [0, 1, 2, 3]
    assert [o.result.score for o in observations] == [1.0, 0.0, 1.0, 0.0]
    assert all(o.result is r for o, r in zip(observations, scores))
    assert all(o.extracted_sql == real_extract(o.completion) for o in observations)
    assert result.rates == {tasks[0].name: 0.5}
    assert [f.name for f in dataclasses.fields(api.SampleObservation)] == [
        "task_id", "slot_index", "completion", "extracted_sql", "result"]
    assert tasks[0].gold_sql not in repr(observations[0])
    with pytest.raises(dataclasses.FrozenInstanceError):
        observations[0].slot_index = 9


def test_defaults(tasks, monkeypatch):
    api = _probe()
    bounds = []

    def score(*args, **kwargs):
        bounds.append(kwargs)
        return ExResult(1.0, "match", True)

    def forbidden(*args, **kwargs):
        raise AssertionError("disabled observation constructed")

    monkeypatch.setattr(api, "execution_accuracy", score)
    monkeypatch.setattr(api, "SampleObservation", forbidden)
    a = api.probe(tasks[:1], lambda t: t.gold_sql, policy="fixture")
    b = api.probe(tasks[:1], lambda t: t.gold_sql,
                  policy="fixture", sample_observer=None)
    assert a == b
    assert bounds == [{"compare": "set", "timeout_s": 30.0, "max_rows": 500_000}] * 8


@pytest.mark.parametrize("status", ["gold_error", "gold_timeout", "gold_truncated",
                                   "db_missing"])
def test_invalid_observation(tasks, monkeypatch, status):
    api = _probe()
    original = ExResult(0.0, status, False, "sensitive detail", 3, 7)
    observations, calls = [], []
    monkeypatch.setattr(api, "execution_accuracy", lambda *a, **k: original)

    def generate(task):
        calls.append(task.name)
        return task.gold_sql

    result = api.probe(tasks[:2], generate, policy="fixture",
                       sample_observer=observations.append)
    assert calls == [t.name for t in tasks[:2]]
    assert [o.slot_index for o in observations] == [0, 0]
    assert all(o.result is original for o in observations)
    assert result.void == dict.fromkeys(calls, status)
    assert result.rates == {}
    failure = KeyboardInterrupt("observer-private")

    def refuse(observation):
        assert observation.result is original
        raise failure

    calls.clear()
    with pytest.raises(KeyboardInterrupt) as caught:
        api.probe(tasks[:2], generate, policy="fixture", sample_observer=refuse)
    assert caught.value is failure
    assert calls == [tasks[0].name]


@pytest.mark.parametrize("phase", ["generate", "extract", "score", "observe"])
def test_exception_identity(tasks, monkeypatch, phase):
    api = _probe()
    failure = SystemExit("private original")
    calls = []

    def fail(*args, **kwargs):
        raise failure

    def generate(task):
        calls.append(task.name)
        return fail() if phase == "generate" else task.gold_sql

    if phase == "extract":
        monkeypatch.setattr(api, "extract_sql", fail)
    if phase == "score":
        monkeypatch.setattr(api, "execution_accuracy", fail)
    with pytest.raises(SystemExit) as caught:
        api.probe(tasks[:2], generate, policy="fixture",
                  sample_observer=fail if phase == "observe" else lambda o: None)
    assert caught.value is failure
    assert len(calls) == 1


def test_draw_defaults_and_explicit_forwarding(tasks, monkeypatch):
    api = importlib.import_module("bench.frontier.draw_probe")
    from bench.prepare import ValidatedDraw

    admitted = ValidatedDraw(tuple(tasks[:1]), tuple(tasks[:1]), (), "a" * 64,
                             "b" * 64, True, 0.5, 2, "multiset", ())
    calls, loads = [], []

    def load(*args, **kwargs):
        loads.append(1)
        return admitted

    def probe(*args, **kwargs):
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(api, "load_validated_draw", load)
    monkeypatch.setattr(api, "probe", probe)
    kwargs = dict(expected_draw_sha256="a" * 64,
                  expected_supplement_sha256="b" * 64, fixture=True,
                  policy="fixture", g=4, dead_ceiling=0.6)
    for extra in ({}, {"sample_observer": None}):
        api.probe_validated_draw("root", "draw", "supplement", lambda t: "",
                                 **kwargs, **extra)
    assert calls == [dict(policy="fixture", g=4, dead_ceiling=0.6,
                          compare="multiset", timeout_s=0.5, max_rows=2)] * 2
    observer = lambda o: None
    api.probe_validated_draw("root", "draw", "supplement", lambda t: "",
                             **kwargs, sample_observer=observer)
    assert calls[-1]["sample_observer"] is observer
    assert len(loads) == 6
