"""Real-subprocess integration tests for `ptc/bash_qa.py`.

Real `BashHarness` program (bundled chat program via `launch_chat_program`),
real `SubprocessRuntime` bash execution, real framework `InterceptionServer`
on 127.0.0.1 ephemeral port, in-process scripted `vf.Client`. Zero external
model/provider/Docker calls; every fixture is bounded at <=20s outer.

Fixture seams (the ONLY framework seams used; documented, not product code):

- `verifiers.v1.rollout.make_runtime` is monkeypatched to a factory that
  returns real `ScratchRuntime` instances — real `SubprocessRuntime`
  subclasses whose `workdir`/`scripts_dir`/`_uv_interpreters` are
  instance-local under `tmp_path` instead of `~/.cache/verifiers`. The
  installed interpreter-preparation seam is used: the bundled
  `CHAT_PROGRAM_SOURCE` digest is seeded for `sys.executable` and
  `prepare_uv_script` REFUSES an unseeded digest instead of bootstrapping
  dependencies (no uv sync/install/download, no global script cache writes).
  The rollout still owns normal runtime lifecycle: `runtime.start()` and
  `runtime.stop()` run through the real framework path per launch.
- `InterceptionServer.clients[cfg.model_dump_json()] = scripted` pre-seeds
  the server-owned client slot. `register` assigns `session.client` from that
  map; `resolve_client`/`resolve_api_key` are never invoked.
- `session.ctx.client` is a `TrainClientConfig`, which selects the
  interception server's non-relay path (`session.client.get_response`,
  server.py:600,793-799) — the scripted client returns typed `Response`s and
  the server frames SSE from `Response.raw` itself.
- `agent.harness = <real QaBashHarness>` replaces the loader-built
  `BashHarness` (id "bash" cannot produce the QA subclass through config;
  `Agent.harness` is a public attribute, not product forwarding).
- A delegating `asyncio.create_subprocess_exec` wrapper records only actual
  foreground processes in fixture-owned workdirs, returning them unchanged.
  Runtime teardown drains those transports after framework run completion.
  This compensates for the installed SDK's kill-without-wait cancellation
  cleanup; it is fixture bookkeeping, not product transport cleanup.
- Child env strips `*API_KEY*` names automatically (subprocess.py:101).
  Unknown script digests refuse before any dependency bootstrap.

Module import opens no listener; everything binds inside the fixture body.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import os
import sys
import time
from pathlib import Path

import pytest

from verifiers.v1.agent import Agent
from verifiers.v1.clients.client import Client
from verifiers.v1.configs.agent import AgentConfig, TimeoutConfig
from verifiers.v1.configs.client import TrainClientConfig
from verifiers.v1.configs.retries import RetryConfig
from verifiers.v1.harnesses.utils.compaction import truncate_tool_output
from verifiers.v1.harnesses.utils.launch import CHAT_PROGRAM_SOURCE
from verifiers.v1.interception.server import InterceptionServer
from verifiers.v1.runtimes import ProgramResult
from verifiers.v1.runtimes.subprocess import SubprocessConfig, SubprocessRuntime
from verifiers.v1.task import Task, TaskData
from verifiers.v1.types import (
    AssistantMessage,
    Response,
    Sampling,
    ToolCall,
    Usage,
)

from ptc.bash_qa import (
    BashQaBinding,
    BashQaTaskMixin,
    QaBashHarness,
    QaBashHarnessConfig,
    run_bash_qa,
)
from ptc.sql_qa import (
    BASH_REPORT,
    QaChannel,
    REPORT_MARKER,
    REPORT_OVERFLOW,
    REPORT_PROMPT,
    REPORT_REFUSED,
    REPORT_TOOL,
    report_ack,
)

MODEL = "fixture-model"
OUTER_TIMEOUT_S = 20.0
AGENT_TIMEOUT_S = 15.0
FRAMEWORK_TOOL_BOUND = 20000
ACK = report_ack()


def _response(message: AssistantMessage, raw_message: dict, finish: str, n: int) -> Response:
    """Typed vf Response plus the native completion dict `stream_events` frames."""
    raw = {
        "id": f"chatcmpl-qa-{n}",
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


def _tool_step(call_id: str, name: str, arguments: dict) -> dict:
    return {"call_id": call_id, "name": name, "arguments": arguments}


def _text_step(text: str) -> dict:
    return {"text": text}


def _report_call(payload: dict) -> dict:
    """A `bash` step invoking the real `report_defect` shim with strict JSON."""
    return _tool_step(
        "call_report", "bash",
        {"command": f"{REPORT_TOOL} '{json.dumps(payload, separators=(',', ':'))}'"},
    )


def _bash_call(command: str, call_id: str = "call_bash") -> dict:
    return _tool_step(call_id, "bash", {"command": command})


class ScriptedClient(Client):
    """In-process scripted policy behind the real listener.

    Records every effective request `body` the server dispatched and whether
    each request's tail already carried the fixed ack (`receipt_at`) — the
    receipt-before-next-action oracle. A missing receipt is RECORDED, never
    raised here (raising becomes a provider 502 and the failure mode the spec
    wants to distinguish). `gate` is an optional async barrier hook for
    true-overlap tests.
    """

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
        message = AssistantMessage(
            tool_calls=[ToolCall(id=step["call_id"], name=step["name"],
                                 arguments=arguments)]
        )
        raw_message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": step["call_id"], "type": "function",
                "function": {"name": step["name"], "arguments": arguments},
            }],
        }
        return _response(message, raw_message, "tool_calls", self.calls)


class ScratchRuntime(SubprocessRuntime):
    """Real SubprocessRuntime pinned to a unique tmp dir; refuses bootstrap."""

    def __init__(self, config: SubprocessConfig, scratch: Path, name: str) -> None:
        super().__init__(config, name)
        self._scratch = scratch
        self.scripts_dir = str(scratch / "scripts")
        self._uv_interpreters = {}
        self._uv_script_locks = {}
        self._owned_foreground = []

    async def start(self) -> None:
        self.workdir = self._scratch / "workdir" / self.name
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.info.id = str(self.workdir)
        for package in ("openai", "mcp", "httpx", "httpx2", "tenacity"):
            importlib.metadata.version(package)
        assert importlib.metadata.version("mcp") == "2.0.0"
        data = CHAT_PROGRAM_SOURCE.encode()
        digest = hashlib.sha256(data).hexdigest()
        scripts = Path(self.scripts_dir)
        scripts.mkdir(parents=True, exist_ok=True)
        (scripts / f"{digest}.py").write_bytes(data)
        self._uv_interpreters[digest] = sys.executable

    async def prepare_uv_script(self, script, env=None, *, activate=True):
        data = script.encode() if isinstance(script, str) else script
        digest = hashlib.sha256(data).hexdigest()
        assert digest in self._uv_interpreters, "refusing dependency bootstrap"
        return await super().prepare_uv_script(script, env, activate=activate)

    async def teardown(self):
        try:
            if self._owned_foreground:
                await asyncio.wait_for(
                    asyncio.gather(
                        *(proc.communicate() for proc in self._owned_foreground)
                    ),
                    timeout=5.0,
                )
                self._owned_foreground.clear()
        finally:
            await super().teardown()


class ProbeTask(BashQaTaskMixin, Task):
    """A real Task mixed with BashQaTaskMixin so task-side @intercept discovery
    finds the rewrite hook (interceptors are discovered on the task, not the
    harness — rollout.py:101-104)."""


class RecordingQaHarness(QaBashHarness):
    """Captures the real ProgramResult the product launch returns."""

    def __init__(self, config, *, qa_factory, qa_binding) -> None:
        super().__init__(config, qa_factory=qa_factory, qa_binding=qa_binding)
        self.last_result: ProgramResult | None = None

    async def launch(self, ctx, trace, runtime, endpoint, secret, mcp_urls,
                     data, tool_interception_url=None):
        self.last_result = result = await super().launch(
            ctx, trace, runtime, endpoint, secret, mcp_urls, data,
            tool_interception_url=tool_interception_url)
        return result


def _patch_runtimes(monkeypatch, root: Path, bucket: list):
    """Fixture-only runtime construction: real ScratchRuntime per launch."""
    from verifiers.v1 import rollout as rollout_mod

    counter = {"n": 0}

    def make(config, name=None):
        counter["n"] += 1
        rt = ScratchRuntime(
            config, root / f"launch-{counter['n']}",
            name=name or f"probe-{counter['n']}",
        )
        bucket.append(rt)
        return rt

    monkeypatch.setattr(rollout_mod, "make_runtime", make)
    create_process = asyncio.create_subprocess_exec

    async def tracked_process(*argv, **kwargs):
        process = await create_process(*argv, **kwargs)
        if (kwargs.get("stdout") == asyncio.subprocess.PIPE
                and kwargs.get("stderr") == asyncio.subprocess.PIPE
                and kwargs.get("stdin") != asyncio.subprocess.PIPE):
            cwd = kwargs.get("cwd")
            for runtime in bucket:
                if runtime.workdir is not None and cwd == runtime.workdir:
                    runtime._owned_foreground.append(process)
                    break
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", tracked_process)


def _agent(server: InterceptionServer, scripted: ScriptedClient, *,
           harness: QaBashHarness, lane: str = "", max_turns: int = 6) -> Agent:
    client_config = TrainClientConfig(
        api_key_var="PROBE_UNUSED_API_KEY",
        headers={"x-probe-lane": lane} if lane else {},
    )
    server.clients[client_config.model_dump_json()] = scripted
    agent = Agent(
        AgentConfig(
            model=MODEL,
            client=client_config,
            sampling=Sampling(),
            runtime=SubprocessConfig(),
            max_turns=max_turns,
            timeout=TimeoutConfig(setup=None, rollout=AGENT_TIMEOUT_S,
                                  finalize=5.0, scoring=5.0),
            retries=RetryConfig(max_retries=0),
        ),
        interception=server,
    )
    agent.harness = harness  # fixture: seat's harness is a public attribute
    return agent


def _qa_harness(factory, binding) -> RecordingQaHarness:
    return RecordingQaHarness(
        QaBashHarnessConfig(id="bash", edit=False, search=False,
                            compaction=None, skills=[]),
        qa_factory=factory, qa_binding=binding,
    )


def _export(channel: QaChannel) -> dict:
    return json.loads(channel.export())


def _tool_bodies(client: ScriptedClient) -> list[dict]:
    """Tool-result messages the model actually received, per request."""
    out = []
    for body in client.bodies:
        for message in body.get("messages") or []:
            if message.get("role") == "tool":
                out.append(message)
    return out


@pytest.fixture
def server():
    srv = InterceptionServer()  # tunnel=None -> loopback-only, ephemeral port
    yield srv


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, OUTER_TIMEOUT_S))


def test_real_report_receipt_before_next_action(monkeypatch, tmp_path, server):
    """1 real report_defect invocation -> 1 bash agent_output report; the fixed
    ack is visible to the scripted policy in the NEXT request before it picks
    the subsequent action. Not-forwarding the rewrite leaves
    `receipt_before_next_action` empty -> a call-phase assertion failure, not a
    setup error."""
    factory_calls: list = []
    channels: list = []

    def factory(data):
        factory_calls.append(data)
        channel = QaChannel()
        channels.append(channel)
        return channel

    binding = BashQaBinding()
    harness = _qa_harness(factory, binding)
    task = ProbeTask(TaskData(prompt="Run the steps."), qa_binding=binding)
    scripted = ScriptedClient([
        _report_call({"kind": "task_defect", "detail": "first allegation"}),
        _bash_call("printf 'next\\n'"),
        _text_step("done"),
    ])
    agent = _agent(server, scripted, harness=harness)

    async def scenario():
        _patch_runtimes(monkeypatch, tmp_path, runtimes := [])
        async with server:
            assert server.tunnel is None
            assert server.base_url.startswith("http://127.0.0.1:")
            trace = await run_bash_qa(agent, task)
        return trace, runtimes

    trace, runtimes = _run(scenario())

    # 1 real report, 1 event, agent_output provenance on arm bash.
    doc = _export(channels[0])
    assert doc["arms"]["bash"]["reports"] == 1
    events = doc["arms"]["bash"]["events"]
    assert len(events) == 1
    assert events[0]["type"] == "report"
    assert events[0]["provenance"] == "agent_output"
    assert events[0]["arm"] == "bash"

    # Receipt reached the model BEFORE the next action: request #2's tool
    # tail carried the ack when the policy chose call #2's bash action.
    assert scripted.calls == 3
    assert scripted.receipt_at == [2], (
        "receipt must be visible in the request that precedes the next "
        "action — a consume-without-forwarding implementation reads as a "
        "call-phase failure here, not a setup error"
    )
    # Original framing/count/IDs/status preserved: the rewritten tail is the
    # same tool message, not a new one.
    tail = scripted.bodies[1]["messages"][-1]
    assert tail["role"] == "tool"
    assert tail["tool_call_id"] == "call_report"
    assert len(scripted.bodies[1]["messages"]) == len(scripted.bodies[0]["messages"]) + 2
    assert str(tail.get("content") or "").startswith(REPORT_MARKER)
    # Reporting instructions extend the launch-local system prompt.
    opening = scripted.bodies[0]["messages"][0]
    assert opening["role"] == "system"
    assert REPORT_PROMPT in str(opening.get("content") or "")
    assert BASH_REPORT in str(opening.get("content") or "")
    # The factory saw the exact original task.data once.
    assert factory_calls == [task.data]
    assert factory_calls[0] is task.data

    assert harness.last_result is not None
    assert harness.last_result.exit_code == 0
    assert trace.ok
    assert trace.num_turns == 3
    assert server.sessions == {} and server.state_sessions == {}


def test_real_invalid_report_rejected(monkeypatch, tmp_path, server):
    """1 invalid-schema report: 0 accepted, bounded refusal, framing intact,
    no submitted sentinel bytes inside the appended refusal."""
    channels: list = []

    def factory(data):
        channel = QaChannel()
        channels.append(channel)
        return channel

    binding = BashQaBinding()
    harness = _qa_harness(factory, binding)
    task = ProbeTask(TaskData(prompt="Run the steps."), qa_binding=binding)
    scripted = ScriptedClient([
        _bash_call(f"{REPORT_TOOL} 'not-a-report'"),
        _text_step("done"),
    ])
    agent = _agent(server, scripted, harness=harness)

    async def scenario():
        _patch_runtimes(monkeypatch, tmp_path, [])
        async with server:
            return await run_bash_qa(agent, task)

    trace = _run(scenario())

    doc = _export(channels[0])
    assert doc["arms"]["bash"]["reports"] == 0
    events = doc["arms"]["bash"]["events"]
    rejected = [e for e in events if e["type"] == "report_rejected"]
    assert len(rejected) == 1
    assert rejected[0]["provenance"] == "agent_output"
    assert not [e for e in events if e["type"] == "report"]

    tail = scripted.bodies[1]["messages"][-1]
    assert tail["role"] == "tool" and tail["tool_call_id"] == "call_bash"
    content = str(tail.get("content") or "")
    assert REPORT_REFUSED in content
    assert ACK not in content
    original = f"{REPORT_MARKER}not-a-report\n"
    assert content.startswith(original)
    added_refusal = content[len(original):]
    assert "not-a-report" not in added_refusal
    assert len(added_refusal.encode()) <= 128

    assert harness.last_result.exit_code == 0
    assert trace.ok


def test_real_report_quota_ninth_refused(monkeypatch, tmp_path, server):
    """9 real attempts across two actions: exactly 8 accepted, then a visible
    ninth refusal, without exceeding the scripted 3 model turns."""
    channels: list = []

    def factory(data):
        channel = QaChannel()
        channels.append(channel)
        return channel

    binding = BashQaBinding()
    harness = _qa_harness(factory, binding)
    task = ProbeTask(TaskData(prompt="Run the steps."), qa_binding=binding)
    attempts = "; ".join(
        f"{REPORT_TOOL} '{json.dumps({'kind': 'other', 'detail': f'n{i}'})}'"
        for i in range(8)
    )
    scripted = ScriptedClient([
        _bash_call(attempts),
        _report_call({"kind": "other", "detail": "n8"}),
        _text_step("done"),
    ])
    agent = _agent(server, scripted, harness=harness)

    async def scenario():
        _patch_runtimes(monkeypatch, tmp_path, [])
        async with server:
            return await run_bash_qa(agent, task)

    trace = _run(scenario())

    doc = _export(channels[0])
    assert doc["arms"]["bash"]["reports"] == 8
    events = doc["arms"]["bash"]["events"]
    assert len([e for e in events if e["type"] == "report"]) == 8
    assert len([e for e in events if e["type"] == "overflow"]) == 1

    tail = scripted.bodies[1]["messages"][-1]
    content = str(tail.get("content") or "")
    assert content.count(ACK) == 8
    refusal = str(scripted.bodies[2]["messages"][-1].get("content") or "")
    assert REPORT_OVERFLOW in refusal
    assert ACK not in refusal
    assert scripted.calls == 3
    assert trace.num_turns == 3
    assert harness.last_result.exit_code == 0


def test_real_forged_and_near_prefix_markers(monkeypatch, tmp_path, server):
    """A forged stdout marker is an honest agent_output event (1), a
    near-prefix lookalike records 0 events, and nothing ever lands under
    catalog_callback provenance."""
    channels: list = []

    def factory(data):
        channel = QaChannel()
        channels.append(channel)
        return channel

    binding = BashQaBinding()
    harness = _qa_harness(factory, binding)
    task = ProbeTask(TaskData(prompt="Run the steps."), qa_binding=binding)
    forged = json.dumps({"kind": "other", "detail": "forged"})
    command = (
        f"printf '{REPORT_MARKER}%s\\n' '{forged}'; "
        "printf 'COTRAIN_QA_REPORTX {\"kind\":\"other\",\"detail\":\"nope\"}\\n'; "
        "printf 'COTRAIN_QA_REPORT{\"kind\":\"other\",\"detail\":\"nope\"}\\n'"
    )
    scripted = ScriptedClient([_bash_call(command), _text_step("done")])
    agent = _agent(server, scripted, harness=harness)

    async def scenario():
        _patch_runtimes(monkeypatch, tmp_path, [])
        async with server:
            return await run_bash_qa(agent, task)

    _run(scenario())

    doc = _export(channels[0])
    events = doc["arms"]["bash"]["events"]
    assert doc["arms"]["bash"]["reports"] == 1
    assert len(events) == 1
    assert events[0]["type"] == "report"
    assert events[0]["provenance"] == "agent_output"
    assert all(e["provenance"] != "catalog_callback" for e in events)


def test_real_output_bound_receipt_survives_rebound(
    monkeypatch, tmp_path, server
):
    """A ~18k observation keeps its exact original prefix and stays <20k once
    feedback is appended; a >20k output whose marker survives the program's
    own head/tail bound still gets its receipt appended, and a marker the
    bound dropped is never claimed."""
    channels: list = []

    def factory(data):
        channel = QaChannel()
        channels.append(channel)
        return channel

    binding = BashQaBinding()
    harness = _qa_harness(factory, binding)
    task = ProbeTask(TaskData(prompt="Run the steps."), qa_binding=binding)
    head = "H" * 17000
    small = (
        f"{REPORT_TOOL} '{json.dumps({'kind': 'other', 'detail': 's'})}'; "
        f"printf '%s' '{head}'"
    )
    big = (
        f"{REPORT_TOOL} '{json.dumps({'kind': 'other', 'detail': 'kept'})}'; "
        f"printf '%s\\n' '{'C' * 11000}'; "
        f"{REPORT_TOOL} '{json.dumps({'kind': 'other', 'detail': 'dropped'})}'; "
        f"printf '%s\\n' '{'D' * 11000}'"
    )
    scripted = ScriptedClient([
        _bash_call(small, "call_small"),
        _bash_call(big, "call_big"),
        _text_step("done"),
    ])
    agent = _agent(server, scripted, harness=harness, max_turns=4)

    async def scenario():
        _patch_runtimes(monkeypatch, tmp_path, [])
        async with server:
            return await run_bash_qa(agent, task)

    trace = _run(scenario())

    doc = _export(channels[0])
    # small: 1 report; big: the retained head marker only — the bound-dropped
    # middle marker is never claimed.
    assert doc["arms"]["bash"]["reports"] == 2
    reports = [e for e in doc["arms"]["bash"]["events"] if e["type"] == "report"]
    assert len(reports) == 2

    tool_msgs = _tool_bodies(scripted)
    small_result = next(m for m in tool_msgs if m["tool_call_id"] == "call_small")
    big_result = next(m for m in tool_msgs if m["tool_call_id"] == "call_big")
    small_content = str(small_result.get("content") or "")
    big_content = str(big_result.get("content") or "")
    assert REPORT_MARKER in small_content
    assert small_content.splitlines()[0].startswith(REPORT_MARKER)
    original = (
        f"{REPORT_MARKER}{json.dumps({'kind': 'other', 'detail': 's'})}\n{head}"
    )
    assert small_content.startswith(original)
    assert ACK in small_content
    assert len(small_content.encode()) <= FRAMEWORK_TOOL_BOUND
    assert REPORT_MARKER in big_content
    assert ACK in big_content
    # SDK retains 20,000 payload bytes PLUS warning/separator metadata.
    # Check its exact double-bound result, not a fictional wire-size ceiling.
    raw_big = (
        f"{REPORT_MARKER}{json.dumps({'kind': 'other', 'detail': 'kept'})}\n"
        + "C" * 11000 + "\n"
        + f"{REPORT_MARKER}{json.dumps({'kind': 'other', 'detail': 'dropped'})}\n"
        + "D" * 11000 + "\n"
    )
    delivered = truncate_tool_output(raw_big)
    assert '"detail": "dropped"' not in delivered
    assert delivered.endswith("\n")
    assert big_content == truncate_tool_output(delivered + ACK)
    assert harness.last_result.exit_code == 0
    assert trace.ok


def test_two_true_overlapping_launches(monkeypatch, tmp_path, server):
    """Barrier-proven 2 overlapping launches: distinct wrapper dirs and
    runtime PATHs, each channel sees only its own report, parent PATH
    unchanged, zero owned dirs/registrations left."""
    parent_path = os.environ.get("PATH")
    channels: dict[str, QaChannel] = {}
    factories: dict[str, list] = {"a": [], "b": []}

    def lane_factory(lane):
        def factory(data):
            factories[lane].append(data)
            channel = QaChannel()
            channels[lane] = channel
            return channel
        return factory

    bindings = {lane: BashQaBinding() for lane in "ab"}
    harnesses = {
        lane: _qa_harness(lane_factory(lane), bindings[lane]) for lane in "ab"
    }
    tasks = {
        lane: ProbeTask(
            TaskData(prompt=f"lane {lane}"), qa_binding=bindings[lane]
        )
        for lane in "ab"
    }
    clients = {
        lane: ScriptedClient([
            _bash_call("printf '%s' \"$PATH\"", "call_path"),
            _report_call({"kind": "other", "detail": f"lane-{lane}"}),
            _text_step("done"),
        ])
        for lane in "ab"
    }

    async def scenario():
        # Barrier created inside the running loop: each lane's first model
        # call sets its own event and awaits the other's — proves both
        # launches are simultaneously in flight.
        first, second = asyncio.Event(), asyncio.Event()

        async def gate_a(_call: int) -> None:
            first.set()
            await asyncio.wait_for(second.wait(), 10.0)

        async def gate_b(_call: int) -> None:
            second.set()
            await asyncio.wait_for(first.wait(), 10.0)

        clients["a"].on_call = gate_a
        clients["b"].on_call = gate_b

        _patch_runtimes(monkeypatch, tmp_path, runtimes := [])
        async with server:
            assert server.tunnel is None
            assert server.base_url.startswith("http://127.0.0.1:")
            agents = {
                "a": _agent(server, clients["a"], harness=harnesses["a"],
                            lane="a", max_turns=4),
                "b": _agent(server, clients["b"], harness=harnesses["b"],
                            lane="b", max_turns=4),
            }
            traces = await asyncio.gather(
                run_bash_qa(agents["a"], tasks["a"]),
                run_bash_qa(agents["b"], tasks["b"]),
            )
        return traces, runtimes

    traces, runtimes = _run(scenario())

    # Each channel holds exactly its own arm-bash report — zero cross-talk.
    for lane, detail in (("a", "lane-a"), ("b", "lane-b")):
        doc = _export(channels[lane])
        assert doc["arms"]["bash"]["reports"] == 1
        events = doc["arms"]["bash"]["events"]
        assert len(events) == 1
        assert events[0]["provenance"] == "agent_output"
        assert events[0]["detail"] == detail
        assert doc["arms"]["ptc"]["events"] == []
        assert factories[lane] == [tasks[lane].data]

    # Distinct wrapper locations: each lane's delivered PATH differs.
    paths = {}
    for lane in "ab":
        tool_msgs = _tool_bodies(clients[lane])
        path_msg = next(m for m in tool_msgs if m["tool_call_id"] == "call_path")
        paths[lane] = str(path_msg.get("content") or "")
    assert paths["a"] != paths["b"]
    assert paths["a"] and paths["b"]
    # Parent PATH untouched.
    assert os.environ.get("PATH") == parent_path
    # Distinct real runtimes, all teardown-complete: no owned dirs, no live
    # session registrations.
    assert len(runtimes) == 2
    assert runtimes[0].workdir != runtimes[1].workdir
    for runtime in runtimes:
        assert not runtime.workdir.exists()
        assert runtime.stopped
    assert server.sessions == {} and server.state_sessions == {}
    for trace in traces:
        assert trace.ok
        assert trace.num_turns == 3


def test_real_occurrence_cache_no_rescan(monkeypatch, tmp_path, server):
    """Two identical outputs under distinct issuing occurrences -> 2 events,
    not 1 or 3; empty gate probes don't count; a later request re-carrying
    pinned results adds 0 events and 0 extra ack lines."""
    channels: list = []

    def factory(data):
        channel = QaChannel()
        channels.append(channel)
        return channel

    binding = BashQaBinding()
    harness = _qa_harness(factory, binding)
    task = ProbeTask(TaskData(prompt="Run the steps."), qa_binding=binding)
    payload = {"kind": "other", "detail": "same twice"}
    cmd = f"{REPORT_TOOL} '{json.dumps(payload)}'"
    scripted = ScriptedClient([
        _tool_step("call_one", "bash", {"command": cmd}),
        _tool_step("call_two", "bash", {"command": cmd}),
        _bash_call("printf 'tail\\n'"),
        _text_step("done"),
    ])
    agent = _agent(server, scripted, harness=harness, max_turns=5)

    async def scenario():
        _patch_runtimes(monkeypatch, tmp_path, [])
        async with server:
            return await run_bash_qa(agent, task)

    trace = _run(scenario())

    doc = _export(channels[0])
    events = [e for e in doc["arms"]["bash"]["events"] if e["type"] == "report"]
    assert doc["arms"]["bash"]["reports"] == 2
    assert len(events) == 2
    # Pinned results re-carried in later history are NOT re-scanned: each
    # delivered result carries exactly one appended receipt.
    tool_msgs = _tool_bodies(scripted)
    for call_id in ("call_one", "call_two"):
        sent = [m for m in tool_msgs if m["tool_call_id"] == call_id]
        assert sent, f"call {call_id} never reached the model"
        for message in sent:
            content = str(message.get("content") or "")
            assert content.count(ACK) == 1, (
                f"{call_id}: receipt count {content.count(ACK)} — "
                "pinned re-delivery must not re-consume or re-append"
            )
    assert scripted.calls == 4
    assert harness.last_result.exit_code == 0
    assert trace.ok


def test_real_cancellation_leaves_no_owned_state(monkeypatch, tmp_path, server):
    """A cancelled launch mid-flight leaves 0 owned wrapper dirs, 0 session
    registrations, and the spent channel unexported-but-consistent."""
    channels: list = []

    def factory(data):
        channel = QaChannel()
        channels.append(channel)
        return channel

    binding = BashQaBinding()
    harness = _qa_harness(factory, binding)
    task = ProbeTask(TaskData(prompt="Run the steps."), qa_binding=binding)

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
                    {"role": "assistant", "tool_calls": [{
                        "id": "call_x", "type": "function",
                        "function": {"name": "bash", "arguments": arguments}}]},
                    "tool_calls", self.calls)
            entered.set()
            await blocked.wait()
            return _response(
                AssistantMessage(content="released"),
                {"role": "assistant", "content": "released"},
                "stop", self.calls,
            )

    scripted = BlockingClient([_text_step("never")])
    parent_path = os.environ.get("PATH")

    async def scenario():
        _patch_runtimes(monkeypatch, tmp_path, runtimes := [])
        async with server:
            assert server.tunnel is None
            assert server.base_url.startswith("http://127.0.0.1:")
            agent = _agent(server, scripted, harness=harness, max_turns=4)
            running = asyncio.create_task(run_bash_qa(agent, task))
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
        return runtimes

    runtimes = _run(scenario())

    assert server.sessions == {} and server.state_sessions == {}
    for runtime in runtimes:
        assert not runtime.workdir.exists()
        leftover = list(tmp_path.rglob(REPORT_TOOL))
        assert leftover == []
    assert os.environ.get("PATH") == parent_path
    assert scripted.calls == 2
    with pytest.raises(ValueError):
        channels[0]._claim_launch()
