"""Registered SDK composition, with an explicit UNIT_ONLY native-result seam.

Real retained 8/7/1 draw, SQLite fixture files, inert first-party profile,
PilotExecutor filesystem admission, PROGRAM builder/catalog/preflight, scorer
construction/admit/empty-job close, registered classes, Agent/eval and JSONL.
Policy emits ONE text SELECT 42 per rollout, NEVER a PROGRAM tool call.

ONLY OwnedSqlScorer.score_sql is a native-result MOCK. Its declared ExResult
is NOT decoded from an OwnedSqlInvocation and proves NO SQL accuracy, native
execution, active owner ACK or canonical-actor cleanup. No synthetic ACK exists.
The concurrency controller holds two mock score calls, not native processes.

Future mandatory gates: actual canonical owned actors, repeated cancellation,
unknown/deadline retention, sibling failure, association fault mutations and an
independent Env writer-barrier bypass. Passing this file cannot approve those.
Source/safety review is required BEFORE anyone executes these tests.
"""
from __future__ import annotations

import asyncio
from collections import Counter
import importlib
import importlib.metadata
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from types import SimpleNamespace

import pytest

from ptc.test_bash_qa_eval_integration import framework  # noqa: F401


ID = "cotrain_owned_sql"
PREDICTION = "SELECT 42"
UNIT_RESULT = "UNIT_ONLY_NATIVE_RESULT_MOCK: no invocation or native accuracy"
SAFETY_SECONDS = 40.0
pytestmark = pytest.mark.filterwarnings(
    "error::pytest.PytestUnraisableExceptionWarning")


def _module():
    # Missing production API is a CALL-phase assertion, never skip/setup ERROR.
    assert importlib.util.find_spec(ID) is not None, (
        "registered owned SQL module missing: cotrain_owned_sql")
    api = importlib.import_module(ID)
    for name in (
        "OwnedSqlDrawInput", "RegisteredOwnedSqlBinding",
        "build_registered_owned_sql_binding", "run_registered_owned_sql_eval",
        "OwnedSqlHarness", "OwnedSqlHarnessConfig", "OwnedSqlTaskset",
        "OwnedSqlTasksetConfig", "OwnedSqlEnv", "OwnedSqlEnvConfig",
    ):
        assert hasattr(api, name), "registered owned SQL API missing: " + name
    return api


def _aliases(patch, module, original, replacement):
    # Host public factory aliases only. Never SDK internals or root lifecycle.
    for name, value in tuple(vars(module).items()):
        if value is original:
            patch.setattr(module, name, replacement)


def _rows(config, *, completed=False):
    files = list(Path(config.output_dir).rglob("*.jsonl"))
    if completed:
        assert len(files) == 1, "original SDK writer must publish one JSONL"
    return [json.loads(line) for path in files
            for line in path.read_text().splitlines() if line.strip()]


def _successful(row):
    return bool(row.get("ok") or any(
        trace.get("ok") for trace in row.get("traces", [])))


def _config(f, *, rollouts, num_tasks):
    from verifiers.v1.configs.cli.eval import EvalConfig
    config = EvalConfig.model_validate_json(json.dumps({
        "model": "fixture-model",
        "client": {"type": "train", "api_key_var": "PROBE_UNUSED_API_KEY"},
        "env": {
            "id": ID, "taskset": {"id": ID},
            "interception": {"type": "server"},
            "agent": {
                "harness": {
                    "id": ID, "max_turns": f.instrument.action_cap,
                    "program_timeout": f.instrument.program_timeout_s,
                },
                "runtime": {"type": "subprocess"},
                "max_turns": f.instrument.action_cap,
                "timeout": {"setup": 5.0, "rollout": 15.0,
                            "finalize": 5.0, "scoring": 15.0},
                "retries": {"max_retries": 0},
            },
            "retries": {"max_retries": 0},
        },
        "num_tasks": num_tasks, "num_rollouts": rollouts,
        "shuffle": False, "max_concurrent": 2,
        "push": False, "resume": False, "clean": False, "rich": None,
        "output_dir": str(f.state.root / "owned-sdk-composition"),
        "run": {"dir": "run"},
    }))
    assert type(config.env) is f.api.OwnedSqlEnvConfig
    assert type(config.env.taskset) is f.api.OwnedSqlTasksetConfig
    assert type(config.env.agent.harness) is f.api.OwnedSqlHarnessConfig
    assert config.num_tasks is None or config.num_tasks == 7
    assert config.max_concurrent == 2 and config.push is False
    assert config.env.retries.max_retries == 0
    assert config.env.agent.retries.max_retries == 0
    return config


def _prepare(request, monkeypatch, *, rollouts, num_tasks, status):
    api = _module()  # MUST precede lazy entry into the first-party framework.
    state = request.getfixturevalue("framework")
    assert importlib.metadata.version("verifiers") == "0.3.2.dev137"
    from bench import prepare
    from bench.score import ExResult, INVALID_STATUSES
    from bench.test_validated_draw import _load
    from bench.test_validated_draw_databases import _artifacts
    from ptc import sql_isolation as core, sql_owned_program, sql_owned_score
    from ptc.harness import PTCHarness, PTCHarnessConfig
    from ptc.test_bash_qa_activation_integration import ScriptedClient, _text_step
    from ptc.test_sql_owned_invocation import _profile
    from train.sql_episodes import InstrumentSettings
    from verifiers.v1.task import TaskData
    from verifiers.v1.trace import TraceTask
    from verifiers.v1.utils import loaders

    # Read-only SDK source review confirmed this PUBLIC wire record, not Task.
    assert set(TraceTask.model_fields) == {"type", "data", "key", "hash"}
    assert set(api.__all__) == {
        "OwnedSqlHarness", "OwnedSqlTaskset", "OwnedSqlEnv"}
    assert loaders.harness_class(ID) is api.OwnedSqlHarness
    assert loaders.taskset_class(ID) is api.OwnedSqlTaskset
    assert loaders.environment_class(ID, ID) is api.OwnedSqlEnv
    assert status == "match" or status in INVALID_STATUSES
    assert sql_owned_program.build_owned_sql_program_harness.__module__ == (
        "ptc.sql_owned_program")
    assert {"build_owned_sql_scorer", "OwnedSqlScorer"} <= set(
        sql_owned_score.__all__)
    scorer_type = sql_owned_score.OwnedSqlScorer
    assert scorer_type.__module__ == "ptc.sql_owned_score"

    # Fixture publication and _profile precede EVERY SQLite/process guard.
    # _artifacts publishes the real synthetic SQLite corpus/frozen supplement.
    root, draw, draw_sha, supplement, supplement_sha = _artifacts(
        state.root, excluded_only=True)
    known = _load(prepare, root, draw, supplement, draw_sha, supplement_sha)
    profile = _profile(state.root)
    executor = core.PilotExecutor(profile, state_dir=state.root / "never-staged")
    public_data = tuple(TaskData(name=task.name, prompt=task.question)
                        for task in known.eligible)
    instrument = InstrumentSettings(
        action_cap=2, action_max_rows=3, scorer_max_rows=known.max_rows,
        compare=known.comparison, scorer_timeout_s=known.timeout_s,
        program_timeout_s=5.0, wrapper_timeout_s=1.25,
        python_version="fixture-python", sqlite_version="fixture-sqlite",
        source_paths=("ptc/sql_isolation.py",), source_sha256="a" * 64)
    assert instrument.action_max_rows != instrument.scorer_max_rows
    f = SimpleNamespace(
        api=api, state=state, known=known, executor=executor, profile=profile,
        instrument=instrument, public_data=public_data, loads=[], load_calls=[],
        programs=[], scorers=[], by_scorer={}, admissions=[], forbidden=[],
        entered=[], overlap=[], both_entered=asyncio.Event(),
        release_scores=asyncio.Event(), rollouts=rollouts, status=status,
        documents=(draw.read_bytes(), supplement.read_bytes()))
    f.config = _config(f, rollouts=rollouts, num_tasks=num_tasks)
    state.config = f.config
    state.policy = f.policy = ScriptedClient(
        [_text_step(PREDICTION) for _ in range(7 * rollouts)])
    original_load = prepare.load_validated_draw
    original_program = sql_owned_program.build_owned_sql_program_harness
    original_scorer = sql_owned_score.build_owned_sql_scorer
    original_admit, original_close = scorer_type.admit, scorer_type.aclose
    original_executor_admit = core.PilotExecutor.admit_program

    def observed_load(*args, **kwargs):
        call = inspect.signature(original_load).bind(*args, **kwargs)
        actual = original_load(*args, **kwargs)
        f.load_calls.append(dict(call.arguments))
        f.loads.append(actual)
        return actual

    def observed_program(*args, **kwargs):
        actual = original_program(*args, **kwargs)  # Real catalog and binding.
        call = inspect.signature(original_program).bind(*args, **kwargs)
        assert type(actual) is PTCHarness
        assert type(call.arguments["config"]) is PTCHarnessConfig
        assert call.arguments["config"].id == PTCHarnessConfig().id
        assert actual.program_runner_factory is not None
        f.programs.append(SimpleNamespace(
            harness=actual, kwargs=dict(call.arguments)))
        return actual

    def observed_scorer(*args, **kwargs):
        actual = original_scorer(*args, **kwargs)  # Never substitute the class.
        assert type(actual) is scorer_type and actual not in f.by_scorer
        call = inspect.signature(original_scorer).bind(*args, **kwargs)
        record = SimpleNamespace(
            scorer=actual, kwargs=dict(call.arguments), events=[],
            result=ExResult(
                score=1.0 if status == "match" else 0.0,
                status=status, valid=status == "match", detail=UNIT_RESULT))
        f.scorers.append(record)
        f.by_scorer[actual] = record  # OBJECT identity, NEVER task-name lookup.
        return actual

    def observed_admit(self):
        record = f.by_scorer[self]
        result = original_admit(self)  # Actual pure filesystem admission.
        assert result is None
        record.events.append("admit")
        return result

    def observed_executor_admit(self, **kwargs):
        actual = original_executor_admit(self, **kwargs)
        f.admissions.append((self, dict(kwargs), actual))
        return actual

    async def native_result_mock(self, predicted_sql):
        # Explicit UNIT/COMPOSITION seam. NOT a decoded owned native result.
        record = f.by_scorer[self]
        assert record.events == ["admit"]
        assert predicted_sql.strip() == PREDICTION
        record.events.append("score")
        f.entered.append(record)
        if len(f.entered) <= 2:
            if len(f.entered) == 2:
                f.both_entered.set()
            await f.release_scores.wait()
        return record.result

    async def observed_close(self):
        record = f.by_scorer[self]
        record.events.append("close")
        # The real scorer has ZERO native jobs. No invented cleanup ACK.
        result = await original_close(self)
        assert result is None
        record.events.append("closed")
        return result

    def deny(label):
        def refused(*args, **kwargs):
            f.forbidden.append(label)
            raise AssertionError("composition reached forbidden " + label)
        return refused

    # Keep first-party loopback/egress/runtime/transport-drain fixture intact.
    # Server.start is aiohttp AppRunner/TCPSite, no Popen needed for startup.
    # Do NOT deny Thread.start, socket.bind or self-pipe/socketpair creation.
    for name in ("owned_program", "owned_score", "run_program", "score_sql"):
        monkeypatch.setattr(core.PilotExecutor, name, deny("executor." + name))
    for name in ("execute", "_spawn"):
        monkeypatch.setattr(core.OwnedSqlInvocation, name, deny("owner." + name))
    for name in (
        "_spawn_owned_guardian", "_stage_sources", "_stage_database",
        "_secure_directory", "_owned_boundary_io", "_run_isolated",
    ):
        monkeypatch.setattr(core, name, deny(name))
    monkeypatch.setattr(core._CreatorPopen, "__init__", deny("_CreatorPopen"))
    monkeypatch.setattr(sqlite3, "connect", deny("sqlite3.connect"))
    class ForbiddenPopen(subprocess.Popen):
        # SDK lazy imports may evaluate Popen[bytes]; construction still denies.
        def __init__(self, *args, **kwargs):
            deny("Popen")(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", ForbiddenPopen)
    monkeypatch.setattr(os, "kill", deny("PID signal"))
    monkeypatch.setattr(os, "killpg", deny("group signal"))
    for module_name, names in (
        ("bench.score", ("execution_accuracy", "validate_golds")),
        ("bench.suite", ("select",)),
    ):
        module = importlib.import_module(module_name)
        for name in names:
            original = getattr(module, name)
            replacement = deny(module_name + "." + name)
            _aliases(monkeypatch, api, original, replacement)
            _aliases(monkeypatch, prepare, original, replacement)
            monkeypatch.setattr(module, name, replacement)
    for module, original, replacement in (
        (prepare, original_load, observed_load),
        (sql_owned_program, original_program, observed_program),
        (sql_owned_score, original_scorer, observed_scorer),
    ):
        _aliases(monkeypatch, api, original, replacement)
        _aliases(monkeypatch, module, original, replacement)
    monkeypatch.setattr(scorer_type, "admit", observed_admit)
    monkeypatch.setattr(scorer_type, "score_sql", native_result_mock)
    monkeypatch.setattr(scorer_type, "aclose", observed_close)
    monkeypatch.setattr(core.PilotExecutor, "admit_program", observed_executor_admit)

    # No protected root Task/Harness/Env hooks, SDK Agent/run_eval/writer or
    # private scope/context variables are patched. If public seam observation
    # is rejected by admission, report the contract gap; NEVER bypass sealing.
    f.binding = api.build_registered_owned_sql_binding(
        draw=api.OwnedSqlDrawInput(
            root=root, draw_path=draw, supplement_path=supplement,
            expected_draw_sha256=draw_sha,
            expected_supplement_sha256=supplement_sha, fixture=True),
        executor=executor, instrument=instrument, public_data=public_data)
    assert type(f.binding) is api.RegisteredOwnedSqlBinding
    actual, = f.loads
    call, = f.load_calls
    assert call == dict(
        root=root, draw_path=draw, supplement_path=supplement,
        expected_draw_sha256=draw_sha,
        expected_supplement_sha256=supplement_sha, fixture=True)
    assert (len(actual.planned), len(actual.eligible), len(actual.exclusions)) == (8, 7, 1)
    assert actual == known and actual is not known
    assert actual.databases == known.databases and len(actual.databases) == 2
    assert "excluded-only" in {db.db_id for db in actual.databases}
    assert "excluded-only" not in {task.db_id for task in actual.eligible}
    assert all(any(task is planned for planned in actual.planned)
               for task in actual.eligible)
    assert (draw.read_bytes(), supplement.read_bytes()) == f.documents
    return f


async def _evaluate(f):
    caller = asyncio.create_task(f.api.run_registered_owned_sql_eval(
        f.config, binding=f.binding))
    rendezvous = asyncio.create_task(f.both_entered.wait())
    try:
        done, _ = await asyncio.wait(
            (caller, rendezvous), return_when=asyncio.FIRST_COMPLETED)
        if caller in done:
            await caller  # Preserve real refusal/failure instead of hiding it.
            pytest.fail("evaluation ended before two mock score calls overlapped")
        first, second = f.entered
        assert first.scorer is not second.scorer
        assert first.events == second.events == ["admit", "score"]
        assert not caller.done() and not f.release_scores.is_set()
        if f.rollouts == 1:
            assert first.kwargs["task"] is not second.kwargs["task"]
        else:
            assert first.kwargs["task"] is second.kwargs["task"]
        first_programs = [record for record in f.programs
                          if record.kwargs["task"] is first.kwargs["task"]]
        second_programs = [record for record in f.programs
                           if record.kwargs["task"] is second.kwargs["task"]]
        assert first_programs and second_programs
        first_data = first_programs[0].kwargs["data"]
        second_data = second_programs[0].kwargs["data"]
        assert all(record.kwargs["data"] is first_data
                   for record in first_programs)
        assert all(record.kwargs["data"] is second_data
                   for record in second_programs)
        assert (first_data is second_data) is (f.rollouts == 2)
        f.overlap[:] = [first, second]
        assert _rows(f.config) == [], "writer escaped held mock scoring"
        # Release is exclusively test-controller authority, not scorer 2.
        f.release_scores.set()
        return await caller
    finally:
        f.release_scores.set()
        if not rendezvous.done():
            rendezvous.cancel()
        if not caller.done():
            caller.cancel()
        await asyncio.gather(caller, rendezvous, return_exceptions=True)


def _assert_composition(f, episodes):
    actual, = f.loads
    expected = 7 * f.rollouts
    assert len(episodes) == len(f.scorers) == len(f.programs) == expected
    assert len(f.by_scorer) == expected
    assert f.policy.calls == len(f.policy.bodies) == expected
    assert all(not any(message.get("role") == "tool"
                       for message in body["messages"])
               for body in f.policy.bodies)
    assert all(episode.task.data is data for episode, data in zip(
        episodes, [data for data in f.public_data for _ in range(f.rollouts)],
        strict=True))
    assert len(f.state.agents) == len(f.state.runtimes) == expected
    assert f.state.channels == [] and f.state.external == []
    assert f.forbidden == []
    assert not f.executor.state_dir.exists()
    assert not f.profile.shared_state_dir.exists()
    assert all(record.events == ["admit", "score", "close", "closed"]
               for record in f.scorers)
    assert len({id(record.scorer) for record in f.scorers}) == expected
    assert len({id(record.harness) for record in f.programs}) == expected
    for agent, original in f.state.agents:
        assert agent.harness is original
        assert type(original) is f.api.OwnedSqlHarness
    # 1 real scorer admit + 1 real PROGRAM runner preflight per rollout.
    assert len(f.admissions) == 2 * expected
    assert all(executor is f.executor for executor, _, _ in f.admissions)
    for private, data in zip(actual.eligible, f.public_data, strict=True):
        programs = [record for record in f.programs
                    if record.kwargs["task"] is private]
        scorers = [record for record in f.scorers
                   if record.kwargs["task"] is private]
        samples = [episode for episode in episodes if episode.task.data is data]
        assert len(programs) == len(scorers) == len(samples) == f.rollouts
        assert all(record.kwargs["data"] is data for record in programs)
        for record in programs:
            args = record.kwargs
            assert args["executor"] is f.executor
            assert args["max_rows"] == f.instrument.action_max_rows
            assert args["config"].program_timeout == 5
            assert args["config"].max_turns == f.instrument.action_cap
        for record in scorers:
            assert record.kwargs["executor"] is f.executor
            assert record.kwargs["instrument"] is f.instrument
            assert record.kwargs["instrument"].scorer_max_rows == actual.max_rows
        db, = [db for db in actual.databases if db.db_id == private.db_id]
        assert all(record.kwargs["db_sha256"] == db.sha256
                   for record in (*programs, *scorers))
        for episode in samples:
            trace, = episode.traces
            # Public SDK TraceTask is NOT the live Task. Factory observations
            # establish the original private Task/public Data association.
            assert trace.task.data is episode.task.data is data
            assert trace.task.hash == episode.task.hash
            assert trace.task.key == episode.task.key
    assert len(f.overlap) == 2
    traces = [trace for episode in episodes for trace in episode.traces]
    assert len({id(trace) for trace in traces}) == expected
    assert len({trace.id for trace in traces}) == expected
    rows = _rows(f.config, completed=True)
    assert len(rows) == expected
    assert Counter(row["task"]["hash"] for row in rows) == Counter(
        episode.task.hash for episode in episodes)
    assert {trace["id"] for row in rows for trace in row["traces"]} == {
        trace.id for trace in traces}
    for row in rows:
        trace, = row["traces"]
        assert trace["task"]["data"] == row["task"]["data"]
        assert trace["task"]["hash"] == row["task"]["hash"]
        # Episode.to_record omits None recursively; match its public wire form.
        assert row["task"]["data"] in [
            data.model_dump(mode="json", exclude_none=True)
            for data in f.public_data]
    private_strings = [value for task in actual.planned
                       for value in (task.gold_sql, task.db_path)]
    # Full dispatched policy body plus persisted public TaskData, not log text.
    public_wire = json.dumps([
        f.policy.bodies,
        [row["task"]["data"] for row in rows],
        [trace["task"]["data"] for row in rows for trace in row["traces"]],
    ])
    assert "gold_sql" not in public_wire and "db_path" not in public_wire
    assert all(value not in public_wire for value in private_strings)
    if f.status == "match":
        assert all(episode.ok for episode in episodes)
        assert all(trace.ok and set(trace.rewards) == {"execution_accuracy"}
                   and trace.rewards["execution_accuracy"].score == 1.0
                   for trace in traces)
        assert all(_successful(row) and row["ok"] for row in rows)
        assert all(trace["ok"] and set(trace["rewards"]) == {"execution_accuracy"}
                   and trace["rewards"]["execution_accuracy"]["score"] == 1.0
                   for row in rows for trace in row["traces"])
    else:
        assert not any(episode.ok for episode in episodes), (
            "INVALID_NATIVE_STATUS_PUBLISHED_EPISODE")
        assert all(not trace.ok and trace.rewards == {} for trace in traces)
        assert not any(_successful(row) for row in rows)
        assert all(not trace.get("rewards")
                   for row in rows for trace in row.get("traces", []))


@pytest.mark.parametrize("rollouts,num_tasks", [(1, None), (2, 7)], ids=(
    "distinct-tasks-one-sample", "same-task-two-samples"))
def test_registered_sdk_mock_result_concurrent_success(
        request, monkeypatch, rollouts, num_tasks):
    f = _prepare(request, monkeypatch, rollouts=rollouts,
                 num_tasks=num_tasks, status="match")
    episodes = asyncio.run(asyncio.wait_for(_evaluate(f), SAFETY_SECONDS))
    _assert_composition(f, episodes)


@pytest.mark.parametrize("status", (
    "gold_error", "gold_timeout", "gold_truncated", "db_missing"))
def test_registered_sdk_mock_invalid_status_never_rewards(
        request, monkeypatch, status):
    # Same invalid native-status MOCK on ALL seven eligible Tasks: no zeros
    # masquerading as valid rewards, and no successful episode OR trace rows.
    f = _prepare(request, monkeypatch, rollouts=1, num_tasks=7, status=status)
    episodes = asyncio.run(asyncio.wait_for(_evaluate(f), SAFETY_SECONDS))
    _assert_composition(f, episodes)
