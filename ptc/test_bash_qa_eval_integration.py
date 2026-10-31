"""Actual SDK evaluation, episode agents, Bash child/tool gate and JSONL.

No replacement evaluation loop, loader, Agent.run, Env.run, configured runner,
QA rewrite, attachment or writer. On-disk synthetic Taskset plugins use the
real loaders. Seams: delegated interception construction with preseeded scripted
clients; existing ownership-filtered ScratchRuntime/cache/transport drain;
delegated Agent/QaChannel constructors record real objects without replacing
their classes. Parent socket/DNS guard blocks/counts external attempts. Child
executes the real bundled program against the owned loopback endpoint, not a
parent HTTP mock. Fixture transport draining is not a product SDK reaping claim.
"""
from __future__ import annotations

import asyncio
import importlib
import ipaddress
import json
import os
from pathlib import Path
import socket
from types import SimpleNamespace
import uuid

import pytest

from verifiers.v1 import env as env_mod
from verifiers.v1.agent import Agent
from verifiers.v1.clients.client import Client
from verifiers.v1.configs.cli.eval import EvalConfig
from verifiers.v1.interception.server import InterceptionServer

from cotrain_bash_qa_env import run_bash_qa_eval
from ptc.sql_qa import MAX_EXPORT_BYTES, QaChannel, REPORT_TOOL
from ptc.test_bash_qa import _trace
from ptc.test_bash_qa_activation_integration import (
    ScriptedClient, _bash_call, _report_call, _text_step,
)
from ptc.test_bash_qa_integration import _patch_runtimes

pytestmark = pytest.mark.filterwarnings(
    "error::pytest.PytestUnraisableExceptionWarning"
)
QA_KEY = "cotrain_bash_qa"

_SOURCE = '''
from typing import Literal
from verifiers.v1.configs.taskset import TasksetConfig
from verifiers.v1.task import Task, TaskData
from verifiers.v1.taskset import Taskset
from ptc.bash_qa import BashQaTaskMixin

__all__ = ["FixtureTaskset"]
seeds, builds, events = [], [], []

class SeedTask(Task):
    def __init__(self, data, config, *, state):
        super().__init__(data, config)
        self.state = state

    __BUILDER__

    async def setup(self, trace, runtime):
        events.append(("setup", self))
        await super().setup(trace, runtime)

    async def finalize(self, trace, runtime):
        events.append(("finalize", self))
        await super().finalize(trace, runtime)

    async def score(self, trace, runtime=None):
        events.append(("score", self))
        if self.state["fail_score"]:
            raise ValueError("synthetic scoring failure")
        trace.record_reward("fixture", self.state["bias"])
        trace.record_metric("fixture_score", 1.0)

class PairedTask(BashQaTaskMixin, SeedTask):
    pass

class Config(TasksetConfig):
    id: Literal["__PLUGIN__"] = "__PLUGIN__"
    count: int = 1
    fail_score: bool = False

class FixtureTaskset(Taskset[SeedTask, Config]):
    def load(self):
        for i in range(self.config.count):
            task = SeedTask(TaskData(prompt=f"synthetic lane-{i}"),
                            self.config.task,
                            state={"lane": i, "bias": 0.375,
                                   "fail_score": self.config.fail_score})
            seeds.append(task)
            yield task
'''
_BUILDER = '''def build_bash_qa_task(self, binding):
        paired = PairedTask(self.data, self.config, state=dict(self.state),
                            qa_binding=binding)
        builds.append((self, paired, binding))
        return paired'''


class RoutingClient(Client):
    """Separate per-lane policies, selected from the actual opening prompt."""

    def __init__(self, clients):
        self.clients = clients

    async def get_response(self, dialect, body, sampling, session_id=None,
                           turn=None, headers=None):
        opening, = [
            message for message in body["messages"]
            if message["role"] == "user"
        ]
        matches = [
            client for label, client in self.clients.items()
            if label in str(opening["content"])
        ]
        assert len(matches) == 1, "synthetic policy lane not uniquely routed"
        return await matches[0].get_response(
            dialect, body, sampling, session_id=session_id,
            turn=turn, headers=headers,
        )


@pytest.fixture
def framework(monkeypatch, tmp_path):
    state = SimpleNamespace(
        root=tmp_path, config=None, policy=None, servers=[], runtimes=[],
        agents=[], channels=[], modules=[], external=[],
    )
    host_path = os.environ.get("PATH")
    _patch_runtimes(monkeypatch, tmp_path / "runtimes", state.runtimes)
    original_make = env_mod.make_interception
    agent_init, channel_init = Agent.__init__, QaChannel.__init__
    connect, connect_ex, resolve = (
        socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo,
    )

    def seeded(config, *, requires_tunnel, state_service_secrets=()):
        assert requires_tunnel is False
        server = original_make(
            config, requires_tunnel=requires_tunnel,
            state_service_secrets=state_service_secrets,
        )
        assert type(server) is InterceptionServer and server.tunnel is None
        assert state.policy is not None
        server.clients[state.config.client.model_dump_json()] = state.policy
        state.servers.append(server)
        return server

    def observe_agent(self, *args, **kwargs):
        agent_init(self, *args, **kwargs)
        if type(self).__name__ == "_EpisodeAgent":
            state.agents.append((self, self.harness))

    def observe_channel(self, *args, **kwargs):
        channel_init(self, *args, **kwargs)
        state.channels.append(self)

    def local(host):
        if host is None or host == "localhost":
            return True
        try:
            if isinstance(host, bytes):
                host = host.decode("ascii")
            return ipaddress.ip_address(host).is_loopback
        except (ValueError, UnicodeError):
            return False

    def check(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not local(address[0]):
            state.external.append("connect")
            raise AssertionError("external fixture connection forbidden")

    def guarded_connect(sock, address):
        check(sock, address)
        return connect(sock, address)

    def guarded_connect_ex(sock, address):
        check(sock, address)
        return connect_ex(sock, address)

    def guarded_resolve(host, *args, **kwargs):
        if not local(host):
            state.external.append("DNS")
            raise AssertionError("external fixture DNS forbidden")
        return resolve(host, *args, **kwargs)

    monkeypatch.setattr(env_mod, "make_interception", seeded)
    monkeypatch.setattr(Agent, "__init__", observe_agent)
    monkeypatch.setattr(QaChannel, "__init__", observe_channel)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_resolve)
    yield state
    assert state.external == []
    assert os.environ.get("PATH") == host_path
    assert list(tmp_path.rglob(REPORT_TOOL)) == []
    for server in state.servers:
        assert server.sessions == server.state_sessions == {}
    for runtime in state.runtimes:
        assert "PATH" not in runtime.env
        assert runtime._owned_foreground == []
    for agent, original in state.agents:
        assert agent.harness is original
    for module in state.modules:
        for seed, paired, binding in module.builds:
            assert binding._routes == {}
            assert paired._qa_binding is binding
            assert not any(isinstance(v, QaChannel) for v in vars(seed).values())


def _config(monkeypatch, state, *, count=1, concurrent=1, fail_score=False,
            missing_builder=False, system_prompt=None, label="run"):
    name = "qa_eval_fixture_" + uuid.uuid4().hex
    source = _SOURCE.replace("__PLUGIN__", name).replace(
        "__BUILDER__", "pass" if missing_builder else _BUILDER,
    )
    (state.root / f"{name}.py").write_text(source)
    monkeypatch.syspath_prepend(str(state.root))
    taskset = {"id": name, "count": count, "fail_score": fail_score}
    if system_prompt is not None:
        taskset["system_prompt"] = str(system_prompt)
    cfg = EvalConfig.model_validate_json(json.dumps({
        "model": "fixture-model",
        "client": {"type": "train", "api_key_var": "PROBE_UNUSED_API_KEY"},
        "env": {
            "id": "cotrain_bash_qa_env", "taskset": taskset,
            "interception": {"type": "server"},
            "agent": {
                "harness": {"id": "cotrain_bash_qa", "edit": False, "search": False},
                "runtime": {"type": "subprocess"}, "max_turns": 4,
                "timeout": {"rollout": 15.0, "finalize": 5.0, "scoring": 5.0},
                "retries": {"max_retries": 0},
            },
            "retries": {"max_retries": 0},
        },
        "num_tasks": count, "num_rollouts": 1, "max_concurrent": concurrent,
        "push": False, "resume": False, "clean": False, "rich": None,
        "output_dir": str(state.root / label), "run": {"dir": "run"},
    }))
    state.config = cfg
    module = importlib.import_module(name)
    state.modules.append(module)
    return cfg, module


def _policy(detail, *, on_call=None, ordinary_action=False):
    steps = [_report_call({"kind": "other", "detail": detail})]
    if ordinary_action:
        steps.append(_bash_call("printf 'after-report\\n'"))
    steps.append(_text_step("done"))
    return ScriptedClient(steps, on_call=on_call)


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, 20.0))


def _rows(config):
    files = list(Path(config.output_dir).rglob("*.jsonl"))
    assert len(files) == 1, "actual SDK episode writer must produce one JSONL"
    return [json.loads(line) for line in files[0].read_text().splitlines()]


def _qa(trace):
    assert QA_KEY in trace.info, "QA telemetry missing from actual SDK Trace"
    return trace.info[QA_KEY]


def _check_pairing(module):
    for seed, paired, binding in module.builds:
        assert isinstance(paired, type(seed))
        assert paired.data is seed.data and paired.config is seed.config
        assert paired.state == seed.state and paired.state is not seed.state
        assert paired._qa_binding is binding


def test_real_eval_receipt_and_persisted_telemetry(monkeypatch, framework):
    state = framework
    config, module = _config(monkeypatch, state)
    state.policy = policy = _policy("episode-lane-0", ordinary_action=True)
    episode, = _run(run_bash_qa_eval(config))
    assert episode.ok, f"evaluation activation failed: {episode.errors}"
    trace, = episode.traces
    assert trace.ok, f"evaluation activation failed: {trace.last_error}"
    assert len(state.channels) == len(module.builds) == 1, (
        "evaluation activation requires one fresh channel and pairing"
    )
    assert policy.calls == 3
    assert policy.receipt_at == [2], "receipt missing before next policy action"
    assert policy.bodies[1]["messages"][-1]["tool_call_id"] == "call_report"
    doc = _qa(trace)
    channel, = state.channels
    assert doc == json.loads(channel.export())
    assert doc["arms"]["bash"]["reports"] == 1
    event, = doc["arms"]["bash"]["events"]
    assert event["provenance"] == "agent_output"
    assert event["detail"] == "episode-lane-0"
    assert len(channel.export()) <= MAX_EXPORT_BYTES
    row, = _rows(config)
    assert row["ok"] and row["traces"][0]["info"][QA_KEY] == doc
    seed, paired, _ = module.builds[0]
    assert trace.task.data is seed.data
    assert row["task"]["hash"] == row["traces"][0]["task"]["hash"] == seed.hash
    assert trace.reward == 0.375 and trace.metrics["fixture_score"] == 1.0
    assert [kind for kind, task in module.events if task is paired] == [
        "setup", "finalize", "score",
    ]
    assert len(state.agents) == len(state.runtimes) == len(state.servers) == 1
    _check_pairing(module)


def test_two_sequential_episodes_keep_channels_separate(monkeypatch, framework):
    state = framework
    config, module = _config(monkeypatch, state, count=2)
    clients = {f"lane-{i}": _policy(f"only-lane-{i}") for i in range(2)}
    state.policy = RoutingClient(clients)
    episodes = _run(run_bash_qa_eval(config))
    assert len(episodes) == 2 and all(episode.ok for episode in episodes)
    assert len(state.channels) == len(module.builds) == len(state.agents) == 2
    assert state.channels[0] is not state.channels[1]
    assert module.builds[0][2] is not module.builds[1][2]
    assert state.agents[0][0] is not state.agents[1][0]
    for episode in episodes:
        lane = episode.task.data.prompt.rsplit(" ", 1)[-1]
        event, = _qa(episode.traces[0])["arms"]["bash"]["events"]
        assert event["detail"] == "only-" + lane
    rows = _rows(config)
    assert len(rows) == 2
    assert [row["traces"][0]["info"][QA_KEY] for row in rows] == [
        _qa(episode.traces[0]) for episode in episodes
    ]
    assert all(client.receipt_at == [2] for client in clients.values())
    assert [kind for kind, _ in module.events] == [
        "setup", "finalize", "score",
    ] * 2
    _check_pairing(module)


def test_two_real_episodes_overlap_without_path_or_report_leak(monkeypatch, framework):
    state = framework
    config, module = _config(monkeypatch, state, count=2, concurrent=2)
    host_path = os.environ.get("PATH")

    async def scenario():
        arrived, snapshot = set(), []
        release = asyncio.Event()

        def barrier(label):
            async def on_call(n):
                if n == 2:
                    arrived.add(label)
                    if len(arrived) == 2:
                        snapshot.extend(rt.env["PATH"] for rt in state.runtimes)
                        assert os.environ.get("PATH") == host_path
                        release.set()
                    await asyncio.wait_for(release.wait(), 10.0)
            return on_call

        clients = {
            f"lane-{i}": _policy(f"only-lane-{i}", on_call=barrier(f"lane-{i}"))
            for i in range(2)
        }
        state.policy = RoutingClient(clients)
        episodes = await run_bash_qa_eval(config)
        assert arrived == {"lane-0", "lane-1"}
        assert len(snapshot) == 2
        assert len({path.split(os.pathsep)[0] for path in snapshot}) == 2
        return episodes

    episodes = _run(scenario())
    assert len(episodes) == len(state.channels) == len(module.builds) == 2
    assert all(episode.ok for episode in episodes)
    assert state.channels[0] is not state.channels[1]
    assert module.builds[0][2] is not module.builds[1][2]
    assert state.agents[0][0] is not state.agents[1][0]
    for episode in episodes:
        lane = episode.task.data.prompt.rsplit(" ", 1)[-1]
        doc = _qa(episode.traces[0])
        assert doc["arms"]["bash"]["reports"] == 1
        assert doc["arms"]["bash"]["events"][0]["detail"] == "only-" + lane
    rows = _rows(config)
    assert len(rows) == 2
    assert {row["task"]["hash"] for row in rows} == {
        episode.task.hash for episode in episodes
    }
    assert {
        row["task"]["hash"]: row["traces"][0]["info"][QA_KEY] for row in rows
    } == {
        episode.task.hash: _qa(episode.traces[0]) for episode in episodes
    }
    _check_pairing(module)


def test_actual_system_prompt_clone_preserves_custom_score(monkeypatch, framework):
    state = framework
    prompt_file = state.root / "synthetic-system.txt"
    prompt_file.write_text("Synthetic system-prompt override.")
    config, module = _config(monkeypatch, state, system_prompt=prompt_file)
    state.policy = policy = _policy("clone-report")

    async def scenario():
        episode, = await run_bash_qa_eval(config)
        assert episode.ok
        seed, paired, _ = module.builds[0]
        baseline = _trace(seed, state.agents[0][0])
        await seed.score(baseline)
        assert baseline.reward == episode.traces[0].reward == 0.375
        assert baseline.metrics == episode.traces[0].metrics
        return episode

    episode = _run(scenario())
    original, = module.seeds
    seed, paired, _ = module.builds[0]
    assert seed is not original and seed.data is not original.data
    assert original.data.system_prompt is None
    assert seed.data.system_prompt == prompt_file.read_text()
    assert paired.data.system_prompt == seed.data.system_prompt
    assert paired.config is original.config
    assert "Synthetic system-prompt override." in str(policy.bodies[0]["messages"])
    row, = _rows(config)
    assert row["task"]["hash"] == row["traces"][0]["task"]["hash"] == seed.hash
    assert row["traces"][0]["info"][QA_KEY] == _qa(episode.traces[0])
    _check_pairing(module)


def test_failed_scoring_trace_persists_actual_report(monkeypatch, framework):
    state = framework
    config, module = _config(monkeypatch, state, fail_score=True)
    state.policy = policy = _policy("failed-after-report")
    episode, = _run(run_bash_qa_eval(config))
    assert not episode.ok
    trace, = episode.traces
    assert not trace.ok and "synthetic scoring failure" in str(trace.last_error)
    assert policy.receipt_at == [2]
    assert len(state.channels) == 1
    assert _qa(trace) == json.loads(state.channels[0].export())
    assert _qa(trace)["arms"]["bash"]["events"][0]["detail"] == "failed-after-report"
    row, = _rows(config)
    assert not row["ok"] and not row["traces"][0]["ok"]
    assert row["traces"][0]["info"][QA_KEY] == _qa(trace)
    _check_pairing(module)


@pytest.mark.parametrize("direct_sdk", [False, True])
def test_prelaunch_refusal_has_no_fabricated_qa(monkeypatch, framework, direct_sdk):
    state = framework
    config, module = _config(monkeypatch, state, missing_builder=not direct_sdk)
    state.policy = policy = ScriptedClient([_text_step("must not run")])
    if direct_sdk:
        from verifiers.v1.cli.eval.runner import run_eval
        episode, = _run(run_eval(config))
        reason = "requires an active run_bash_qa_eval"
    else:
        episode, = _run(run_bash_qa_eval(config))
        reason = "build_bash_qa_task must be callable"
    assert not episode.ok and reason in str(episode.errors)
    assert episode.traces == [] and module.builds == []
    assert policy.calls == 0 and state.channels == state.runtimes == []
    row, = _rows(config)
    assert not row["ok"] and row["traces"] == []


def test_actual_cancellation_revokes_then_fresh_eval_succeeds(monkeypatch, framework):
    state = framework
    config, module = _config(monkeypatch, state, label="cancelled")

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def blocked(n):
            if n == 2:
                entered.set()
                await asyncio.wait_for(release.wait(), 10.0)

        first = _policy("cancelled-report", on_call=blocked)
        state.policy = first
        running = asyncio.create_task(run_bash_qa_eval(config))
        try:
            await asyncio.wait_for(entered.wait(), 10.0)
            assert not running.done() and len(state.channels) == 1
            assert json.loads(state.channels[0].export())["arms"]["bash"]["reports"] == 1
            assert running.cancel()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await running
        finally:
            release.set()
            if not running.done():
                running.cancel()
                try:
                    await running
                except asyncio.CancelledError:
                    pass
        for agent, original in state.agents:
            assert agent.harness is original
        assert module.builds[0][2]._routes == {}
        retry_config, retry_module = _config(monkeypatch, state, label="retry")
        state.policy = retry = _policy("after-cancellation")
        episode, = await run_bash_qa_eval(retry_config)
        assert episode.ok and retry.receipt_at == [2]
        row, = _rows(retry_config)
        assert row["traces"][0]["info"][QA_KEY] == _qa(episode.traces[0])
        _check_pairing(retry_module)
        return first, episode

    first, episode = _run(scenario())
    assert first.calls == 2
    assert first.receipt_at == [2]
    assert len(state.channels) == len(state.runtimes) == len(state.agents) == 2
    assert state.channels[0] is not state.channels[1]
    assert _qa(episode.traces[0])["arms"]["bash"]["events"][0]["detail"] == "after-cancellation"
    for channel in state.channels:
        with pytest.raises(ValueError):
            channel._claim_launch()
