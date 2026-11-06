"""Offline integration contracts, scripted callbacks are not policy evidence."""

from __future__ import annotations

import builtins
import dataclasses
import importlib
import json
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # noqa: E402

from bench import fixture, prepare  # noqa: E402
from bench.frontier.probe import ProbeResult, probe  # noqa: E402
from bench.loader import load_bird  # noqa: E402


@dataclasses.dataclass(frozen=True)
class Staged:
    root: Path
    draw: Path
    supplement: Path
    draw_sha: str
    supplement_sha: str
    admitted: prepare.ValidatedDraw


def _api():
    return importlib.import_module("bench.frontier.draw_probe")


def _stage(tmp_path, *, broken=False, row_cap=500_000, declared_fixture=True):
    root = fixture.materialize(tmp_path / "corpus")
    if broken or row_cap == 2:
        records = json.loads((root / "dev.json").read_text())
        if row_cap == 2:
            for record in records:
                record["SQL"] = "SELECT 1 UNION ALL SELECT 2"
        if broken:
            records[0]["SQL"] = "SELECT * FROM absent_probe_table"
        (root / "dev.json").write_text(json.dumps(records))
    draw = tmp_path / "draw.json"
    supplement = tmp_path / "supplement.json"
    draw_sha = prepare.freeze_draw(
        root, draw, seed=0,
        per_tier={"simple": 2, "moderate": 3, "challenging": 3},
        fixture=declared_fixture, max_rows=row_cap,
        timeout_s=0.5 if row_cap == 2 else 30.0,
    )
    supplement_sha = prepare.validate_draw(
        root, draw, supplement, expected_draw_sha256=draw_sha)
    admitted = prepare.load_validated_draw(
        root, draw, supplement, expected_draw_sha256=draw_sha,
        expected_supplement_sha256=supplement_sha, fixture=declared_fixture)
    return Staged(root, draw, supplement, draw_sha, supplement_sha, admitted)


def _run(staged, generate, **overrides):
    kwargs = {
        "expected_draw_sha256": staged.draw_sha,
        "expected_supplement_sha256": staged.supplement_sha,
        "fixture": staged.admitted.fixture,
        "policy": "scripted-fixture-not-a-checkpoint",
        "g": 4,
        "dead_ceiling": 0.6,
    }
    kwargs.update(overrides)
    return _api().probe_validated_draw(
        staged.root, staged.draw, staged.supplement, generate, **kwargs)


def _alternating(calls):
    counts = {}

    def generate(task):
        calls.append(task.name)
        attempt = counts.get(task.name, 0)
        counts[task.name] = attempt + 1
        sql = task.gold_sql if attempt % 2 == 0 else "SELECT 'wrong' AS x"
        return f"```sql\n{sql}\n```"

    return generate


def _assert_refused(staged, **overrides):
    calls = []
    published = []
    try:
        published.append(_run(staged, _alternating(calls), **overrides))
    except prepare.PreparationError:
        pass
    else:
        raise AssertionError("admission accepted invalid retained inputs")
    assert calls == []
    assert published == []


def test_real_admitted_draw_probes_8_tasks_32_times_in_order(tmp_path):
    staged = _stage(tmp_path)
    calls = []
    result = _run(staged, _alternating(calls))
    names = [task.name for task in staged.admitted.eligible]
    planned = json.loads(staged.draw.read_text())["planned"]
    assert names == [entry["id"] for entry in planned]
    assert len(names) == 8
    assert calls == [name for name in names for _ in range(4)]
    assert len(calls) == 32
    assert isinstance(result, ProbeResult)
    assert list(result.rates) == names
    assert result.rates == dict.fromkeys(names, 0.5)
    assert result.retained == names
    assert result.void == {}
    assert result.policy == "scripted-fixture-not-a-checkpoint"
    assert result.g == 4 and result.dead_ceiling == 0.6
    assert result.compare == "set"


def test_real_preexcluded_gold_never_generated_scored_or_zero_filled(
        tmp_path, monkeypatch):
    staged = _stage(tmp_path, broken=True)
    assert len(staged.admitted.planned) == 8
    assert len(staged.admitted.exclusions) == 1
    excluded = staged.admitted.exclusions[0]
    assert excluded.status == "gold_error"
    names = [task.name for task in staged.admitted.eligible]
    assert len(names) == 7
    probe_module = importlib.import_module("bench.frontier.probe")
    real_score = probe_module.execution_accuracy
    scored = []

    def score(sql, task, **kwargs):
        scored.append(task.name)
        return real_score(sql, task, **kwargs)

    monkeypatch.setattr(probe_module, "execution_accuracy", score)
    calls = []
    result = _run(staged, _alternating(calls))
    assert calls == scored == [name for name in names for _ in range(4)]
    assert len(calls) == 28
    assert list(result.rates) == result.retained == names
    assert set(result.rates.values()) == {0.5}
    assert excluded.id not in calls
    assert excluded.id not in result.rates
    assert excluded.id not in result.retained
    assert result.void == {}


@pytest.mark.parametrize("overrides", [
    {"expected_draw_sha256": "0" * 64},
    {"expected_supplement_sha256": "0" * 64},
    {"fixture": False},
])
def test_bad_digest_or_fixture_mismatch_has_zero_callbacks(tmp_path, overrides):
    _assert_refused(_stage(tmp_path), **overrides)


def test_fixture_opt_in_defaults_to_false(tmp_path):
    staged = _stage(tmp_path)
    calls = []
    with pytest.raises(prepare.PreparationError, match="fixture"):
        _api().probe_validated_draw(
            staged.root, staged.draw, staged.supplement, _alternating(calls),
            expected_draw_sha256=staged.draw_sha,
            expected_supplement_sha256=staged.supplement_sha,
            policy="scripted", g=4, dead_ceiling=0.6)
    assert calls == []


@pytest.mark.parametrize("row_cap,declared_fixture,timeout_s", [
    (2, True, 0.5),
    (500_000, False, 30.0),
])
def test_admitted_scoring_bounds_forward_unchanged_with_real_sqlite(
        tmp_path, monkeypatch, row_cap, declared_fixture, timeout_s):
    staged = _stage(
        tmp_path, row_cap=row_cap, declared_fixture=declared_fixture)
    probe_module = importlib.import_module("bench.frontier.probe")
    real_score = probe_module.execution_accuracy
    observed = []
    statuses = []

    def score(sql, task, **kwargs):
        observed.append(kwargs)
        result = real_score(sql, task, **kwargs)
        statuses.append(result.status)
        return result

    monkeypatch.setattr(probe_module, "execution_accuracy", score)
    calls = []

    def generate(task):
        calls.append(task.name)
        if row_cap == 2:
            return "SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3"
        return task.gold_sql

    result = _run(staged, generate)
    assert len(calls) == len(observed) == 32
    assert observed == [
        {"compare": "set", "timeout_s": timeout_s, "max_rows": row_cap}
    ] * 32
    assert all(type(kwargs["max_rows"]) is int for kwargs in observed)
    assert result.compare == "set"
    assert result.void == {}
    if row_cap == 2:
        assert statuses == ["pred_truncated"] * 32
        assert set(result.rates.values()) == {0.0}
    else:
        assert set(result.rates.values()) == {1.0}


def test_legacy_probe_preserves_default_scoring_bounds(tmp_path, monkeypatch):
    root = fixture.materialize(tmp_path / "corpus")
    tasks = load_bird(root)
    probe_module = importlib.import_module("bench.frontier.probe")
    real_score = probe_module.execution_accuracy
    observed = []

    def score(sql, task, **kwargs):
        observed.append(kwargs)
        return real_score(sql, task, **kwargs)

    monkeypatch.setattr(probe_module, "execution_accuracy", score)
    result = probe(tasks, lambda task: task.gold_sql, policy="scripted")
    assert result.g == 4 and result.dead_ceiling == 0.6
    assert len(observed) == 32
    assert observed == [
        {"compare": "set", "timeout_s": 30.0, "max_rows": 500_000}
    ] * 32
    assert set(result.rates.values()) == {1.0}


def test_admission_is_fresh_before_and_after_all_callbacks(tmp_path, monkeypatch):
    staged = _stage(tmp_path)
    api = _api()
    real_load = api.load_validated_draw
    calls = []
    admissions = []

    def load(*args, **kwargs):
        admissions.append((len(calls), args, kwargs))
        return real_load(*args, **kwargs)

    monkeypatch.setattr(api, "load_validated_draw", load)
    _run(staged, _alternating(calls))
    expected_args = (staged.root, staged.draw, staged.supplement)
    expected_kwargs = {
        "expected_draw_sha256": staged.draw_sha,
        "expected_supplement_sha256": staged.supplement_sha,
        "fixture": True,
    }
    assert admissions == [
        (0, expected_args, expected_kwargs),
        (32, expected_args, expected_kwargs),
    ]


@pytest.mark.parametrize("target", ["database", "corpus", "draw", "supplement"])
def test_callback_drift_refuses_whole_operation_after_probing(
        tmp_path, target):
    staged = _stage(tmp_path)
    calls = []
    published = []
    mutations = []

    def generate(task):
        calls.append(task.name)
        if len(calls) == 16:
            if target == "database":
                connection = sqlite3.connect(task.db_path)
                try:
                    connection.execute("CREATE TABLE probe_drift (value INTEGER)")
                    connection.commit()
                finally:
                    connection.close()
            elif target == "corpus":
                path = staged.root / "dev.json"
                records = json.loads(path.read_text())
                records[0]["question"] += " changed during probe"
                path.write_text(json.dumps(records))
            else:
                path = staged.draw if target == "draw" else staged.supplement
                path.write_bytes(path.read_bytes() + b" ")
            mutations.append(target)
        return task.gold_sql

    with pytest.raises(prepare.PreparationError):
        published.append(_run(staged, generate))
    assert mutations == [target]
    assert len(calls) == 32
    assert published == []
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "corpus", "draw.json", "supplement.json"]


def test_generation_exception_preserves_same_object(tmp_path):
    staged = _stage(tmp_path)
    sentinel = RuntimeError("scripted callback failure")
    calls = []
    published = []

    def generate(task):
        calls.append(task.name)
        if len(calls) == 3:
            raise sentinel
        return task.gold_sql

    with pytest.raises(RuntimeError) as caught:
        published.append(_run(staged, generate))
    assert caught.value is sentinel
    assert len(calls) == 3
    assert published == []


@pytest.mark.parametrize("overrides", [
    {"g": True}, {"g": False}, {"g": 4.0}, {"g": "4"},
    {"g": 0}, {"g": 1}, {"g": -2},
    {"policy": ""}, {"policy": "   "}, {"policy": None}, {"policy": 4},
    {"dead_ceiling": float("nan")}, {"dead_ceiling": float("inf")},
    {"dead_ceiling": -float("inf")}, {"dead_ceiling": 0.0},
    {"dead_ceiling": 1.0}, {"dead_ceiling": -0.1},
    {"dead_ceiling": 1.1}, {"dead_ceiling": True},
    {"dead_ceiling": "0.6"}, {"dead_ceiling": None},
    {"dead_ceiling": 10 ** 1000},
])
def test_invalid_explicit_probe_settings_have_zero_callbacks(tmp_path, overrides):
    staged = _stage(tmp_path)
    calls = []
    with pytest.raises(ValueError):
        _run(staged, _alternating(calls), **overrides)
    assert calls == []


@pytest.mark.parametrize("missing", ["policy", "g", "dead_ceiling"])
def test_policy_g_and_ceiling_have_no_defaults(tmp_path, missing):
    staged = _stage(tmp_path)
    calls = []
    kwargs = {
        "expected_draw_sha256": staged.draw_sha,
        "expected_supplement_sha256": staged.supplement_sha,
        "fixture": True, "policy": "scripted", "g": 4, "dead_ceiling": 0.6,
    }
    del kwargs[missing]
    with pytest.raises(TypeError):
        _api().probe_validated_draw(
            staged.root, staged.draw, staged.supplement,
            _alternating(calls), **kwargs)
    assert calls == []


@pytest.mark.parametrize("max_rows", [True, False, 0, -1, 2.0, "2", None])
def test_legacy_probe_rejects_invalid_row_cap_before_generation(
        tmp_path, max_rows):
    tasks = load_bird(fixture.materialize(tmp_path / "corpus"))
    calls = []
    with pytest.raises(ValueError, match="max_rows"):
        probe(tasks, _alternating(calls), policy="scripted", max_rows=max_rows)
    assert calls == []


def test_integration_has_no_publication_provider_or_network_side_effects(
        tmp_path, monkeypatch):
    staged = _stage(tmp_path)
    _api()
    probe_module = importlib.import_module("bench.frontier.probe")
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*") if path.is_file()
    }
    real_import = builtins.__import__
    forbidden_calls = []
    forbidden_modules = {
        "train", "torch", "transformers", "unsloth", "openai", "anthropic",
        "requests", "httpx", "litellm",
    }

    def forbid(*args, **kwargs):
        forbidden_calls.append((args, kwargs))
        raise AssertionError("forbidden integration side effect")

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in forbidden_modules:
            forbid(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(prepare, "_publish", forbid)
    monkeypatch.setattr(prepare, "freeze_draw", forbid)
    monkeypatch.setattr(prepare, "validate_draw", forbid)
    monkeypatch.setattr(prepare, "validate_golds", forbid)
    monkeypatch.setattr(prepare, "select", forbid)
    monkeypatch.setattr(probe_module, "write_manifest", forbid)
    monkeypatch.setattr(probe_module, "write_report", forbid)
    monkeypatch.setattr(Path, "write_text", forbid)
    monkeypatch.setattr(Path, "write_bytes", forbid)
    monkeypatch.setattr(socket.socket, "connect", forbid)
    monkeypatch.setattr(socket, "create_connection", forbid)
    monkeypatch.setattr(subprocess, "Popen", forbid)
    calls = []
    result = _run(staged, _alternating(calls))
    assert len(result.rates) == 8 and len(calls) == 32
    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*") if path.is_file()
    }
    assert before == after
    assert forbidden_calls == []


def test_guard_loss_canary_detects_skipped_digest_admission(
        tmp_path, monkeypatch):
    staged = _stage(tmp_path)
    _assert_refused(staged, expected_draw_sha256="0" * 64)
    bypass_hits = []

    def bypass(*args, **kwargs):
        bypass_hits.append(kwargs)
        return staged.admitted

    with monkeypatch.context() as patch:
        patch.setattr(_api(), "load_validated_draw", bypass)
        with pytest.raises(
                AssertionError, match="admission accepted invalid retained inputs"):
            _assert_refused(staged, expected_draw_sha256="0" * 64)
    assert len(bypass_hits) == 2
    _assert_refused(staged, expected_draw_sha256="0" * 64)
