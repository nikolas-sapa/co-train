"""Retained-draw admission and real SDK registration, before implementation.

Only the wrapper's stock run_eval seam is replaced, with a bounded recorder.
That proves pre-entry refusal, NOT SDK rollout/cleanup/reward correctness.
Supported-entry mocks return real SDK Episode/TraceTask records, explicitly
UNIT_ONLY_MOCK, failed and unscored, covering every original loaded Task/sample.
These records prove no Env scope activity, concurrency, success or JSONL writes.
SQLite fixture publication and inert profile construction precede all guards.
No holder internals, private scope/proxy API, native outcome or ACK is invented.
"""
from __future__ import annotations

import asyncio
import dataclasses
import importlib
import importlib.util
import inspect
import json
import os
import socket
import sqlite3
import subprocess
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from typing import Any

import pytest


ID = "cotrain_owned_sql"
REFUSAL = (TypeError, ValueError, RuntimeError)
INSTRUMENT_FIELDS = (
    "action_cap", "action_max_rows", "scorer_max_rows", "compare",
    "scorer_timeout_s", "program_timeout_s", "wrapper_timeout_s",
    "python_version", "sqlite_version", "source_paths", "source_sha256",
)


def _module():
    # Intentionally missing module/symbols fail HERE, never during collection.
    assert importlib.util.find_spec(ID) is not None, (
        "registered owned SQL module missing: cotrain_owned_sql")
    module = importlib.import_module(ID)
    for name in (
        "OwnedSqlDrawInput", "RegisteredOwnedSqlBinding",
        "build_registered_owned_sql_binding", "run_registered_owned_sql_eval",
        "OwnedSqlHarness", "OwnedSqlHarnessConfig",
        "OwnedSqlTaskset", "OwnedSqlTasksetConfig",
        "OwnedSqlEnv", "OwnedSqlEnvConfig",
    ):
        assert hasattr(module, name), "registered owned SQL API missing: " + name
    return module


def _aliases(patch, module, original, replacement):
    for name, value in tuple(vars(module).items()):
        if value is original:
            patch.setattr(module, name, replacement)


def _sdk_seam(patch, module, replacement):
    from verifiers.v1.cli.eval import runner
    original = runner.run_eval
    _aliases(patch, module, original, replacement)
    patch.setattr(runner, "run_eval", replacement)


def _run(coroutine):
    # Unit watchdog only. This file never exercises an owned cleanup deadline.
    return asyncio.run(asyncio.wait_for(coroutine, 3.0))


def _build(f, **updates):
    options = dict(
        draw=f.draw, executor=f.executor, instrument=f.instrument,
        public_data=f.public_data)
    options.update(updates)
    return f.api.build_registered_owned_sql_binding(**options)


def _config(f):
    from verifiers.v1.configs.cli.eval import EvalConfig
    return EvalConfig.model_validate_json(json.dumps({
        "model": "fixture-model-never-requested",
        "client": {"type": "train", "api_key_var": "UNIT_UNUSED_API_KEY"},
        "env": {
            "id": ID,
            "taskset": {"id": ID},
            "interception": {"type": "server"},
            "agent": {
                "harness": {
                    "id": ID, "max_turns": f.instrument.action_cap,
                    "program_timeout": f.instrument.program_timeout_s,
                },
                "runtime": {"type": "subprocess"},
                "max_turns": f.instrument.action_cap,
                "retries": {"max_retries": 0},
            },
            "retries": {"max_retries": 0},
        },
        "num_tasks": len(f.public_data), "num_rollouts": 1,
        "max_concurrent": 1, "push": False, "rich": None,
        "resume": False, "clean": False,
        "output_dir": str(f.root.parent / "never-written-eval"),
        "run": {"dir": "admission-unit"},
    }))


def _record_sdk(f, monkeypatch, *, observe_tasks=False):
    calls, tasks, episodes = [], [], []

    async def recorder(config):
        calls.append(config)
        if observe_tasks:
            from verifiers.v1.episode import Episode, EnvInfo
            from verifiers.v1.trace import Error, TraceTask
            from verifiers.v1.utils.loaders import load_taskset
            # Real registered class, real loader, real load(), exact caller data.
            taskset = load_taskset(config.env.taskset)
            assert type(taskset) is f.api.OwnedSqlTaskset
            tasks.extend(taskset.load())
            repeated = tuple(taskset.load())
            assert len(tasks) == len(repeated) == 7
            assert all(original is again for original, again in
                       zip(tasks, repeated, strict=True))
            for index, task in enumerate(tasks):
                for sample in range(config.num_rollouts):
                    # Stock public wire shape, NOT Episode(task=live_task).
                    # No lifecycle hooks run. Keep default ok=False/traces=[].
                    episodes.append(Episode(
                        id=f"UNIT_ONLY_MOCK:{index}:{sample}",
                        env=EnvInfo(id=config.env.env_id, name="UNIT_ONLY_MOCK"),
                        task=TraceTask(
                            type=type(task).__name__, data=task.data,
                            key=task.key, hash=task.hash),
                        errors=[Error(
                            type="UNIT_ONLY_MOCK",
                            message="Unit entry recorder only; no rollout or scoring.")],
                    ))
        return episodes

    _sdk_seam(monkeypatch, f.api, recorder)
    return calls, tasks, episodes


@pytest.fixture
def admitted(tmp_path, monkeypatch):
    # Lazy entry is essential: missing API must fail in the TEST CALL phase,
    # not turn every node into a fixture-setup error.
    with ExitStack() as stack:
        yield lambda: stack.enter_context(_admission_fixture(tmp_path, monkeypatch))


@contextmanager
def _admission_fixture(tmp_path, monkeypatch):
    api = _module()
    from bench import prepare
    from bench.test_validated_draw import _load
    from bench.test_validated_draw_databases import _artifacts
    from bench.test_prepare import _sentries
    from ptc import sql_isolation as core
    from ptc.test_sql_owned_invocation import _profile
    from train.sql_episodes import InstrumentSettings
    from verifiers.v1.clients import EvalClient, TrainClient
    from verifiers.v1.task import TaskData

    # These are REAL synthetic SQLite publications, not fabricated admissions.
    root, draw_path, draw_sha, supplement_path, supplement_sha = _artifacts(
        tmp_path, excluded_only=True)
    known = _load(
        prepare, root, draw_path, supplement_path, draw_sha, supplement_sha)
    profile = _profile(tmp_path)
    executor = core.PilotExecutor(profile, state_dir=tmp_path / "never-staged")

    class PublicData(TaskData):
        payload: Any = None

    public_data = tuple(
        PublicData(
            name=task.name, prompt=task.question,
            payload={"fixture": ["original"]})
        for task in known.eligible)
    instrument = InstrumentSettings(
        action_cap=2, action_max_rows=3, scorer_max_rows=known.max_rows,
        compare=known.comparison, scorer_timeout_s=known.timeout_s,
        program_timeout_s=5.0, wrapper_timeout_s=1.25,
        python_version="fixture-python", sqlite_version="fixture-sqlite",
        source_paths=("ptc/sql_isolation.py",), source_sha256="a" * 64)
    assert instrument.action_max_rows != instrument.scorer_max_rows
    draw = api.OwnedSqlDrawInput(
        root=root, draw_path=draw_path, supplement_path=supplement_path,
        expected_draw_sha256=draw_sha,
        expected_supplement_sha256=supplement_sha, fixture=True)
    state = SimpleNamespace(
        api=api, root=root, draw=draw, known=known, instrument=instrument,
        executor=executor, public_data=public_data, forbidden=[],
        consumer_calls=[], consumer_returns=[],
        documents=(draw_path.read_bytes(), supplement_path.read_bytes()))

    def deny(label):
        def refused(*args, **kwargs):
            state.forbidden.append(label)
            raise AssertionError("admission unit reached forbidden " + label)
        return refused

    original_load = prepare.load_validated_draw

    def observed_load(*args, **kwargs):
        bound = inspect.signature(original_load).bind(*args, **kwargs)
        state.consumer_calls.append(dict(bound.arguments))
        actual = original_load(*args, **kwargs)  # Never substitute a draw.
        state.consumer_returns.append(actual)
        return actual

    # Guards install LAST. Do not block socketpair/self-pipe creation by asyncio.
    with _sentries(monkeypatch, prepare) as sentries:
        state.sentries = sentries
        _aliases(monkeypatch, api, original_load, observed_load)
        monkeypatch.setattr(prepare, "load_validated_draw", observed_load)
        _sdk_seam(monkeypatch, api, deny("stock run_eval"))
        for client in (EvalClient, TrainClient):
            monkeypatch.setattr(client, "get_response", deny("policy"))
        for name in (
            "owned_program", "owned_score", "run_program", "score_sql",
            "admit_program",
        ):
            monkeypatch.setattr(core.PilotExecutor, name, deny(name))
        monkeypatch.setattr(core.OwnedSqlInvocation, "execute", deny("dispatch"))
        for name in (
            "_stage_sources", "_stage_database", "_secure_directory",
            "_spawn_owned_guardian", "_owned_boundary_io", "_run_isolated",
        ):
            monkeypatch.setattr(core, name, deny(name))
        monkeypatch.setattr(sqlite3, "connect", deny("SQLite"))
        class ForbiddenPopen(subprocess.Popen):
            # Preserve Popen[bytes] annotations during lazy SDK imports while
            # still refusing every actual process construction.
            def __init__(self, *args, **kwargs):
                deny("Popen")(*args, **kwargs)

        monkeypatch.setattr(subprocess, "Popen", ForbiddenPopen)
        if hasattr(core, "_CreatorPopen"):
            monkeypatch.setattr(core._CreatorPopen, "__init__", deny("creator"))
        monkeypatch.setattr(core.threading.Thread, "start", deny("controller"))
        for name in ("connect", "connect_ex", "bind"):
            monkeypatch.setattr(socket.socket, name, deny("socket." + name))
        monkeypatch.setattr(socket, "getaddrinfo", deny("DNS"))
        monkeypatch.setattr(os, "kill", deny("PID signal"))
        monkeypatch.setattr(os, "killpg", deny("group signal"))
        # Refuse selection/gold/EX outright, rather than run SQL before noticing.
        for module_name, names in (
            ("bench.suite", ("select",)),
            ("bench.score", ("validate_golds", "execution_accuracy")),
        ):
            target = importlib.import_module(module_name)
            for name in names:
                original = getattr(target, name)
                refused = deny(name)
                _aliases(monkeypatch, prepare, original, refused)
                _aliases(monkeypatch, api, original, refused)
                monkeypatch.setattr(target, name, refused)
        yield state
        assert state.forbidden == [], state.forbidden
        assert all(sentries[key] == 0
                   for key in ("connects", "selects", "golds", "ex"))
        assert not executor.state_dir.exists()
        assert not profile.shared_state_dir.exists()
        assert not (root.parent / "never-written-eval").exists()


def test_exact_frozen_draw_input_and_callable_api(admitted):
    f = admitted()
    assert dataclasses.is_dataclass(f.draw)
    assert type(f.draw) is f.api.OwnedSqlDrawInput
    assert tuple(field.name for field in dataclasses.fields(f.draw)) == (
        "root", "draw_path", "supplement_path", "expected_draw_sha256",
        "expected_supplement_sha256", "fixture")
    assert f.api.OwnedSqlDrawInput.__dataclass_fields__["fixture"].default is False
    for field in dataclasses.fields(f.draw):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(f.draw, field.name, getattr(f.draw, field.name))
    assert callable(f.api.build_registered_owned_sql_binding)
    assert not inspect.iscoroutinefunction(f.api.build_registered_owned_sql_binding)
    assert inspect.iscoroutinefunction(f.api.run_registered_owned_sql_eval)


def test_real_registry_resolves_three_exact_classes_without_admission(admitted):
    f = admitted()
    from ptc.harness import PTCHarness, PTCHarnessConfig
    from verifiers.v1.configs.taskset import TasksetConfig
    from verifiers.v1.env import Env
    from verifiers.v1.envs.single_agent import SingleAgentEnvConfig
    from verifiers.v1.harness import Harness
    from verifiers.v1.taskset import Taskset
    from verifiers.v1.utils import loaders

    assert len(f.api.__all__) == 3
    assert set(f.api.__all__) == {
        "OwnedSqlHarness", "OwnedSqlTaskset", "OwnedSqlEnv"}
    assert loaders.import_harness(ID) is f.api
    assert loaders.import_taskset(ID) is f.api
    assert loaders.import_environment(ID) is f.api
    assert loaders.harness_class(ID) is f.api.OwnedSqlHarness
    assert loaders.taskset_class(ID) is f.api.OwnedSqlTaskset
    assert loaders.environment_class(ID, ID) is f.api.OwnedSqlEnv
    assert loaders.harness_config_type(ID) is f.api.OwnedSqlHarnessConfig
    assert loaders.taskset_config_type(ID) is f.api.OwnedSqlTasksetConfig
    assert loaders.env_config_type(ID, ID) is f.api.OwnedSqlEnvConfig
    assert issubclass(f.api.OwnedSqlHarness, PTCHarness)
    assert issubclass(f.api.OwnedSqlHarness, Harness)
    assert issubclass(f.api.OwnedSqlTaskset, Taskset)
    assert issubclass(f.api.OwnedSqlEnv, Env)
    for cls, base in (
        (f.api.OwnedSqlHarnessConfig, PTCHarnessConfig),
        (f.api.OwnedSqlTasksetConfig, TasksetConfig),
        (f.api.OwnedSqlEnvConfig, SingleAgentEnvConfig),
    ):
        assert issubclass(cls, base) and cls().id == ID
    assert f.consumer_calls == []


def test_canonical_eval_json_resolves_exact_config_classes_no_authority(admitted):
    f = admitted()
    from verifiers.v1.configs.cli.eval import EvalConfig
    config = _config(f)
    restored = EvalConfig.model_validate_json(config.model_dump_json())
    for current in (config, restored):
        assert type(current) is EvalConfig
        assert type(current.env) is f.api.OwnedSqlEnvConfig
        assert type(current.env.taskset) is f.api.OwnedSqlTasksetConfig
        assert type(current.env.agent.harness) is f.api.OwnedSqlHarnessConfig
        assert current.env.agent.harness.program_timeout == 5
        assert current.env.agent.harness.max_turns == f.instrument.action_cap
    wire = restored.model_dump_json()
    for private in ("expected_draw_sha256", "gold_sql", "db_path", "source_sha256"):
        assert private not in wire
    assert f.consumer_calls == []


def test_builder_delegates_real_consumer_with_retained_pins_and_full_partition(
        admitted):
    f = admitted()
    before = dataclasses.asdict(f.instrument)
    holder = _build(f)
    assert type(holder) is f.api.RegisteredOwnedSqlBinding
    assert len(f.consumer_calls) == len(f.consumer_returns) == 1
    call, = f.consumer_calls
    assert call == {
        "root": f.draw.root, "draw_path": f.draw.draw_path,
        "supplement_path": f.draw.supplement_path,
        "expected_draw_sha256": f.draw.expected_draw_sha256,
        "expected_supplement_sha256": f.draw.expected_supplement_sha256,
        "fixture": True,
    }
    # Observe the ACTUAL returned consumer object, not guessed holder attributes.
    actual, = f.consumer_returns
    assert actual == f.known and actual is not f.known
    assert (len(actual.planned), len(actual.eligible), len(actual.exclusions)) == (8, 7, 1)
    assert [task.name for task in actual.eligible] == [
        data.name for data in f.public_data]
    assert len(actual.databases) == 2
    excluded_db, = {task.db_id for task in actual.planned} - {
        task.db_id for task in actual.eligible}
    assert excluded_db == "excluded-only"
    assert excluded_db in {record.db_id for record in actual.databases}
    assert actual.databases == f.known.databases
    assert all(any(task is planned for planned in actual.planned)
               for task in actual.eligible)
    assert set(before) == set(INSTRUMENT_FIELDS)
    assert dataclasses.asdict(f.instrument) == before
    assert f.instrument.scorer_max_rows == actual.max_rows
    assert f.instrument.action_max_rows != actual.max_rows
    for data, task in zip(f.public_data, actual.eligible, strict=True):
        wire = data.model_dump_json()
        assert isinstance(data.prompt, str) and data.image is None
        assert task.gold_sql not in wire and task.db_path not in wire
        assert "gold_sql" not in wire and "db_path" not in wire
    assert (f.draw.draw_path.read_bytes(), f.draw.supplement_path.read_bytes()) == (
        f.documents)
    assert f.sentries["loads"] == 2


@pytest.mark.parametrize("fault", (
    "lookalike", "empty-draw-pin", "malformed-supplement-pin",
    "wrong-draw-pin", "wrong-supplement-pin", "fixture-off", "fixture-integer",
))
def test_draw_admission_refuses_without_eval_policy_or_dispatch(admitted, fault):
    f = admitted()
    updates = {
        "empty-draw-pin": {"expected_draw_sha256": ""},
        "malformed-supplement-pin": {"expected_supplement_sha256": "G" * 64},
        "wrong-draw-pin": {"expected_draw_sha256": "0" * 64},
        "wrong-supplement-pin": {"expected_supplement_sha256": "0" * 64},
        "fixture-off": {"fixture": False},
        "fixture-integer": {"fixture": 1},
    }
    with pytest.raises(REFUSAL):
        draw = (SimpleNamespace(**dataclasses.asdict(f.draw))
                if fault == "lookalike"
                else dataclasses.replace(f.draw, **updates[fault]))
        _build(f, draw=draw)
    assert f.consumer_returns == []


@pytest.mark.parametrize("fault", ("corpus", "eligible-db", "excluded-only-db"))
def test_real_consumer_rejects_current_drift_never_repins(admitted, fault):
    f = admitted()
    if fault == "corpus":
        path = f.root / "dev.json"
        records = json.loads(path.read_bytes())
        records[0]["question"] += " changed after publication"
        path.write_text(json.dumps(records))
    else:
        task = (f.known.eligible[0] if fault == "eligible-db" else
                next(task for task in f.known.planned
                     if task.db_id == "excluded-only"))
        from pathlib import Path
        Path(task.db_path).write_bytes(b"changed synthetic DB, never adopted")
    with pytest.raises(REFUSAL):
        _build(f)
    assert len(f.consumer_calls) == 1 and f.consumer_returns == []
    assert f.consumer_calls[0]["expected_draw_sha256"] == f.draw.expected_draw_sha256
    assert f.consumer_calls[0]["expected_supplement_sha256"] == (
        f.draw.expected_supplement_sha256)


@pytest.mark.parametrize("field", (
    "scorer_timeout_s", "scorer_max_rows", "compare", "program_timeout_s",
))
def test_instrument_must_match_admitted_bounds_and_fixed_program_timeout(
        admitted, field):
    f = admitted()
    changed = {
        "scorer_timeout_s": f.known.timeout_s - 0.25,
        "scorer_max_rows": f.known.max_rows - 1,
        "compare": "multiset" if f.known.comparison == "set" else "set",
        "program_timeout_s": 4.0,
    }
    instrument = dataclasses.replace(f.instrument, **{field: changed[field]})
    with pytest.raises(REFUSAL):
        _build(f, instrument=instrument)


@pytest.mark.parametrize("fault", (
    "missing", "extra", "reordered", "wrong-name", "non-task-data",
    "list-container", "image", "nonfinite-json", "nontext-prompt",
))
def test_public_rows_require_exact_count_order_names_and_plain_json(admitted, fault):
    f = admitted()
    rows = f.public_data
    if fault == "missing":
        rows = rows[:-1]
    elif fault == "extra":
        rows = (*rows, rows[0])
    elif fault == "reordered":
        rows = tuple(reversed(rows))
    elif fault == "wrong-name":
        rows = (rows[0].model_copy(update={"name": "not-an-eligible-task"}), *rows[1:])
    elif fault == "non-task-data":
        rows = (SimpleNamespace(name=rows[0].name, prompt="q"), *rows[1:])
    elif fault == "list-container":
        rows = list(rows)
    else:
        update = {
            "image": {"image": "unsupported-fixture-image"},
            "nonfinite-json": {"payload": {"nested": float("nan")}},
            "nontext-prompt": {"prompt": 123},
        }[fault]
        rows = (rows[0].model_copy(update=update), *rows[1:])
    with pytest.raises(REFUSAL):
        _build(f, public_data=rows)


def test_public_prompt_association_is_not_semantic_provenance(admitted):
    f = admitted()
    # Trusted host may phrase its public prompt differently from the corpus.
    rows = tuple(data.model_copy(update={"prompt": "Caller-authored fixture prompt."})
                 for data in f.public_data)
    assert type(_build(f, public_data=rows)) is f.api.RegisteredOwnedSqlBinding


def test_public_data_mutation_after_binding_refuses_before_sdk(
        admitted, monkeypatch):
    f = admitted()
    binding = _build(f)
    config = _config(f)
    calls, _, _ = _record_sdk(f, monkeypatch)
    f.public_data[0].payload["fixture"].append("changed after admission")
    with pytest.raises(REFUSAL):
        _run(f.api.run_registered_owned_sql_eval(config, binding=binding))
    assert calls == []


def test_config_loading_alone_cannot_authorize_eval(admitted, monkeypatch):
    f = admitted()
    config = _config(f)
    calls, _, _ = _record_sdk(f, monkeypatch)
    with pytest.raises(REFUSAL):
        _run(f.api.run_registered_owned_sql_eval(config, binding=None))
    assert calls == [] and f.consumer_calls == []


def test_holder_matching_type_is_not_authority(admitted, monkeypatch):
    f = admitted()
    original = _build(f)
    forged = object.__new__(type(original))
    assert type(forged) is type(original) and forged is not original
    config = _config(f)
    calls, _, _ = _record_sdk(f, monkeypatch)
    with pytest.raises(REFUSAL):
        _run(f.api.run_registered_owned_sql_eval(config, binding=forged))
    assert calls == []


@pytest.mark.parametrize("num_tasks", (None, 7), ids=("all", "exact-seven"))
@pytest.mark.parametrize("num_rollouts", (1, 2), ids=("one-sample", "two-samples"))
def test_supported_wrapper_preserves_config_and_data_and_consumes_binding_once(
        admitted, monkeypatch, num_tasks, num_rollouts):
    f = admitted()
    from verifiers.v1.episode import Episode
    from verifiers.v1.trace import TraceTask

    binding = _build(f)
    config = _config(f).model_copy(update={
        "num_tasks": num_tasks, "num_rollouts": num_rollouts, "shuffle": False})
    before = config.model_dump_json(), dataclasses.asdict(f.instrument)
    calls, tasks, episodes = _record_sdk(f, monkeypatch, observe_tasks=True)
    result = _run(f.api.run_registered_owned_sql_eval(config, binding=binding))
    assert result is episodes
    assert len(result) == 7 * num_rollouts
    assert len(calls) == 1 and calls[0] is config
    assert len(tasks) == len({id(task) for task in tasks}) == 7
    assert [task.data.name for task in tasks] == [
        task.name for task in f.known.eligible]
    assert all(task.data is data
               for task, data in zip(tasks, f.public_data, strict=True))
    for index, task in enumerate(tasks):
        samples = result[index * num_rollouts:(index + 1) * num_rollouts]
        assert len(samples) == num_rollouts
        for sample, episode in enumerate(samples):
            assert type(episode) is Episode and type(episode.task) is TraceTask
            assert episode.task.data is task.data
            assert episode.task.type == type(task).__name__
            assert episode.task.key == task.key and episode.task.hash == task.hash
            assert episode.id == f"UNIT_ONLY_MOCK:{index}:{sample}"
            assert episode.env.name == "UNIT_ONLY_MOCK"
            assert episode.ok is False and episode.traces == []
            assert len(episode.errors) == 1
            assert episode.errors[0].type == "UNIT_ONLY_MOCK"
    assert all(sum(episode.task.data is task.data for episode in result) == num_rollouts
               for task in tasks)
    assert before == (config.model_dump_json(), dataclasses.asdict(f.instrument))
    with pytest.raises(REFUSAL):
        _run(f.api.run_registered_owned_sql_eval(config, binding=binding))
    assert len(calls) == 1


@pytest.mark.parametrize("field,value", (
    ("num_tasks", 6),
    ("num_tasks", 8),
    ("num_tasks", True),
    ("num_tasks", False),
    ("num_tasks", 7.0),
    ("shuffle", True),
    ("num_rollouts", 0),
    ("num_rollouts", True),
    ("num_rollouts", False),
    ("num_rollouts", 1.0),
), ids=(
    "omit-one", "exceed-eligible", "task-count-true", "task-count-false",
    "task-count-float", "shuffle", "zero-rollouts", "rollouts-true",
    "rollouts-false", "rollouts-float",
))
def test_incomplete_or_noncanonical_selection_refuses_before_stock_entry(
        admitted, monkeypatch, field, value):
    f = admitted()
    binding = _build(f)
    # Deliberate Pydantic bypass: wrapper must inspect native value/type itself.
    config = _config(f).model_copy(update={field: value})
    assert getattr(config, field) is value
    calls, _, _ = _record_sdk(f, monkeypatch)
    with pytest.raises(REFUSAL):
        _run(f.api.run_registered_owned_sql_eval(config, binding=binding))
    assert calls == [], "incomplete/noncanonical selection entered stock run_eval"


def _unsupported_config(config, fault):
    """Single mutation of a real canonical EvalConfig; no revalidation coercion."""
    from verifiers.v1.configs.retries import RetryConfig
    from verifiers.v1.configs.task import RewardFunctionConfig

    if fault in ("resume", "push", "clean"):
        return config.model_copy(update={fault: True})
    env, agent = config.env, config.env.agent
    harness, taskset = agent.harness, env.taskset
    if fault == "env-retries":
        env = env.model_copy(update={"retries": RetryConfig(max_retries=1)})
    elif fault == "agent-retries":
        agent = agent.model_copy(update={"retries": RetryConfig(max_retries=1)})
        env = env.model_copy(update={"agent": agent})
    elif fault in ("program-timeout", "turn-cap", "MCP", "QA"):
        update = {
            "program-timeout": {"program_timeout": 4.0},
            "turn-cap": {"max_turns": harness.max_turns + 1},
            "MCP": {"mcp_header_env": {"fixture": {"x-fixture": "UNIT_UNUSED"}}},
            "QA": {"id": "cotrain_ptc_qa"},
        }[fault]
        agent = agent.model_copy(update={"harness": harness.model_copy(update=update)})
        env = env.model_copy(update={"agent": agent})
    elif fault in ("plugged-reward", "judge"):
        update = (
            {"rewards": {"execution_accuracy": RewardFunctionConfig(weight=0.0)}}
            if fault == "plugged-reward" else {"judges": [object()]})
        taskset = taskset.model_copy(update={
            "task": taskset.task.model_copy(update=update)})
        env = env.model_copy(update={"taskset": taskset})
    elif fault == "task-rewrite":
        from pathlib import Path
        taskset = taskset.model_copy(update={"system_prompt": Path("never-read.txt")})
        env = env.model_copy(update={"taskset": taskset})
    elif fault == "interceptor-rewrite":
        from verifiers.v1.interception import ElasticInterceptionPoolConfig
        env = env.model_copy(update={"interception": ElasticInterceptionPoolConfig()})
    else:
        raise AssertionError("unknown unit mutation")
    return config.model_copy(update={"env": env})


@pytest.mark.parametrize("fault", (
    "resume", "push", "clean", "env-retries", "agent-retries",
    "program-timeout", "turn-cap", "MCP", "QA", "plugged-reward", "judge",
    "task-rewrite", "interceptor-rewrite",
))
def test_unsupported_config_refuses_with_valid_binding_before_stock_entry(
        admitted, monkeypatch, fault):
    f = admitted()
    binding = _build(f)  # A missing/invalid holder cannot explain this refusal.
    config = _unsupported_config(_config(f), fault)
    calls, _, _ = _record_sdk(f, monkeypatch)
    with pytest.raises(REFUSAL):
        _run(f.api.run_registered_owned_sql_eval(config, binding=binding))
    assert calls == [], "unsupported config entered stock run_eval"


@pytest.mark.parametrize("fault", (
    "taskset-toolsets", "task-toolsets", "deferred-scoring",
    "task-scoring", "harness-scoring",
))
def test_registered_behavior_mutation_refuses_before_stock_entry(
        admitted, monkeypatch, fault):
    f = admitted()
    binding = _build(f)
    config = _config(f)
    calls, _, _ = _record_sdk(f, monkeypatch)
    task_type = f.api.OwnedSqlTaskset.task_type()

    def unexpected(*args, **kwargs):
        raise AssertionError("unsupported registered hook was invoked")

    if fault == "taskset-toolsets":
        monkeypatch.setattr(f.api.OwnedSqlTaskset, "toolsets", classmethod(unexpected))
    elif fault == "task-toolsets":
        monkeypatch.setattr(task_type, "toolsets", classmethod(unexpected))
    elif fault == "deferred-scoring":
        monkeypatch.setattr(task_type, "scoring_deferred", True)
    elif fault == "task-scoring":
        monkeypatch.setattr(task_type, "score", unexpected)
    else:
        monkeypatch.setattr(f.api.OwnedSqlHarness, "score", unexpected)
    with pytest.raises(REFUSAL):
        _run(f.api.run_registered_owned_sql_eval(config, binding=binding))
    assert calls == [], "unsupported hooks entered stock run_eval"
