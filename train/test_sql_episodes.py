"""Offline contracts for scripted SQL evidence, not model/policy reproduction.

The missing implementation fails inside _api(), never during collection. Real
fixture tasks, existing arms and the existing scorer are the execution oracle.
The SHA envelope detects corruption only; caller IDs are not authenticated.
"""

from __future__ import annotations

import builtins
import dataclasses
import hashlib
import importlib
import inspect
import io
import json
import platform
import re
import shlex
import shutil
import sqlite3
from pathlib import Path

import pytest

from bench import fixture, score
from bench.loader import load_bird
from ptc import runtime, sql_arms, sql_runtime
from train import guards


MAX_BYTES = 8 * 1024 * 1024
REJECT = (TypeError, ValueError)
SOURCE_PATHS = (
    "bench/score.py",
    "ptc/sql_arms.py",
    "ptc/runtime.py",
    "ptc/sql_runtime.py",
    "ptc/sqlite_safety.py",
    "ptc/harness.py",
)
ID_FIELDS = (
    "corpus_id", "split_id", "run_id", "episode_id", "policy_id",
    "policy_revision",
)


def _api():
    try:
        return importlib.import_module("train.sql_episodes")
    except ModuleNotFoundError as exc:
        if exc.name != "train.sql_episodes":
            raise
        pytest.fail("train.sql_episodes is not implemented", pytrace=False)


def _ids(api, **changes):
    values = dict(zip(ID_FIELDS, (
        "committed-bird-fixture", "offline-engineering", "fixture-run",
        "fixture-episode", "scripted-gold", "fixture-v1",
    )))
    values.update(changes)
    return api.EpisodeIds(**values)


def _actions(task, arm):
    if arm == "ptc":
        return (
            f"print(execute_sql(query={task.gold_sql!r}))",
            "print(execute_sql(query='SELECT FROM nowhere'))",
            "print('partial-marker'); "
            "print(execute_sql(query='SELECT FROM nowhere'))",
        )
    return (
        "execute_sql " + shlex.quote(task.gold_sql),
        "execute_sql 'SELECT FROM nowhere'",
        "printf 'partial-marker\\n'; execute_sql 'SELECT FROM nowhere'",
    )


def _record(api, task, *, arm="ptc", actions=(), final_answer=None, ids=None):
    return api.record_scripted(
        task, arm=arm, actions=actions,
        final_answer=task.gold_sql if final_answer is None else final_answer,
        ids=_ids(api) if ids is None else ids,
    )


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _envelope(payload, *, version=1):
    return _canonical({
        "schema_version": version,
        "payload": payload,
        "sha256": hashlib.sha256(_canonical(payload)).hexdigest(),
    })


def _forbid_dispatch(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("backend action dispatched before validation/opt-in")

    monkeypatch.setattr(sql_arms.ArmPair, "run", forbidden)
    return calls


def _spy_dispatch(monkeypatch):
    original = sql_arms.ArmPair.run
    calls = []

    def run(pair, arm, action, *, bindir=None):
        calls.append((arm, action, bindir))
        return original(pair, arm, action, bindir=bindir)

    monkeypatch.setattr(sql_arms.ArmPair, "run", run)
    return calls


@pytest.fixture(autouse=True)
def no_model_stack(monkeypatch):
    """Fail even when an implementation catches an unwanted import."""
    original_import = builtins.__import__
    original_import_module = importlib.import_module
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

    def guarded_import_module(name, *args, **kwargs):
        check(name)
        return original_import_module(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(importlib, "import_module", guarded_import_module)
    yield
    assert attempted == []


@pytest.fixture
def tasks(tmp_path):
    return load_bird(fixture.materialize(tmp_path / "corpus"))


@pytest.fixture
def task(tasks):
    return tasks[0]


@pytest.mark.parametrize("arm", ("ptc", "bash"))
def test_all_fixture_tasks_match_direct_backend_and_two_fresh_replays(
    tasks, arm, tmp_path,
):
    api = _api()
    assert len(tasks) == len(fixture.records()) >= 8
    for index, task in enumerate(tasks):
        ids = _ids(api, episode_id=f"{arm}-{index}")
        actions = _actions(task, arm)
        pair = sql_arms.build_sql_arms(task)
        expected = tuple(
            pair.run(arm, action, bindir=tmp_path / f"direct-{arm}-{index}")
            for action in actions
        )
        episode = _record(api, task, arm=arm, actions=actions, ids=ids)
        assert episode.origin == "scripted"
        assert episode.schema_version == 1
        assert episode.ids == ids
        assert episode.arm == arm
        assert episode.task_id == task.name
        assert episode.schema == pair.schema
        assert episode.prompt.encode("utf-8") == pair.prompt(arm).encode("utf-8")
        assert episode.backend == pair.backend.name == "ptc-v1"
        assert isinstance(episode.steps, tuple)
        assert tuple(step.action for step in episode.steps) == actions
        observations = tuple(step.observation for step in episode.steps)
        assert tuple(x.encode("utf-8") for x in observations) == tuple(
            x.encode("utf-8") for x in expected
        )
        if arm == "ptc":
            assert "partial-marker" not in observations[-1]
        else:
            assert "partial-marker" in observations[-1]
        assert episode.result == score.execution_accuracy(task.gold_sql, task)
        assert episode.result.score == 1.0
        original = api.encode_episode(episode)
        for _ in range(2):
            replay = api.reexecute_sql(
                episode, task, ids=ids, allow_execution=True,
            )
            assert isinstance(replay.observations, tuple)
            assert replay.observations == expected
            assert replay.result == episode.result
            assert replay.observations_match is True
            assert replay.score_matches is True
            assert api.encode_episode(episode) == original


def test_instrument_records_distinct_limits_defaults_and_runtime(task):
    api = _api()
    episode = _record(api, task)
    instrument = episode.instrument
    pair = sql_arms.build_sql_arms(task)
    scorer = inspect.signature(score.execution_accuracy).parameters
    assert instrument.action_cap == guards.eval_max_turns() == 8
    assert instrument.action_max_rows == pair.max_rows == sql_runtime.MAX_ROWS
    assert instrument.scorer_max_rows == scorer["max_rows"].default == score.MAX_ROWS
    assert instrument.action_max_rows != instrument.scorer_max_rows
    assert instrument.compare == scorer["compare"].default == "set"
    assert instrument.scorer_timeout_s == scorer["timeout_s"].default
    assert instrument.program_timeout_s == pair.budget.program_timeout == runtime.TIMEOUT
    assert instrument.wrapper_timeout_s == sql_arms.WRAPPER_TIMEOUT
    assert instrument.python_version == platform.python_version()
    assert instrument.sqlite_version == sqlite3.sqlite_version
    assert re.fullmatch("[0-9a-f]{64}", instrument.source_sha256)
    assert instrument.source_paths == SOURCE_PATHS
    assert re.fullmatch("[0-9a-f]{64}", episode.task_fingerprint)
    assert episode.db_sha256 == hashlib.sha256(Path(task.db_path).read_bytes()).hexdigest()
    assert episode.final_answer == task.gold_sql
    assert episode.extracted_sql == score.extract_sql(task.gold_sql)
    assert episode.terminal_label == "scripted_final"
    assert not any(
        word in field.name
        for field in dataclasses.fields(episode)
        for word in ("token", "logprob", "model", "generation")
    )


@pytest.mark.parametrize("arm", ("ptc", "bash"))
def test_eight_actions_accepted_and_final_does_not_spend_an_action(
    task, arm, monkeypatch,
):
    api = _api()
    calls = _spy_dispatch(monkeypatch)
    actions = (_actions(task, arm)[0],) * 8
    episode = _record(api, task, arm=arm, actions=actions)
    assert len(episode.steps) == len(calls) == guards.eval_max_turns() == 8
    assert episode.result.score == 1.0


@pytest.mark.parametrize("arm", ("ptc", "bash"))
@pytest.mark.parametrize("bad", ("nine", "late_nonstring", "bare_string", "iterator"))
def test_complete_action_admission_precedes_build_and_dispatch(
    task, arm, bad, monkeypatch,
):
    api = _api()
    action = _actions(task, arm)[0]
    actions = {
        "nine": (action,) * 9,
        "late_nonstring": (action,) * 7 + (None,),
        "bare_string": action,
        "iterator": iter((action,)),
    }[bad]
    calls = _forbid_dispatch(monkeypatch)
    built = []

    def forbidden(*args, **kwargs):
        built.append(True)
        raise AssertionError("arms built before complete action admission")

    monkeypatch.setattr(sql_arms, "build_sql_arms", forbidden)
    if hasattr(api, "build_sql_arms"):
        monkeypatch.setattr(api, "build_sql_arms", forbidden)
    with pytest.raises(REJECT):
        _record(api, task, arm=arm, actions=actions)
    assert calls == built == []


@pytest.mark.parametrize("arm", ("", "other", None, True, 1))
def test_invalid_arm_rejected_without_dispatch(task, arm, monkeypatch):
    api = _api()
    calls = _forbid_dispatch(monkeypatch)
    with pytest.raises(REJECT):
        _record(api, task, arm=arm)
    assert calls == []


@pytest.mark.parametrize("field", ID_FIELDS)
@pytest.mark.parametrize("value", ("", None, True, 7))
def test_ids_are_nonempty_strings(field, value):
    api = _api()
    with pytest.raises(REJECT):
        _ids(api, **{field: value})


@pytest.mark.parametrize("value", (None, 1, True, [], {}))
def test_final_answer_requires_string_before_dispatch(task, value, monkeypatch):
    api = _api()
    calls = _forbid_dispatch(monkeypatch)
    with pytest.raises(REJECT):
        api.record_scripted(task, arm="ptc", actions=(), final_answer=value, ids=_ids(api))
    assert calls == []


@pytest.mark.parametrize("arm", ("ptc", "bash"))
@pytest.mark.parametrize("final", (
    "gold", "SELECT 'definitely wrong' AS answer", "", "SELECT FROM nowhere",
    "fenced",
))
@pytest.mark.parametrize("invalid_gold", (False, True))
def test_every_exresult_field_and_extraction_match_existing_scorer(
    task, arm, final, invalid_gold,
):
    api = _api()
    if invalid_gold:
        task = dataclasses.replace(task, gold_sql="SELECT * FROM nonexistent_gold_table")
    answer = (
        task.gold_sql if final == "gold" else
        f"Some reasoning.\n```sql\n{task.gold_sql};\n```" if final == "fenced" else final
    )
    expected = score.execution_accuracy(score.extract_sql(answer), task)
    episode = _record(
        api, task, arm=arm, actions=(_actions(task, arm)[1],), final_answer=answer,
    )
    assert isinstance(episode.result, score.ExResult)
    assert dataclasses.asdict(episode.result) == dataclasses.asdict(expected)
    assert episode.final_answer == answer
    assert episode.extracted_sql == score.extract_sql(answer)
    assert api.rescore_sql(episode, task, ids=episode.ids) == expected
    if invalid_gold:
        assert episode.result.valid is False
        assert episode.result.status == "gold_error"
    elif final in ("gold", "fenced"):
        # A rejected action is not a verdict on the final SQL.
        assert episode.result.score == 1.0


@pytest.mark.parametrize("arm", ("ptc", "bash"))
def test_decode_and_rescore_dispatch_zero_actions_and_replay_exact_count(
    task, arm, monkeypatch,
):
    api = _api()
    episode = _record(api, task, arm=arm, actions=_actions(task, arm))
    data = api.encode_episode(episode)
    calls = _spy_dispatch(monkeypatch)
    restored = api.decode_episode(data)
    assert calls == []
    assert api.rescore_sql(restored, task, ids=episode.ids) == episode.result
    assert calls == []
    api.reexecute_sql(restored, task, ids=episode.ids, allow_execution=True)
    assert len(calls) == len(episode.steps) == 3
    assert tuple(action for _, action, _ in calls) == _actions(task, arm)


@pytest.mark.parametrize("opt_in", ("omitted", False, None, 1, "true"))
def test_replay_requires_literal_true(task, opt_in, monkeypatch):
    api = _api()
    episode = _record(api, task, actions=_actions(task, "ptc"))
    calls = _forbid_dispatch(monkeypatch)
    kwargs = {} if opt_in == "omitted" else {"allow_execution": opt_in}
    with pytest.raises(REJECT):
        api.reexecute_sql(episode, task, ids=episode.ids, **kwargs)
    assert calls == []


def test_bash_wrapper_directories_are_fresh_private_and_managed(task, monkeypatch):
    api = _api()
    original = sql_arms.ArmPair.run
    directories = []

    def run(pair, arm, action, *, bindir=None):
        assert arm == "bash"
        assert bindir is not None
        directory = Path(bindir)
        assert directory.is_dir()
        assert directory.stat().st_mode & 0o777 == 0o700
        directories.append(directory)
        return original(pair, arm, action, bindir=bindir)

    monkeypatch.setattr(sql_arms.ArmPair, "run", run)
    episode = _record(api, task, arm="bash", actions=_actions(task, "bash")[:1])
    for _ in range(2):
        api.reexecute_sql(episode, task, ids=episode.ids, allow_execution=True)
    assert len(set(directories)) == len(directories) == 3
    assert all(not directory.exists() for directory in directories)
    assert "bindir" not in inspect.signature(api.record_scripted).parameters
    assert "bindir" not in inspect.signature(api.reexecute_sql).parameters


def test_replay_reports_mismatch_without_normalizing_retrying_or_mutating(
    task, monkeypatch,
):
    api = _api()
    episode = _record(api, task, actions=_actions(task, "ptc")[:1])
    before = api.encode_episode(episode)
    calls = []

    def different(*args, **kwargs):
        calls.append(True)
        return episode.steps[0].observation + "\n"

    monkeypatch.setattr(sql_arms.ArmPair, "run", different)
    replay = api.reexecute_sql(episode, task, ids=episode.ids, allow_execution=True)
    assert calls == [True]
    assert replay.observations == (episode.steps[0].observation + "\n",)
    assert replay.observations_match is False
    assert replay.score_matches is True
    assert replay.result == episode.result
    assert api.encode_episode(episode) == before


def test_episode_and_all_nested_records_are_immutable(task):
    api = _api()
    supplied_actions = list(_actions(task, "ptc")[:1])
    episode = _record(api, task, actions=supplied_actions)
    supplied_actions[0] = "print('changed after recording')"
    assert episode.steps[0].action == _actions(task, "ptc")[0]

    def visit(value):
        assert not isinstance(value, (dict, list, set))
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

    visit(episode)


def test_canonical_utf8_sha_envelope_roundtrips_byte_for_byte(task):
    api = _api()
    ids = _ids(api, episode_id="fixture-ελληνικά")
    episode = _record(api, task, ids=ids, actions=_actions(task, "ptc")[:1])
    encoded = api.encode_episode(episode)
    assert isinstance(encoded, bytes)
    envelope = json.loads(encoded)
    assert set(envelope) == {"schema_version", "payload", "sha256"}
    assert envelope["schema_version"] == 1
    assert envelope["payload"] == json.loads(_canonical(dataclasses.asdict(episode)))
    assert encoded == _canonical(envelope)
    assert envelope["sha256"] == hashlib.sha256(_canonical(envelope["payload"])).hexdigest()
    assert "ελληνικά".encode("utf-8") in encoded
    restored = api.decode_episode(encoded)
    assert restored == episode
    assert api.encode_episode(restored) == encoded


@pytest.mark.parametrize("bad", (
    b"", b"{", b"[]", b"null", b'{"payload":', b"\xff",
    b'{"schema_version":1,"schema_version":1}',
    b'__import__("os").system("false")', b"\x80\x04pickle-is-not-json",
))
def test_malformed_data_is_rejected_not_executed(bad, monkeypatch):
    api = _api()
    calls = _forbid_dispatch(monkeypatch)
    with pytest.raises(REJECT):
        api.decode_episode(bad)
    assert calls == []


@pytest.mark.parametrize("location", ("envelope", "payload", "ids", "instrument", "step", "result"))
def test_unknown_keys_rejected_at_every_record_layer(task, location):
    api = _api()
    episode = _record(api, task, actions=_actions(task, "ptc")[:1])
    payload = json.loads(api.encode_episode(episode))["payload"]
    if location == "envelope":
        envelope = json.loads(_envelope(payload))
        envelope["unexpected"] = 1
        encoded = _canonical(envelope)
    else:
        target = (
            payload if location == "payload" else payload["steps"][0]
            if location == "step" else payload[location]
        )
        target["unexpected"] = 1
        encoded = _envelope(payload)
    with pytest.raises(REJECT):
        api.decode_episode(encoded)


@pytest.mark.parametrize("version", (0, 2, True, "1", None))
@pytest.mark.parametrize("location", ("envelope", "payload"))
def test_unknown_or_mistyped_versions_rejected(task, version, location):
    api = _api()
    payload = json.loads(api.encode_episode(_record(api, task)))["payload"]
    if location == "payload":
        payload["schema_version"] = version
    encoded = _envelope(payload, version=version if location == "envelope" else 1)
    with pytest.raises(REJECT):
        api.decode_episode(encoded)


@pytest.mark.parametrize("digest", ("", "a" * 63, "g" * 64, "A" * 64, None, 1, "0" * 64))
def test_malformed_or_wrong_envelope_digest_rejected(task, digest):
    api = _api()
    envelope = json.loads(api.encode_episode(_record(api, task)))
    envelope["sha256"] = digest
    with pytest.raises(REJECT):
        api.decode_episode(_canonical(envelope))


@pytest.mark.parametrize("location,key,value", (
    ("payload", "origin", "model"),
    ("payload", "arm", "other"),
    ("payload", "final_answer", None),
    ("payload", "steps", {}),
    ("payload", "task_fingerprint", "bad-digest"),
    ("payload", "db_sha256", "bad-digest"),
    ("ids", "run_id", True),
    ("instrument", "action_cap", True),
    ("instrument", "action_cap", 8.5),
    ("instrument", "action_max_rows", 0),
    ("instrument", "scorer_max_rows", "500000"),
    ("instrument", "scorer_timeout_s", True),
    ("instrument", "source_sha256", "bad-digest"),
    ("result", "score", True),
    ("result", "valid", 1),
    ("result", "n_pred_rows", -1),
    ("step", "action", 1),
    ("step", "observation", []),
))
def test_invalid_nested_types_rejected_even_with_recomputed_digest(
    task, location, key, value,
):
    api = _api()
    payload = json.loads(api.encode_episode(
        _record(api, task, actions=_actions(task, "ptc")[:1]),
    ))["payload"]
    target = (
        payload if location == "payload" else payload["steps"][0]
        if location == "step" else payload[location]
    )
    target[key] = value
    with pytest.raises(REJECT):
        api.decode_episode(_envelope(payload))


@pytest.mark.parametrize("field", ("score", "scorer_timeout_s"))
@pytest.mark.parametrize("number", (float("nan"), float("inf"), -float("inf")))
def test_nonfinite_json_numbers_rejected(task, field, number):
    api = _api()
    payload = json.loads(api.encode_episode(_record(api, task)))["payload"]
    payload["result" if field == "score" else "instrument"][field] = number
    # Deliberately nonstandard JSON, with a matching corruption digest.
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    encoded = json.dumps({
        "schema_version": 1, "payload": payload,
        "sha256": hashlib.sha256(body.encode()).hexdigest(),
    }).encode()
    with pytest.raises(REJECT):
        api.decode_episode(encoded)


@pytest.mark.parametrize("location", ("envelope", "ids", "step", "result"))
def test_duplicate_json_keys_rejected_even_when_values_are_identical(task, location):
    api = _api()
    encoded = api.encode_episode(_record(api, task, actions=_actions(task, "ptc")[:1]))
    key = {"envelope": "sha256", "ids": "run_id", "step": "action", "result": "valid"}[location]
    # Duplicate a complete primitive member without changing parsed meaning/hash.
    pattern = rb'"' + key.encode() + rb'":("(?:\\.|[^"\\])*"|true|false)'
    encoded, count = re.subn(
        pattern, lambda match: match[0] + b"," + match[0], encoded, count=1,
    )
    assert count == 1
    with pytest.raises(REJECT):
        api.decode_episode(encoded)


def test_encoding_and_decoding_enforce_eight_mib_limit(task):
    api = _api()
    with pytest.raises(REJECT):
        api.decode_episode(b" " * (MAX_BYTES + 1))
    episode = _record(api, task)
    with pytest.raises(REJECT):
        oversized = dataclasses.replace(episode, final_answer="x" * MAX_BYTES)
        api.encode_episode(oversized)
    payload = dataclasses.asdict(episode)
    payload["final_answer"] = "x" * MAX_BYTES
    with pytest.raises(REJECT):
        api.decode_episode(_envelope(payload))


def test_decoding_does_not_execute_a_recomputed_artifact(task, tmp_path, monkeypatch):
    api = _api()
    episode = _record(api, task, arm="bash", actions=_actions(task, "bash")[:1])
    marker = tmp_path / "must-not-exist"
    step = dataclasses.replace(
        episode.steps[0], action="printf unsafe > " + shlex.quote(str(marker)),
    )
    changed = dataclasses.replace(episode, steps=(step,))
    encoded = _envelope(dataclasses.asdict(changed))
    calls = _forbid_dispatch(monkeypatch)
    restored = api.decode_episode(encoded)
    assert restored.steps[0].action == step.action
    assert calls == []
    assert not marker.exists()
    # Rescoring runs protected final/gold SQL, not the action in the envelope.
    assert api.rescore_sql(restored, task, ids=episode.ids) == episode.result
    assert not marker.exists()
    assert calls == []


def _check_bound_operation(api, operation, episode, task, ids):
    if operation == "rescore":
        return api.rescore_sql(episode, task, ids=ids)
    return api.reexecute_sql(episode, task, ids=ids, allow_execution=True)


@pytest.mark.parametrize("operation", ("rescore", "reexecute"))
@pytest.mark.parametrize("field", (
    "name", "question", "evidence", "gold_sql", "db_id", "tier",
    "tier_source", "shape", "coarse_shape", "source",
))
def test_every_task_field_except_mount_path_is_bound(
    task, operation, field, monkeypatch,
):
    api = _api()
    episode = _record(api, task, actions=_actions(task, "ptc")[:1])
    value = (
        "challenging" if field == "tier" else "derived" if field == "tier_source"
        else getattr(task, field) + "-changed"
    )
    changed_task = dataclasses.replace(task, **{field: value})
    calls = _forbid_dispatch(monkeypatch)
    with pytest.raises(REJECT):
        _check_bound_operation(api, operation, episode, changed_task, episode.ids)
    assert calls == []


def test_database_relocation_preserves_content_task_and_prompt_binding(task, tmp_path):
    api = _api()
    episode = _record(api, task)
    moved = tmp_path / "relocated.sqlite"
    shutil.copyfile(task.db_path, moved)
    relocated = dataclasses.replace(task, db_path=str(moved))
    other = _record(api, relocated)
    assert other.task_fingerprint == episode.task_fingerprint
    assert other.db_sha256 == episode.db_sha256
    assert other.prompt == episode.prompt
    assert api.rescore_sql(episode, relocated, ids=episode.ids) == episode.result


@pytest.mark.parametrize("operation", ("rescore", "reexecute"))
@pytest.mark.parametrize("field", ID_FIELDS)
def test_all_caller_ids_are_externally_bound(task, operation, field, monkeypatch):
    api = _api()
    episode = _record(api, task, actions=_actions(task, "ptc")[:1])
    changed_ids = dataclasses.replace(
        episode.ids, **{field: getattr(episode.ids, field) + "-changed"},
    )
    calls = _forbid_dispatch(monkeypatch)
    with pytest.raises(REJECT):
        _check_bound_operation(api, operation, episode, task, changed_ids)
    assert calls == []


@pytest.mark.parametrize("operation", ("rescore", "reexecute"))
@pytest.mark.parametrize("field", (
    "task_id", "task_fingerprint", "db_sha256", "prompt", "schema", "backend",
    "caller_ids", "action_cap", "action_max_rows", "scorer_max_rows", "compare",
    "scorer_timeout_s", "program_timeout_s", "wrapper_timeout_s",
    "source_sha256", "source_paths", "python_version", "sqlite_version",
))
def test_recomputed_self_digest_cannot_bypass_external_binding(
    task, operation, field, monkeypatch,
):
    api = _api()
    episode = _record(api, task, actions=_actions(task, "ptc")[:1])
    payload = json.loads(api.encode_episode(episode))["payload"]
    if field == "caller_ids":
        payload["ids"]["run_id"] += "-changed"
    elif field in ("task_fingerprint", "db_sha256"):
        payload[field] = "0" * 64
    elif field in ("task_id", "prompt", "schema", "backend"):
        payload[field] += "-changed"
    else:
        old = payload["instrument"][field]
        payload["instrument"][field] = (
            "0" * 64 if field == "source_sha256" else
            old[:-1] if field == "source_paths" else
            "multiset" if field == "compare" else
            old + "-changed" if isinstance(old, str) else old + 1
        )
    calls = _forbid_dispatch(monkeypatch)
    with pytest.raises(REJECT):
        changed = api.decode_episode(_envelope(payload))
        _check_bound_operation(api, operation, changed, task, episode.ids)
    assert calls == []


@pytest.mark.parametrize("operation", ("rescore", "reexecute"))
@pytest.mark.parametrize("relative_path", SOURCE_PATHS)
def test_current_instrument_source_bytes_are_rechecked(
    task, operation, relative_path, monkeypatch,
):
    """Substitute a changed file read, without editing any upstream source."""
    api = _api()
    episode = _record(api, task, actions=_actions(task, "ptc")[:1])
    target = Path(__file__).resolve().parents[1] / relative_path
    reads = []

    def altered_reader(original):
        def read(file, mode="r", *args, **kwargs):
            try:
                selected = Path(file).resolve() == target
            except TypeError:  # open() also accepts a file descriptor.
                selected = False
            if selected and "r" in mode:
                with original(file, mode, *args, **kwargs) as handle:
                    data = handle.read()
                reads.append(relative_path)
                if "b" in mode:
                    return io.BytesIO(data + b"\n# source-change-negative-control\n")
                return io.StringIO(data + "\n# source-change-negative-control\n")
            return original(file, mode, *args, **kwargs)
        return read

    monkeypatch.setattr(builtins, "open", altered_reader(builtins.open))
    monkeypatch.setattr(io, "open", altered_reader(io.open))
    calls = _forbid_dispatch(monkeypatch)
    with pytest.raises(REJECT):
        _check_bound_operation(api, operation, episode, task, episode.ids)
    assert relative_path in reads
    assert calls == []


def _mutate_database(task):
    conn = sqlite3.connect(task.db_path)
    try:
        conn.execute("UPDATE school SET name = name || '-changed' WHERE school_id = 1")
        conn.commit()
    finally:
        conn.close()


@pytest.mark.parametrize("operation", ("rescore", "reexecute"))
def test_changed_database_rejected_before_action_dispatch(task, operation, monkeypatch):
    api = _api()
    episode = _record(api, task, actions=_actions(task, "ptc")[:1])
    _mutate_database(task)
    calls = _forbid_dispatch(monkeypatch)
    with pytest.raises(REJECT):
        _check_bound_operation(api, operation, episode, task, episode.ids)
    assert calls == []


@pytest.mark.parametrize("operation", ("record", "rescore", "reexecute"))
@pytest.mark.parametrize("suffix", ("-wal", "-journal"))
@pytest.mark.parametrize("contents", (b"", b"stale sidecar"))
def test_stale_or_empty_sidecars_are_not_accepted_as_stable_snapshots(
    task, operation, suffix, contents, monkeypatch,
):
    api = _api()
    episode = _record(api, task, actions=_actions(task, "ptc")[:1])
    Path(task.db_path + suffix).write_bytes(contents)
    calls = _forbid_dispatch(monkeypatch)
    with pytest.raises(REJECT):
        if operation == "record":
            _record(api, task, actions=_actions(task, "ptc")[:1])
        else:
            _check_bound_operation(api, operation, episode, task, episode.ids)
    assert calls == []


def test_real_uncheckpointed_wal_is_rejected_before_dispatch(task, monkeypatch):
    api = _api()
    conn = sqlite3.connect(task.db_path)
    try:
        assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute("UPDATE school SET name = name || '-wal' WHERE school_id = 1")
        conn.commit()
        assert Path(task.db_path + "-wal").stat().st_size > 0
        calls = _forbid_dispatch(monkeypatch)
        with pytest.raises(REJECT):
            _record(api, task, actions=_actions(task, "ptc")[:1])
        assert calls == []
    finally:
        conn.close()


@pytest.mark.parametrize("operation", ("record", "reexecute"))
def test_database_checked_after_actions_not_only_before(task, operation, monkeypatch):
    api = _api()
    episode = _record(api, task, actions=_actions(task, "ptc")[:1])
    original = sql_arms.ArmPair.run
    calls = []

    def mutate(pair, arm, action, *, bindir=None):
        observation = original(pair, arm, action, bindir=bindir)
        calls.append(True)
        _mutate_database(task)
        return observation

    monkeypatch.setattr(sql_arms.ArmPair, "run", mutate)
    with pytest.raises(REJECT):
        if operation == "record":
            _record(api, task, actions=_actions(task, "ptc")[:1])
        else:
            api.reexecute_sql(episode, task, ids=episode.ids, allow_execution=True)
    assert calls == [True]


def test_database_checked_after_rescoring(task, monkeypatch):
    api = _api()
    episode = _record(api, task)
    original = score.execution_accuracy
    calls = []

    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(True)
        _mutate_database(task)
        return result

    monkeypatch.setattr(score, "execution_accuracy", mutate)
    if hasattr(api, "execution_accuracy"):
        monkeypatch.setattr(api, "execution_accuracy", mutate)
    with pytest.raises(REJECT):
        api.rescore_sql(episode, task, ids=episode.ids)
    assert calls == [True]
