"""Private product composition, synthetic executor/upstream, no native proof."""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import importlib
import json
import os
import sys
from types import SimpleNamespace

import httpx
import pytest

from verifiers.v1.agent import Agent, _EpisodeAgent
from verifiers.v1.clients import ModelContext
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.configs.cli.eval import EvalConfig
from verifiers.v1.configs.env import _declared_agent_configs
from verifiers.v1.episode import Episode
from verifiers.v1.task import Task, TaskData
from verifiers.v1.utils import loaders

from bench.score import ExResult
from ptc import sql_isolation as core
from ptc.harness import PTCHarness, PTCHarnessConfig
from ptc.sql_owned_score import OwnedSqlScorer
from ptc.test_sql_owned_program import _fixture
from train.sql_episodes import InstrumentSettings


@pytest.fixture(autouse=True)
def restore_vf_run_id():
    present, value = "VF_RUN_ID" in os.environ, os.environ.get("VF_RUN_ID")
    try:
        yield
    finally:
        if present:
            os.environ["VF_RUN_ID"] = value
        else:
            os.environ.pop("VF_RUN_ID", None)


def _api():
    return importlib.import_module("train.sql_live_reuse")


def _case(tmp_path):
    api = _api()
    fixture = _fixture(tmp_path)
    task = dataclasses.replace(fixture.task, question="PUBLIC_QUESTION_V29",
        evidence="PRIVATE_EVIDENCE_V29", gold_sql="PRIVATE_GOLD_V29")
    config = EvalConfig.model_validate({
        "model": "synthetic-policy",
        "client": {"type": "eval", "base_url": "http://synthetic.invalid/v1",
                   "api_key_var": "UNUSED_SYNTHETIC_V29"},
        "env": {"id": "cotrain_bird_sql_live",
                "taskset": {"id": "cotrain_bird_sql_live"},
                "interception": {"type": "server"},
                "agent": {"harness": {"id": "cotrain_bird_sql_harness",
                                      "max_turns": 2, "program_timeout": 5},
                          "runtime": {"type": "subprocess"},
                          "retries": {"max_retries": 0}},
                "retries": {"max_retries": 0}},
        "num_tasks": 1, "num_rollouts": 1, "max_concurrent": 1,
        "push": False, "resume": False, "clean": False, "rich": None,
        "output_dir": str(tmp_path / "output"), "run": {"dir": "run"},
    })
    instrument = InstrumentSettings(
        2, 7, 7, "set", 30.0, 5.0, 30.0,
        "synthetic-python", "synthetic-sqlite", (), "a" * 64)
    expected = config.env.agent.model_copy(deep=True, update={
        "model": config.model, "client": config.client.model_copy(deep=True),
        "sampling": config.sampling.model_copy(deep=True)})
    policy = api.SqlLivePolicy(expected, ModelContext(
        "synthetic-policy", config.client.model_copy(deep=True),
        config.sampling.model_copy(deep=True)))
    plan = api.SqlLivePlan((api.SqlLiveInput(
        task, "CREATE TABLE public_v29(x INTEGER)", fixture.digest),))
    scope = api._Scope(plan, config, fixture.executor, instrument, policy, None)
    return SimpleNamespace(api=api, fixture=fixture, plan=plan, config=config,
                           instrument=instrument, policy=policy, scope=scope)


def _activate(case):
    return case.api._ACTIVE_SCOPE.set(case.scope)


def _tasks(case):
    plugin = importlib.import_module("bench.bird_sdk_live")
    token = _activate(case)
    try:
        taskset = loaders.load_taskset(case.config.env.taskset)
        tasks = tuple(taskset)
        assert tuple(taskset)[0] is tasks[0]
        return plugin, tasks
    finally:
        case.api._ACTIVE_SCOPE.reset(token)


def test_loader_original_classes():
    before = set(sys.modules)
    assert loaders.harness_class("cotrain_bird_sql_harness") is PTCHarness
    assert loaders.harness_config_type("cotrain_bird_sql_harness") is PTCHarnessConfig
    harness_entrypoint = importlib.import_module("cotrain_bird_sql_harness")
    assert harness_entrypoint.__all__ == ["PTCHarness"]
    assert not ({"bench.bird_sdk_live", "cotrain_bird_sql_live"} & (set(sys.modules) - before))
    assert loaders.harness_class("cotrain_bird_sql_live") is PTCHarness
    assert loaders.harness_config_type("cotrain_bird_sql_live") is PTCHarnessConfig
    plugin = importlib.import_module("bench.bird_sdk_live")
    entrypoint = importlib.import_module("cotrain_bird_sql_live")
    assert entrypoint.__all__ == ["PTCHarness", "BirdSqlTaskset", "BirdSqlEnv"]
    assert loaders.taskset_class("cotrain_bird_sql_live") is plugin.BirdSqlTaskset
    assert loaders.environment_class("cotrain_bird_sql_live") is plugin.BirdSqlEnv
    first, second = plugin.BirdSqlEnvConfig(), plugin.BirdSqlEnvConfig()
    assert first.id == second.id == "cotrain_bird_sql_live"
    assert type(first.agent.harness) is type(second.agent.harness) is PTCHarnessConfig
    assert first.agent.harness == second.agent.harness == PTCHarnessConfig(
        id="cotrain_bird_sql_harness")
    assert first.agent is not second.agent and first.agent.harness is not second.agent.harness
    assert not any("cotrain_fixture" in name for name in set(sys.modules) - before)
    assert plugin.BirdSqlTask.score is Task.score


def test_declared_role_defaults_and_partial_override():
    plugin = importlib.import_module("bench.bird_sdk_live")
    field = plugin.BirdSqlEnvConfig.model_fields["agent"]
    assert type(field.default) is AgentConfig and field.default_factory is None
    config = plugin.BirdSqlEnvConfig.model_validate({
        "agent": {"harness": {"max_turns": 2}}})
    assert _declared_agent_configs(config) == {"agent": config.agent}
    assert type(config.agent.harness) is PTCHarnessConfig
    assert config.agent.harness.id == "cotrain_bird_sql_harness"
    assert config.agent.harness.max_turns == 2 and config.agent.harness.program_timeout == 5


@pytest.mark.parametrize("kind,group", [
    ("harness", "harnesses"), ("taskset", "tasksets"), ("environment", "envs"),
])
def test_dotted_plugin_id_fails_before_fallback(kind, group):
    resolve = getattr(loaders, "import_" + kind)
    with pytest.raises(ModuleNotFoundError) as caught:
        resolve("bench.bird_sdk_live")
    assert caught.value.name == "verifiers.v1." + group + ".bench"


def test_public_projection_private_canaries(tmp_path):
    case = _case(tmp_path)
    _, tasks = _tasks(case)
    assert len(tasks) == 1 and type(tasks[0].data) is TaskData
    wire = tasks[0].data.model_dump_json()
    assert "PUBLIC_QUESTION_V29" in wire and "CREATE TABLE public_v29" in wire
    assert all(value not in wire for value in (
        "PRIVATE_EVIDENCE_V29", "PRIVATE_GOLD_V29", case.fixture.task.db_path,
        "db_path", "gold_sql", "approved_skill", "executor"))


def test_scope_revocation(tmp_path):
    case = _case(tmp_path)
    case.scope.live = False
    token = _activate(case)
    try:
        with pytest.raises(case.api.SqlLiveError):
            loaders.load_taskset(case.config.env.taskset)
    finally:
        case.api._ACTIVE_SCOPE.reset(token)
    with pytest.raises(case.api.SqlLiveError):
        loaders.load_taskset(case.config.env.taskset)


@pytest.mark.parametrize("fault", ["short", "long", "bool", "copy", "view", "transform"])
def test_taskset_refuses_noncanonical_views(tmp_path, fault):
    case = _case(tmp_path)
    token = _activate(case)
    try:
        taskset = loaders.load_taskset(case.config.env.taskset)
        original, = taskset
        candidate, count = taskset, 1
        if fault in ("short", "long", "bool"):
            count = {"short": 0, "long": 2, "bool": True}[fault]
        elif fault == "copy":
            candidate = copy.copy(taskset)
        elif fault == "view":
            candidate = taskset.view(lambda tasks: tasks)
        else:
            taskset.transform = lambda tasks: tasks
        with pytest.raises(case.api.SqlLiveError):
            candidate.head(count)
        if fault in ("copy", "view"):
            with pytest.raises(case.api.SqlLiveError):
                candidate.load()
        assert tuple(case.scope.tasks.values()) == (original,)
    finally:
        case.api._ACTIVE_SCOPE.reset(token)


@pytest.mark.parametrize("location", ["task", "harness"])
def test_skills_refused_before_rollout(tmp_path, location):
    case = _case(tmp_path)
    plugin, (task,) = _tasks(case)
    agent = Agent(case.policy.agent.model_copy(deep=True))
    if location == "task":
        task.data.skills.append("synthetic-skill")
    else:
        agent.harness.config.skills.append("synthetic-skill")
    token = _activate(case)
    try:
        with pytest.raises(case.api.SqlLiveError):
            case.api._Association(case.scope, task, agent)
        assert agent.harness._launch_started is False
    finally:
        case.api._ACTIVE_SCOPE.reset(token)


@pytest.mark.parametrize("fault", ["task", "config", "instrument", "scorer"])
def test_composition_custody_refusals(tmp_path, fault):
    case = _case(tmp_path)
    plugin, (task,) = _tasks(case)
    agent = Agent(case.policy.agent.model_copy(deep=True))
    token = _activate(case)
    try:
        if fault == "task":
            task = plugin.BirdSqlTask(task.data, task.config)
            with pytest.raises(case.api.SqlLiveError):
                case.api._Association(case.scope, task, agent)
        else:
            association = case.api._Association(case.scope, task, agent)
            if fault == "config":
                agent.config = agent.config.model_copy(deep=True)
            elif fault == "instrument":
                association.scorer._instrument = dataclasses.replace(case.instrument)
            else:
                association.scorer = object()
            with pytest.raises(case.api.SqlLiveError):
                association.check()
        assert agent.harness._launch_started is False
    finally:
        case.api._ACTIVE_SCOPE.reset(token)


def _execution_fixture(case, monkeypatch, tmp_path, *, invalid=False):
    from verifiers.v1 import rollout as rollout_mod
    from verifiers.v1.clients.eval import EvalClient
    from verifiers.v1.runtimes.subprocess import SubprocessRuntime
    from ptc import sql_owned_program

    state = SimpleNamespace(requests=[], agents=[], scores=[], program_closes=[],
                            scorer_closes=[], traces=[], associations=[], bindings=[])
    original_init = Agent.__init__
    original_close = sql_owned_program._Runner.aclose
    original_scorer_close = OwnedSqlScorer.aclose
    original_bind = sql_owned_program.build_owned_sql_program_harness

    class LocalRuntime(SubprocessRuntime):
        async def start(self):
            self.workdir = tmp_path / "runtime"
            self.workdir.mkdir(exist_ok=True)
            self.info.id = str(self.workdir)
            self.scripts_dir = str(tmp_path / "scripts")

    def agent_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        state.agents.append((self, self.harness))

    def bind(*args, **kwargs):
        before = kwargs["existing_harness"]
        result = original_bind(*args, **kwargs)
        assert result is before
        state.bindings.append(result)
        return result

    def respond(request):
        assert request.url.host == "synthetic.invalid"
        state.requests.append(json.loads(request.content))
        delta = {"content": "SELECT 1"}
        chunk = {"id": "synthetic-v29", "object": "chat.completion.chunk",
                 "created": 1, "model": "synthetic-policy",
                 "choices": [{"index": 0, "delta": delta, "finish_reason": "stop"}]}
        usage = dict(chunk, choices=[], usage={
            "prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14})
        raw = "".join("data: " + json.dumps(item) + "\n\n" for item in (chunk, usage))
        return httpx.Response(200, content=(raw + "data: [DONE]\n\n").encode(),
                              headers={"content-type": "text/event-stream"})

    def client_init(self, config):
        self.base_url, self.api_key, self.headers = config.base_url, "synthetic", {}
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))

    def admit(self, *, db_path, db_sha256):
        assert self is case.fixture.executor
        return core.ProgramDatabaseIdentity(db_path, db_sha256, 1, 1, 1, 1, 1, 1, 1, 1)

    async def score(self, predicted_sql):
        assert type(self) is OwnedSqlScorer and self._task is case.plan.inputs[0].task
        association = case.api._ACTIVE_ASSOCIATION.get()
        assert association.scorer is self
        state.associations.append(association)
        state.traces.append(association.trace)
        state.scores.append(self)
        return ExResult(0.0 if invalid else 1.0,
                        "gold_error" if invalid else "match", not invalid)

    async def close_program(self):
        await original_close(self)
        state.program_closes.append(self)

    async def close_scorer(self):
        await original_scorer_close(self)
        state.scorer_closes.append(self)

    monkeypatch.setattr(rollout_mod, "make_runtime",
                        lambda config, name=None: LocalRuntime(config, name))
    monkeypatch.setattr(Agent, "__init__", agent_init)
    monkeypatch.setattr(EvalClient, "__init__", client_init)
    monkeypatch.setattr(core.PilotExecutor, "admit_program", admit)
    monkeypatch.setattr(OwnedSqlScorer, "score_sql", score)
    monkeypatch.setattr(OwnedSqlScorer, "aclose", close_scorer)
    monkeypatch.setattr(sql_owned_program._Runner, "aclose", close_program)
    monkeypatch.setattr(sql_owned_program, "build_owned_sql_program_harness", bind)
    return state


def _execute(case):
    return case.api.run_sql_live(
        case.plan, case.config, executor=case.fixture.executor,
        instrument=case.instrument, expected_policy=case.policy,
        allow_execution=True, allow_model_requests=True)


@pytest.mark.parametrize("num_tasks", [None, 1])
def test_original_sdk_composition(tmp_path, monkeypatch, num_tasks):
    case = _case(tmp_path)
    case.config.num_tasks = num_tasks
    state = _execution_fixture(case, monkeypatch, tmp_path)
    original_register = case.api._Scope.register
    original_finish = case.api._Scope.finish
    registered = []

    def register(scope, task):
        original_register(scope, task)
        registered.append(task)
        assert scope.taskset.head(1) is scope.taskset

    def finish(scope, episodes):
        task, = registered
        assert tuple(scope.taskset) == (task,)
        assert tuple(scope.taskset.head(1))[0] is task
        return original_finish(scope, episodes)

    monkeypatch.setattr(case.api._Scope, "register", register)
    monkeypatch.setattr(case.api._Scope, "finish", finish)
    result = asyncio.run(asyncio.wait_for(_execute(case), 5))
    assert len(result.episodes) == len(result.receipts) == len(state.requests) == 1
    episode, = result.episodes
    assert type(episode) is Episode and episode.ok
    trace, = episode.traces
    assert result.receipts[0].trace is trace and trace.ok
    assert trace.rewards["execution_accuracy"].score == 1.0
    assert len(state.scores) == len(state.program_closes) == len(state.scorer_closes) == 1
    assert len(state.agents) == len(state.bindings) == 1
    assert state.agents[0][0].harness is state.agents[0][1] is state.bindings[0]
    association, = state.associations
    task, = registered
    assert association.task is task is association.scope.tasks[task.data.name]
    assert trace.num_input_tokens == 11 and trace.num_output_tokens == 3
    assert case.api._ACTIVE_SCOPE.get() is None


@pytest.mark.parametrize("later_cancellations", [1, 3])
def test_env_body_cancellation_survives_scorer_cleanup(
        tmp_path, monkeypatch, later_cancellations):
    case = _case(tmp_path)
    state = _execution_fixture(case, monkeypatch, tmp_path)
    real_close = OwnedSqlScorer.aclose
    primary = asyncio.CancelledError("original-env-body-A")
    associations, observed = [], []

    async def exercise():
        close_started, close_release = asyncio.Event(), asyncio.Event()

        async def cancel_score(scorer, predicted_sql):
            association = case.api._ACTIVE_ASSOCIATION.get()
            assert type(scorer) is OwnedSqlScorer and association.scorer is scorer
            associations.append(association)
            raise primary

        async def held_close(scorer):
            assert scorer is associations[0].scorer
            close_started.set()
            await close_release.wait()
            await real_close(scorer)

        monkeypatch.setattr(OwnedSqlScorer, "score_sql", cancel_score)
        monkeypatch.setattr(OwnedSqlScorer, "aclose", held_close)

        async def invoke():
            token = _activate(case)
            try:
                env = loaders.load_environment(case.config.env)
                task, = env.taskset
                agent = _EpisodeAgent(
                    case.policy.agent.model_copy(deep=True), interception=None,
                    name="agent", shared_tools={}, task_cls=type(task), gate=None,
                    completed=[], on_trace=None, on_discard=None, warned_resources=set())
                try:
                    await env.run(task, SimpleNamespace(agent=agent))
                except asyncio.CancelledError as exc:
                    observed.append(exc)
                    assert case.api._ACTIVE_ASSOCIATION.get() is None
                    assert not associations[0].live
                    raise
            finally:
                case.api._ACTIVE_SCOPE.reset(token)

        caller = asyncio.create_task(invoke())
        try:
            await close_started.wait()
            association, = associations
            assert not association.live and state.scorer_closes == []
            for index in range(later_cancellations):
                assert caller.cancel("later-env-cleanup-B-" + str(index))
                await asyncio.sleep(0)
                assert not caller.done() and not association.scorer._closed
            close_release.set()
            with pytest.raises(asyncio.CancelledError) as caught:
                await caller
            assert caught.value is primary and observed == [primary]
            assert caught.value.args == ("original-env-body-A",)
            assert state.scorer_closes == [association.scorer]
            assert association.scorer._closed and association.scorer._jobs == []
            assert len(state.requests) == len(state.program_closes) == 1
            assert case.api._ACTIVE_SCOPE.get() is case.api._ACTIVE_ASSOCIATION.get() is None
        finally:
            close_release.set()
            if not caller.done():
                caller.cancel()
            await asyncio.gather(caller, return_exceptions=True)

    asyncio.run(asyncio.wait_for(exercise(), 5))


def test_invalid_ex_has_no_reward(tmp_path, monkeypatch):
    case = _case(tmp_path)
    state = _execution_fixture(case, monkeypatch, tmp_path, invalid=True)
    with pytest.raises(case.api.SqlLiveError):
        asyncio.run(asyncio.wait_for(_execute(case), 5))
    assert len(state.scores) == len(state.scorer_closes) == 1
    assert case.api._ACTIVE_SCOPE.get() is None


def test_invalid_ex_failed_trace_publishes_no_numeric_reward(tmp_path, monkeypatch):
    case = _case(tmp_path)
    state = _execution_fixture(case, monkeypatch, tmp_path, invalid=True)
    with pytest.raises(case.api.SqlLiveError):
        asyncio.run(asyncio.wait_for(_execute(case), 5))
    trace, = state.traces
    association, = state.associations
    assert trace is association.trace is association.original_trace
    assert not trace.ok and trace.errors
    assert set(trace.rewards) == {"execution_accuracy"}
    assert trace.rewards["execution_accuracy"] is None
    assert all(reward is None for reward in trace.rewards.values())
    assert association.result is association.receipt is None
    assert len(state.requests) == len(state.scores) == len(state.scorer_closes) == 1
    assert not association.live and not association.scope.live
    assert case.api._ACTIVE_SCOPE.get() is case.api._ACTIVE_ASSOCIATION.get() is None


@pytest.mark.parametrize("fault", ["missing", "duplicate", "trace"])
def test_whole_coverage_refusals(tmp_path, monkeypatch, fault):
    case = _case(tmp_path)
    state = _execution_fixture(case, monkeypatch, tmp_path)
    original = case.api._Scope.finish

    def altered(self, episodes):
        if fault == "missing":
            episodes = []
        elif fault == "duplicate":
            episodes = episodes + episodes
        else:
            episodes[0].traces[0] = episodes[0].traces[0].model_copy(deep=True)
        return original(self, episodes)
    monkeypatch.setattr(case.api._Scope, "finish", altered)
    with pytest.raises(case.api.SqlLiveError):
        asyncio.run(asyncio.wait_for(_execute(case), 5))
    assert len(state.requests) == 1
