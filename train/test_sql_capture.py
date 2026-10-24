"""Acceptance contracts for trusted incremental SQL/PTC execution capture.

Not model trajectories, token-faithful provider capture, or learning evidence.
Missing implementation fails inside test bodies, never during collection.
Real fixture SQLite and the existing environment/scorer are the primary oracle.
Fresh-copy mutation controls are specified in spec/sql-execution-capture.md.
"""

from __future__ import annotations

import builtins
import dataclasses
import hashlib
import importlib
import inspect
import io
import json
import re
import sqlite3
from pathlib import Path

import pytest


MAX_BYTES = 8 * 1024 * 1024
FORMAT = "sql_execution_capture"
REJECT = (TypeError, ValueError)
ID_FIELDS = (
    "corpus_id", "split_id", "run_id", "episode_id", "policy_id",
    "policy_revision",
)
TASK_FIELDS = (
    "name", "question", "evidence", "gold_sql", "db_id", "tier",
    "tier_source", "shape", "coarse_shape", "source",
)
SOURCE_PATHS = (
    "bench/score.py", "ptc/sql_arms.py", "ptc/runtime.py",
    "ptc/sql_runtime.py", "ptc/sqlite_safety.py", "ptc/harness.py",
    "train/sql_capture.py", "train/sql_episodes.py", "train/grpo_ptc.py",
    "train/guards.py", "bench/task.py",
)
FIRST = 'print(execute_sql(query="SELECT COUNT(*) AS n FROM school")[0]["n"])'


def _api():
    try:
        return importlib.import_module("train.sql_capture")
    except ModuleNotFoundError as exc:
        if exc.name != "train.sql_capture":
            raise
        pytest.fail("train.sql_capture is not implemented", pytrace=False)


def _ids(**changes):
    from train.sql_episodes import EpisodeIds

    values = dict(zip(ID_FIELDS, (
        "committed-bird-fixture", "capture-engineering-only", "capture-run",
        "capture-episode", "trusted-host-policy", "capture-fixture-v1",
    )))
    values.update(changes)
    return EpisodeIds(**values)


def _start(api, task, *, ids=None):
    return api.start_capture(
        task, ids=_ids() if ids is None else ids, allow_execution=True,
    )


def _finished(api, task, *, actions=(), ids=None):
    session = _start(api, task, ids=ids)
    for action in actions:
        session.step(action)
    return session.finish(task.gold_sql)


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _envelope(payload, *, version=1):
    return _canonical({
        "format": FORMAT, "schema_version": version, "payload": payload,
        "sha256": hashlib.sha256(_canonical(payload)).hexdigest(),
    })


def _dispatch_spy(monkeypatch):
    from ptc import sql_arms

    original = sql_arms.ArmPair.run
    calls = []

    def run(pair, arm, action, *, bindir=None):
        calls.append((arm, action))
        return original(pair, arm, action, bindir=bindir)

    monkeypatch.setattr(sql_arms.ArmPair, "run", run)
    return calls


def _score_spy(monkeypatch, api, *, forbidden=False):
    from bench import score
    from train import sql_episodes

    original = score.execution_accuracy
    calls = []

    def execute(*args, **kwargs):
        calls.append((args, kwargs))
        if forbidden:
            raise AssertionError("protected scorer called before validation")
        return original(*args, **kwargs)

    for module in (score, sql_episodes, api):
        if getattr(module, "execution_accuracy", None) is original:
            monkeypatch.setattr(module, "execution_accuracy", execute)
    return calls


def _invalidated(session):
    for operation in (
        lambda: session.step("print('must-not-run')"),
        lambda: session.finish("SELECT 1"),
        session.abort,
    ):
        with pytest.raises(RuntimeError):
            operation()


def _operation(api, operation, session, capture, task, ids):
    if operation == "step":
        return session.step(FIRST)
    if operation == "finish":
        return session.finish(task.gold_sql)
    return api.rescore_capture(capture, task, ids=ids)


@pytest.fixture(autouse=True)
def no_model_stack(monkeypatch):
    original_import = builtins.__import__
    original_module = importlib.import_module
    attempted = []
    forbidden = {
        "torch", "transformers", "trl", "unsloth", "vllm", "verifiers",
        "datasets", "huggingface_hub", "httpx", "pydantic",
    }

    def check(name):
        if name.split(".")[0] in forbidden or name == "ptc.harness":
            attempted.append(name)
            raise AssertionError(f"model/framework import attempted: {name}")

    def guarded_import(name, *args, **kwargs):
        check(name)
        return original_import(name, *args, **kwargs)

    def guarded_module(name, *args, **kwargs):
        check(name)
        return original_module(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(importlib, "import_module", guarded_module)
    yield
    assert attempted == []


@pytest.fixture
def tasks(tmp_path):
    from bench import fixture
    from bench.loader import load_bird

    return load_bird(fixture.materialize(tmp_path / "corpus"))


@pytest.fixture
def task(tasks):
    return tasks[0]


def test_reactive_capture_matches_direct_environment_for_all_tasks(tasks, monkeypatch):
    from bench import fixture, score
    from train import grpo_ptc

    api = _api()
    assert len(tasks) == len(fixture.records()) >= 8
    calls = _dispatch_spy(monkeypatch)
    for index, original in enumerate(tasks):
        task = dataclasses.replace(
            original, gold_sql=original.gold_sql + " /* GOLD_ONLY_CAPTURE_TEST */",
        )
        ids = _ids(episode_id=f"reactive-{index}")
        direct_prompt, direct = grpo_ptc.sql_environment(task)
        session = _start(api, task, ids=ids)
        assert session.prompt.encode("utf-8") == direct_prompt.encode("utf-8")
        assert "GOLD_ONLY_CAPTURE_TEST" not in session.prompt
        assert task.gold_sql not in session.prompt
        assert not any(marker in session.prompt for marker in (
            ids.policy_id, ids.episode_id, FORMAT, "db_sha256", "terminal_label",
            "scorer_timeout_s",
        ))
        before = len(calls)
        first = session.step(FIRST)
        assert first.encode("utf-8") == direct.step(FIRST).encode("utf-8")
        # The caller cannot form this exact second action until it has observation A.
        count = int(first.strip())
        assert count > 0
        second = (
            "print(execute_sql(query="
            f"'SELECT name FROM school ORDER BY school_id LIMIT {count}'))"
        )
        observed = session.step(second)
        assert observed.encode("utf-8") == direct.step(second).encode("utf-8")
        assert calls[before:] == [
            ("ptc", FIRST), ("ptc", FIRST), ("ptc", second), ("ptc", second),
        ]
        # Two belong to the independent oracle; exactly two belong to capture.
        before_final = len(calls)
        capture = session.finish(task.gold_sql)
        encoded = api.encode_capture(capture)
        restored = api.decode_capture(encoded)
        assert len(calls) == before_final
        assert capture.origin == "incremental_execution"
        assert capture.arm == "ptc"
        assert capture.ids == ids
        assert capture.terminal_label == "final_submitted"
        assert capture.prompt == session.prompt
        assert [(step.action, step.observation) for step in capture.steps] == [
            (FIRST, first), (second, observed),
        ]
        assert capture.refusals == ()
        assert capture.result == score.execution_accuracy(
            score.extract_sql(task.gold_sql), task,
        )
        assert capture.result.score == 1.0
        assert restored == capture
        assert api.rescore_capture(restored, task, ids=ids) == capture.result
        assert len(calls) == before_final


@pytest.mark.parametrize("value", ("omitted", False, None, 1, "true", [], {}))
def test_start_requires_literal_true_before_environment(task, value, monkeypatch):
    from ptc import sql_arms
    from train import grpo_ptc

    api = _api()
    built = []

    def forbidden(*args, **kwargs):
        built.append(True)
        raise AssertionError("execution environment built before literal opt-in")

    real_environment = grpo_ptc.sql_environment
    monkeypatch.setattr(grpo_ptc, "sql_environment", forbidden)
    monkeypatch.setattr(sql_arms, "build_sql_arms", forbidden)
    if getattr(api, "sql_environment", None) is real_environment:
        monkeypatch.setattr(api, "sql_environment", forbidden)
    kwargs = {} if value == "omitted" else {"allow_execution": value}
    with pytest.raises(REJECT):
        api.start_capture(task, ids=_ids(), **kwargs)
    assert built == []


def test_capture_uses_actual_environment_step_and_fresh_budget(task, monkeypatch):
    from train import grpo_ptc

    api = _api()
    original = grpo_ptc.PTCEnvironment.step
    environments = []

    def tracked(environment, code):
        environments.append(environment)
        return original(environment, code)

    monkeypatch.setattr(grpo_ptc.PTCEnvironment, "step", tracked)
    first, second = _start(api, task), _start(api, task)
    assert first.step(FIRST) == second.step(FIRST)
    assert len(environments) == 2
    assert environments[0] is not environments[1]
    assert environments[0].budget is not environments[1].budget
    assert environments[0].turns_used == environments[1].turns_used == 1
    first.abort()
    second.abort()


def test_eight_dispatches_then_separate_refusals(task, monkeypatch):
    from train import guards
    from train.sql_episodes import ActionObservation

    api = _api()
    calls = _dispatch_spy(monkeypatch)
    session = _start(api, task)
    for _ in range(8):
        assert int(session.step(FIRST).strip()) > 0
    assert calls == [("ptc", FIRST)] * 8
    refusal = guards.TurnBudget(max_turns=guards.eval_max_turns()).exhausted_message()
    assert session.step("print('ninth')") == refusal
    assert session.step("print('tenth')") == refusal
    capture = session.finish(task.gold_sql)
    assert len(calls) == len(capture.steps) == capture.instrument.action_cap == 8
    assert capture.refusals == (
        ActionObservation("print('ninth')", refusal),
        ActionObservation("print('tenth')", refusal),
    )
    assert capture.final_answer == task.gold_sql
    assert capture.result.score == 1.0


def test_program_rejection_is_executed_not_a_budget_refusal(task, monkeypatch):
    api = _api()
    calls = _dispatch_spy(monkeypatch)
    session = _start(api, task)
    code = "print('partial'); execute_sql(query='SELECT FROM nowhere')"
    observation = session.step(code)
    assert observation.startswith("rejected:")
    assert "partial" not in observation
    capture = session.finish(task.gold_sql)
    assert calls == [("ptc", code)]
    assert len(capture.steps) == 1
    assert capture.refusals == ()
    assert capture.result.score == 1.0


@pytest.mark.parametrize("answer", ("gold", "wrong", "", "SELECT FROM nowhere", "fenced"))
@pytest.mark.parametrize("invalid_gold", (False, True))
def test_final_preserves_every_existing_exresult_field(task, answer, invalid_gold, monkeypatch):
    from bench import score

    api = _api()
    if invalid_gold:
        task = dataclasses.replace(task, gold_sql="SELECT * FROM missing_gold_table")
    final = (
        task.gold_sql if answer == "gold" else
        f"Reasoning.\n```sql\n{task.gold_sql};\n```" if answer == "fenced" else
        "SELECT 'known-wrong-fixture-answer'" if answer == "wrong" else answer
    )
    expected = score.execution_accuracy(score.extract_sql(final), task)
    session = _start(api, task)
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, api)
    capture = session.finish(final)
    assert len(scores) == 1
    assert dataclasses.asdict(capture.result) == dataclasses.asdict(expected)
    assert len(dataclasses.fields(capture.result)) == 6
    assert capture.final_answer == final
    assert capture.extracted_sql == score.extract_sql(final)
    assert capture.terminal_label == "final_submitted"
    assert api.rescore_capture(capture, task, ids=capture.ids) == expected
    assert len(scores) == 2
    assert calls == []
    if invalid_gold:
        assert capture.result.valid is False
        assert capture.result.status == "gold_error"
    elif answer in ("gold", "fenced"):
        assert capture.result.score == 1.0
    else:
        assert capture.result.valid is True
        assert capture.result.score == 0.0


@pytest.mark.parametrize("with_step", (False, True))
def test_abort_has_no_final_no_score_and_cannot_be_rescored(task, with_step, monkeypatch):
    api = _api()
    session = _start(api, task)
    if with_step:
        session.step(FIRST)
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, api, forbidden=True)
    capture = session.abort()
    assert capture.terminal_label == "aborted"
    assert capture.final_answer is capture.extracted_sql is capture.result is None
    assert len(capture.steps) == int(with_step)
    restored = api.decode_capture(api.encode_capture(capture))
    assert restored == capture
    with pytest.raises(REJECT):
        api.rescore_capture(restored, task, ids=capture.ids)
    assert calls == scores == []


def test_start_and_intermediate_observations_never_score_without_final(task, monkeypatch):
    api = _api()
    scores = _score_spy(monkeypatch, api, forbidden=True)
    calls = _dispatch_spy(monkeypatch)
    session = _start(api, task)
    assert scores == calls == []
    session.step(FIRST)
    session.step("print(execute_sql(query='SELECT name FROM school LIMIT 1'))")
    assert len(calls) == 2
    assert scores == []
    capture = session.abort()
    assert capture.result is None
    assert len(capture.steps) == 2
    assert scores == []


@pytest.mark.parametrize("terminal", ("finish", "abort"))
def test_terminal_sessions_reject_later_calls(task, terminal, monkeypatch):
    api = _api()
    session = _start(api, task)
    session.step(FIRST)
    if terminal == "finish":
        session.finish(task.gold_sql)
    else:
        session.abort()
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, api, forbidden=True)
    _invalidated(session)
    assert calls == scores == []


def test_independent_session_exhaustion_does_not_spend_other_budget(task, monkeypatch):
    api = _api()
    first, second = _start(api, task), _start(api, task)
    calls = _dispatch_spy(monkeypatch)
    for _ in range(8):
        first.step(FIRST)
    assert "budget" in first.step(FIRST).lower()
    assert int(second.step(FIRST).strip()) > 0
    assert len(calls) == 9
    assert len(first.abort().steps) == 8
    assert len(second.abort().steps) == 1


def test_unexpected_executor_failure_propagates_and_invalidates(task, monkeypatch):
    from ptc import sql_arms

    api = _api()
    session = _start(api, task)
    session.step(FIRST)

    def failed(*args, **kwargs):
        raise OSError("capture executor sentinel")

    with monkeypatch.context() as patch:
        patch.setattr(sql_arms.ArmPair, "run", failed)
        with pytest.raises(OSError, match="capture executor sentinel"):
            session.step(FIRST)
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, api, forbidden=True)
    _invalidated(session)
    assert calls == scores == []


def test_unexpected_scorer_failure_propagates_and_invalidates(task, monkeypatch):
    from bench import score
    from train import sql_episodes

    api = _api()
    session = _start(api, task)
    original = score.execution_accuracy

    def failed(*args, **kwargs):
        raise OSError("capture scorer sentinel")

    with monkeypatch.context() as patch:
        for module in (score, sql_episodes, api):
            if getattr(module, "execution_accuracy", None) is original:
                patch.setattr(module, "execution_accuracy", failed)
        with pytest.raises(OSError, match="capture scorer sentinel"):
            session.finish(task.gold_sql)
    _invalidated(session)


@pytest.mark.parametrize("operation", ("step", "finish", "rescore"))
@pytest.mark.parametrize("field", ID_FIELDS)
def test_each_caller_id_is_bound_before_next_operation(task, operation, field, monkeypatch):
    api = _api()
    ids = _ids()
    capture = _finished(api, task, ids=ids)
    session = _start(api, task, ids=ids)
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, api, forbidden=True)
    old = getattr(ids, field)
    try:
        # Bypass frozen only as a test of independent snapshot binding.
        object.__setattr__(ids, field, old + "-changed")
        with pytest.raises(REJECT):
            _operation(api, operation, session, capture, task, ids)
    finally:
        object.__setattr__(ids, field, old)
    if operation != "rescore":
        _invalidated(session)
    assert calls == scores == []


@pytest.mark.parametrize("operation", ("step", "finish", "rescore"))
@pytest.mark.parametrize("field", TASK_FIELDS)
def test_every_nonmount_task_field_is_bound(task, operation, field, monkeypatch):
    api = _api()
    capture = _finished(api, task)
    session = _start(api, task)
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, api, forbidden=True)
    old = getattr(task, field)
    replacement = (
        "challenging" if field == "tier" else
        "derived" if field == "tier_source" else old + "-changed"
    )
    assert replacement != old
    try:
        object.__setattr__(task, field, replacement)
        with pytest.raises(REJECT):
            _operation(api, operation, session, capture, task, capture.ids)
    finally:
        object.__setattr__(task, field, old)
    if operation != "rescore":
        _invalidated(session)
    assert calls == scores == []


def _mutate_database(task):
    conn = sqlite3.connect(task.db_path)
    try:
        conn.execute("UPDATE school SET name = name || '-changed' WHERE school_id = 1")
        conn.commit()
    finally:
        conn.close()


@pytest.mark.parametrize("operation", ("step", "finish", "rescore"))
def test_changed_database_rejected_before_next_operation(task, operation, monkeypatch):
    api = _api()
    capture = _finished(api, task)
    session = _start(api, task)
    _mutate_database(task)
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, api, forbidden=True)
    with pytest.raises(REJECT):
        _operation(api, operation, session, capture, task, capture.ids)
    if operation != "rescore":
        _invalidated(session)
    assert calls == scores == []


@pytest.mark.parametrize("operation", ("start", "step", "finish", "rescore"))
@pytest.mark.parametrize("suffix", ("-wal", "-journal", "-shm"))
@pytest.mark.parametrize("contents", (b"", b"stale-sidecar"))
def test_sidecars_reject_before_execution_or_scoring(task, operation, suffix, contents, monkeypatch):
    api = _api()
    capture = _finished(api, task)
    session = _start(api, task)
    Path(task.db_path + suffix).write_bytes(contents)
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, api, forbidden=True)
    with pytest.raises(REJECT):
        if operation == "start":
            _start(api, task)
        else:
            _operation(api, operation, session, capture, task, capture.ids)
    assert calls == scores == []


def test_live_uncheckpointed_wal_rejects_before_next_step(task, monkeypatch):
    api = _api()
    session = _start(api, task)
    connection = sqlite3.connect(task.db_path)
    try:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("UPDATE school SET name = name || '-wal' WHERE school_id = 1")
        connection.commit()
        assert Path(task.db_path + "-wal").stat().st_size > 0
        calls = _dispatch_spy(monkeypatch)
        scores = _score_spy(monkeypatch, api, forbidden=True)
        with pytest.raises(REJECT):
            session.step(FIRST)
        _invalidated(session)
        assert calls == scores == []
    finally:
        connection.close()


@pytest.mark.parametrize("operation", ("step", "finish", "rescore"))
@pytest.mark.parametrize("change", ("prompt", "cap"))
def test_current_prompt_and_budget_settings_are_rechecked(task, operation, change, monkeypatch):
    from ptc import sql_arms
    from train import grpo_ptc, guards

    api = _api()
    capture = _finished(api, task)
    session = _start(api, task)
    if change == "prompt":
        monkeypatch.setattr(sql_arms, "SHARED_PROMPT", sql_arms.SHARED_PROMPT + "\nchanged")
    else:
        original = guards.eval_max_turns
        for module in (guards, grpo_ptc, api):
            if getattr(module, "eval_max_turns", None) is original:
                monkeypatch.setattr(module, "eval_max_turns", lambda *args, **kwargs: 7)
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, api, forbidden=True)
    with pytest.raises(REJECT):
        _operation(api, operation, session, capture, task, capture.ids)
    assert calls == scores == []


@pytest.mark.parametrize("operation", ("step", "finish", "rescore"))
@pytest.mark.parametrize("relative_path", SOURCE_PATHS)
def test_actual_capture_environment_budget_and_scorer_sources_are_bound(
    task, operation, relative_path, monkeypatch,
):
    api = _api()
    capture = _finished(api, task)
    session = _start(api, task)
    assert set(SOURCE_PATHS) <= set(capture.instrument.source_paths)
    target = Path(__file__).resolve().parents[1] / relative_path
    reads = []

    def altered_reader(original):
        def read(file, mode="r", *args, **kwargs):
            try:
                selected = Path(file).resolve() == target
            except TypeError:
                selected = False
            if selected and "r" in mode:
                with original(file, mode, *args, **kwargs) as handle:
                    data = handle.read()
                reads.append(relative_path)
                return (
                    io.BytesIO(data + b"\n# capture-source-change\n") if "b" in mode
                    else io.StringIO(data + "\n# capture-source-change\n")
                )
            return original(file, mode, *args, **kwargs)
        return read

    monkeypatch.setattr(builtins, "open", altered_reader(builtins.open))
    monkeypatch.setattr(io, "open", altered_reader(io.open))
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, api, forbidden=True)
    with pytest.raises(REJECT):
        _operation(api, operation, session, capture, task, capture.ids)
    assert relative_path in reads
    assert calls == scores == []


@pytest.mark.parametrize("operation", ("step", "finish", "rescore"))
def test_database_is_checked_after_execution_and_scoring(task, operation, monkeypatch):
    from bench import score
    from ptc import sql_arms
    from train import sql_episodes

    api = _api()
    capture = _finished(api, task)
    session = _start(api, task)
    original_run = sql_arms.ArmPair.run
    original_score = score.execution_accuracy
    calls = []

    def changed_run(*args, **kwargs):
        observation = original_run(*args, **kwargs)
        calls.append("action")
        _mutate_database(task)
        return observation

    def changed_score(*args, **kwargs):
        result = original_score(*args, **kwargs)
        calls.append("score")
        _mutate_database(task)
        return result

    if operation == "step":
        monkeypatch.setattr(sql_arms.ArmPair, "run", changed_run)
    else:
        for module in (score, sql_episodes, api):
            if getattr(module, "execution_accuracy", None) is original_score:
                monkeypatch.setattr(module, "execution_accuracy", changed_score)
    with pytest.raises(REJECT):
        _operation(api, operation, session, capture, task, capture.ids)
    assert calls == ["action" if operation == "step" else "score"]
    if operation != "rescore":
        _invalidated(session)


@pytest.mark.parametrize("field", (
    "task_id", "task_fingerprint", "db_sha256", "prompt", "schema", "backend",
    "ids", "action_cap", "action_max_rows", "scorer_max_rows", "compare",
    "scorer_timeout_s", "program_timeout_s", "wrapper_timeout_s",
    "source_sha256", "source_paths", "python_version", "sqlite_version",
))
def test_recomputed_digest_cannot_bypass_external_bindings(task, field, monkeypatch):
    api = _api()
    capture = _finished(api, task)
    payload = json.loads(api.encode_capture(capture))["payload"]
    if field == "ids":
        payload["ids"]["run_id"] += "-forged"
    elif field in ("task_fingerprint", "db_sha256"):
        payload[field] = "0" * 64
    elif field in ("task_id", "prompt", "schema", "backend"):
        payload[field] += "-forged"
    else:
        old = payload["instrument"][field]
        payload["instrument"][field] = (
            "0" * 64 if field == "source_sha256" else
            old[:-1] if field == "source_paths" else
            "multiset" if field == "compare" else
            old + "-forged" if isinstance(old, str) else old + 1
        )
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, api, forbidden=True)
    with pytest.raises(REJECT):
        forged = api.decode_capture(_envelope(payload))
        api.rescore_capture(forged, task, ids=capture.ids)
    assert calls == scores == []


def test_canonical_frozen_roundtrip_and_distinct_scripted_format(task):
    from train import sql_episodes

    api = _api()
    capture = _finished(api, task, actions=(FIRST,), ids=_ids(episode_id="capture-ελληνικά"))

    def visit(value):
        assert not isinstance(value, (list, dict, set))
        assert not callable(value)
        if dataclasses.is_dataclass(value):
            assert value.__dataclass_params__.frozen
            for field in dataclasses.fields(value):
                child = getattr(value, field.name)
                with pytest.raises(dataclasses.FrozenInstanceError):
                    setattr(value, field.name, child)
                visit(child)
        elif isinstance(value, tuple):
            for child in value:
                visit(child)
        else:
            assert value is None or type(value) in (str, int, float, bool)

    visit(capture)
    assert type(capture.ids) is sql_episodes.EpisodeIds
    assert type(capture.instrument) is sql_episodes.InstrumentSettings
    assert type(capture.steps[0]) is sql_episodes.ActionObservation
    encoded = api.encode_capture(capture)
    envelope = json.loads(encoded)
    assert set(envelope) == {"format", "schema_version", "payload", "sha256"}
    assert envelope["format"] == FORMAT
    assert envelope["schema_version"] == capture.schema_version == 1
    assert encoded == _canonical(envelope)
    assert envelope["payload"] == json.loads(_canonical(dataclasses.asdict(capture)))
    assert envelope["sha256"] == hashlib.sha256(_canonical(envelope["payload"])).hexdigest()
    assert "ελληνικά".encode("utf-8") in encoded
    assert api.encode_capture(api.decode_capture(encoded)) == encoded
    scripted = sql_episodes.record_scripted(
        task, arm="ptc", actions=(), final_answer=task.gold_sql, ids=capture.ids,
    )
    assert scripted.schema_version == 1
    assert scripted.origin == "scripted"
    assert scripted.terminal_label == "scripted_final"
    with pytest.raises(REJECT):
        api.decode_capture(sql_episodes.encode_episode(scripted))
    with pytest.raises(REJECT):
        sql_episodes.decode_episode(encoded)


def test_decode_and_rescore_never_execute_artifact_actions(task, tmp_path, monkeypatch):
    from ptc import sql_arms
    from train import grpo_ptc

    api = _api()
    capture = _finished(api, task, actions=(FIRST,))
    payload = json.loads(api.encode_capture(capture))["payload"]
    marker = tmp_path / "decode-must-not-execute"
    payload["steps"][0]["action"] = f"open({str(marker)!r}, 'w').write('unsafe')"
    calls = _dispatch_spy(monkeypatch)
    with monkeypatch.context() as patch:
        scores = _score_spy(patch, api, forbidden=True)
        builds = []

        def forbidden(*args, **kwargs):
            builds.append(True)
            raise AssertionError("decode built an execution environment")

        real_environment = grpo_ptc.sql_environment
        patch.setattr(grpo_ptc, "sql_environment", forbidden)
        patch.setattr(sql_arms, "build_sql_arms", forbidden)
        if getattr(api, "sql_environment", None) is real_environment:
            patch.setattr(api, "sql_environment", forbidden)
        restored = api.decode_capture(_envelope(payload))
        assert builds == scores == calls == []
    assert api.rescore_capture(restored, task, ids=capture.ids) == capture.result
    assert calls == []
    assert not marker.exists()


@pytest.mark.parametrize("location", (
    "envelope", "payload", "ids", "instrument", "step", "result",
))
def test_unknown_keys_rejected_at_every_layer(task, location):
    api = _api()
    envelope = json.loads(api.encode_capture(_finished(api, task, actions=(FIRST,))))
    if location == "envelope":
        envelope["unexpected"] = 1
        data = _canonical(envelope)
    else:
        payload = envelope["payload"]
        target = (
            payload if location == "payload" else payload["steps"][0]
            if location == "step" else payload[location]
        )
        target["unexpected"] = 1
        data = _envelope(payload)
    with pytest.raises(REJECT):
        api.decode_capture(data)


@pytest.mark.parametrize("location", (
    "envelope", "payload", "ids", "instrument", "step", "result",
))
def test_duplicate_keys_rejected_even_with_unchanged_meaning(task, location):
    api = _api()
    encoded = api.encode_capture(_finished(api, task, actions=(FIRST,)))
    key = {
        "envelope": "format", "payload": "origin", "ids": "run_id",
        "instrument": "source_sha256", "step": "action", "result": "valid",
    }[location]
    pattern = rb'"' + key.encode() + rb'":("(?:\\.|[^"\\])*"|true|false)'
    changed, count = re.subn(
        pattern, lambda match: match[0] + b"," + match[0], encoded, count=1,
    )
    assert count == 1
    with pytest.raises(REJECT):
        api.decode_capture(changed)


@pytest.mark.parametrize("version", (0, 2, True, "1", None))
@pytest.mark.parametrize("location", ("envelope", "payload"))
def test_unknown_or_mistyped_versions_rejected(task, version, location):
    api = _api()
    payload = json.loads(api.encode_capture(_finished(api, task)))["payload"]
    if location == "payload":
        payload["schema_version"] = version
    with pytest.raises(REJECT):
        api.decode_capture(_envelope(
            payload, version=version if location == "envelope" else 1,
        ))


@pytest.mark.parametrize("location,key,value", (
    ("payload", "origin", "scripted"),
    ("payload", "arm", "bash"),
    ("payload", "terminal_label", "scripted_final"),
    ("payload", "steps", {}),
    ("payload", "refusals", None),
    ("payload", "final_answer", None),
    ("payload", "extracted_sql", 1),
    ("payload", "result", None),
    ("ids", "run_id", True),
    ("instrument", "action_cap", True),
    ("instrument", "action_cap", 8.5),
    ("instrument", "action_max_rows", 0),
    ("instrument", "scorer_max_rows", "500000"),
    ("instrument", "scorer_timeout_s", True),
    ("instrument", "source_paths", "train/sql_capture.py"),
    ("result", "score", True),
    ("result", "valid", 1),
    ("result", "n_pred_rows", -1),
    ("step", "action", 1),
    ("step", "observation", []),
))
def test_wrong_nested_types_rejected_with_recomputed_digest(task, location, key, value):
    api = _api()
    payload = json.loads(api.encode_capture(
        _finished(api, task, actions=(FIRST,)),
    ))["payload"]
    target = (
        payload if location == "payload" else payload["steps"][0]
        if location == "step" else payload[location]
    )
    target[key] = value
    with pytest.raises(REJECT):
        api.decode_capture(_envelope(payload))


@pytest.mark.parametrize("field", ("score", "scorer_timeout_s"))
@pytest.mark.parametrize("number", (float("nan"), float("inf"), -float("inf")))
def test_nonfinite_numbers_rejected(task, field, number):
    api = _api()
    payload = json.loads(api.encode_capture(_finished(api, task)))["payload"]
    payload["result" if field == "score" else "instrument"][field] = number
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    data = json.dumps({
        "format": FORMAT, "schema_version": 1, "payload": payload,
        "sha256": hashlib.sha256(body.encode()).hexdigest(),
    }).encode()
    with pytest.raises(REJECT):
        api.decode_capture(data)


@pytest.mark.parametrize("bad", (
    b"", b"{", b"[]", b"null", b"\xff", b'{"payload":',
    b'__import__("os").system("false")', b"\x80\x04not-json",
    "", None, [], {},
))
def test_malformed_or_nonbytes_evidence_rejected(bad):
    api = _api()
    with pytest.raises(REJECT):
        api.decode_capture(bad)


@pytest.mark.parametrize("digest", ("", "a" * 63, "g" * 64, "A" * 64, "0" * 64, None, 1))
def test_bad_corruption_digest_rejected(task, digest):
    api = _api()
    envelope = json.loads(api.encode_capture(_finished(api, task)))
    envelope["sha256"] = digest
    with pytest.raises(REJECT):
        api.decode_capture(_canonical(envelope))


@pytest.mark.parametrize("format_name", ("scripted", "", None, True, 1))
def test_distinct_format_discriminator_is_required(task, format_name):
    api = _api()
    envelope = json.loads(api.encode_capture(_finished(api, task)))
    envelope["format"] = format_name
    with pytest.raises(REJECT):
        api.decode_capture(_canonical(envelope))


def test_terminal_and_attempt_invariants_rejected(task):
    api = _api()
    capture = _finished(api, task, actions=(FIRST,))
    baseline = json.loads(api.encode_capture(capture))["payload"]
    for mutate in (
        lambda p: p.update(steps=p["steps"] * 9),
        lambda p: p.update(refusals=p["steps"]),
        lambda p: p.update(terminal_label="aborted"),
    ):
        payload = json.loads(_canonical(baseline))
        mutate(payload)
        with pytest.raises(REJECT):
            api.decode_capture(_envelope(payload))


@pytest.mark.parametrize("method", ("step", "finish"))
@pytest.mark.parametrize("value", (None, True, 1, [], {}))
def test_bad_session_input_invalidates_before_dispatch(task, method, value, monkeypatch):
    api = _api()
    session = _start(api, task)
    calls = _dispatch_spy(monkeypatch)
    scores = _score_spy(monkeypatch, api, forbidden=True)
    with pytest.raises(REJECT):
        getattr(session, method)(value)
    _invalidated(session)
    assert calls == scores == []


def test_eight_mib_limit_fails_loudly_without_truncation(task, monkeypatch):
    from ptc import sql_arms

    api = _api()
    capture = _finished(api, task, actions=(FIRST,))
    with pytest.raises(REJECT):
        api.decode_capture(b" " * (MAX_BYTES + 1))
    payload = dataclasses.asdict(capture)
    payload["steps"] = [{"action": FIRST, "observation": "x" * MAX_BYTES}]
    with pytest.raises(REJECT):
        api.decode_capture(_envelope(payload))
    with pytest.raises(REJECT):
        oversized = dataclasses.replace(
            capture, steps=(dataclasses.replace(capture.steps[0], observation="x" * MAX_BYTES),),
        )
        api.encode_capture(oversized)
    for method in ("step", "finish"):
        session = _start(api, task)
        with monkeypatch.context() as patch:
            calls = _dispatch_spy(patch)
            scores = _score_spy(patch, api, forbidden=True)
            with pytest.raises(REJECT):
                getattr(session, method)("x" * MAX_BYTES)
            _invalidated(session)
            assert calls == scores == []
    session = _start(api, task)

    def oversized_observation(*args, **kwargs):
        return "x" * MAX_BYTES

    with monkeypatch.context() as patch:
        patch.setattr(sql_arms.ArmPair, "run", oversized_observation)
        with pytest.raises(REJECT):
            session.step(FIRST)
    _invalidated(session)


def test_capture_methods_are_not_native_tools_and_training_gate_stays_closed(task):
    from train import grpo_ptc, guards, sql_bridge

    _api()
    inputs = sql_bridge.prepare_sql_training([task], Path(task.db_path).parents[1])
    environment = inputs.environment_factory()
    assert [
        name for name, method in inspect.getmembers(environment, inspect.ismethod)
        if not name.startswith("_") and name not in ("reset", "get_reward")
    ] == ["run_program"]
    assert grpo_ptc.THE_TOOL_SCHEMA["function"]["name"] == "run_program"
    assert not any(hasattr(environment, name) for name in (
        "start_capture", "finish", "abort", "encode_capture", "decode_capture",
    ))
    with pytest.raises(guards.PreconditionUnmet):
        grpo_ptc.main(["--preflight-only"])


def _extraction_attack(wrapper):
    sql = "SELECT '" + ";" * 2_000_000 + "'"
    answer = (
        f"```sql\n{sql}\n```" if wrapper == "tagged" else
        f"Reasoning, then final query:\n{sql}" if wrapper == "prose" else sql
    )
    return answer, sql


def _extraction_sentries(monkeypatch, api):
    calls = []

    def sentry(kind):
        def fail(*args, **kwargs):
            calls.append(kind)
            raise AssertionError(f"extraction-admission sentry: {kind}")
        return fail

    monkeypatch.setattr(api.evidence, "extract_sql", sentry("extractor"))
    monkeypatch.setattr(api.evidence, "_score", sentry("scorer"))
    monkeypatch.setattr(api.evidence.sql_arms.ArmPair, "run", sentry("dispatch"))
    return calls


@pytest.mark.parametrize("wrapper", ("bare", "tagged", "prose"))
def test_decode_rejects_extraction_work_before_extractor(task, wrapper, monkeypatch):
    api = _api()
    capture = _finished(api, task)
    answer, sql = _extraction_attack(wrapper)
    payload = dataclasses.asdict(capture)
    payload.update(final_answer=answer, extracted_sql=sql)
    encoded = _envelope(payload)
    assert len(encoded) < MAX_BYTES
    calls = _extraction_sentries(monkeypatch, api)
    with pytest.raises(ValueError, match="extraction work"):
        api.decode_capture(encoded)
    assert calls == []


@pytest.mark.parametrize("operation", ("finish", "rescore", "encode", "constructor"))
@pytest.mark.parametrize("wrapper", ("bare", "tagged", "prose"))
def test_all_capture_paths_bound_extraction_before_side_effects(
    task, operation, wrapper, monkeypatch,
):
    api = _api()
    capture = _finished(api, task)
    session = _start(api, task)
    answer, sql = _extraction_attack(wrapper)
    if operation in ("rescore", "encode"):
        # Exercise entry validation without triggering the constructor in setup.
        object.__setattr__(capture, "final_answer", answer)
        object.__setattr__(capture, "extracted_sql", sql)
    calls = _extraction_sentries(monkeypatch, api)
    with pytest.raises(ValueError, match="extraction work"):
        if operation == "finish":
            session.finish(answer)
        elif operation == "rescore":
            api.rescore_capture(capture, task, ids=capture.ids)
        elif operation == "encode":
            api.encode_capture(capture)
        else:
            dataclasses.replace(capture, final_answer=answer, extracted_sql=sql)
    if operation == "finish":
        _invalidated(session)
    assert calls == []


@pytest.mark.parametrize("alphabet", ("ascii", "utf8"))
def test_extraction_work_exact_boundary_counts_utf8_bytes(task, alphabet, monkeypatch):
    api = _api()
    capture = _finished(api, task)
    limit = 64 * 1024 * 1024
    # Eight trailing semicolons: W = 9*N + 44 + tail_bytes.
    length, tail = divmod(limit - 44, 9)
    prefix = (
        "x" * length if alphabet == "ascii"
        else "é" * (length // 2) + "x" * (length % 2)
    )
    answer = prefix + ";" * 8 + "y" * tail
    encoded = answer.encode("utf-8")
    work = len(encoded) + sum(match.end() for match in re.finditer(b";", encoded))
    assert work == limit
    assert len(encoded) < MAX_BYTES
    if alphabet == "utf8":
        character_work = len(answer) + sum(match.end() for match in re.finditer(";", answer))
        assert character_work + 1 < limit
    calls = []

    def stub(text):
        calls.append(text)
        return "SELECT 1"

    monkeypatch.setattr(api.evidence, "extract_sql", stub)
    admitted = dataclasses.replace(capture, final_answer=answer, extracted_sql="SELECT 1")
    assert admitted.final_answer == answer
    assert calls == [answer]
    calls.clear()
    with pytest.raises(ValueError, match="extraction work"):
        dataclasses.replace(capture, final_answer=answer + "z", extracted_sql="SELECT 1")
    assert calls == []


@pytest.mark.parametrize("answer", (
    "SELECT 1",
    "```sql\nSELECT 1;\n```",
    "Reasoning.\n```sql\nSELECT 'a;b' AS value;\n```",
    "SELECT 'a;b' AS value; SELECT 2",
    "SELECT 1 /* ; ; quoted-looking ';' */; SELECT 2",
    "SELECT 1 -- ; ;\n; SELECT 2",
    "SELECT '" + "x" * 1_000_000 + "'",
), ids=("plain", "fence", "fenced-quoted", "quoted", "comment", "line-comment", "large-literal"))
def test_admitted_extraction_preserves_actual_existing_semantics(task, answer, monkeypatch):
    api = _api()
    capture = _finished(api, task)
    original = api.evidence.extract_sql
    expected = original(answer)
    calls = []

    def tracked(text):
        calls.append(text)
        return original(text)

    monkeypatch.setattr(api.evidence, "extract_sql", tracked)
    changed = dataclasses.replace(capture, final_answer=answer, extracted_sql=expected)
    assert calls == [answer]
    assert api.decode_capture(api.encode_capture(changed)) == changed
    assert all(text == answer for text in calls)
