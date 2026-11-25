"""Track A numeric admission tests. No runtime/model/provider required."""
from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path

import pytest
from verifiers.v1.agent import Agent, Agents, _EpisodeAgent
from verifiers.v1.clients import ModelContext
from verifiers.v1.configs.cli.eval import EvalConfig
from verifiers.v1.task import Task, TaskData
from verifiers.v1.taskset import Taskset
from verifiers.v1.utils.loaders import load_environment

import cotrain_ptc_qa as activation
from ptc.sql_qa import MAX_EXPORT_BYTES, QaChannel
from ptc.test_bash_qa_eval import UNIT_TASKSET_ID, UnitTaskset
from ptc.test_bash_qa import _trace
from ptc.test_ptc_qa_activation_integration import _agent_json


def _prod():
    return importlib.import_module("cotrain_ptc_qa_env")


def _config(tmp_path):
    return EvalConfig.model_validate_json(json.dumps({
        "model": "fixture-model",
        "client": {"type": "train", "api_key_var": "UNUSED_FIXTURE_KEY"},
        "env": {
            "id": "cotrain_ptc_qa_env", "taskset": {"id": UNIT_TASKSET_ID},
            "interception": {"type": "server"}, "agent": _agent_json(),
        },
        "num_tasks": 1, "num_rollouts": 1, "max_concurrent": 1,
        "push": False, "rich": None, "output_dir": str(tmp_path / "output"),
    }))


def test_A_missing_private_API_call_phase():
    # RED must be an assertion after real dependency/product imports, not
    # ModuleNotFoundError or a missing optional plugin.
    assert callable(getattr(activation, "_run_episode_ptc_qa", None)), (
        "A_AGENT_BOUNDARY: missing private episode activation API")


def test_A_JSON_CANONICAL_exact_one(tmp_path):
    api = _prod()
    config = _config(tmp_path)
    assert type(config.env) is api.ReportingPTCEnvConfig
    assert type(config.env.agent.harness) is activation.ReportingPTCConfig
    assert config.env.agent.harness.program_timeout == 2
    assert config.env.agent.max_turns == 4
    assert EvalConfig.model_validate_json(config.model_dump_json()) == config
    assert type(load_environment(config.env)) is api.ReportingPTCEnv


@pytest.mark.parametrize("path,value", [
    ("push", True), ("resume", True), ("clean", True), ("dry_run", True),
    ("run.attach", "refuse"),
    ("env.retries.max_retries", 1), ("env.agent.retries.max_retries", 1),
    ("num_tasks", None), ("num_tasks", 0), ("num_tasks", True),
    ("num_rollouts", 0), ("max_concurrent", None),
    ("env.max_concurrent_agents", None),
    ("env.agent.max_turns", 0),
    ("env.agent.max_output_tokens", 0),
    ("env.agent.timeout.setup", float("inf")),
    ("env.agent.timeout.scoring", None),
    ("env.agent.harness.program_timeout", 0),
    ("env.agent.harness.tool_timeout", float("inf")),
    ("env.agent.harness.skills", ["not-supported"]),
    ("env.agent.model", ""),
    ("env.timeout.episode", float("nan")),
])
def test_A_PREFLIGHT_zero_eval_resource_policy(monkeypatch, tmp_path, path, value):
    api = _prod()
    config = _config(tmp_path)
    target = config
    parts = path.split(".")
    for part in parts[:-1]:
        target = getattr(target, part)
    object.__setattr__(target, parts[-1], value)
    calls = []

    async def forbidden(config):
        calls.append(config)
        raise AssertionError("SDK evaluator reached")

    monkeypatch.setattr(api, "run_eval", forbidden)
    with pytest.raises((ValueError, TypeError)):
        asyncio.run(api.run_ptc_qa_eval(config))
    assert calls == []
    assert not Path(config.output_dir).exists()
    assert api._admission.get() is None


@pytest.mark.parametrize("hook", ["task_type", "toolsets", "task_toolsets"])
@pytest.mark.parametrize("inherited", [False, True])
def test_A_RESOURCE_hooks_zero_invocations(monkeypatch, tmp_path, hook, inherited):
    api = _prod()
    calls = []

    def forbidden(*args):
        calls.append("hook")
        raise AssertionError("custom resource hook invoked")

    parent = type("CustomParent", (UnitTaskset,), {})
    cls = type("CustomChild", (parent,), {}) if inherited else parent
    if hook == "task_toolsets":
        task = type("CustomTask", (Task,), {"toolsets": classmethod(forbidden)})
        # Canonical selector, custom declared task via a real generic.
        class Custom(Taskset[task]):
            def load(self):
                return []
        cls = Custom
    else:
        setattr(parent, hook, classmethod(forbidden))
    monkeypatch.setattr(api, "taskset_class", lambda _: cls)
    config = _config(tmp_path)
    eval_calls, base_calls = [], []

    async def forbidden_eval(config):
        eval_calls.append(config)

    monkeypatch.setattr(api, "run_eval", forbidden_eval)
    with pytest.raises(ValueError, match="resource"):
        asyncio.run(api.run_ptc_qa_eval(config))
    original_init = UnitTaskset.__init__
    def observe_init(self, config):
        base_calls.append(config)
        original_init(self, config)
    monkeypatch.setattr(UnitTaskset, "__init__", observe_init)
    with pytest.raises(ValueError, match="resource"):
        api.ReportingPTCEnv(config.env)
    assert calls == eval_calls == base_calls == []


def test_A_AGENT_BOUNDARY_public_zero_runs_even_active_eval(monkeypatch, tmp_path):
    api = _prod()
    config = _config(tmp_path)
    calls = []

    async def sdk(config):
        env = load_environment(config.env)
        ctx = ModelContext(config.model, config.client, config.sampling)
        agents = env._episode_agents(ctx, [], None, None)
        assert type(agents.agent) is _EpisodeAgent
        task = Task(TaskData(prompt="no dispatch"))
        class Arbitrary(Agent):
            pass
        same_name = type("_EpisodeAgent", (Agent,), {})(config.env.agent)
        base_with_gate = Agent(config.env.agent)
        base_with_gate._gate = asyncio.Semaphore(1)
        for agent in (
            agents.agent, Arbitrary(config.env.agent), same_name, base_with_gate,
        ):
            with pytest.raises(ValueError):
                await activation.run_configured_ptc_qa(
                    agent, task, qa_factory=lambda data: calls.append(data))
            assert getattr(agent, activation._OWNER_ATTR, None) is None
        return []

    monkeypatch.setattr(api, "run_eval", sdk)
    asyncio.run(api.run_ptc_qa_eval(config))
    assert calls == [] and activation._ACTIVE.get() is None


@pytest.mark.parametrize("mode", ["success", "error", "cancel"])
def test_A_admission_revoked_in_inherited_context(monkeypatch, tmp_path, mode):
    api = _prod()
    held = []

    async def sdk(config):
        held.append(api._admission.get())
        if mode == "error":
            raise RuntimeError("fixture")
        if mode == "cancel":
            raise asyncio.CancelledError()
        return []

    monkeypatch.setattr(api, "run_eval", sdk)
    async def scenario():
        try:
            await api.run_ptc_qa_eval(_config(tmp_path))
        except (RuntimeError, asyncio.CancelledError):
            pass
        assert api._admission.get() is None
    asyncio.run(scenario())
    assert len(held) == 1 and held[0].active is False


def test_A_QUOTA_9_to_8_and_attachment_errors(monkeypatch, tmp_path):
    api = _prod()
    channel = QaChannel()
    from ptc.sql_qa import ReportRejected
    for i in range(8):
        channel.submit("ptc", kind="other", detail=str(i))
    with pytest.raises(ReportRejected):
        channel.submit("ptc", kind="other", detail="ninth")
    assert json.loads(channel.export())["arms"]["ptc"]["reports"] == 8
    assert len(channel.export()) <= MAX_EXPORT_BYTES == 65536
    agent = Agent(_config(tmp_path).env.agent)
    trace = _trace(Task(TaskData(prompt="attachment")), agent)
    api._attach_qa(trace, channel)
    before = dict(trace.info)
    with pytest.raises(ValueError):
        api._attach_qa(trace, channel)
    assert trace.info == before
    trace.info.clear()
    boom = RuntimeError("export failure")
    monkeypatch.setattr(channel, "export", lambda: (_ for _ in ()).throw(boom))
    with pytest.raises(RuntimeError) as exc:
        api._attach_qa(trace, channel)
    assert exc.value is boom and trace.info == {}


def test_A_attachment_write_failure_propagates(tmp_path):
    from types import MappingProxyType
    api = _prod()
    trace = _trace(Task(TaskData(prompt="immutable info")),
                   Agent(_config(tmp_path).env.agent))
    object.__setattr__(trace, "info", MappingProxyType({}))
    with pytest.raises(TypeError):
        api._attach_qa(trace, QaChannel())
    assert dict(trace.info) == {}


def test_A_constructor_claim_precedes_callback_and_no_second_owner(monkeypatch, tmp_path):
    api = _prod()
    observed = []
    check = api._check_tool_free
    async def sdk(config):
        def probe(cls):
            owner = api._admission.get()
            assert owner.env is not None
            with pytest.raises(ValueError):
                api.ReportingPTCEnv(config.env)
            observed.append(owner.env)
            return check(cls)
        with monkeypatch.context() as scoped:
            scoped.setattr(api, "_check_tool_free", probe)
            env = load_environment(config.env)
        assert observed == [env]
        return []
    monkeypatch.setattr(api, "run_eval", sdk)
    asyncio.run(api.run_ptc_qa_eval(_config(tmp_path)))


def test_A_private_exact_episode_without_owner_zero_factory(monkeypatch, tmp_path):
    api = _prod()
    config = _config(tmp_path)
    env = load_environment(config.env)
    ctx = ModelContext(config.model, config.client, config.sampling)
    agents = env._episode_agents(ctx, [], None, None)
    calls = []
    async def scenario():
        with pytest.raises(ValueError):
            await activation._run_episode_ptc_qa(
                agents.agent, Task(TaskData(prompt="no owner")),
                qa_factory=lambda data: calls.append(data))
    asyncio.run(scenario())
    assert calls == [] and activation._ACTIVE.get() is None
    assert getattr(agents.agent, activation._OWNER_ATTR, None) is None


@pytest.mark.parametrize("case", ["runtime", "harness_subtype", "marked", "wrong_id"])
def test_A_PREFLIGHT_exact_runtime_harness_zero_eval(monkeypatch, tmp_path, case):
    from verifiers.v1.runtimes import PrimeConfig
    api = _prod()
    config = _config(tmp_path)
    if case == "runtime":
        object.__setattr__(config.env.agent, "runtime", PrimeConfig())
    elif case == "harness_subtype":
        class Subtype(activation.ReportingPTCConfig):
            pass
        object.__setattr__(config.env.agent, "harness", Subtype())
    elif case == "marked":
        object.__setattr__(config.env.agent.harness, "_qa_required", True)
    else:
        object.__setattr__(config.env.agent.harness, "id", "ptc")
    calls = []
    async def forbidden(config):
        calls.append(config)
    monkeypatch.setattr(api, "run_eval", forbidden)
    with pytest.raises(ValueError):
        asyncio.run(api.run_ptc_qa_eval(config))
    assert calls == [] and not Path(config.output_dir).exists()
