"""Configured-activation integration tests for `cotrain_ptc_qa.py`.

Real end-to-end: canonical `AgentConfig` JSON -> real SDK harness resolution ->
`Agent` holding an UNBOUND `ReportingPTCHarness` -> `run_configured_ptc_qa`
claims the Agent, binds the reporting harness for ONE real
`agent.run(original_task)` and restores the exact original afterwards. The PTC
loop is in-process: real `PTCHarness.launch`, real SSE against the owned
loopback `InterceptionServer`, a real `QaChannel` through the injected
`report_defect` catalog callback. No Bash child is spawned or claimed. The only
"model" is an in-process scripted `vf.Client`; zero external calls, zero
JSONL/Env/persistence claims for this configured-only increment.

Fixture seams (reused unchanged from the eval-integration fixture): `framework`
supplies the parent socket/DNS guard counting external attempts, the actual
`ScratchRuntime` source-cache/owned-transport drain, and
`state.servers`/`state.agents`/`state.channels` recording — it records only
`_EpisodeAgent`s, so this file appends `(agent, original)` itself.
`server.clients[client.model_dump_json()] = scripted` pre-seeds the owned
client slot so `resolve_client`/`resolve_api_key` never run.

ZERO fixture/caller `agent.harness` assignments: the product runner alone
binds. The reference probe's manual binding is a SHORTCUT, absent here.

Planned controls (each turns exactly its labelled assertion RED):
- Suppress `_bind_harness` -> "PTC activation" call-phase; restored GREEN.
- `QaChannel.submit` no-op keeping ack -> "PTC collector"; restored GREEN.
- Wrong `report_ack` text after real submit -> "PTC receipt"; restored GREEN.
"""
from __future__ import annotations

import asyncio
import json

import pytest

pytestmark = pytest.mark.filterwarnings(
    "error::pytest.PytestUnraisableExceptionWarning"
)

from verifiers.v1.agent import Agent
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.errors import RolloutError
from verifiers.v1.interception.server import InterceptionServer
from verifiers.v1.task import Task, TaskData

from cotrain_ptc_qa import (
    ReportingPTCConfig,
    ReportingPTCHarness,
    run_configured_ptc_qa,
)
from ptc.sql_qa import QaChannel, REPORT_PROMPT, report_ack
from ptc.test_bash_qa_activation_integration import ScriptedClient, _text_step
from ptc.test_bash_qa_eval_integration import framework  # noqa: F401

MODEL = "fixture-model"
OUTER_TIMEOUT_S = 20.0
WAIT_S = 10.0
ACK = report_ack()


def _program_call(code: str, call_id: str = "call_program") -> dict:
    """One generic ScriptedClient step: a `run_program` tool call."""
    return {"call_id": call_id, "name": "run_program",
            "arguments": {"code": code}}


def _report_program(detail: str, kind: str = "other") -> dict:
    """Files one allegation and PRINTS the receipt — printing is required for
    the ack to reach the next observation."""
    return _program_call(
        f"print(report_defect(kind={kind!r}, detail={detail!r}))",
        "call_report")


def _agent_json(lane: str = "") -> dict:
    """Canonical AgentConfig JSON; `cotrain_ptc_qa` resolves to an UNBOUND
    ReportingPTCHarness — the runner, not this fixture, performs activation."""
    client = {"type": "train", "api_key_var": "PROBE_UNUSED_API_KEY"}
    if lane:
        client["headers"] = {"x-probe-lane": lane}
    return json.loads(json.dumps({
        "model": MODEL,
        "client": client,
        "harness": {"id": "cotrain_ptc_qa", "max_turns": 4,
                    "program_timeout": 2.0},
        "runtime": {"type": "subprocess"},
        "max_turns": 4,
        "retries": {"max_retries": 0},
        "timeout": {"setup": 5.0, "rollout": 15.0, "finalize": 5.0,
                    "scoring": 5.0},
    }))


def _configured_agent(server: InterceptionServer, scripted: ScriptedClient,
                      *, lane: str = "") -> Agent:
    """JSON -> SDK narrowing -> Agent with an unbound harness built by
    `load_harness`; preseeds the server-owned client slot."""
    config = AgentConfig.model_validate_json(json.dumps(_agent_json(lane)))
    server.clients[config.client.model_dump_json()] = scripted
    agent = Agent(config, interception=server)
    assert type(agent.harness) is ReportingPTCHarness
    assert type(agent.harness.config) is ReportingPTCConfig
    return agent


def _server_agent(state, scripted, *, lane: str = ""):
    """Fresh owned server + configured Agent; registers both with the shared
    fixture teardown (`state.agents` records the original harness)."""
    server = InterceptionServer()
    state.servers.append(server)
    agent = _configured_agent(server, scripted, lane=lane)
    state.agents.append((agent, agent.harness))
    return server, agent


def _factory(factory_calls: list, channels: list):
    """The caller `qa_factory`: one fresh caller-owned channel per launch."""
    def factory(data: TaskData) -> QaChannel:
        factory_calls.append(data)
        channel = QaChannel()
        channels.append(channel)
        return channel
    return factory


def _export(channel: QaChannel) -> dict:
    return json.loads(channel.export())


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, OUTER_TIMEOUT_S))


async def _configured_run(agent, task, factory):
    """Converts ONLY the admission vocabulary (ValueError/TypeError) into a
    labelled 'PTC activation' assertion, so a planned control surfaces as an
    intended call-phase failure rather than an unhandled error."""
    try:
        return await run_configured_ptc_qa(agent, task, qa_factory=factory)
    except (ValueError, TypeError) as exc:
        raise AssertionError(
            f"PTC activation refused the real pairing: {exc!r}")


class ProbedTask(Task):
    """Ordinary Task subclass: no mixin, no builder — the runner takes the
    original instance unchanged and its own setup/finalize/scoring run."""

    def __init__(self, data: TaskData, *, state: dict) -> None:
        super().__init__(data)
        self.state = state
        self.events: list = []

    async def setup(self, trace, runtime):
        self.state["receivers"].append(self)
        self.events.append("setup")
        await super().setup(trace, runtime)

    async def finalize(self, trace, runtime):
        self.state["receivers"].append(self)
        self.events.append("finalize")
        await super().finalize(trace, runtime)

    async def score(self, trace, runtime=None):
        self.state["receivers"].append(self)
        self.events.append("score")
        trace.record_reward("fixture", self.state["bias"])
        trace.record_metric("fixture_score", 1.0)


def test_real_configured_ptc_report_and_receipt(framework):
    """1 real catalog_callback report; the fixed receipt is visible in the
    request preceding the next model action; exact original harness, Agent
    config, turn limit and timeouts restored."""
    state = framework
    factory_calls: list = []
    channels: list = []
    scripted = ScriptedClient([
        _report_program("own"),
        _program_call("print('ordinary step')"),
        _text_step("done"),
    ])
    task = Task(TaskData(prompt="Report once."))

    async def scenario():
        server, agent = _server_agent(state, scripted)
        original = agent.harness
        agent_dump = agent.config.model_dump(mode="json")
        harness_dump = original.config.model_dump(mode="json")
        turns = agent.limits.max_turns
        async with server:
            assert server.tunnel is None
            assert server.base_url.startswith("http://127.0.0.1:")
            trace = await _configured_run(
                agent, task, _factory(factory_calls, channels))
        assert agent.harness is original
        assert agent.config.model_dump(mode="json") == agent_dump
        assert agent.harness.config.model_dump(mode="json") == harness_dump
        assert agent.limits.max_turns == turns
        return trace

    trace = _run(scenario())

    assert trace.ok, f"PTC activation: {trace.last_error}"
    assert trace.num_turns == 3
    assert factory_calls == [task.data] and factory_calls[0] is task.data
    assert trace.task.data is task.data and trace.task.hash == task.hash

    channel, = channels
    assert state.channels == channels, (
        "factory/caller retains the channels; nothing else may create one")
    arm = _export(channel)["arms"]["ptc"]
    assert arm["reports"] == 1, f"PTC collector: {arm}"
    event, = arm["events"]
    assert event["type"] == "report"
    assert event["provenance"] == "catalog_callback"
    assert event["kind"] == "other" and event["detail"] == "own", (
        f"PTC collector: {event}")

    assert scripted.calls == 3
    assert scripted.receipt_at == [2], (
        "PTC receipt: ack must precede the next model action")
    tail = scripted.bodies[1]["messages"][-1]
    assert tail["role"] == "tool" and tail["tool_call_id"] == "call_report"
    assert ACK in str(tail.get("content") or "")
    system = scripted.bodies[0]["messages"][0]
    assert system["role"] == "system"
    assert REPORT_PROMPT in str(system.get("content") or "")
    assert "report_defect" in str(system.get("content") or "")

    # The bound launch consumed the channel's one-shot claim; the caller owns
    # it outright afterwards (spent channels stay spent).
    with pytest.raises(ValueError):
        channel._claim_launch()


def test_two_sequential_configured_runs_same_agent(framework):
    """Two sequential configured runs on ONE Agent: unbound harness restored
    each time, two fresh caller-owned channels with own details only."""
    state = framework
    scripted_a = ScriptedClient([
        _report_program("run-one"), _text_step("done")])
    scripted_b = ScriptedClient([
        _report_program("run-two"), _text_step("done")])
    factory_calls: list = []
    channels: list = []

    async def scenario():
        server, agent = _server_agent(state, scripted_a)
        original = agent.harness
        async with server:
            trace_a = await _configured_run(
                agent, Task(TaskData(prompt="first.")),
                _factory(factory_calls, channels))
            assert agent.harness is original
            # Same canonical client key serves the second script.
            server.clients[agent.ctx.client.model_dump_json()] = scripted_b
            trace_b = await _configured_run(
                agent, Task(TaskData(prompt="second.")),
                _factory(factory_calls, channels))
            assert agent.harness is original
        return trace_a, trace_b

    trace_a, trace_b = _run(scenario())

    assert trace_a.ok and trace_b.ok
    assert len(channels) == len(factory_calls) == 2
    assert channels[0] is not channels[1]
    doc_a, doc_b = _export(channels[0]), _export(channels[1])
    assert doc_a["arms"]["ptc"]["reports"] == 1
    assert doc_b["arms"]["ptc"]["reports"] == 1
    assert doc_a["arms"]["ptc"]["events"][0]["detail"] == "run-one"
    assert doc_b["arms"]["ptc"]["events"][0]["detail"] == "run-two"
    assert all(e.get("detail") != "run-two"
               for e in doc_a["arms"]["ptc"]["events"])
    assert all(e.get("detail") != "run-one"
               for e in doc_b["arms"]["ptc"]["events"])
    assert scripted_a.receipt_at == [2] and scripted_b.receipt_at == [2]
    for channel in channels:
        with pytest.raises(ValueError):
            channel._claim_launch()


def test_two_agents_configured_overlap(framework):
    """Barrier-proven overlap of two distinct configured Agents with EQUAL
    prompts: routing is by the canonical client key (distinct headers), never
    the prompt; each channel carries its own report only."""
    state = framework
    channels_a: list = []
    channels_b: list = []
    factory_a: list = []
    factory_b: list = []
    client_a = ScriptedClient([_report_program("lane-a"), _text_step("done")])
    client_b = ScriptedClient([_report_program("lane-b"), _text_step("done")])

    async def scenario():
        first, second = asyncio.Event(), asyncio.Event()

        async def gate_a(_n: int) -> None:
            first.set()
            await asyncio.wait_for(second.wait(), WAIT_S)

        async def gate_b(_n: int) -> None:
            second.set()
            await asyncio.wait_for(first.wait(), WAIT_S)

        client_a.on_call = gate_a
        client_b.on_call = gate_b

        server = InterceptionServer()
        state.servers.append(server)
        agent_a = _configured_agent(server, client_a, lane="a")
        agent_b = _configured_agent(server, client_b, lane="b")
        original_a, original_b = agent_a.harness, agent_b.harness
        state.agents.extend((a, a.harness) for a in (agent_a, agent_b))
        async with server:
            assert server.base_url.startswith("http://127.0.0.1:")
            trace_a, trace_b = await asyncio.gather(
                _configured_run(
                    agent_a, Task(TaskData(prompt="same prompt.")),
                    _factory(factory_a, channels_a)),
                _configured_run(
                    agent_b, Task(TaskData(prompt="same prompt.")),
                    _factory(factory_b, channels_b)),
            )
        assert agent_a.harness is original_a
        assert agent_b.harness is original_b
        return trace_a, trace_b

    trace_a, trace_b = _run(scenario())

    assert trace_a.ok and trace_b.ok
    doc_a, doc_b = _export(channels_a[0]), _export(channels_b[0])
    assert doc_a["arms"]["ptc"]["reports"] == 1
    assert doc_b["arms"]["ptc"]["reports"] == 1
    assert doc_a["arms"]["ptc"]["events"][0]["detail"] == "lane-a"
    assert doc_b["arms"]["ptc"]["events"][0]["detail"] == "lane-b"
    assert all(e.get("detail") != "lane-b"
               for e in doc_a["arms"]["ptc"]["events"])
    assert all(e.get("detail") != "lane-a"
               for e in doc_b["arms"]["ptc"]["events"])
    assert client_a.receipt_at == [2] and client_b.receipt_at == [2]
    assert factory_a[0] is not factory_b[0]


def test_custom_task_preserves_setup_finalize_scoring(framework):
    """An original Task subclass instance is accepted unchanged: its own
    setup/finalize/score run, state and reward survive, factory receives the
    exact original TaskData."""
    state = framework
    factory_calls: list = []
    channels: list = []
    scripted = ScriptedClient([
        _report_program("custom"), _text_step("done")])
    receivers: list = []
    task = ProbedTask(
        TaskData(prompt="custom task."),
        state={"bias": 0.375, "receivers": receivers},
    )

    async def scenario():
        server, agent = _server_agent(state, scripted)
        async with server:
            return await _configured_run(
                agent, task, _factory(factory_calls, channels))

    trace = _run(scenario())
    assert trace.ok, f"PTC activation: {trace.last_error}"
    assert trace.task.type == "ProbedTask"
    assert trace.task.data is task.data
    assert task.events == ["setup", "finalize", "score"]
    assert len(receivers) == 3
    assert all(receiver is task for receiver in receivers), "PTC Task identity"
    assert trace.reward == 0.375
    assert trace.metrics["fixture_score"] == 1.0
    assert factory_calls == [task.data] and factory_calls[0] is task.data
    event, = _export(channels[0])["arms"]["ptc"]["events"]
    assert event["provenance"] == "catalog_callback"
    assert event["detail"] == "custom"


def test_accepted_report_survives_program_error(framework):
    """A report then a real program error in ONE program: the allegation stays
    recorded while the error — not the printed receipt — is the observation
    the model reads (declared asymmetry, never asserted as a receipt)."""
    state = framework
    channels: list = []
    scripted = ScriptedClient([
        _program_call(
            "print(report_defect(kind='task_defect', detail='kept'))\n1/0",
            "call_report"),
        _text_step("done"),
    ])

    async def scenario():
        server, agent = _server_agent(state, scripted)
        async with server:
            return await _configured_run(
                agent, Task(TaskData(prompt="report then fail.")),
                _factory([], channels))

    trace = _run(scenario())
    assert trace.ok, f"PTC activation: {trace.last_error}"
    channel, = channels
    arm = _export(channel)["arms"]["ptc"]
    assert arm["reports"] == 1, f"PTC collector: {arm}"
    event, = arm["events"]
    assert event["provenance"] == "catalog_callback"
    assert event["kind"] == "task_defect" and event["detail"] == "kept"
    tail = scripted.bodies[1]["messages"][-1]
    assert "error:" in str(tail.get("content") or "")
    # The program died after printing the receipt, so the ack never reached an
    # observation — no receipt claim exists for error programs.
    assert scripted.receipt_at == []


def test_nine_reports_accept_eight_then_overflow(framework):
    """Nine `report_defect` calls in one program: exactly 8 accepted with
    `catalog_callback` provenance, the ninth refused with a visible overflow
    record and a `rejected:` observation — never a false receipt."""
    state = framework
    channels: list = []
    scripted = ScriptedClient([
        _program_call(
            "for i in range(9):\n"
            "    print(report_defect(kind='other', detail='d'))",
            "call_flood"),
        _text_step("done"),
    ])

    async def scenario():
        server, agent = _server_agent(state, scripted)
        async with server:
            return await _configured_run(
                agent, Task(TaskData(prompt="flood.")),
                _factory([], channels))

    trace = _run(scenario())
    assert trace.ok, f"PTC activation: {trace.last_error}"
    channel, = channels
    arm = _export(channel)["arms"]["ptc"]
    reports = [e for e in arm["events"] if e["type"] == "report"]
    assert arm["reports"] == len(reports) == 8, f"PTC collector: {arm}"
    assert all(e["provenance"] == "catalog_callback" for e in reports)
    overflow = [e for e in arm["events"] if e["type"] == "overflow"]
    assert overflow and overflow[0]["reason"] == "report_cap"
    tail = scripted.bodies[1]["messages"][-1]
    content = str(tail.get("content") or "")
    assert content.startswith("rejected:")
    assert ACK not in content


def test_configured_cancellation_restores_and_retries(framework):
    """Cancelling a configured run while a model call is in flight restores
    the exact original harness and releases the claim; a fresh configured run
    on the same Agent still works."""
    state = framework
    entered = asyncio.Event()
    release = asyncio.Event()
    blocked = ScriptedClient([
        _report_program("before-cancel"),
        _program_call("print('unreached')"),
        _text_step("done"),
    ])

    async def on_call(n: int) -> None:
        if n == 2:
            entered.set()
            await asyncio.wait_for(release.wait(), WAIT_S)

    blocked.on_call = on_call
    retry = ScriptedClient([
        _report_program("after-cancel"), _text_step("done")])
    factory_calls: list = []
    channels: list = []

    async def scenario():
        server, agent = _server_agent(state, blocked)
        original = agent.harness
        async with server:
            running = asyncio.create_task(run_configured_ptc_qa(
                agent, Task(TaskData(prompt="cancel me.")),
                qa_factory=_factory(factory_calls, channels)))
            try:
                await asyncio.wait_for(entered.wait(), WAIT_S)
                assert len(channels) == 1
                assert not running.done()
                running.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await running
            finally:
                release.set()
                if not running.done():
                    running.cancel()
                    await asyncio.gather(running, return_exceptions=True)
            assert agent.harness is original
            # Claim must be released: a fresh configured run succeeds.
            server.clients[agent.ctx.client.model_dump_json()] = retry
            trace = await _configured_run(
                agent, Task(TaskData(prompt="retry.")),
                _factory(factory_calls, channels))
        assert agent.harness is original
        return trace

    trace = _run(scenario())
    assert trace.ok, f"PTC activation: {trace.last_error}"
    assert len(channels) == len(factory_calls) == 2
    # An accepted report survives cancellation; the retry gets a fresh channel.
    first_arm = _export(channels[0])["arms"]["ptc"]
    assert first_arm["reports"] == 1
    assert first_arm["events"][0]["detail"] == "before-cancel"
    assert blocked.receipt_at == [2]
    event, = _export(channels[1])["arms"]["ptc"]["events"]
    assert event["detail"] == "after-cancel"
    assert retry.receipt_at == [2]
    with pytest.raises(ValueError):
        channels[0]._claim_launch()


def test_unbound_and_unsupported_routes_refuse_without_actions(framework):
    """Bare `agent.run` on the unbound configured harness, and the runner on
    an Agent configured with a different real harness id, both refuse before
    any policy call or factory call. Runtime provisioning and Task setup may
    legitimately have run before refusal."""
    state = framework
    factory_calls: list = []
    channels: list = []
    scripted = ScriptedClient([_text_step("unused")])
    unsupported_client = ScriptedClient([_text_step("unused")])

    async def scenario():
        server, agent = _server_agent(state, scripted)
        original = agent.harness
        async with server:
            # 1. Bare run on an ordinary task: the unbound harness refuses
            #    neutrally; nothing reaches the policy.
            try:
                t = await agent.run(Task(TaskData(prompt="ordinary.")))
            except (RolloutError, ValueError) as exc:
                assert "run_configured_ptc_qa" in str(exc)
            else:
                assert not t.ok
                assert "run_configured_ptc_qa" in str(t.last_error)
            assert agent.harness is original
            # 2. An Agent resolved through a DIFFERENT real harness id is not
            #    the canonical configured pair: refused with 0 actions.
            wrong_json = _agent_json()
            wrong_json["harness"] = {
                "id": "cotrain_bash_qa", "edit": False, "search": False,
                "compaction": None, "skills": []}
            wrong = AgentConfig.model_validate_json(json.dumps(wrong_json))
            server.clients[wrong.client.model_dump_json()] = (
                unsupported_client)
            wrong_agent = Agent(wrong, interception=server)
            wrong_original = wrong_agent.harness
            assert not isinstance(wrong_original, ReportingPTCHarness)
            with pytest.raises((ValueError, TypeError)):
                await run_configured_ptc_qa(
                    wrong_agent, Task(TaskData(prompt="unsupported.")),
                    qa_factory=_factory(factory_calls, channels))
            assert wrong_agent.harness is wrong_original
        assert agent.harness is original

    _run(scenario())

    assert scripted.calls == 0 and unsupported_client.calls == 0
    assert factory_calls == [] and channels == []
