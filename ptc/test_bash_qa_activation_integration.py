"""Configured-activation integration tests for `cotrain_bash_qa.py`.

Real end-to-end: canonical `AgentConfig` JSON -> real SDK `narrow_plugin_field`
/`harness_config_type`/`load_harness` chain -> `Agent` holding an UNBOUND
`ReportingBashHarness` -> `run_configured_bash_qa` builds the task through the
caller builder, one binding and the bound harness -> existing `run_bash_qa` ->
real bundled Bash child + real SubprocessRuntime + real loopback
`InterceptionServer` + real `/tool` gate. The only "model" is an in-process
scripted `vf.Client`; zero external calls.

Fixture seams (documented, unchanged from the approved baseline fixture):

- `verifiers.v1.rollout.make_runtime` is monkeypatched to a factory returning
  real `ScratchRuntime` instances — real `SubprocessRuntime` subclasses with
  workdir/`scripts_dir`/`_uv_interpreters` instance-local under `tmp_path`.
  `start()` seeds the bundled `CHAT_PROGRAM_SOURCE` digest for the already
  installed `sys.executable`; `prepare_uv_script` REFUSES an unseeded digest,
  so no uv sync/install/download and no global script-cache write can occur.
  The reused fixture records only its actual foreground processes through a
  delegating creation wrapper; runtime teardown drains their transports in
  <=5s. Errors propagate, never suppress. This is fixture-only compensation
  for SDK cancellation killing without awaiting transports.
- `InterceptionServer.clients[cfg.model_dump_json()] = scripted` pre-seeds the
  server-owned client slot; `register` assigns `session.client` from it, so
  `resolve_client`/`resolve_api_key` never run. The `train` client type
  selects the server's non-relay `get_response` path (server.py:600).
- Child env strips `*API_KEY*` names; unknown script bootstrap is refused.

ZERO fixture/caller `agent.harness` assignments: the Agent is built from JSON
and the runner alone performs binding/assignment/restore — that boundary is
what the configured negative controls exercise. Module import opens no
listener; everything binds inside the fixture body.
"""
from __future__ import annotations

import asyncio
import json
import os
import time

import pytest

pytestmark = pytest.mark.filterwarnings(
    "error::pytest.PytestUnraisableExceptionWarning"
)

from verifiers.v1.agent import Agent
from verifiers.v1.clients.client import Client
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.errors import RolloutError
from verifiers.v1.interception.server import InterceptionServer
from verifiers.v1.task import Task, TaskData
from verifiers.v1.types import (
    AssistantMessage,
    Response,
    ToolCall,
    Usage,
)

from cotrain_bash_qa import (
    ReportingBashConfig,
    ReportingBashHarness,
    run_configured_bash_qa,
)
from ptc.bash_qa import BashQaBinding, BashQaTaskMixin
from ptc.sql_qa import (
    BASH_REPORT,
    QaChannel,
    REPORT_MARKER,
    REPORT_PROMPT,
    REPORT_TOOL,
    report_ack,
)
from ptc.test_bash_qa_integration import _patch_runtimes

MODEL = "fixture-model"
OUTER_TIMEOUT_S = 20.0
AGENT_TIMEOUT_S = 15.0
ACK = report_ack()


def _response(message: AssistantMessage, raw_message: dict, finish: str, n: int) -> Response:
    """Typed vf Response plus the native completion dict `stream_events` frames."""
    raw = {
        "id": f"chatcmpl-cfg-{n}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL,
        "choices": [{"index": 0, "message": raw_message, "finish_reason": finish}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    return Response(
        id=raw["id"], created=raw["created"], model=MODEL,
        message=message, finish_reason=finish,
        usage=Usage(prompt_tokens=1, completion_tokens=1), raw=raw,
    )


def _tool_step(call_id: str, arguments: dict) -> dict:
    return {"call_id": call_id, "name": "bash", "arguments": arguments}


def _text_step(text: str) -> dict:
    return {"text": text}


def _report_call(payload: dict, call_id: str = "call_report") -> dict:
    return _tool_step(
        call_id,
        {"command": f"{REPORT_TOOL} '{json.dumps(payload, separators=(',', ':'))}'"},
    )


def _bash_call(command: str, call_id: str = "call_bash") -> dict:
    return _tool_step(call_id, {"command": command})


class ScriptedClient(Client):
    """Scripted policy behind the real listener. `bodies` records every
    effective request dispatched; `receipt_at` records calls whose request
    tail already carried the fixed ack — the receipt-before-next-action
    oracle (missing receipt is RECORDED, never raised through HTTP)."""

    def __init__(self, steps: list[dict], *, on_call=None) -> None:
        self.steps = list(steps)
        self.on_call = on_call
        self.calls = 0
        self.bodies: list[dict] = []
        self.receipt_at: list[int] = []

    async def get_response(self, dialect, body, sampling, session_id=None,
                           turn=None, headers=None) -> Response:
        self.calls += 1
        self.bodies.append(body)
        tail = (body.get("messages") or [{}])[-1]
        if tail.get("role") == "tool" and ACK in str(tail.get("content") or ""):
            self.receipt_at.append(self.calls)
        if self.on_call is not None:
            await self.on_call(self.calls)
        if self.calls > len(self.steps):
            raise RuntimeError(
                f"scripted model exceeded its {len(self.steps)}-step script "
                f"(call {self.calls})"
            )
        step = self.steps[self.calls - 1]
        if "text" in step:
            return _response(
                AssistantMessage(content=step["text"]),
                {"role": "assistant", "content": step["text"]},
                "stop", self.calls,
            )
        arguments = json.dumps(step["arguments"])
        return _response(
            AssistantMessage(tool_calls=[ToolCall(
                id=step["call_id"], name=step["name"], arguments=arguments)]),
            {"role": "assistant", "content": None, "tool_calls": [{
                "id": step["call_id"], "type": "function",
                "function": {"name": step["name"], "arguments": arguments}}]},
            "tool_calls", self.calls,
        )


def _agent_json(lane: str = "", max_turns: int = 4) -> dict:
    """Canonical AgentConfig JSON through the real SDK loader path. The
    `cotrain_bash_qa` flat id resolves to `ReportingBashHarness` unbound —
    the runner, not this fixture, performs activation."""
    client = {"type": "train", "api_key_var": "PROBE_UNUSED_API_KEY"}
    if lane:
        client["headers"] = {"x-probe-lane": lane}
    return json.loads(json.dumps({
        "model": MODEL,
        "client": client,
        "sampling": {},
        "runtime": {"type": "subprocess"},
        "harness": {
            "id": "cotrain_bash_qa",
            "edit": False,
            "search": False,
            "compaction": None,
            "skills": [],
        },
        "max_turns": max_turns,
        "timeout": {"rollout": AGENT_TIMEOUT_S, "finalize": 5.0,
                    "scoring": 5.0},
        "retries": {"max_retries": 0},
    }))


def _configured_agent(server: InterceptionServer, scripted: ScriptedClient, *,
                      lane: str = "", max_turns: int = 4) -> Agent:
    """JSON -> SDK narrowing -> `Agent` whose `agent.harness` is an UNBOUND
    ReportingBashHarness built by `load_harness`. No harness assignment here."""
    config = AgentConfig.model_validate_json(
        json.dumps(_agent_json(lane, max_turns))
    )
    server.clients[config.client.model_dump_json()] = scripted
    agent = Agent(config, interception=server)
    assert isinstance(agent.harness, ReportingBashHarness)
    assert isinstance(agent.harness.config, ReportingBashConfig)
    return agent


class ProbeTask(BashQaTaskMixin, Task):
    """Real Task + mixin so task-side @intercept discovery finds the rewrite
    hook; the runner supplies its fresh binding through the builder."""


def _builder(prompt: str, built: list):
    """The runner's `make_task` callable: one fresh binding in, one task out."""
    def make_task(binding):
        task = ProbeTask(TaskData(prompt=prompt), qa_binding=binding)
        built.append((binding, task))
        return task
    return make_task


def _factory(factory_calls: list, channels: list, detail: str):
    def factory(data: TaskData) -> QaChannel:
        factory_calls.append(data)
        channel = QaChannel()
        channels.append(channel)
        return channel
    return factory


def _export(channel: QaChannel) -> dict:
    return json.loads(channel.export())


@pytest.fixture
def server():
    srv = InterceptionServer()  # tunnel=None -> 127.0.0.1 ephemeral only
    yield srv


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, OUTER_TIMEOUT_S))


async def _configured_run(agent, make_task, factory):
    """The runner await — converting ONLY the admission vocabulary
    (ValueError/TypeError) into a labelled activation assertion, so the
    parent's bound-constructor-bypass mutation surfaces as an intended
    call-phase activation failure rather than an unhandled error."""
    try:
        return await run_configured_bash_qa(agent, make_task,
                                          qa_factory=factory)
    except (ValueError, TypeError) as exc:
        raise AssertionError(
            f"configured activation refused the real pairing: {exc!r}")


def test_real_configured_receipt_before_next_action(
    monkeypatch, tmp_path, server
):
    """Canonical JSON -> real SDK -> unbound harness -> runner -> 1 real
    report_defect -> 1 bash/agent_output report; receipt visible in the
    request that precedes the next action. Bound-constructor bypass must land
    on the `_configured_run` AssertionError; consume-without-forward must land
    on `receipt_at == [2]`."""
    factory_calls: list = []
    channels: list = []
    built: list = []
    scripted = ScriptedClient([
        _report_call({"kind": "task_defect", "detail": "first allegation"}),
        _bash_call("printf 'next\\n'"),
        _text_step("done"),
    ])

    async def scenario():
        agent = _configured_agent(server, scripted)
        original = agent.harness
        original_dump = original.config.model_dump(mode="json")
        agent_dump = agent.config.model_dump(mode="json")
        turns = agent.limits.max_turns
        _patch_runtimes(monkeypatch, tmp_path, runtimes := [])
        async with server:
            assert server.tunnel is None
            assert server.base_url.startswith("http://127.0.0.1:")
            trace = await _configured_run(
                agent,
                _builder("Run the steps.", built),
                _factory(factory_calls, channels, "first allegation"),
            )
        assert agent.harness is original
        assert agent.harness.config.model_dump(mode="json") == original_dump
        assert agent.config.model_dump(mode="json") == agent_dump
        assert agent.limits.max_turns == turns
        return trace, agent

    trace, agent = _run(scenario())

    doc = _export(channels[0])
    assert doc["arms"]["bash"]["reports"] == 1
    events = doc["arms"]["bash"]["events"]
    assert len(events) == 1
    assert events[0]["type"] == "report"
    assert events[0]["provenance"] == "agent_output"

    assert scripted.calls == 3
    assert scripted.receipt_at == [2], (
        "receipt must be visible in the request preceding the next action; "
        "a consume-without-forwarding mutation reads as a call-phase "
        "receipt failure here"
    )
    tail = scripted.bodies[1]["messages"][-1]
    assert tail["role"] == "tool"
    assert tail["tool_call_id"] == "call_report"
    assert str(tail.get("content") or "").startswith(REPORT_MARKER)
    system = scripted.bodies[0]["messages"][0]
    assert system["role"] == "system"
    assert REPORT_PROMPT in str(system.get("content") or "")
    assert BASH_REPORT in str(system.get("content") or "")

    # Builder ran exactly once; factory ran exactly once with the original
    # TaskData object (the prompt it was constructed with).
    assert len(built) == 1
    assert len(factory_calls) == 1
    assert factory_calls[0] is built[0][1].data
    assert factory_calls[0].prompt == "Run the steps."

    assert trace.ok
    assert trace.num_turns == 3
    assert server.sessions == {} and server.state_sessions == {}
    assert list(tmp_path.rglob(REPORT_TOOL)) == []


def test_two_sequential_configured_runs_same_agent(
    monkeypatch, tmp_path, server
):
    """Two sequential configured runs on ONE Agent: unbound harness restored
    each time, two fresh channels (own details only), fresh bindings per run,
    first channel stays spent."""
    scripted_a = ScriptedClient([
        _report_call({"kind": "other", "detail": "run-one"}),
        _text_step("done"),
    ])
    scripted_b = ScriptedClient([
        _report_call({"kind": "other", "detail": "run-two"}),
        _text_step("done"),
    ])
    factory_calls: list = []
    channels: list = []
    built: list = []

    async def scenario():
        agent = _configured_agent(server, scripted_a, max_turns=3)
        original = agent.harness
        _patch_runtimes(monkeypatch, tmp_path, runtimes := [])
        async with server:
            assert server.tunnel is None
            trace_a = await _configured_run(
                agent, _builder("first.", built),
                _factory(factory_calls, channels, "run-one"))
            assert agent.harness is original
            # Same Agent, second configured run — the client slot now serves
            # the second script (same canonical client key).
            server.clients[agent.ctx.client.model_dump_json()] = scripted_b
            trace_b = await _configured_run(
                agent, _builder("second.", built),
                _factory(factory_calls, channels, "run-two"))
            assert agent.harness is original
        return trace_a, trace_b

    trace_a, trace_b = _run(scenario())

    assert trace_a.ok and trace_b.ok
    assert len(channels) == 2 and channels[0] is not channels[1]
    assert len(built) == 2 and built[0][0] is not built[1][0]
    assert len(factory_calls) == 2
    doc_a, doc_b = _export(channels[0]), _export(channels[1])
    assert doc_a["arms"]["bash"]["reports"] == 1
    assert doc_b["arms"]["bash"]["reports"] == 1
    # Own details only: run-one's detail is absent from run-two's channel.
    assert all(
        e.get("detail") != "run-two"
        for e in doc_a["arms"]["bash"]["events"]
    )
    assert all(
        e.get("detail") != "run-one"
        for e in doc_b["arms"]["bash"]["events"]
    )
    # Both factory calls saw the exact TaskData objects of their own tasks.
    assert all(factory_calls[i] is built[i][1].data for i in range(2))
    assert doc_a["arms"]["bash"]["events"][0]["detail"] == "run-one"
    assert doc_b["arms"]["bash"]["events"][0]["detail"] == "run-two"
    for channel in channels:
        with pytest.raises(ValueError):
            channel._claim_launch()
    assert server.sessions == {} and server.state_sessions == {}
    assert list(tmp_path.rglob(REPORT_TOOL)) == []


def test_two_agents_configured_overlap(monkeypatch, tmp_path, server):
    """Barrier-proven overlap of two distinct configured Agents: own report
    only per channel, PATH isolation, both unbound harnesses restored."""
    parent_path = os.environ.get("PATH")
    channels_a: list = []
    channels_b: list = []
    factory_calls_a: list = []
    factory_calls_b: list = []
    built_a: list = []
    built_b: list = []
    client_a = ScriptedClient([
        _bash_call("printf '%s' \"$PATH\"", "call_path_a"),
        _report_call({"kind": "other", "detail": "lane-a"}),
        _text_step("done"),
    ])
    client_b = ScriptedClient([
        _bash_call("printf '%s' \"$PATH\"", "call_path_b"),
        _report_call({"kind": "other", "detail": "lane-b"}),
        _text_step("done"),
    ])

    async def scenario():
        first, second = asyncio.Event(), asyncio.Event()

        async def gate_a(_call: int) -> None:
            first.set()
            await asyncio.wait_for(second.wait(), 10.0)

        async def gate_b(_call: int) -> None:
            second.set()
            await asyncio.wait_for(first.wait(), 10.0)

        client_a.on_call = gate_a
        client_b.on_call = gate_b

        agent_a = _configured_agent(server, client_a, lane="a")
        agent_b = _configured_agent(server, client_b, lane="b")
        original_a, original_b = agent_a.harness, agent_b.harness
        _patch_runtimes(monkeypatch, tmp_path, runtimes := [])
        async with server:
            assert server.tunnel is None
            assert server.base_url.startswith("http://127.0.0.1:")
            trace_a, trace_b = await asyncio.gather(
                _configured_run(
                    agent_a, _builder("lane a.", built_a),
                    _factory(factory_calls_a, channels_a, "lane-a")),
                _configured_run(
                    agent_b, _builder("lane b.", built_b),
                    _factory(factory_calls_b, channels_b, "lane-b")),
            )
        assert agent_a.harness is original_a
        assert agent_b.harness is original_b
        return trace_a, trace_b

    trace_a, trace_b = _run(scenario())

    assert trace_a.ok and trace_b.ok
    doc_a, doc_b = _export(channels_a[0]), _export(channels_b[0])
    assert doc_a["arms"]["bash"]["reports"] == 1
    assert doc_b["arms"]["bash"]["reports"] == 1
    assert doc_a["arms"]["bash"]["events"][0]["detail"] == "lane-a"
    assert doc_b["arms"]["bash"]["events"][0]["detail"] == "lane-b"
    assert factory_calls_a == [built_a[0][1].data]
    assert factory_calls_b == [built_b[0][1].data]
    assert all(e.get("detail") != "lane-b"
               for e in doc_a["arms"]["bash"]["events"])
    assert all(e.get("detail") != "lane-a"
               for e in doc_b["arms"]["bash"]["events"])
    # PATH isolation: each lane's real `$PATH` observation differs.
    def delivered_path(client, call_id):
        for body in client.bodies:
            for message in body.get("messages") or []:
                if message.get("role") == "tool" and \
                        message.get("tool_call_id") == call_id:
                    return str(message.get("content") or "")
        return ""
    path_a = delivered_path(client_a, "call_path_a")
    path_b = delivered_path(client_b, "call_path_b")
    assert path_a and path_b and path_a != path_b
    assert os.environ.get("PATH") == parent_path
    assert server.sessions == {} and server.state_sessions == {}
    assert list(tmp_path.rglob(REPORT_TOOL)) == []


def test_configured_cancellation_restores_and_retries(
    monkeypatch, tmp_path, server
):
    """A cancelled configured run restores the exact unbound harness, and a
    fresh configured run on the same Agent still works (claim released)."""
    blocked = asyncio.Event()
    entered = asyncio.Event()

    class BlockingClient(ScriptedClient):
        async def get_response(self, dialect, body, sampling,
                               session_id=None, turn=None, headers=None):
            self.calls += 1
            self.bodies.append(body)
            if self.calls == 1:
                arguments = json.dumps({"command": "printf 'x\\n'"})
                return _response(
                    AssistantMessage(tool_calls=[ToolCall(
                        id="call_x", name="bash", arguments=arguments)]),
                    {"role": "assistant", "content": None, "tool_calls": [{
                        "id": "call_x", "type": "function",
                        "function": {"name": "bash",
                                     "arguments": arguments}}]},
                    "tool_calls", self.calls)
            entered.set()
            await blocked.wait()
            return _response(
                AssistantMessage(content="released"),
                {"role": "assistant", "content": "released"},
                "stop", self.calls,
            )

    scripted = BlockingClient([_text_step("never")])
    retry_client = ScriptedClient([
        _report_call({"kind": "other", "detail": "after-cancel"}),
        _text_step("done"),
    ])
    factory_calls: list = []
    channels: list = []
    built: list = []

    async def scenario():
        agent = _configured_agent(server, scripted, max_turns=3)
        original = agent.harness
        _patch_runtimes(monkeypatch, tmp_path, runtimes := [])
        async with server:
            assert server.tunnel is None
            running = asyncio.create_task(run_configured_bash_qa(
                agent, _builder("cancel me.", built),
                qa_factory=_factory(factory_calls, channels, "x"),
            ))
            try:
                await asyncio.wait_for(entered.wait(), 10.0)
                assert len(channels) == 1
                running.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await running
            finally:
                blocked.set()
                if not running.done():
                    running.cancel()
                    await asyncio.gather(running, return_exceptions=True)
            assert agent.harness is original
            # Claim must be released: a fresh configured run succeeds.
            server.clients[agent.ctx.client.model_dump_json()] = retry_client
            trace = await _configured_run(
                agent, _builder("retry.", built),
                _factory(factory_calls, channels, "after-cancel"))
        assert agent.harness is original
        return trace

    trace = _run(scenario())

    assert trace.ok
    # Only the retry produced a report; the cancelled run may have consumed
    # a factory call (channel stays spent, caller-owned).
    doc = _export(channels[-1])
    assert doc["arms"]["bash"]["reports"] == 1
    assert len(channels) == len(factory_calls) == 2
    assert scripted.calls == 2
    assert _export(channels[0])["arms"]["bash"]["reports"] == 0
    with pytest.raises(ValueError):
        channels[0]._claim_launch()
    assert server.sessions == {} and server.state_sessions == {}
    assert list(tmp_path.rglob(REPORT_TOOL)) == []


def test_configured_factory_failure_restores_and_retries(
    monkeypatch, tmp_path, server
):
    """Real launch failure, before the first policy action, releases the
    configured runner and task route so the same Agent can run fresh."""
    scripted = ScriptedClient([
        _report_call({"kind": "other", "detail": "after-failure"}),
        _text_step("done"),
    ])
    failures, factory_calls, channels, built = [], [], [], []

    def failing_factory(data):
        failures.append(data)
        raise ValueError("configured factory failure")

    async def scenario():
        agent = _configured_agent(server, scripted, max_turns=3)
        original = agent.harness
        original_dump = agent.config.model_dump(mode="json")
        _patch_runtimes(monkeypatch, tmp_path, runtimes := [])
        async with server:
            failed = await run_configured_bash_qa(
                agent, _builder("fail launch.", built),
                qa_factory=failing_factory,
            )
            assert not failed.ok
            assert "configured factory failure" in str(failed.last_error)
            assert scripted.calls == 0
            assert failures == [built[0][1].data]
            assert failures[0] is built[0][1].data
            assert agent.harness is original
            retried = await _configured_run(
                agent, _builder("retry launch.", built),
                _factory(factory_calls, channels, "after-failure"),
            )
        assert agent.harness is original
        assert agent.config.model_dump(mode="json") == original_dump
        return retried

    trace = _run(scenario())
    assert trace.ok
    assert len(channels) == len(factory_calls) == 1
    assert factory_calls[0] is built[1][1].data
    assert _export(channels[0])["arms"]["bash"]["reports"] == 1
    assert server.sessions == {} and server.state_sessions == {}
    assert list(tmp_path.rglob(REPORT_TOOL)) == []


def test_unbound_and_direct_routes_refuse_without_actions(
    monkeypatch, tmp_path, server
):
    """Unbound configured agent running an ordinary task, a mixin task run
    directly (no permit), and a builder returning a plain Task all refuse
    before any policy call, factory call or harness mutation."""
    scripted = ScriptedClient([_text_step("unused")])
    factory_calls: list = []
    channels: list = []

    async def scenario():
        agent = _configured_agent(server, scripted, max_turns=3)
        original = agent.harness
        original_dump = original.config.model_dump(mode="json")
        _patch_runtimes(monkeypatch, tmp_path, runtimes := [])
        async with server:
            # 1. Bare agent.run on an ordinary task: unbound harness refuses
            #    neutrally; nothing reaches the policy.
            try:
                t = await agent.run(Task(TaskData(prompt="ordinary.")))
            except (RolloutError, ValueError) as exc:
                assert "run_configured_bash_qa" in str(exc)
            else:
                assert not t.ok
                assert "run_configured_bash_qa" in str(t.last_error)
            # 2. Direct run of a mixin task: no permit -> refuses.
            binding_task = ProbeTask(
                TaskData(prompt="no permit."), qa_binding=BashQaBinding())
            try:
                t = await agent.run(binding_task)
            except (RolloutError, ValueError) as exc:
                assert "run_bash_qa" in str(exc)
            else:
                assert not t.ok
                assert "run_bash_qa" in str(t.last_error)
            # 3. Builder returning a non-mixin Task: runner refuses before
            #    assignment; original harness untouched.
            with pytest.raises((ValueError, TypeError)):
                await run_configured_bash_qa(
                    agent,
                    lambda binding: Task(TaskData(prompt="not mixed.")),
                    qa_factory=_factory(factory_calls, channels, "x"))
        assert agent.harness is original
        assert agent.harness.config.model_dump(mode="json") == original_dump

    _run(scenario())

    assert scripted.calls == 0, f"policy reached {scripted.calls} times"
    assert factory_calls == [] and channels == []
    assert server.sessions == {} and server.state_sessions == {}
    assert list(tmp_path.rglob(REPORT_TOOL)) == []
