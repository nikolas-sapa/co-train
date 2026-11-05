"""Actual SDK episode Agent, in-process PTC, loopback and original JSONL.

Reuses first-party scripted fixture. Parent Python socket/DNS guard only,
not an OS/subprocess sandbox. PTC program executes in process. No provider,
native, profile or training runs. Each real fixture has a 20s outer bound.
"""
from __future__ import annotations

import asyncio
import importlib
import json

import pytest

import cotrain_ptc_qa as activation
from ptc.sql_qa import QaChannel, MAX_EXPORT_BYTES
from ptc.test_bash_qa_eval_integration import (
    framework, _config as _bash_config, _rows, RoutingClient,
)
from ptc.test_bash_qa_activation_integration import ScriptedClient, _text_step
from ptc.test_ptc_qa_activation_integration import (
    _agent_json, _report_program, _program_call,
)
from verifiers.v1.configs.cli.eval import EvalConfig

pytestmark = pytest.mark.filterwarnings(
    "error::pytest.PytestUnraisableExceptionWarning")
QA_KEY = "cotrain_ptc_qa"


def _api():
    return importlib.import_module("cotrain_ptc_qa_env")


def _config(monkeypatch, state, **kwargs):
    config, module = _bash_config(monkeypatch, state, **kwargs)
    payload = json.loads(config.model_dump_json())
    payload["env"]["id"] = "cotrain_ptc_qa_env"
    payload["env"]["agent"] = _agent_json()
    config = EvalConfig.model_validate_json(json.dumps(payload))
    state.config = config
    return config, module


def _policy(detail, *, on_call=None, error=False):
    return ScriptedClient([
        _report_program(detail),
        *([_program_call("1 / 0")] if error else []),
        _text_step("done"),
    ], on_call=on_call)


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, 20))


def _qa(trace):
    assert QA_KEY in trace.info, "A attachment: missing telemetry"
    return trace.info[QA_KEY]


def _proof(state, config, module, episodes, policies):
    assert len(episodes) == len(state.channels) == len(state.agents), (
        "A activation: one channel and episode Agent per run")
    assert len({id(c) for c in state.channels}) == len(episodes)
    rows = _rows(config)
    assert len(rows) == len(episodes)
    for episode in episodes:
        trace, = episode.traces
        assert episode.ok and trace.ok, f"A activation: {episode.errors}, {trace.last_error}"
        doc = _qa(trace)
        arm = doc["arms"]["ptc"]
        assert arm["reports"] == 1, "A retention: exactly one report"
        event, = arm["events"]
        lane = episode.task.data.prompt.rsplit(" ", 1)[-1]
        assert event["detail"] == "only-" + lane
        assert event["provenance"] == "catalog_callback"
        assert trace.task.data is episode.task.data
        assert trace.task.hash == episode.task.hash
        assert trace.reward == 0.375 and trace.metrics["fixture_score"] == 1
        row, = [r for r in rows if r["task"]["hash"] == episode.task.hash]
        assert row["traces"][0]["info"][QA_KEY] == doc
    for policy in policies:
        assert policy.receipt_at == [2], "A receipt: request 2"
    assert all(len(c.export()) <= MAX_EXPORT_BYTES for c in state.channels)
    assert state.external == []
    assert activation._ACTIVE.get() is _api()._admission.get() is None
    for agent, original in state.agents:
        assert agent.harness is original
        assert agent._gate is not None
        assert getattr(agent, activation._OWNER_ATTR, None) is None
    assert module.builds == []  # Original Task, no Bash pairing builder.


def test_A_REAL_1_eval_run_activation_channel_report_original_writer(monkeypatch, framework):
    state = framework
    config, module = _config(monkeypatch, state)
    state.policy = policy = _policy("only-lane-0")
    records, tasks, gates, eval_calls = [], [], [], []
    bind = activation._bind_harness
    api = _api()
    original_eval = api.run_eval

    def observe(harness_config, binding):
        records.append(binding._record)
        tasks.append(binding._record.task)
        gates.append(binding._record.agent._gate)
        assert binding._record.agent.config is not config.env.agent
        return bind(harness_config, binding)

    async def delegate(exact):
        eval_calls.append(exact)
        return await original_eval(exact)

    monkeypatch.setattr(activation, "_bind_harness", observe)
    monkeypatch.setattr(api, "run_eval", delegate)
    episodes = _run(api.run_ptc_qa_eval(config))
    _proof(state, config, module, episodes, [policy])
    assert len(records) == 1 and records[0].state == "revoked"
    assert records[0].active is False and records[0].agent is None
    trace, = episodes[0].traces
    assert _qa(trace) == json.loads(state.channels[0].export())
    assert policy.calls == 2 and trace.num_turns == 2
    assert len(state.agents[0][0]._completed) == 1
    assert len(eval_calls) == 1 and eval_calls[0] is config
    assert len(tasks) == 1 and tasks[0] is module.seeds[0]
    assert trace.task.data is tasks[0].data
    assert gates[0] is state.agents[0][0]._gate


@pytest.mark.parametrize("concurrent", [1, 2])
def test_A_ISOLATION_2_sequential_or_barrier_overlapping(monkeypatch, framework, concurrent):
    state = framework
    config, module = _config(monkeypatch, state, count=2, concurrent=concurrent)
    async def scenario():
        arrived = set()
        release = asyncio.Event()
        def barrier(label):
            async def on_call(n):
                if n == 2 and concurrent == 2:
                    arrived.add(label)
                    if len(arrived) == 2:
                        release.set()
                    await asyncio.wait_for(release.wait(), 10)
            return on_call
        clients = {f"lane-{i}": _policy(
            f"only-lane-{i}", on_call=barrier(i)) for i in range(2)}
        state.policy = RoutingClient(clients)
        episodes = await _api().run_ptc_qa_eval(config)
        assert len(arrived) == (2 if concurrent == 2 else 0)
        return episodes, clients
    episodes, clients = _run(scenario())
    _proof(state, config, module, episodes, clients.values())


@pytest.mark.parametrize("fail_score,program_error", [(False, True), (True, False)])
def test_A_report_then_program_feedback_or_real_failed_scoring(
        monkeypatch, framework, fail_score, program_error):
    state = framework
    config, module = _config(monkeypatch, state, fail_score=fail_score)
    state.policy = policy = _policy("retained", error=program_error)
    episode, = _run(_api().run_ptc_qa_eval(config))
    trace, = episode.traces
    assert episode.ok is (not fail_score) and trace.ok is (not fail_score)
    if fail_score:
        assert "synthetic scoring failure" in str(trace.last_error)
    else:
        assert "ZeroDivisionError" in str(policy.bodies[2])
        assert trace.reward == 0.375
    assert _qa(trace)["arms"]["ptc"]["reports"] == 1
    assert policy.receipt_at == [2]
    row, = _rows(config)
    assert row["traces"][0]["info"][QA_KEY] == _qa(trace)
    assert row["traces"][0]["ok"] is (not fail_score)


def test_A_cancel_release_then_fresh_eval(monkeypatch, framework):
    state = framework
    config, module = _config(monkeypatch, state, label="cancel")
    async def scenario():
        entered = asyncio.Event()
        async def blocked(n):
            if n == 2:
                entered.set()
                await asyncio.Event().wait()
        state.policy = _policy("cancelled", on_call=blocked)
        running = asyncio.create_task(_api().run_ptc_qa_eval(config))
        try:
            await asyncio.wait_for(entered.wait(), 10)
            assert len(state.channels) == 1
        finally:
            running.cancel()
            with pytest.raises(asyncio.CancelledError):
                await running
        for agent, original in state.agents:
            assert agent.harness is original
            assert getattr(agent, activation._OWNER_ATTR, None) is None
        assert _api()._admission.get() is activation._ACTIVE.get() is None
        assert _rows(config) == []  # Raised without a returned Trace: no fabrication.
        fresh, fresh_module = _config(monkeypatch, state, label="fresh")
        state.policy = _policy("fresh")
        episode, = await _api().run_ptc_qa_eval(fresh)
        assert episode.ok and _qa(episode.traces[0])["arms"]["ptc"]["reports"] == 1
    _run(scenario())
    assert len(state.channels) == 2 and state.channels[0] is not state.channels[1]


def test_A_unbound_SDK_zero_policy_channels_no_fabrication(monkeypatch, framework):
    from verifiers.v1.cli.eval.runner import run_eval
    state = framework
    config, _ = _config(monkeypatch, state)
    state.policy = policy = _policy("must not execute")
    episode, = _run(run_eval(config))
    assert not episode.ok and episode.traces == []
    assert policy.calls == 0 and state.channels == []
    row, = _rows(config)
    assert row["traces"] == []


def test_A_no_channel_before_launch_no_attachment(monkeypatch, framework):
    state = framework
    config, module = _config(monkeypatch, state)
    state.policy = policy = _policy("must not run")
    async def refuse_setup(task, trace, runtime):
        raise RuntimeError("synthetic setup failure")
    monkeypatch.setattr(module.SeedTask, "setup", refuse_setup)
    episode, = _run(_api().run_ptc_qa_eval(config))
    trace, = episode.traces
    assert not episode.ok and not trace.ok
    assert policy.calls == 0 and state.channels == []
    assert QA_KEY not in trace.info
    assert QA_KEY not in _rows(config)[0]["traces"][0]["info"]


def test_A_private_real_scope_gate_seat_owner_and_revocation(monkeypatch, framework):
    """Negative probes inside actual Task.setup, before policy request 1."""
    from verifiers.v1.agent import Agent, _EpisodeAgent
    state = framework
    api = _api()
    config, module = _config(monkeypatch, state)
    state.policy = _policy("only-lane-0")
    original = module.SeedTask.setup
    held, checked = [], []

    async def setup(task, trace, runtime):
        scope = api._episode.get()
        agent = scope.agent
        assert type(agent) is _EpisodeAgent
        assert scope.gate is agent._gate is activation._ACTIVE.get().gate
        assert state.policy.calls == 0
        held.append(scope)
        with pytest.raises(ValueError):
            await activation.run_configured_ptc_qa(
                agent, task, qa_factory=lambda _: pytest.fail("public factory"))
        for field, replacement in (
            ("_gate", asyncio.Semaphore(1)), ("_completed", []),
            ("_shared_tools", {}), ("_task_cls", Task),
            ("_on_trace", lambda _: None), ("_on_discard", lambda _: None),
            ("interception", object()),
        ):
            value = getattr(agent, field)
            setattr(agent, field, replacement)
            try:
                with pytest.raises(ValueError):
                    api._current_episode(agent, task)
                checked.append(field)
            finally:
                setattr(agent, field, value)
        value = scope.agents._agents["agent"]
        scope.agents._agents["agent"] = Agent(agent.config)
        try:
            with pytest.raises(ValueError):
                api._current_episode(agent, task)
        finally:
            scope.agents._agents["agent"] = value
        scope.active = False
        try:
            with pytest.raises(ValueError):
                api._current_episode(agent, task)
        finally:
            scope.active = True
        owner = scope.owner
        owner.env = object()
        try:
            with pytest.raises(ValueError):
                api._current_episode(agent, task)
        finally:
            owner.env = scope.env
        await original(task, trace, runtime)

    from verifiers.v1.task import Task
    monkeypatch.setattr(module.SeedTask, "setup", setup)
    episodes = _run(api.run_ptc_qa_eval(config))
    _proof(state, config, module, episodes, [state.policy])
    assert len(checked) == 7 and len(held) == 1
    assert held[0].active is False and held[0].owner.active is False
    with pytest.raises(ValueError):
        held[0].check(held[0].agent, held[0].task)


def test_A_real_quota_9_reports_retains_8_original_writer(monkeypatch, framework):
    state = framework
    config, _ = _config(monkeypatch, state)
    state.policy = policy = ScriptedClient([
        _program_call("for i in range(8):\n print(report_defect(kind='other', detail='accepted'))"),
        _report_program("ninth"),
        _text_step("done"),
    ])
    episode, = _run(_api().run_ptc_qa_eval(config))
    trace, = episode.traces
    assert episode.ok and trace.ok
    doc = _qa(trace)
    assert doc["arms"]["ptc"]["reports"] == 8
    assert len(state.channels[0].export()) <= 65536
    assert "report limit reached" in str(policy.bodies[2])
    assert _rows(config)[0]["traces"][0]["info"][QA_KEY] == doc


@pytest.mark.parametrize("mode", ["collision", "export", "attachment"])
def test_A_real_metadata_failure_loud_no_false_reward(monkeypatch, framework, mode):
    state = framework
    api = _api()
    config, module = _config(monkeypatch, state)
    state.policy = _policy("kept")
    if mode == "collision":
        original = module.SeedTask.score
        async def score(task, trace, runtime=None):
            await original(task, trace, runtime)
            trace.info[QA_KEY] = {"original": "never overwritten"}
        monkeypatch.setattr(module.SeedTask, "score", score)
    elif mode == "export":
        def fail(channel):
            raise RuntimeError("synthetic export failure")
        monkeypatch.setattr(QaChannel, "export", fail)
    else:
        # Product attachment seam, not the SDK writer or scoring lifecycle.
        def fail(trace, channel):
            raise RuntimeError("synthetic attachment failure")
        monkeypatch.setattr(api, "_attach_qa", fail)
    episode, = _run(api.run_ptc_qa_eval(config))
    trace, = episode.traces
    assert not episode.ok and trace.ok and trace.reward == 0.375
    if mode == "collision":
        assert trace.info[QA_KEY] == {"original": "never overwritten"}
        assert "collision" in str(episode.errors)
    else:
        assert QA_KEY not in trace.info
        assert "synthetic" in str(episode.errors)
    row, = _rows(config)
    assert row["ok"] is False
    assert row["traces"][0]["rewards"] == trace.model_dump(mode="json")["rewards"]


async def _followup01_probe_refusal(monkeypatch, state, config, policy):
    """Observe real SDK delegation/resources, never substitute the evaluator."""
    from pathlib import Path
    api = _api()
    evaluator, discover, factory = (
        api.run_eval, api.taskset_class, activation._Record._call_factory,
    )
    calls = {"eval": [], "discovery": [], "factory": []}
    before = (
        len(state.servers), len(state.runtimes), len(state.agents),
        len(state.channels), policy.calls,
    )

    async def observe_eval(exact):
        calls["eval"].append(exact)
        return await evaluator(exact)

    def observe_discovery(ident):
        calls["discovery"].append(ident)
        return discover(ident)

    def observe_factory(record, data):
        calls["factory"].append(data)
        return factory(record, data)

    with monkeypatch.context() as scoped:
        scoped.setattr(api, "run_eval", observe_eval)
        scoped.setattr(api, "taskset_class", observe_discovery)
        scoped.setattr(activation._Record, "_call_factory", observe_factory)
        try:
            await api.run_ptc_qa_eval(config)
        except ValueError:
            refused = True
        else:
            refused = False
    after = (
        len(state.servers), len(state.runtimes), len(state.agents),
        len(state.channels), policy.calls,
    )
    return {
        "refused": refused, "calls": calls, "unchanged": before == after,
        "output_absent": not Path(config.output_dir).exists(),
    }


def _followup01_assert_refused(probe):
    assert probe == {
        "refused": True,
        "calls": {"eval": [], "discovery": [], "factory": []},
        "unchanged": True, "output_absent": True,
    }, "followup01: inherited activation must refuse before discovery/eval/resources"


@pytest.mark.parametrize("context_state", ["active", "revoked"])
def test_followup01_standalone_context_zero_eval_starts(
        monkeypatch, framework, context_state):
    from contextvars import copy_context
    from verifiers.v1.task import Task, TaskData
    from ptc.test_ptc_qa_activation_integration import _server_agent, _factory
    state = framework
    nested, _ = _config(monkeypatch, state, label="nested-standalone")
    state.policy = policy = _policy("standalone")
    captures, probes, factory_calls, channels = [], [], [], []

    class CallbackTask(Task):
        async def setup(self, trace, runtime):
            assert activation._ACTIVE.get().active is True
            captures.append(copy_context())
            if context_state == "active":
                probes.append(await _followup01_probe_refusal(
                    monkeypatch, state, nested, policy))
            await super().setup(trace, runtime)

    async def scenario():
        server, agent = _server_agent(state, policy)
        async with server:
            trace = await activation.run_configured_ptc_qa(
                agent, CallbackTask(TaskData(prompt="standalone callback")),
                qa_factory=_factory(factory_calls, channels))
        assert trace.ok and policy.calls == 2 and len(factory_calls) == 1
        assert activation._ACTIVE.get() is None
        if context_state == "revoked":
            assert captures[0].get(activation._ACTIVE).active is False
            # Actual context propagation into a child task after revocation.
            probes.append(await asyncio.create_task(
                _followup01_probe_refusal(monkeypatch, state, nested, policy),
                context=captures[0]))
        assert len(probes) == 1
        _followup01_assert_refused(probes[0])
        assert policy.calls == 2 and len(factory_calls) == 1
        clean, _ = _config(monkeypatch, state, label="clean-standalone")
        state.policy = _policy("clean")
        episode, = await _api().run_ptc_qa_eval(clean)
        assert episode.ok and _qa(episode.traces[0])["arms"]["ptc"]["reports"] == 1
        assert state.policy.calls == 2 and len(state.channels) == 2
    _run(scenario())


@pytest.mark.parametrize("context_state", ["active", "revoked"])
def test_followup01_eval_context_zero_nested_starts(
        monkeypatch, framework, context_state):
    from contextvars import copy_context
    state = framework
    outer, module = _config(monkeypatch, state, label="outer-eval")
    nested, _ = _config(monkeypatch, state, label="nested-eval")
    state.config = outer
    state.policy = policy = _policy("outer")
    original = module.SeedTask.setup
    captures, probes = [], []

    async def setup(task, trace, runtime):
        assert _api()._admission.get().active is True
        captures.append(copy_context())
        if context_state == "active":
            probes.append(await _followup01_probe_refusal(
                monkeypatch, state, nested, policy))
        await original(task, trace, runtime)

    monkeypatch.setattr(module.SeedTask, "setup", setup)

    async def scenario():
        episode, = await _api().run_ptc_qa_eval(outer)
        assert episode.ok and policy.calls == 2
        assert _api()._admission.get() is activation._ACTIVE.get() is None
        if context_state == "revoked":
            assert captures[0].get(_api()._admission).active is False
            probes.append(await asyncio.create_task(
                _followup01_probe_refusal(monkeypatch, state, nested, policy),
                context=captures[0]))
        assert len(probes) == 1
        _followup01_assert_refused(probes[0])
        assert policy.calls == 2 and len(state.channels) == 1
        clean, _ = _config(monkeypatch, state, label="clean-eval")
        state.policy = _policy("clean")
        episode, = await _api().run_ptc_qa_eval(clean)
        assert episode.ok and state.policy.calls == 2 and len(state.channels) == 2
    _run(scenario())
