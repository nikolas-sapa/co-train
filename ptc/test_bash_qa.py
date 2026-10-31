"""Unit, lifecycle and strict-admission tests for `ptc/bash_qa.py`.

`test_harness_qa.py` covered the PTC arm; this file covers the Bash arm's
opt-in reporting composition (`spec/bash-launch-reporting.md`): the paired
`BashQaBinding` / `BashQaTaskMixin` / `QaBashHarness` / `QaBashHarnessConfig`
surface plus `run_bash_qa`. Everything uses the real framework classes
(`Request`, `Trace`, `Task`, `Agent`, `SubprocessRuntime`, `TaskError`) and a
real `QaChannel`. The only fakes are the two declared unit boundaries:

* the delegate — `BashHarness.launch` is stubbed where a real subprocess
  program is out of unit scope (the real end-to-end Bash route belongs to the
  integration worker);
* `agent.run` — replaced inside `run_bash_qa` tests with a driver that runs
  the real task/harness lifecycle (setup -> launch -> rewrites -> finalize)
  without provisioning a rollout.

No model endpoint, no server, no MCP discovery, no subprocess execution.
The product module is imported inside test bodies: a missing or incomplete
implementation fails the test outright rather than skipping.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verifiers.v1.agent import Agent
from verifiers.v1.clients import EvalClientConfig, ModelContext
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.configs.retries import RetryConfig
from verifiers.v1.errors import TaskError
from verifiers.v1.graph import MessageNode
from verifiers.v1.harnesses.bash.harness import (
    BashHarness,
    CompactionConfig,
)
from verifiers.v1.runtimes import (
    PrimeConfig,
    ProgramResult,
    SubprocessConfig,
    SubprocessRuntime,
)
from verifiers.v1.task import Task, TaskData
from verifiers.v1.trace import AgentInfo, Trace, TraceTask
from verifiers.v1.types import (
    AssistantMessage,
    Request,
    SystemMessage,
    Tool,
    ToolCall,
    ToolMessage,
    UserMessage,
    content_text,
)
from verifiers.v1.utils.decorators import discover_decorated

from ptc.sql_qa import (
    BASH_REPORT,
    MAX_REPORTS_PER_ARM,
    QaChannel,
    REPORT_MARKER,
    REPORT_PROMPT,
    REPORT_REFUSED,
    REPORT_TOOL,
    report_ack,
)
from ptc.test_harness import ENDPOINT, SECRET

REPO_ROOT = Path(__file__).resolve().parents[1]
INTERCEPT_URL = "http://127.0.0.1:9/tool"


def _mod():
    """Import the product module inside the test call: a missing
    implementation is a failure, never a skip."""
    import ptc.bash_qa as bash_qa

    return bash_qa


def _ctx() -> ModelContext:
    return ModelContext(model="test-model", client=EvalClientConfig())


def _runtime(workdir: Path) -> SubprocessRuntime:
    """A real `SubprocessRuntime` object with a real workdir but no start():

    launch needs subprocess/workdir, not a provisioned box."""
    runtime = SubprocessRuntime(SubprocessConfig())
    runtime.workdir = workdir
    workdir.mkdir(parents=True, exist_ok=True)
    return runtime


def _trace(task, agent) -> Trace:
    return Trace(
        task=TraceTask(
            type=type(task).__name__,
            data=task.data,
            key=task.key,
            hash=task.hash,
        ),
        agent=AgentInfo(config=agent.config),
    )


def _agent(*, harness_config=None, runtime_config=None,
           max_turns: int | None = 4, retries: int = 0) -> Agent:
    return Agent(AgentConfig(
        model="test-model",
        harness=harness_config,
        runtime=runtime_config or SubprocessConfig(),
        max_turns=max_turns,
        retries=RetryConfig(max_retries=retries),
    ))


class _RecordingBase(Task):
    """Task base that proves the mixin's setup/finalize chain into super()."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_calls: list = []
        self.finalize_calls: list = []

    async def setup(self, trace, runtime):
        self.setup_calls.append(trace)

    async def finalize(self, trace, runtime):
        self.finalize_calls.append(trace)


def _task_type(bash_qa, base=Task):
    class _Task(bash_qa.BashQaTaskMixin, base):
        pass

    return _Task


def _system() -> SystemMessage:
    return SystemMessage(content="sys")


def _user() -> UserMessage:
    return UserMessage(content="go")


def _assistant_call(call_id: str) -> AssistantMessage:
    return AssistantMessage(tool_calls=[
        ToolCall(id=call_id, name="bash", arguments='{"command":"true"}')
    ])


def _tool_result(call_id: str, content) -> ToolMessage:
    return ToolMessage(tool_call_id=call_id, content=content)


def _marker(detail: str = "x") -> str:
    return (REPORT_MARKER
            + '{"kind": "other", "detail": "' + detail + '"}')


def _report_request(detail: str, *, call_id: str = "c1",
                    prefix: list | None = None) -> Request:
    """One assistant `bash` call issuing one tool result carrying the marker."""
    return Request(messages=[
        _system(), _user(), *(prefix or []),
        _assistant_call(call_id),
        _tool_result(call_id, "out\n" + _marker(detail) + "\n"),
    ])


def _report_events(channel: QaChannel) -> list:
    return [e for e in channel.events if e["type"] == "report"]


def _content(message) -> str:
    return content_text(message.content)


def _commit(trace: Trace, messages: list) -> None:
    """Commit messages onto the trace's real node graph, in order."""
    for message in messages:
        parent = len(trace.nodes) - 1 if trace.nodes else None
        trace.nodes.append(MessageNode(
            parent=parent,
            message=message,
            sampled=isinstance(message, AssistantMessage),
        ))


# ---------------------------------------------------------------------------
# Config + constructor: private marker, clone safety, pairing, resume.
# ---------------------------------------------------------------------------

def test_config_private_marker_absent_from_dump_and_schema():
    """`_qa_required` is a PrivateAttr: it marks intent for the constructor but
    must never appear in a serialized config or its JSON schema."""
    bash_qa = _mod()
    config = bash_qa.QaBashHarnessConfig(edit=False)
    assert getattr(config, "_qa_required", False) is False
    dumped = config.model_dump()
    assert "_qa_required" not in dumped
    assert "qa_required" not in dumped
    assert "_qa_required" not in config.model_json_schema().get(
        "properties", {})


def test_enabled_harness_marks_a_copy_and_clone_refuses(tmp_path):
    """An enabled harness copies the supplied config and marks ITS copy: the
    caller's config stays unmarked, `model_copy` preserves the private marker,
    and reconstructing `type(h)(marked_copy)` without factory AND binding
    refuses before a single factory call or action."""
    bash_qa = _mod()
    binding = bash_qa.BashQaBinding()
    calls = []

    def factory(data):
        calls.append(data)
        return QaChannel()

    config = bash_qa.QaBashHarnessConfig(edit=False)
    harness = bash_qa.QaBashHarness(
        config, qa_factory=factory, qa_binding=binding)

    assert harness.config is not config
    assert getattr(harness.config, "_qa_required", False) is True
    assert getattr(config, "_qa_required", False) is False

    cloned = harness.config.model_copy(
        update={"skills": [tmp_path / "no-such-skill"]})
    assert getattr(cloned, "_qa_required", False) is True
    with pytest.raises(Exception):
        type(harness)(cloned)
    assert calls == [], "a refused reconstruction must not touch the factory"


def test_constructor_pairing_and_unsupported_config():
    """Pairing is both-or-neither, noncallables are rejected, and skills /
    compaction configs are refused at construction time."""
    bash_qa = _mod()
    binding = bash_qa.BashQaBinding()
    config = bash_qa.QaBashHarnessConfig(edit=False)

    # Disabled construction is legal.
    assert bash_qa.QaBashHarness(config) is not None
    # Half a pairing is not.
    with pytest.raises(Exception):
        bash_qa.QaBashHarness(config, qa_factory=lambda data: QaChannel())
    with pytest.raises(Exception):
        bash_qa.QaBashHarness(config, qa_binding=binding)
    with pytest.raises(Exception):
        bash_qa.QaBashHarness(
            config, qa_factory=object(), qa_binding=binding)

    with pytest.raises(Exception):
        bash_qa.QaBashHarness(
            bash_qa.QaBashHarnessConfig(edit=False, skills=[Path("/x")]),
            qa_factory=lambda data: QaChannel(), qa_binding=binding)
    with pytest.raises(Exception):
        bash_qa.QaBashHarness(
            bash_qa.QaBashHarnessConfig(
                edit=False, compaction=CompactionConfig()),
            qa_factory=lambda data: QaChannel(), qa_binding=binding)


def test_supports_resume_is_off():
    """Resumed rollouts are out of scope: the harness must say so."""
    bash_qa = _mod()
    assert bash_qa.QaBashHarness.SUPPORTS_RESUME is False


def test_mixin_requires_binding_and_exposes_interceptor():
    """`qa_binding` is a required kwarg; `_qa_rewrite` must be a real
    task-discovered `@intercept` (framework discovers on the task only)."""
    bash_qa = _mod()
    task_cls = _task_type(bash_qa)
    binding = bash_qa.BashQaBinding()
    with pytest.raises(TypeError):
        task_cls(TaskData(prompt="go"))
    task = task_cls(TaskData(prompt="go"), qa_binding=binding)
    hooks = discover_decorated(task, "intercept")
    names = {fn.__name__ for fn in hooks}
    assert "_qa_rewrite" in names


# ---------------------------------------------------------------------------
# Entry point: permit, admission, run lifecycle.
# ---------------------------------------------------------------------------

def test_task_setup_without_entry_permit_refuses(tmp_path):
    """The private permit is required BEFORE the underlying setup runs: a
    direct `task.setup` (what a bare `agent.run` would reach) refuses without
    touching the caller's own setup, and leaves no live route."""
    bash_qa = _mod()
    binding = bash_qa.BashQaBinding()
    task = _task_type(bash_qa, base=_RecordingBase)(
        TaskData(prompt="go"), qa_binding=binding)
    agent = _agent()
    trace = _trace(task, agent)
    runtime = _runtime(tmp_path / "rt")

    with pytest.raises(Exception):
        asyncio.run(task.setup(trace, runtime))
    assert task.setup_calls == [], (
        "the permit check must run before super().setup")
    # No registration survived: a real tool result now fails closed.
    with pytest.raises(TaskError):
        task._qa_rewrite(_report_request("x"), trace)


def _qa_agent(bash_qa, binding, factory, *, config=None, **agent_kw):
    config = config or bash_qa.QaBashHarnessConfig(edit=False)
    agent = _agent(harness_config=config, **agent_kw)
    agent.harness = bash_qa.QaBashHarness(
        config, qa_factory=factory, qa_binding=binding)
    return agent


def _stubbed_run(agent, body):
    """Replace `agent.run` at the unit boundary with a lifecycle driver."""
    calls = []

    async def run(task, **kwargs):
        calls.append(task)
        return await body(task)

    agent.run = run
    return calls


def test_run_bash_qa_refuses_unsupported_before_run(tmp_path):
    """Every admission refusal happens before `agent.run` is invoked and
    before the factory is called: wrong pairing, disabled harness, non-string
    or absent prompt, task skills, toolsets, non-subprocess runtime, unbounded
    or nonpositive turn limits, and nonzero retries."""
    bash_qa = _mod()
    binding = bash_qa.BashQaBinding()
    created = []

    def factory(data):
        created.append(data)
        return QaChannel()

    reached = []

    async def never(task, **kwargs):
        reached.append(task)
        raise RuntimeError("agent.run must not be reached")

    def refuses(agent, task):
        agent.run = never
        with pytest.raises(Exception):
            asyncio.run(bash_qa.run_bash_qa(agent, task))

    def qa_task(data=None, *, binding=binding, base=Task):
        return _task_type(bash_qa, base=base)(
            data or TaskData(prompt="go"), qa_binding=binding)

    # Task and harness disagree about the binding.
    refuses(_qa_agent(bash_qa, bash_qa.BashQaBinding(), factory),
            qa_task())
    # The task is not the mixin at all.
    refuses(_qa_agent(bash_qa, binding, factory), Task(TaskData(prompt="go")))
    # The harness carries no reporting intent.
    agent = _agent()
    agent.harness = bash_qa.QaBashHarness(bash_qa.QaBashHarnessConfig(edit=False))
    refuses(agent, qa_task())
    # A Messages prompt is a replay, not a string opening prompt.
    refuses(_qa_agent(bash_qa, binding, factory),
            qa_task(TaskData(prompt=[UserMessage(content="hi")])))
    refuses(_qa_agent(bash_qa, binding, factory),
            qa_task(TaskData(prompt=None)))
    # Task-declared skills are unsupported.
    refuses(_qa_agent(bash_qa, binding, factory),
            qa_task(TaskData(prompt="go", skills=[tmp_path])))
    # Task-declared toolsets are unsupported (MCP is out of scope).

    class ToolsetTask(_task_type(bash_qa)):
        @classmethod
        def toolsets(cls, config):
            return [object()]

    refuses(_qa_agent(bash_qa, binding, factory),
            ToolsetTask(TaskData(prompt="go"), qa_binding=binding))
    # Only a subprocess runtime is supported.
    refuses(_qa_agent(bash_qa, binding, factory,
                      runtime_config=PrimeConfig()), qa_task())
    # The rollout needs a finite positive turn budget and zero retries.
    refuses(_qa_agent(bash_qa, binding, factory, max_turns=None), qa_task())
    refuses(_qa_agent(bash_qa, binding, factory, max_turns=0), qa_task())
    refuses(_qa_agent(bash_qa, binding, factory, retries=1), qa_task())
    # edit/search are unsupported settings checked at entry.
    refuses(_qa_agent(bash_qa, binding, factory,
                      config=bash_qa.QaBashHarnessConfig(
                          edit=True, search=False)), qa_task())
    refuses(_qa_agent(bash_qa, binding, factory,
                      config=bash_qa.QaBashHarnessConfig(
                          edit=False, search=True)), qa_task())

    assert created == [], "a refused entry must never call the factory"
    assert reached == [], "a refused entry must never reach agent.run"


def test_run_bash_qa_full_unit_lifecycle(tmp_path, monkeypatch):
    """The happy path at unit boundaries: permit reaches task setup, the
    factory is called exactly once with the original `task.data` object, the
    delegate sees a launch-local copy carrying the reporting prompt plus the
    forwarded interception URL, the owned wrapper sits first on the effective
    PATH during the delegate only, and everything is restored after."""
    bash_qa = _mod()
    binding = bash_qa.BashQaBinding()
    created, received = [], []

    def factory(data):
        received.append(data)
        channel = QaChannel()
        created.append(channel)
        return channel

    agent = _qa_agent(bash_qa, binding, factory)
    harness = agent.harness
    task = _task_type(bash_qa, base=_RecordingBase)(
        TaskData(prompt="go"), qa_binding=binding)
    runtime = _runtime(tmp_path / "rt")

    delegated = []
    host_path = os.environ.get("PATH")

    async def delegate(self, ctx, trace, runtime, endpoint, secret,
                       mcp_urls, data, tool_interception_url=None):
        owned = set(Path(runtime.workdir).iterdir()) - pre_existing
        owned_dir = next(iter(owned)) if owned else None
        delegated.append({
            "data": data,
            "url": tool_interception_url,
            "env_path": runtime.env.get("PATH"),
            "owned": owned,
            "wrapper": owned_dir is not None
            and (owned_dir / REPORT_TOOL).is_file(),
        })
        # The route is "active" only while launch is in flight: the real
        # consume/rewrite runs here, inside the delegate.
        result = task._qa_rewrite(_report_request("first"), trace)
        assert result is not None
        return ProgramResult(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(BashHarness, "launch", delegate)

    async def body(task):
        trace = _trace(task, agent)
        await task.setup(trace, runtime)
        await harness.launch(
            _ctx(), trace, runtime, ENDPOINT, SECRET, {}, task.data,
            tool_interception_url=INTERCEPT_URL)
        await task.finalize(trace, runtime)
        return trace

    pre_existing = set(runtime.workdir.iterdir())
    _stubbed_run(agent, body)
    trace = asyncio.run(bash_qa.run_bash_qa(agent, task))
    assert trace is not None

    # Original setup/finalize behavior preserved.
    assert task.setup_calls == [trace]
    assert task.finalize_calls == [trace]

    # Factory: exactly once, with the exact original TaskData object.
    assert len(received) == 1
    assert received[0] is task.data
    assert task.data.system_prompt is None, "task data must not be mutated"

    # Delegate: one call, forwarded interception URL, launch-local prompt copy.
    entry, = delegated
    assert entry["url"] == INTERCEPT_URL
    seen_data = entry["data"]
    assert seen_data is not task.data
    assert seen_data.prompt == "go"
    assert REPORT_PROMPT in seen_data.system_prompt
    assert BASH_REPORT in seen_data.system_prompt

    # The owned wrapper dir was first on PATH during the delegate only.
    owned_dir, = entry["owned"]
    assert entry["wrapper"], "report_defect wrapper missing during delegate"
    assert Path(entry["env_path"].split(os.pathsep)[0]) == owned_dir
    assert "PATH" not in runtime.env, "PATH presence must be restored"
    assert not owned_dir.exists(), "the owned wrapper dir must be removed"
    assert set(runtime.workdir.iterdir()) == pre_existing
    assert os.environ.get("PATH") == host_path

    # The report landed on the caller-owned channel with output provenance.
    channel, = created
    reports = _report_events(channel)
    assert len(reports) == 1
    assert reports[0]["arm"] == "bash"
    assert reports[0]["provenance"] == "agent_output"
    assert reports[0]["detail"] == "first"

    # The route is closed and the permit cleared: a late event raises
    # fail-closed without mutating the channel, and setup refuses too.
    with pytest.raises(TaskError):
        task._qa_rewrite(_report_request("late"), trace)
    assert _report_events(channel) == reports
    with pytest.raises(Exception):
        asyncio.run(task.setup(_trace(task, agent), runtime))


def test_run_bash_qa_clears_permit_on_aborted_setup(tmp_path, monkeypatch):
    """When the framework never finalizes (setup aborts mid-run), the entry
    point still clears every registration owned by its permit."""
    bash_qa = _mod()
    binding = bash_qa.BashQaBinding()
    agent = _qa_agent(bash_qa, binding, lambda data: QaChannel())
    task = _task_type(bash_qa)(TaskData(prompt="go"), qa_binding=binding)
    runtime = _runtime(tmp_path / "rt")
    monkeypatch.setattr(BashHarness, "launch",
                        lambda *a, **k: pytest.fail("unreachable"))

    class Boom(Exception):
        pass

    async def body(task):
        trace = _trace(task, agent)
        await task.setup(trace, runtime)
        raise Boom("framework aborted after setup")

    _stubbed_run(agent, body)
    with pytest.raises(Boom):
        asyncio.run(bash_qa.run_bash_qa(agent, task))

    trace = _trace(task, agent)
    with pytest.raises(TaskError):
        task._qa_rewrite(_report_request("x"), trace)
    with pytest.raises(Exception):
        asyncio.run(task.setup(trace, runtime))


# ---------------------------------------------------------------------------
# Launch admission and cleanup.
# ---------------------------------------------------------------------------

def test_launch_admission_refusals(tmp_path, monkeypatch):
    """Launch refuses -- before the factory and before the delegate -- on a
    missing registration, a stale/different trace, an empty interception URL,
    a non-subprocess runtime, and a factory returning a non-QaChannel or a
    QaChannel subclass (exact type required)."""
    bash_qa = _mod()
    binding = bash_qa.BashQaBinding()
    created = []
    agent = _qa_agent(bash_qa, binding, lambda data: created.append(
        QaChannel()) or created[-1])
    harness = agent.harness
    task = _task_type(bash_qa)(TaskData(prompt="go"), qa_binding=binding)
    runtime = _runtime(tmp_path / "rt")

    delegated = []

    async def delegate(*a, **k):
        delegated.append(k)

    monkeypatch.setattr(BashHarness, "launch", delegate)

    async def drive(task):
        registered = _trace(task, agent)
        other = _trace(task, agent)
        await task.setup(registered, runtime)

        # A trace that was never registered.
        with pytest.raises(ValueError):
            await harness.launch(
                _ctx(), other, runtime, ENDPOINT, SECRET, {}, task.data,
                tool_interception_url=INTERCEPT_URL)
        # An empty / missing tool-interception URL.
        with pytest.raises(ValueError):
            await harness.launch(
                _ctx(), registered, runtime, ENDPOINT, SECRET, {}, task.data)
        # A second launch on the same registration refuses: one shot per
        # trace, even after the first attempt itself refused.
        with pytest.raises(ValueError):
            await harness.launch(
                _ctx(), registered, runtime, ENDPOINT, SECRET, {}, task.data,
                tool_interception_url=INTERCEPT_URL)

        # A non-subprocess runtime refuses TypeError on a FRESH ready
        # registration (the first trace's launch slot is already spent).
        registered2 = _trace(task, agent)
        await task.setup(registered2, runtime)
        fake = SimpleNamespace(config=PrimeConfig(), env={}, workdir=None)
        with pytest.raises(TypeError):
            await harness.launch(
                _ctx(), registered2, fake, ENDPOINT, SECRET, {}, task.data,
                tool_interception_url=INTERCEPT_URL)

        await task.finalize(registered, runtime)
        await task.finalize(registered2, runtime)

    _stubbed_run(agent, drive)
    asyncio.run(bash_qa.run_bash_qa(agent, task))
    assert delegated == []
    assert created == [], "no refusal may reach the channel factory"


def test_launch_factory_shape_errors(tmp_path, monkeypatch):
    """The factory may raise (propagates) and must return exactly QaChannel:
    a subclass or a wrong type is a launch refusal before the delegate."""
    bash_qa = _mod()
    binding = bash_qa.BashQaBinding()

    class SubChannel(QaChannel):
        pass

    delegated = []

    async def delegate(*a, **k):
        delegated.append(k)

    monkeypatch.setattr(BashHarness, "launch", delegate)

    class Boom(Exception):
        pass

    for factory, expected in (
        (lambda data: "not a channel", TypeError),
        (lambda data: SubChannel(), Exception),
        (lambda data: (_ for _ in ()).throw(Boom()), Boom),
    ):
        agent = _qa_agent(bash_qa, binding, factory)
        task = _task_type(bash_qa)(
            TaskData(prompt="go"), qa_binding=binding)
        runtime = _runtime(tmp_path / f"rt-{expected.__name__}")

        async def body(task, agent=agent, runtime=runtime):
            trace = _trace(task, agent)
            await task.setup(trace, runtime)
            try:
                await agent.harness.launch(
                    _ctx(), trace, runtime, ENDPOINT, SECRET, {},
                    task.data, tool_interception_url=INTERCEPT_URL)
            finally:
                await task.finalize(trace, runtime)

        _stubbed_run(agent, body)
        with pytest.raises(expected):
            asyncio.run(bash_qa.run_bash_qa(agent, task))

    assert delegated == []


def test_launch_restores_existing_path_and_owns_cleanup(tmp_path, monkeypatch):
    """When `runtime.env` already carries PATH, the launch prepends the owned
    dir to that value and restores it exactly; the wrapper directory is
    created under `runtime.workdir`, carries `report_defect`, and is removed."""
    bash_qa = _mod()
    binding = bash_qa.BashQaBinding()
    agent = _qa_agent(bash_qa, binding, lambda data: QaChannel())
    task = _task_type(bash_qa)(TaskData(prompt="go"), qa_binding=binding)
    runtime = _runtime(tmp_path / "rt")
    runtime.env["PATH"] = "/orig/bin"

    seen = {}

    async def delegate(self, ctx, trace, runtime, endpoint, secret,
                       mcp_urls, data, tool_interception_url=None):
        seen["path"] = runtime.env["PATH"]
        owned = [p for p in Path(runtime.workdir).iterdir()
                 if p.is_dir() and p.name not in before]
        seen["owned"] = owned
        seen["wrapper"] = bool(owned) and (
            owned[0] / REPORT_TOOL).is_file()
        return ProgramResult(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(BashHarness, "launch", delegate)
    before = {p.name for p in runtime.workdir.iterdir()}

    async def body(task):
        trace = _trace(task, agent)
        await task.setup(trace, runtime)
        await agent.harness.launch(
            _ctx(), trace, runtime, ENDPOINT, SECRET, {}, task.data,
            tool_interception_url=INTERCEPT_URL)
        await task.finalize(trace, runtime)
        return trace

    _stubbed_run(agent, body)
    asyncio.run(bash_qa.run_bash_qa(agent, task))

    owned_dir, = seen["owned"]
    assert seen["path"] == f"{owned_dir}{os.pathsep}/orig/bin"
    assert seen["wrapper"], "report_defect wrapper missing during delegate"
    assert runtime.env["PATH"] == "/orig/bin"
    assert not owned_dir.exists()


def test_launch_rejects_harness_path_override(tmp_path, monkeypatch):
    """An enabled harness whose own resolved env carries PATH would override
    the prepend: that config is refused before the delegate runs."""
    bash_qa = _mod()
    binding = bash_qa.BashQaBinding()
    config = bash_qa.QaBashHarnessConfig(edit=False, env={"PATH": "/evil"})
    agent = _qa_agent(bash_qa, binding, lambda data: QaChannel(),
                      config=config)
    task = _task_type(bash_qa)(TaskData(prompt="go"), qa_binding=binding)
    runtime = _runtime(tmp_path / "rt")

    delegated = []

    async def delegate(*a, **k):
        delegated.append(k)

    monkeypatch.setattr(BashHarness, "launch", delegate)

    async def body(task):
        trace = _trace(task, agent)
        await task.setup(trace, runtime)
        try:
            await agent.harness.launch(
                _ctx(), trace, runtime, ENDPOINT, SECRET, {}, task.data,
                tool_interception_url=INTERCEPT_URL)
        finally:
            await task.finalize(trace, runtime)

    _stubbed_run(agent, body)
    with pytest.raises(Exception):
        asyncio.run(bash_qa.run_bash_qa(agent, task))
    assert delegated == []
    assert "PATH" not in runtime.env


def test_launch_failure_and_cancel_restore_and_spend(tmp_path, monkeypatch):
    """A delegate failure or a cancellation still restores PATH presence,
    removes the owned directory, and leaves the claimed channel spent: a
    second launch on a fresh harness instance refuses."""
    bash_qa = _mod()
    binding = bash_qa.BashQaBinding()
    shared = QaChannel()
    agent = _qa_agent(bash_qa, binding, lambda data: shared)
    task = _task_type(bash_qa)(TaskData(prompt="go"), qa_binding=binding)
    runtime = _runtime(tmp_path / "rt")

    class SetupBoom(RuntimeError):
        pass

    calls = []

    async def failing(self, ctx, trace, runtime, endpoint, secret,
                      mcp_urls, data, tool_interception_url=None):
        calls.append(runtime.env.get("PATH"))
        raise SetupBoom("post-claim failure")

    monkeypatch.setattr(BashHarness, "launch", failing)

    async def body(task):
        trace = _trace(task, agent)
        await task.setup(trace, runtime)
        with pytest.raises(SetupBoom):
            await agent.harness.launch(
                _ctx(), trace, runtime, ENDPOINT, SECRET, {}, task.data,
                tool_interception_url=INTERCEPT_URL)
        await task.finalize(trace, runtime)
        return trace

    _stubbed_run(agent, body)
    asyncio.run(bash_qa.run_bash_qa(agent, task))

    assert "PATH" not in runtime.env
    assert set(runtime.workdir.iterdir()) == set()
    assert len(calls) == 1

    # The channel is spent: a different enabled harness instance cannot claim
    # it, before any delegate call.
    binding2 = bash_qa.BashQaBinding()
    other = _qa_agent(bash_qa, binding2, lambda data: shared)
    task2 = _task_type(bash_qa)(TaskData(prompt="go"), qa_binding=binding2)

    async def body2(task):
        trace = _trace(task, other)
        await task.setup(trace, runtime)
        with pytest.raises(ValueError):
            await other.harness.launch(
                _ctx(), trace, runtime, ENDPOINT, SECRET, {}, task.data,
                tool_interception_url=INTERCEPT_URL)
        await task.finalize(trace, runtime)
        return trace

    _stubbed_run(other, body2)
    asyncio.run(bash_qa.run_bash_qa(other, task2))
    assert len(calls) == 1

    # Cancellation takes the same cleanup path.
    binding2 = bash_qa.BashQaBinding()
    agent3 = _qa_agent(bash_qa, binding2, lambda data: QaChannel())
    task3 = _task_type(bash_qa)(TaskData(prompt="go"), qa_binding=binding2)

    async def cancelled(*a, **k):
        raise asyncio.CancelledError()

    monkeypatch.setattr(BashHarness, "launch", cancelled)

    async def body3(task):
        trace = _trace(task, agent3)
        await task.setup(trace, runtime)
        with pytest.raises(asyncio.CancelledError):
            await agent3.harness.launch(
                _ctx(), trace, runtime, ENDPOINT, SECRET, {}, task.data,
                tool_interception_url=INTERCEPT_URL)
        await task.finalize(trace, runtime)
        return trace

    _stubbed_run(agent3, body3)
    asyncio.run(bash_qa.run_bash_qa(agent3, task3))
    assert "PATH" not in runtime.env
    assert set(runtime.workdir.iterdir()) == set()


def test_concurrent_same_runtime_refused(tmp_path, monkeypatch):
    """Two launches may not drive the same runtime object at once: while the
    first is parked inside the delegate, the second refuses instead of
    queueing behind it."""
    bash_qa = _mod()
    binding = bash_qa.BashQaBinding()
    agent = _qa_agent(bash_qa, binding, lambda data: QaChannel())
    task = _task_type(bash_qa)(TaskData(prompt="go"), qa_binding=binding)
    runtime = _runtime(tmp_path / "rt")

    entered = asyncio.Event()
    release = asyncio.Event()
    delegated = []

    async def parked(self, ctx, trace, runtime, endpoint, secret,
                     mcp_urls, data, tool_interception_url=None):
        delegated.append(trace)
        entered.set()
        await asyncio.wait_for(release.wait(), timeout=10.0)
        return ProgramResult(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(BashHarness, "launch", parked)

    async def body(task):
        trace_a, trace_b = _trace(task, agent), _trace(task, agent)
        await task.setup(trace_a, runtime)
        await task.setup(trace_b, runtime)
        first = asyncio.create_task(agent.harness.launch(
            _ctx(), trace_a, runtime, ENDPOINT, SECRET, {}, task.data,
            tool_interception_url=INTERCEPT_URL))
        await asyncio.wait_for(entered.wait(), timeout=5.0)
        with pytest.raises(Exception):
            await agent.harness.launch(
                _ctx(), trace_b, runtime, ENDPOINT, SECRET, {}, task.data,
                tool_interception_url=INTERCEPT_URL)
        release.set()
        result = await first
        assert result.exit_code == 0
        await task.finalize(trace_a, runtime)
        await task.finalize(trace_b, runtime)
        return trace_a

    _stubbed_run(agent, body)
    asyncio.run(bash_qa.run_bash_qa(agent, task))
    assert len(delegated) == 1


def test_same_runtime_across_bindings_refused(tmp_path, monkeypatch):
    """Runtime exclusivity is about the box, not the pairing: two fully
    independent task/harness/binding triples share ONE runtime object; the
    second launch refuses before any delegate call or PATH mutation while
    the first is parked, and the first still owns and cleans PATH."""
    bash_qa = _mod()
    entered = asyncio.Event()
    release = asyncio.Event()
    delegated = []
    host_path = os.environ.get("PATH")
    runtime = _runtime(tmp_path / "rt")
    pre_existing = set(runtime.workdir.iterdir())

    async def parked(self, ctx, trace, runtime, endpoint, secret,
                     mcp_urls, data, tool_interception_url=None):
        delegated.append(self)
        entered.set()
        await asyncio.wait_for(release.wait(), timeout=10.0)
        return ProgramResult(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(BashHarness, "launch", parked)

    def pairing():
        binding = bash_qa.BashQaBinding()
        channel = QaChannel()
        agent = _qa_agent(bash_qa, binding, lambda data: channel)
        task = _task_type(bash_qa)(
            TaskData(prompt="go"), qa_binding=binding)
        return channel, agent, task

    channel_a, agent_a, task_a = pairing()
    channel_b, agent_b, task_b = pairing()
    refused = []

    async def first(task):
        trace = _trace(task, agent_a)
        await task.setup(trace, runtime)
        await agent_a.harness.launch(
            _ctx(), trace, runtime, ENDPOINT, SECRET, {}, task.data,
            tool_interception_url=INTERCEPT_URL)
        await task.finalize(trace, runtime)
        return trace

    async def second(task):
        trace = _trace(task, agent_b)
        await task.setup(trace, runtime)
        await asyncio.wait_for(entered.wait(), timeout=10.0)
        path_during = runtime.env.get("PATH")
        try:
            await agent_b.harness.launch(
                _ctx(), trace, runtime, ENDPOINT, SECRET, {}, task.data,
                tool_interception_url=INTERCEPT_URL)
        except Exception as err:
            refused.append(err)
            assert runtime.env.get("PATH") == path_during, (
                "the refused launch must not have mutated PATH")
        release.set()
        await task.finalize(trace, runtime)
        return trace

    _stubbed_run(agent_a, first)
    _stubbed_run(agent_b, second)

    async def go():
        return await asyncio.wait_for(asyncio.gather(
            bash_qa.run_bash_qa(agent_a, task_a),
            bash_qa.run_bash_qa(agent_b, task_b)), timeout=20.0)

    asyncio.run(go())

    refused_error, = refused
    assert isinstance(refused_error, ValueError)
    assert delegated == [agent_a.harness], (
        "only the first launch may reach the delegate")
    assert channel_a.events == () and channel_b.events == ()
    assert "PATH" not in runtime.env
    assert set(runtime.workdir.iterdir()) == pre_existing
    assert os.environ.get("PATH") == host_path


def test_effective_path_honors_present_empty_value(tmp_path, monkeypatch):
    """Effective PATH is by PRESENCE: a runtime PATH present-but-empty keeps
    its empty base (no silent host PATH inheritance), and a host PATH of ""
    is the base when the runtime lacks PATH. Restore preserves presence
    exactly. Runs inside the active delegate; no real subprocess."""
    bash_qa = _mod()
    seen = []

    async def delegate(self, ctx, trace, runtime, endpoint, secret,
                       mcp_urls, data, tool_interception_url=None):
        owned, = set(Path(runtime.workdir).iterdir())
        seen.append({
            "owned": owned,
            "parts": runtime.env["PATH"].split(os.pathsep),
        })
        return ProgramResult(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(BashHarness, "launch", delegate)
    host_path = os.environ.get("PATH")

    # Case 1: runtime.env PATH is present but empty.
    binding = bash_qa.BashQaBinding()
    channel = QaChannel()
    agent = _qa_agent(bash_qa, binding, lambda data: channel)
    task = _task_type(bash_qa)(TaskData(prompt="go"), qa_binding=binding)
    runtime = _runtime(tmp_path / "rt-a")
    runtime.env["PATH"] = ""

    _stubbed_run(agent, _driver_body(agent, runtime))
    asyncio.run(bash_qa.run_bash_qa(agent, task))

    entry = seen[0]
    assert Path(entry["parts"][0]) == entry["owned"]
    assert all(p == "" for p in entry["parts"][1:]), (
        "an explicit empty PATH must not silently inherit the host PATH")
    if host_path:
        assert host_path.split(os.pathsep)[0] not in entry["parts"][1:]
    assert runtime.env["PATH"] == "", "PATH presence restored exactly"

    # Case 2: no runtime PATH; the host PATH is present but empty.
    binding2 = bash_qa.BashQaBinding()
    channel2 = QaChannel()
    agent2 = _qa_agent(bash_qa, binding2, lambda data: channel2)
    task2 = _task_type(bash_qa)(
        TaskData(prompt="go"), qa_binding=binding2)
    runtime2 = _runtime(tmp_path / "rt-b")
    assert "PATH" not in runtime2.env
    monkeypatch.setenv("PATH", "")

    _stubbed_run(agent2, _driver_body(agent2, runtime2))
    asyncio.run(bash_qa.run_bash_qa(agent2, task2))

    entry2 = seen[1]
    assert Path(entry2["parts"][0]) == entry2["owned"]
    assert all(p == "" for p in entry2["parts"][1:]), (
        "an empty host PATH must not be replaced by os.defpath or dropped")
    assert "PATH" not in runtime2.env


def test_two_overlapping_launches_isolated(tmp_path, monkeypatch):
    """True async overlap on two independent bindings: each launch gets its
    own wrapper location and its own channel records only its own report --
    zero cross-channel events, parent PATH untouched."""
    bash_qa = _mod()
    barrier = asyncio.Barrier(2)
    tasks_by_harness = {}

    async def parked(self, ctx, trace, runtime, endpoint, secret,
                     mcp_urls, data, tool_interception_url=None):
        # True overlap: both launches are parked inside their active route
        # before either consumes.
        await asyncio.wait_for(barrier.wait(), timeout=10.0)
        task, tag = tasks_by_harness[self]
        result = task._qa_rewrite(_report_request(tag), trace)
        assert result is not None
        return ProgramResult(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(BashHarness, "launch", parked)
    host_path = os.environ.get("PATH")
    channels = {}

    async def drive(tag):
        binding = bash_qa.BashQaBinding()
        created = []

        def factory(data):
            channel = QaChannel()
            created.append(channel)
            return channel

        agent = _qa_agent(bash_qa, binding, factory)
        task = _task_type(bash_qa)(
            TaskData(prompt="go"), qa_binding=binding)
        runtime = _runtime(tmp_path / f"rt-{tag}")
        tasks_by_harness[agent.harness] = (task, tag)

        async def body(task):
            trace = _trace(task, agent)
            await task.setup(trace, runtime)
            await agent.harness.launch(
                _ctx(), trace, runtime, ENDPOINT, SECRET, {}, task.data,
                tool_interception_url=INTERCEPT_URL)
            # The route closed with launch: a late event refuses without
            # touching the channel.
            with pytest.raises(TaskError):
                task._qa_rewrite(_report_request(f"late-{tag}"), trace)
            await task.finalize(trace, runtime)
            return trace

        _stubbed_run(agent, body)
        trace = await bash_qa.run_bash_qa(agent, task)
        channel, = created
        channels[tag] = channel
        return trace

    async def go():
        return await asyncio.wait_for(
            asyncio.gather(drive("alpha"), drive("beta")), timeout=20.0)

    asyncio.run(go())
    assert [e["detail"] for e in _report_events(channels["alpha"])] == ["alpha"]
    assert [e["detail"] for e in _report_events(channels["beta"])] == ["beta"]
    assert os.environ.get("PATH") == host_path


# ---------------------------------------------------------------------------
# The request rewrite: probes, occurrences, cache, bounds, closed routes.
# ---------------------------------------------------------------------------

def test_cleanup_failure_surfaces_and_releases_runtime(tmp_path, monkeypatch):
    """Cleanup error stays visible, but PATH and ownership never remain
    claimed: a fresh channel can launch on this same runtime afterward."""
    bash_qa = _mod()
    binding = bash_qa.BashQaBinding()
    channels, owned, traces = [], [], []

    def factory(data):
        channel = QaChannel()
        channels.append(channel)
        return channel

    agent = _qa_agent(bash_qa, binding, factory)
    task = _task_type(bash_qa)(TaskData(prompt="go"), qa_binding=binding)
    runtime = _runtime(tmp_path / "rt")
    runtime.env["PATH"] = "original"
    remove = bash_qa.shutil.rmtree
    refused = []

    def fail_once(path, *args, **kwargs):
        if Path(path) in owned and not refused:
            refused.append(Path(path))
            raise OSError("fixture cleanup refused")
        return remove(path, *args, **kwargs)

    async def delegate(self, ctx, trace, runtime, endpoint, secret,
                       mcp_urls, data, tool_interception_url=None):
        directory = Path(runtime.env["PATH"].split(os.pathsep)[0])
        assert (directory / REPORT_TOOL).is_file()
        owned.append(directory)
        traces.append(trace)
        return ProgramResult(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(bash_qa.shutil, "rmtree", fail_once)
    monkeypatch.setattr(BashHarness, "launch", delegate)
    _stubbed_run(agent, _driver_body(agent, runtime))
    try:
        with pytest.raises(OSError, match="fixture cleanup refused"):
            asyncio.run(bash_qa.run_bash_qa(agent, task))
        assert runtime.env["PATH"] == "original"
        before = channels[0].export()
        with pytest.raises(TaskError):
            task._qa_rewrite(_report_request("late"), traces[0])
        assert channels[0].export() == before
        with pytest.raises(ValueError):
            channels[0]._claim_launch()
        # Remove only the fixture-owned directory whose injected deletion failed.
        remove(owned[0])
        asyncio.run(bash_qa.run_bash_qa(agent, task))
        assert len(owned) == 2
        assert runtime.env["PATH"] == "original"
        assert list(runtime.workdir.iterdir()) == []
    finally:
        for directory in owned:
            if directory.exists():
                remove(directory)


def _driver_body(agent, runtime):
    """setup -> launch -> finalize inside the stubbed `agent.run` boundary;
    `_qa_rewrite` assertions live in the delegate probe, not here."""

    async def body(task):
        trace = _trace(task, agent)
        await task.setup(trace, runtime)
        await agent.harness.launch(
            _ctx(), trace, runtime, ENDPOINT, SECRET, {}, task.data,
            tool_interception_url=INTERCEPT_URL)
        await task.finalize(trace, runtime)
        return trace

    return body


def _driven(bash_qa, tmp_path, monkeypatch, *, channel=None, probe=None):
    """Stand up one QA task+agent with a stubbed delegate. `probe(task,
    trace)` runs INSIDE the delegate while the launch's route is still
    active -- the only place `_qa_rewrite` may run, because launch's finally
    invalidates the route on return."""
    binding = bash_qa.BashQaBinding()
    channel = channel or QaChannel()
    agent = _qa_agent(bash_qa, binding, lambda data: channel)
    task = _task_type(bash_qa)(TaskData(prompt="go"), qa_binding=binding)
    runtime = _runtime(tmp_path)

    async def delegate(self, ctx, trace, runtime, endpoint, secret,
                       mcp_urls, data, tool_interception_url=None):
        if probe is not None:
            probe(task, trace)
        return ProgramResult(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(BashHarness, "launch", delegate)
    return binding, channel, agent, task, runtime


def test_probe_then_real_result_is_one_event(tmp_path, monkeypatch):
    """Empty synthetic gate probes are ignored and never cached: a probe, a
    non-tool tail and an empty tool tail all return None with 0 events; the
    real marker result then records exactly 1, and replaying it adds 0."""
    bash_qa = _mod()

    def probe(task, trace):
        # Probe shapes the framework sends before execution.
        probe_tail = Request(messages=[
            _system(), _user(), _assistant_call("c1"),
            _tool_result("c1", ""),
        ])
        probe_nontool = Request(messages=[
            _system(), _user(), _assistant_call("c1"),
        ])
        assert task._qa_rewrite(probe_tail, trace) is None
        assert task._qa_rewrite(probe_nontool, trace) is None
        assert _report_events(channel) == []

        request = _report_request("real")
        rewritten = task._qa_rewrite(request, trace)
        assert rewritten is not None
        reports = _report_events(channel)
        assert len(reports) == 1
        assert reports[0]["provenance"] == "agent_output"

        # The same occurrence replayed raw does not rescan or resubmit.
        replayed = task._qa_rewrite(request, trace)
        assert _report_events(channel) == reports
        assert replayed is not None
        assert _content(replayed.messages[-1]) == _content(
            rewritten.messages[-1])

    binding, channel, agent, task, runtime = _driven(
        bash_qa, tmp_path / "rt", monkeypatch, probe=probe)
    _stubbed_run(agent, _driver_body(agent, runtime))
    asyncio.run(bash_qa.run_bash_qa(agent, task))


def test_rewrite_only_touches_the_tail_and_carries_receipt(
        tmp_path, monkeypatch):
    """A rewritten request preserves message count, types, tools, call IDs and
    names; only the current tail's content changes, keeping the original
    output as an exact prefix of the fixed receipt."""
    bash_qa = _mod()

    def probe(task, trace):
        original = "out\n" + _marker("kept") + "\n"
        tools = [Tool(name="bash", description="the bash tool")]
        request = Request(
            messages=[
                _system(), _user(), _assistant_call("c1"),
                _tool_result("c1", original),
            ],
            tools=tools,
        )
        result = task._qa_rewrite(request, trace)
        assert result is not None
        assert result is not request
        assert len(result.messages) == len(request.messages)
        assert result.tools == tools
        for before, after in zip(request.messages[:-1], result.messages[:-1]):
            assert after == before
        tail = result.messages[-1]
        assert type(tail) is ToolMessage
        assert tail.tool_call_id == "c1"
        assert tail.name == _tool_result("c1", original).name
        rewritten = _content(tail)
        assert rewritten.startswith(original)
        assert report_ack() in rewritten

        # An already-rewritten tail is a no-op: unchanged input returns None.
        again = task._qa_rewrite(result, trace)
        assert again is None
        assert len(_report_events(channel)) == 1

    binding, channel, agent, task, runtime = _driven(
        bash_qa, tmp_path / "rt", monkeypatch, probe=probe)
    _stubbed_run(agent, _driver_body(agent, runtime))
    asyncio.run(bash_qa.run_bash_qa(agent, task))


def test_identical_output_under_distinct_occurrences_is_two_events(
        tmp_path, monkeypatch):
    """Same bytes, same call ID, different issuing assistant position: the
    occurrence key separates them -- exactly 2 events, not 1 and not 3."""
    bash_qa = _mod()

    def probe(task, trace):
        output = "same\n" + _marker("dup") + "\n"
        first = task._qa_rewrite(Request(messages=[
            _system(), _user(),
            _assistant_call("c1"), _tool_result("c1", output),
        ]), trace)
        assert first is not None
        second = task._qa_rewrite(Request(messages=[
            _system(), _user(),
            _assistant_call("c1"), first.messages[-1],
            _assistant_call("c1"), _tool_result("c1", output),
        ]), trace)
        assert second is not None
        assert len(_report_events(channel)) == 2

    binding, channel, agent, task, runtime = _driven(
        bash_qa, tmp_path / "rt", monkeypatch, probe=probe)
    _stubbed_run(agent, _driver_body(agent, runtime))
    asyncio.run(bash_qa.run_bash_qa(agent, task))


def test_two_tool_results_in_one_request_each_consumed_once(
        tmp_path, monkeypatch):
    """The framework presents each new tool result as its own tail boundary:
    two results under one assistant are consumed once each -- replaying the
    first boundary produces no third event."""
    bash_qa = _mod()

    def probe(task, trace):
        assistant = AssistantMessage(tool_calls=[
            ToolCall(id="c1", name="bash", arguments="{}"),
            ToolCall(id="c2", name="bash", arguments="{}"),
        ])
        boundary_one = Request(messages=[
            _system(), _user(), assistant,
            _tool_result("c1", "a\n" + _marker("one") + "\n"),
        ])
        first = task._qa_rewrite(boundary_one, trace)
        assert first is not None
        boundary_two = Request(messages=[
            _system(), _user(), assistant,
            first.messages[-1],
            _tool_result("c2", "b\n" + _marker("two") + "\n"),
        ])
        second = task._qa_rewrite(boundary_two, trace)
        assert second is not None
        assert len(_report_events(channel)) == 2

        replay = task._qa_rewrite(boundary_one, trace)
        assert replay is not None
        assert len(_report_events(channel)) == 2

    binding, channel, agent, task, runtime = _driven(
        bash_qa, tmp_path / "rt", monkeypatch, probe=probe)
    _stubbed_run(agent, _driver_body(agent, runtime))
    asyncio.run(bash_qa.run_bash_qa(agent, task))


def test_pending_rewrite_cap_is_64(tmp_path, monkeypatch):
    """At most 64 uncommitted rewritten occurrences may sit pending: the 65th
    distinct occurrence raises TaskError BEFORE any collector mutation."""
    bash_qa = _mod()

    def probe(task, trace):
        pairs: list = []
        for i in range(64):
            pairs.append(_assistant_call(f"cap-{i}"))
            pairs.append(_tool_result(f"cap-{i}", _marker(f"o{i}") + "\n"))
            result = task._qa_rewrite(
                Request(messages=[_system(), _user(), *pairs]), trace)
            assert result is not None, i
        assert len(_report_events(channel)) == MAX_REPORTS_PER_ARM
        before_refusal = channel.export()

        pairs.append(_assistant_call("cap-64"))
        pairs.append(_tool_result("cap-64", _marker("overflow") + "\n"))
        with pytest.raises(TaskError):
            task._qa_rewrite(
                Request(messages=[_system(), _user(), *pairs]), trace)
        assert channel.export() == before_refusal, (
            "the refused occurrence must not reach the collector")

    binding, channel, agent, task, runtime = _driven(
        bash_qa, tmp_path / "rt", monkeypatch, probe=probe)
    _stubbed_run(agent, _driver_body(agent, runtime))
    asyncio.run(bash_qa.run_bash_qa(agent, task))


def test_committed_prefix_is_pruned(tmp_path, monkeypatch):
    """Once earlier occurrences commit onto the trace they stop counting
    against the pending bound: after 64 pending rewrites, committing them and
    presenting a new tail must succeed instead of refusing."""
    bash_qa = _mod()

    def probe(task, trace):
        pairs: list = []
        committed: list = [_system(), _user()]
        for i in range(64):
            pairs.append(_assistant_call(f"pr-{i}"))
            pairs.append(_tool_result(f"pr-{i}", _marker(f"p{i}") + "\n"))
            result = task._qa_rewrite(
                Request(messages=[_system(), _user(), *pairs]), trace)
            assert result is not None, i
            committed.extend([pairs[-2], result.messages[-1]])
        # Commit the full history in rewritten form onto the real graph.
        _commit(trace, committed)
        before_tail = channel.export()

        tail_assistant = _assistant_call("pr-64")
        tail_result = _tool_result("pr-64", _marker("late") + "\n")
        outcome = task._qa_rewrite(Request(messages=[
            *committed, tail_assistant, tail_result,
        ]), trace)
        assert outcome is not None, (
            "committed occurrences must be pruned from the pending bound")
        assert len(_report_events(channel)) == MAX_REPORTS_PER_ARM
        assert channel.export() != before_tail, (
            "after pruning, the new attempt reaches the bounded collector")

    binding, channel, agent, task, runtime = _driven(
        bash_qa, tmp_path / "rt", monkeypatch, probe=probe)
    _stubbed_run(agent, _driver_body(agent, runtime))
    asyncio.run(bash_qa.run_bash_qa(agent, task))


def test_oversize_observation_stays_under_framework_bound(
        tmp_path, monkeypatch):
    """A ~18000-byte observation plus appended feedback stays under the
    framework's 20000-byte bound, with the original bytes kept as the exact
    prefix of the rewritten tail."""
    bash_qa = _mod()

    def probe(task, trace):
        marker_line = _marker("big")
        filler = "x" * (18_000 - len(marker_line) - 1)
        original = filler + "\n" + marker_line
        request = Request(messages=[
            _system(), _user(), _assistant_call("c1"),
            _tool_result("c1", original),
        ])
        result = task._qa_rewrite(request, trace)
        assert result is not None
        rewritten = _content(result.messages[-1])
        assert rewritten.startswith(original)
        assert len(rewritten.encode("utf-8")) < 20_000
        assert len(_report_events(channel)) == 1

    binding, channel, agent, task, runtime = _driven(
        bash_qa, tmp_path / "rt", monkeypatch, probe=probe)
    _stubbed_run(agent, _driver_body(agent, runtime))
    asyncio.run(bash_qa.run_bash_qa(agent, task))


def test_invalid_report_is_a_bounded_refusal(tmp_path, monkeypatch):
    """A malformed marker payload is a bounded refusal, never a receipt: 0
    accepted reports, one rejection event, original framing preserved, and
    none of the submitted bytes echoed into the appended feedback."""
    bash_qa = _mod()

    def probe(task, trace):
        sentinel = "SENTINEL-9e7f3"
        original = "out\n" + REPORT_MARKER + sentinel + "\n"
        request = Request(messages=[
            _system(), _user(), _assistant_call("c1"),
            _tool_result("c1", original),
        ])
        result = task._qa_rewrite(request, trace)
        assert result is not None
        rewritten = _content(result.messages[-1])
        assert _report_events(channel) == []
        rejected = [e for e in channel.events
                    if e["type"] == "report_rejected"]
        assert len(rejected) == 1
        appended = rewritten[len(original):]
        assert REPORT_REFUSED in appended
        assert sentinel not in appended
        assert result.messages[-1].tool_call_id == "c1"

    binding, channel, agent, task, runtime = _driven(
        bash_qa, tmp_path / "rt", monkeypatch, probe=probe)
    _stubbed_run(agent, _driver_body(agent, runtime))
    asyncio.run(bash_qa.run_bash_qa(agent, task))


def test_quota_nine_attempts_eight_reports(tmp_path, monkeypatch):
    """Nine valid attempts produce exactly 8 accepted reports; the ninth is a
    visible overflow refusal, not a success receipt."""
    bash_qa = _mod()

    def probe(task, trace):
        attempts = MAX_REPORTS_PER_ARM + 1
        results = []
        for i in range(attempts):
            results.append(task._qa_rewrite(_report_request(
                f"q{i}", call_id=f"q{i}", prefix=[
                    m for j in range(i) for m in (
                        _assistant_call(f"q{j}"),
                        results[j].messages[-1],
                    )
                ]), trace))
        assert all(r is not None for r in results)
        reports = _report_events(channel)
        assert len(reports) == MAX_REPORTS_PER_ARM
        overflow = [e for e in channel.events if e["type"] == "overflow"]
        assert len(overflow) == 1
        assert overflow[0]["reason"] == "report_cap"
        assert report_ack() not in _content(
            results[-1].messages[-1]).splitlines()[-1]

    binding, channel, agent, task, runtime = _driven(
        bash_qa, tmp_path / "rt", monkeypatch, probe=probe)
    _stubbed_run(agent, _driver_body(agent, runtime))
    asyncio.run(bash_qa.run_bash_qa(agent, task))


def test_near_prefix_lines_record_nothing(tmp_path, monkeypatch):
    """Forgery shape: a line that almost matches the marker prefix records 0
    events; only the exact prefix counts, always as `agent_output`."""
    bash_qa = _mod()

    def probe(task, trace):
        near = "COTRAIN_QA_REPORTX" + _marker() + "\n"
        request = Request(messages=[
            _system(), _user(), _assistant_call("c1"),
            _tool_result("c1", "out\n" + near),
        ])
        result = task._qa_rewrite(request, trace)
        assert result is None or _content(result.messages[-1]) == \
            _content(request.messages[-1])
        assert channel.events == ()

    binding, channel, agent, task, runtime = _driven(
        bash_qa, tmp_path / "rt", monkeypatch, probe=probe)
    _stubbed_run(agent, _driver_body(agent, runtime))
    asyncio.run(bash_qa.run_bash_qa(agent, task))


# ---------------------------------------------------------------------------
# Disabled path: zero QA footprint, proven in an isolated interpreter.
# ---------------------------------------------------------------------------

def test_disabled_path_never_imports_sql_qa(tmp_path):
    """The baseline path must not touch `ptc.sql_qa` -- not at module import,
    not at construction, not across a disabled launch. Proven in an isolated
    interpreter (-I -B), never claimed in-process where another test may have
    imported it already."""
    script = (
        "import asyncio, sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "import ptc.bash_qa as bq\n"
        "assert 'ptc.sql_qa' not in sys.modules, 'import pulled sql_qa'\n"
        "from verifiers.v1.harnesses.bash.harness import BashHarness\n"
        "from verifiers.v1.runtimes import ProgramResult, SubprocessConfig\n"
        "from verifiers.v1.runtimes.subprocess import SubprocessRuntime\n"
        "from verifiers.v1.clients import EvalClientConfig, ModelContext\n"
        "from verifiers.v1.task import TaskData\n"
        "from verifiers.v1.trace import Trace, TraceTask, AgentInfo\n"
        "from verifiers.v1.configs.agent import AgentConfig\n"
        "from pathlib import Path\n"
        "import tempfile\n"
        "calls = []\n"
        "async def stub(self, ctx, trace, runtime, endpoint, secret,"
        " mcp_urls, data, tool_interception_url=None):\n"
        "    calls.append(data)\n"
        "    assert 'ptc.sql_qa' not in sys.modules, 'delegate saw sql_qa'\n"
        "    assert 'PATH' not in runtime.env\n"
        "    return ProgramResult(exit_code=0, stdout='', stderr='')\n"
        "BashHarness.launch = stub\n"
        "harness = bq.QaBashHarness(bq.QaBashHarnessConfig())\n"
        "assert 'ptc.sql_qa' not in sys.modules, 'ctor pulled sql_qa'\n"
        "with tempfile.TemporaryDirectory() as wd:\n"
        "    runtime = SubprocessRuntime(SubprocessConfig())\n"
        "    runtime.workdir = Path(wd)\n"
        "    data = TaskData(prompt='go')\n"
        "    trace = Trace(task=TraceTask(type='T', data=data),"
        " agent=AgentInfo(config=AgentConfig(model='m')))\n"
        "    ctx = ModelContext(model='m', client=EvalClientConfig())\n"
        "    result = asyncio.run(harness.launch("
        "ctx, trace, runtime, 'http://e', 's', {}, data))\n"
        "    assert result.exit_code == 0\n"
        "    assert calls == [data]\n"
        "    assert list(Path(wd).iterdir()) == []\n"
        "assert 'ptc.sql_qa' not in sys.modules, 'launch pulled sql_qa'\n"
        "print('LAZY-OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script],
        capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    assert "LAZY-OK" in proc.stdout
