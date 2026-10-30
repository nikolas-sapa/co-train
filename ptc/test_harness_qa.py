"""The defect-report channel through the real `PTCHarness.launch` entrypoint.

`test_sql_qa_integration.py` proved the collector binding on `sql_arms`' own
runners. This file attacks the other seam `spec/agent-defect-escalation-harness.md`
opens: keyword-only `qa_factory` on `PTCHarness` itself, so a real rollout's
`launch` can file allegations through the program catalog. Everything here goes
through the real `harness.launch` against the scripted SSE policy from
`test_harness.py` — no model endpoint, no server, no real MCP discovery (faked
at `_mcp_catalog`, never networked), no Docker.

`test_launch_collects_real_report` is the spec's behavioral-control target:
mutating `QaChannel.submit` into a no-op must turn it red, because it asserts
the accepted event through the caller-owned channel, not through a stand-in.
"""

from __future__ import annotations

import asyncio
import copy
import gc
import hashlib
import json
import pickle
import subprocess
import sys
import weakref
from contextlib import closing
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("verifiers")

from verifiers.v1.clients import EvalClientConfig, ModelContext  # noqa: E402
from verifiers.v1.runtimes import ProgramResult  # noqa: E402
from verifiers.v1.task import TaskData  # noqa: E402

from bench.score import execution_accuracy  # noqa: E402
from ptc.harness import PTCHarness, PTCHarnessConfig  # noqa: E402
from ptc.runtime import Catalog  # noqa: E402
from ptc.sql_arms import build_probe_db, connect_readonly, sql_catalog  # noqa: E402
from ptc.sql_qa import (  # noqa: E402
    QaChannel,
    REPORT_PROMPT,
    REPORT_TOOL,
    report_ack,
)
from ptc.test_harness import (  # noqa: E402
    ENDPOINT,
    SECRET,
    Policy,
    _assistant,
    _sse,
)

RECEIPT = "report received (unverified allegation; outcome unchanged)"

REPO_ROOT = Path(__file__).resolve().parents[1]


def _harness(policy: Policy, catalog: Catalog, *, qa_factory=None,
             max_turns: int = 8) -> PTCHarness:
    return PTCHarness(
        PTCHarnessConfig(max_turns=max_turns),
        catalog=catalog,
        transport=policy.transport(),
        qa_factory=qa_factory,
    )


def _launch(harness: PTCHarness, data: TaskData, *,
            mcp_urls: dict | None = None):
    """The real entrypoint under test, as a coroutine. Sequential callers run
    it with `asyncio.run`; concurrent callers gather several on one loop."""
    ctx = ModelContext(model="test-model", client=EvalClientConfig())
    return harness.launch(
        ctx, trace=None, runtime=None, endpoint=ENDPOINT, secret=SECRET,
        mcp_urls=mcp_urls or {}, data=data,
    )


def _channel_factory(created: list, received: list):
    """The normal factory shape: one fresh caller-owned channel per launch.

    `created` belongs to the caller — the harness never sees the list — so a
    test can assert on channels after launch. `received` records the object
    the factory was handed so the test can check it IS the launch's exact
    `TaskData`, not merely an equal one.
    """
    def factory(data: TaskData) -> QaChannel:
        received.append(data)
        channel = QaChannel()
        created.append(channel)
        return channel
    return factory


class RoutingPolicy(Policy):
    """A `Policy` that picks its script per launch, keyed on the user prompt.

    `Policy` alone answers in request order, which is meaningless once two
    `launch` coroutines interleave on one transport. Routing each request by
    its user message keeps every concurrent launch deterministic.
    """

    def __init__(self, by_prompt: dict):
        super().__init__()
        self.by_prompt = {prompt: list(turns)
                          for prompt, turns in by_prompt.items()}

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            body = json.loads(request.content)
            self.bodies.append(body)
            prompt = body["messages"][1]["content"]
            turns = self.by_prompt.get(prompt) or []
            turn = turns.pop(0) if turns else _assistant(None)
            return httpx.Response(
                200, content=_sse(turn).encode(),
                headers={"content-type": "text/event-stream"},
            )
        return httpx.MockTransport(handle)


def _report_events(channel: QaChannel) -> list:
    return [e for e in channel.events if e["type"] == "report"]


def _tool_contents(body: dict) -> list:
    return [m["content"] for m in body["messages"]
            if m.get("role") == "tool"]


# ---------------------------------------------------------------------------
# Criterion 1: the default route is inert — no report names, no QA import.
# ---------------------------------------------------------------------------

def test_launch_default_inert(tmp_path):
    """No factory means byte-for-byte the pre-QA arm: unchanged caller catalog,
    no `report_defect` in the prompt or the program, exactly one registered
    tool — and the optional module is never even imported, which the fresh
    interpreter below proves rather than claims."""
    db = build_probe_db(tmp_path / "probe.sqlite")
    catalog = sql_catalog(str(db))
    names_before = catalog.names()
    policy = Policy(_assistant("print(1)"), _assistant(None))
    harness = _harness(policy, catalog)  # qa_factory defaults to None

    result = asyncio.run(_launch(harness, TaskData(prompt="count rows")))
    assert result.exit_code == 0

    system = policy.bodies[0]["messages"][0]["content"]
    assert REPORT_TOOL not in system
    assert REPORT_PROMPT not in system
    assert "defect" not in system
    tools = policy.bodies[0]["tools"]
    assert [t["function"]["name"] for t in tools] == ["run_program"]
    assert catalog.names() == names_before


def test_launch_default_never_imports_the_optional_module():
    """A fresh interpreter running a default launch must not touch
    `ptc.sql_qa`: the spec makes the import lazy so the default native source
    closure cannot silently acquire a missing dependency. An in-process check
    cannot see this — an earlier test may already have imported it — so it is
    proven on a real subprocess instead."""
    script = (
        "import asyncio, json, sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "import httpx\n"
        "from verifiers.v1.clients import EvalClientConfig, ModelContext\n"
        "from verifiers.v1.task import TaskData\n"
        "from ptc.harness import PTCHarness, PTCHarnessConfig\n"
        "from ptc.runtime import Catalog\n"
        "def handle(request):\n"
        "    stream = ('data: ' + json.dumps({'choices': ["
        "{'delta': {'content': 'done'}}]}) + '\\n\\n' + 'data: [DONE]\\n\\n')\n"
        "    return httpx.Response(200, content=stream.encode(),"
        " headers={'content-type': 'text/event-stream'})\n"
        "harness = PTCHarness(PTCHarnessConfig(), catalog=Catalog(),"
        " transport=httpx.MockTransport(handle))\n"
        "ctx = ModelContext(model='m', client=EvalClientConfig())\n"
        "asyncio.run(harness.launch(ctx, trace=None, runtime=None,"
        " endpoint='http://interception.invalid/base', secret='s',"
        " mcp_urls={}, data=TaskData(prompt='go')))\n"
        "assert 'ptc.sql_qa' not in sys.modules, list(sys.modules)\n"
        "print('INERT-OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    assert "INERT-OK" in proc.stdout


def test_launch_default_copyable():
    """The opt-out default must stay an ordinary value: a harness built with
    no transport and no `qa_factory` deep-copies and pickle-round-trips, because
    the concurrency primitives reporting needs are only allocated on the
    enabled path. Asserted on the public surface — distinct harness and
    catalog, equal config — not on the tracking fields themselves."""
    default = PTCHarness(PTCHarnessConfig())
    for clone in (copy.deepcopy(default),
                  pickle.loads(pickle.dumps(default))):
        assert clone is not default
        assert clone.catalog is not default.catalog
        assert clone.catalog.names() == default.catalog.names()
        assert clone.config == default.config


# ---------------------------------------------------------------------------
# Criterion 2: one real report, end to end through launch + restricted Python.
# ---------------------------------------------------------------------------

def test_launch_collects_real_report(tmp_path):
    """The mutation target of criterion 8. Scripted SSE drives the real launch:
    the program files one allegation through the injected catalog callback and
    reads the real probe database in the same program. Exactly one event must
    land on the caller-owned channel with `catalog_callback` provenance, and
    the fixed receipt plus the SQL row must reach the model's next request.
    If `submit` stops storing accepted reports this goes red — the assertion
    is on the channel, not on wire text a no-op could still print."""
    db = build_probe_db(tmp_path / "probe.sqlite")
    catalog = sql_catalog(str(db))
    created, received = [], []
    program = (
        'receipt = report_defect(kind="task_defect", '
        'detail="the question hides the count")\n'
        'rows = execute_sql(query="SELECT name FROM emp WHERE id = 1")\n'
        "print(receipt)\n"
        'print(rows[0]["name"])'
    )
    policy = Policy(_assistant(program), _assistant(None))
    harness = _harness(
        policy, catalog, qa_factory=_channel_factory(created, received))
    data = TaskData(prompt="answer and report")
    result = asyncio.run(_launch(harness, data))
    assert result.exit_code == 0

    # The factory was handed the exact TaskData object launch received.
    assert len(received) == 1
    assert received[0] is data

    # Exactly one caller-visible event, carrying the route's provenance.
    channel, = created
    event, = channel.events
    assert event["type"] == "report"
    assert event["arm"] == "ptc"
    assert event["provenance"] == "catalog_callback"
    assert event["kind"] == "task_defect"
    assert event["detail"] == "the question hides the count"

    # The receipt and the real SQL read both arrived in the next model request.
    assert report_ack() == RECEIPT
    tool, = _tool_contents(policy.bodies[1])
    assert RECEIPT in tool
    assert "Ada" in tool

    # The injection is per-launch: the caller's catalog is not mutated and no
    # report function leaks onto it.
    assert REPORT_TOOL not in catalog.names()

    # Still exactly one registered model tool; reporting lives inside programs.
    tools = policy.bodies[0]["tools"]
    assert [t["function"]["name"] for t in tools] == ["run_program"]

    # The enabled system text carries the shared semantics and the entry name.
    system = policy.bodies[0]["messages"][0]["content"]
    assert REPORT_PROMPT in system
    assert REPORT_TOOL in system

    # The temporary database is still a real, queryable database.
    with closing(connect_readonly(str(db))) as conn:
        assert conn.execute("SELECT COUNT(*) FROM emp").fetchone() == (5,)


# ---------------------------------------------------------------------------
# Criterion 3: bad kinds are visible rejections; the cap holds; turns unchanged.
# ---------------------------------------------------------------------------

def test_launch_bad_report_and_cap(tmp_path):
    """Two sequential enabled launches on one harness. The first submits an
    invalid kind: visible rejection to the model, a `report_rejected` event,
    zero accepted reports. The second submits nine valid reports: eight are
    accepted, the ninth is refused with a visible overflow record — never a
    false receipt."""
    db = build_probe_db(tmp_path / "probe.sqlite")
    created, received = [], []
    bad = 'print(report_defect(kind="not_a_kind", detail="x"))'
    flood = (
        "for i in range(9):\n"
        '    print(report_defect(kind="other", detail="d"))'
    )
    policy = Policy(
        _assistant(bad), _assistant(None),
        _assistant(flood), _assistant(None),
    )
    harness = _harness(
        policy, sql_catalog(str(db)),
        qa_factory=_channel_factory(created, received))
    asyncio.run(_launch(harness, TaskData(prompt="first")))
    asyncio.run(_launch(harness, TaskData(prompt="second")))

    ch_bad, ch_cap = created

    # Invalid kind: nothing accepted, but the refusal is recorded and the
    # model reads it as ordinary rejection data on the next request.
    assert _report_events(ch_bad) == []
    rejected = [e for e in ch_bad.events if e["type"] == "report_rejected"]
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "kind"
    assert rejected[0]["provenance"] == "catalog_callback"
    refusal, = _tool_contents(policy.bodies[1])
    assert refusal.startswith("rejected:")
    assert "kind" in refusal

    # Nine submissions: eight accepted events, then a visible refusal.
    reports = _report_events(ch_cap)
    assert len(reports) == 8
    assert all(e["arm"] == "ptc" and e["provenance"] == "catalog_callback"
               for e in reports)
    overflow = [e for e in ch_cap.events if e["type"] == "overflow"]
    assert overflow and overflow[0]["reason"] == "report_cap"
    capped, = _tool_contents(policy.bodies[3])
    assert capped.startswith("rejected:")
    assert RECEIPT not in capped


def test_launch_reporting_never_increases_the_turn_budget(tmp_path):
    """A report is filed inside a program, inside a turn: the factory wiring
    must not extend the configured model-turn limit. A model that never stops
    calling tools still stops at `max_turns`."""
    db = build_probe_db(tmp_path / "probe.sqlite")
    created, received = [], []
    report_turn = _assistant('print(report_defect(kind="other", detail="x"))')
    policy = Policy(*[report_turn for _ in range(20)])
    harness = _harness(
        policy, sql_catalog(str(db)),
        qa_factory=_channel_factory(created, received), max_turns=3)
    asyncio.run(_launch(harness, TaskData(prompt="flood")))
    assert len(policy.requests) == 3
    assert len(_report_events(created[0])) == 3


# ---------------------------------------------------------------------------
# Criterion 4: collectors are scoped per launch, tracked weakly, never reused.
# ---------------------------------------------------------------------------

def test_launch_scopes_collectors(tmp_path):
    """Four launches on ONE harness — two sequential, two concurrent — each
    file into a distinct caller-owned channel with no crossed events. The
    factory binds channels by the launch's TaskData; RoutingPolicy binds the
    script by the request's prompt, so detail equality proves the binding."""
    db = build_probe_db(tmp_path / "probe.sqlite")
    created, received = [], []
    channels: dict = {}

    def factory(data: TaskData) -> QaChannel:
        received.append(data)
        channel = channels.setdefault(data.prompt, QaChannel())
        created.append(channel)
        return channel

    def report_turn(detail: str):
        return _assistant(
            f'print(report_defect(kind="other", detail={detail!r}))')

    policy = RoutingPolicy({
        name: [report_turn(name), _assistant(None)]
        for name in ("one", "two", "three", "four")
    })
    catalog = sql_catalog(str(db))
    harness = _harness(policy, catalog, qa_factory=factory)

    asyncio.run(_launch(harness, TaskData(prompt="one")))
    asyncio.run(_launch(harness, TaskData(prompt="two")))

    async def pair():
        return await asyncio.gather(
            _launch(harness, TaskData(prompt="three")),
            _launch(harness, TaskData(prompt="four")),
        )
    results = asyncio.run(pair())
    assert all(isinstance(r, ProgramResult) and r.exit_code == 0
               for r in results)

    # Four launches, four distinct caller-owned channels, no sharing.
    assert len(created) == 4
    assert len({id(ch) for ch in created}) == 4
    assert {d.prompt for d in received} == {"one", "two", "three", "four"}
    for prompt, channel in channels.items():
        reports = _report_events(channel)
        assert len(reports) == 1, prompt
        assert reports[0]["detail"] == prompt
        assert reports[0]["provenance"] == "catalog_callback"

    # The caller's catalog was never mutated along the way.
    assert REPORT_TOOL not in catalog.names()


def test_launch_reused_channel_is_refused(tmp_path):
    """One live channel returned twice on one harness refuses the second
    launch before it can make a model request."""
    db = build_probe_db(tmp_path / "probe.sqlite")
    shared = QaChannel()
    received = []

    def factory(data: TaskData) -> QaChannel:
        received.append(data)
        return shared

    policy = Policy(_assistant(None), _assistant(None))
    harness = _harness(
        policy, sql_catalog(str(db)), qa_factory=factory)
    asyncio.run(_launch(harness, TaskData(prompt="first")))
    assert len(policy.requests) == 1

    with pytest.raises(ValueError):
        asyncio.run(_launch(harness, TaskData(prompt="second")))
    assert len(received) == 2
    assert len(policy.requests) == 1, (
        "a refused launch must not reach the model")


class _BarrierTransport(httpx.AsyncBaseTransport):
    """An async transport that parks every request at a release `Event`.

    `Policy`'s `MockTransport` handler answers synchronously, so a `gather`
    over two launches can still run them strictly one-after-another — the same
    coverage as a sequential test. This transport records the request, marks
    `entered`, then holds the response until the test releases it, which makes
    the first launch genuinely in-flight while the second registers."""

    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.requests: list[httpx.Request] = []
        self.bodies: list[dict] = []

    async def handle_async_request(
            self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.bodies.append(json.loads(await request.aread()))
        self.entered.set()
        await self.release.wait()
        return httpx.Response(
            200, content=_sse(_assistant(None)).encode(),
            headers={"content-type": "text/event-stream"},
        )


def test_launch_reused_channel_is_refused_concurrently(tmp_path):
    """Two launches reach real overlap on one loop: the barrier transport
    parks the winner's first model request, and the second launch then
    registers the same live channel and is refused before it can issue a
    request of its own. This observes the reuse rejection under genuine
    in-flight overlap — it claims nothing about the lock mechanics inside the
    implementation."""
    db = build_probe_db(tmp_path / "probe.sqlite")
    shared = QaChannel()
    transport = _BarrierTransport()
    harness = PTCHarness(
        PTCHarnessConfig(),
        catalog=sql_catalog(str(db)),
        transport=transport,
        qa_factory=lambda data: shared,
    )

    async def go():
        tasks = [asyncio.create_task(
            _launch(harness, TaskData(prompt="winner")))]
        results = []
        try:
            await asyncio.wait_for(transport.entered.wait(), timeout=5.0)
            assert not tasks[0].done(), (
                "the barrier released the first launch early")
            tasks.append(asyncio.create_task(
                _launch(harness, TaskData(prompt="reused"))))
            with pytest.raises(ValueError):
                await asyncio.wait_for(tasks[1], timeout=5.0)
            assert not tasks[0].done(), (
                "the reused registration disturbed the blocked launch")
            assert len(transport.requests) == 1, (
                "the refused launch still reached the model")
        finally:
            # Drain every created task so a failure above cannot leak a
            # pending coroutine or an unretrieved exception.
            transport.release.set()
            results.extend(await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=5.0))
        return results

    results = asyncio.run(go())
    assert isinstance(results[0], ProgramResult)
    assert results[0].exit_code == 0
    assert isinstance(results[1], ValueError)
    assert len(transport.requests) == 1


def test_completed_channels_are_not_retained(tmp_path):
    """Tracking is weak, not an owning history: once a launch completes and
    the caller drops its references, the channel must be collectable. A
    harness that keeps finished collectors alive turns the reuse guard into
    unbounded retention — this is the failure the spec calls out by name."""
    db = build_probe_db(tmp_path / "probe.sqlite")
    refs = []

    def factory(data: TaskData) -> QaChannel:
        channel = QaChannel()
        refs.append(weakref.ref(channel))
        return channel

    policy = Policy(_assistant(None))
    harness = _harness(policy, sql_catalog(str(db)), qa_factory=factory)
    result = asyncio.run(_launch(harness, TaskData(prompt="ephemeral")))
    assert result.exit_code == 0
    assert len(refs) == 1
    gc.collect()
    assert refs[0]() is None, (
        "the harness kept a completed collector alive; channel identity "
        "tracking must be weak so reuse checks never retain history")


# ---------------------------------------------------------------------------
# Criterion 5: local or discovered `report_defect` names cannot collide.
# ---------------------------------------------------------------------------

def test_launch_rejects_collisions(tmp_path, monkeypatch):
    """Both collision routes refuse before the first model request, and the
    colliding callable is never invoked. MCP discovery is faked at the
    `_mcp_catalog` seam — the test never opens a socket."""
    db = build_probe_db(tmp_path / "probe.sqlite")

    # Local route: the caller's own catalog already owns the report name.
    local_calls = []

    def local_impostor(*, kind, detail):
        local_calls.append((kind, detail))
        return "impostor"

    created, received = [], []
    policy = Policy(_assistant(None))
    harness = _harness(
        policy, Catalog(tools={REPORT_TOOL: local_impostor}),
        qa_factory=_channel_factory(created, received))
    with pytest.raises(ValueError):
        asyncio.run(_launch(harness, TaskData(prompt="local")))
    assert len(policy.requests) == 0
    assert local_calls == []

    # Discovered route: the fake `_mcp_catalog` hands back a tool named
    # `report_defect`. Awaiting the fake exercises the real merge point.
    mcp_calls = []

    def discovered_impostor(**kwargs):
        mcp_calls.append(kwargs)
        return "impostor"

    async def fake_catalog():
        return ({"report_defect": discovered_impostor}, [],
                {"report_defect": ["kind", "detail"]})

    monkeypatch.setattr(
        "ptc.harness._mcp_catalog",
        lambda urls, stack, timeout: fake_catalog())
    policy = Policy(_assistant(None))
    harness = _harness(
        policy, sql_catalog(str(db)),
        qa_factory=_channel_factory(created, received))
    with pytest.raises(ValueError):
        asyncio.run(_launch(
            harness, TaskData(prompt="discovered"),
            mcp_urls={"srv": "http://mcp.invalid"}))
    assert len(policy.requests) == 0
    assert mcp_calls == []


def test_disabled_launch_keeps_a_local_report_name(tmp_path):
    """'Do not infer activation from a tool's name.' A caller may already own
    a `report_defect` catalog entry; without a factory the launch must call
    THAT function, not refuse and not silently substitute a collector."""
    calls = []

    def theirs(*, kind, detail):
        calls.append((kind, detail))
        return "handled locally"

    policy = Policy(
        _assistant(f'print({REPORT_TOOL}(kind="other", detail="x"))'),
        _assistant(None))
    harness = _harness(policy, Catalog(tools={REPORT_TOOL: theirs}))
    result = asyncio.run(_launch(harness, TaskData(prompt="local only")))
    assert result.exit_code == 0
    assert calls == [("other", "x")]
    tool, = _tool_contents(policy.bodies[1])
    assert tool == "handled locally"


# ---------------------------------------------------------------------------
# Criterion 6: a report then a real failure keeps both; scoring is untouched.
# ---------------------------------------------------------------------------

def test_launch_preserves_failure(tmp_path):
    """A report followed by a real SQL error in one program: the allegation is
    recorded before the program dies, and sqlite's own message is the
    observation the model reads. Independent execution-accuracy on correct and
    incorrect SQL is identical across the reporting launch, and the database
    bytes never change."""
    db = build_probe_db(tmp_path / "probe.sqlite")
    db_bytes = hashlib.sha256(Path(db).read_bytes()).hexdigest()

    class _Task:
        db_path = str(db)
        gold_sql = "SELECT COUNT(*) FROM emp"

    task = _Task()
    correct = execution_accuracy("SELECT COUNT(*) FROM emp", task).score
    incorrect = execution_accuracy("SELECT COUNT(*) FROM dept", task).score
    assert correct == 1.0 and incorrect == 0.0

    created, received = [], []
    program = (
        'print(report_defect(kind="task_defect", detail="allegation"))\n'
        'execute_sql(query="SELECT * FROM missing")'
    )
    policy = Policy(_assistant(program), _assistant(None))
    harness = _harness(
        policy, sql_catalog(str(db)),
        qa_factory=_channel_factory(created, received))
    result = asyncio.run(_launch(harness, TaskData(prompt="go")))

    # The printed receipt is lost with the failed program (declared
    # asymmetry); the recorded allegation is not.
    channel, = created
    reports = _report_events(channel)
    assert len(reports) == 1
    assert reports[0]["detail"] == "allegation"
    assert reports[0]["provenance"] == "catalog_callback"

    assert "no such table: missing" in result.stdout
    tool, = _tool_contents(policy.bodies[1])
    assert "no such table: missing" in tool

    # The scorer is independent of the channel: same numbers, same bytes.
    assert execution_accuracy("SELECT COUNT(*) FROM emp", task).score == correct
    assert execution_accuracy("SELECT COUNT(*) FROM dept", task).score == incorrect
    assert hashlib.sha256(Path(db).read_bytes()).hexdigest() == db_bytes


# ---------------------------------------------------------------------------
# Criterion 7: every bad-factory shape fails explicitly before the wire.
# ---------------------------------------------------------------------------

def test_launch_factory_errors(tmp_path):
    """Noncallable factory, wrong returned type, and a factory that raises:
    each fails explicitly without a model request and without a false
    receipt. Factory exceptions propagate — they are caller configuration,
    not data the launch may swallow."""
    db = build_probe_db(tmp_path / "probe.sqlite")

    policy = Policy(_assistant(None))
    with pytest.raises(TypeError):
        asyncio.run(_launch(
            _harness(policy, sql_catalog(str(db)), qa_factory=object()),
            TaskData(prompt="x")))
    assert len(policy.requests) == 0

    policy = Policy(_assistant(None))
    with pytest.raises(TypeError):
        asyncio.run(_launch(
            _harness(policy, sql_catalog(str(db)),
                     qa_factory=lambda data: "not a channel"),
            TaskData(prompt="x")))
    assert len(policy.requests) == 0

    class FactoryBoom(RuntimeError):
        pass

    def boom(data: TaskData) -> QaChannel:
        raise FactoryBoom("factory exploded")

    policy = Policy(_assistant(None))
    with pytest.raises(FactoryBoom):
        asyncio.run(_launch(
            _harness(policy, sql_catalog(str(db)), qa_factory=boom),
            TaskData(prompt="x")))
    assert len(policy.requests) == 0
