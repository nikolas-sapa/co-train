"""The PTC arm as a `verifiers` Harness: does the restriction survive the loop?

`test_ptc.py` attacks the runtime. This attacks the *harness* — the part that
turns the runtime into an arm a policy can drive. The distinction matters: a
correct runtime wired up wrongly (rejection raised as a crash, catalog shared
between tasks, model calls bypassing the interception endpoint) is still a
broken arm, and none of those failures are visible from `test_ptc.py`.

No server and no model. `httpx.MockTransport` plays the policy, so the loop runs
against a scripted opponent whose tool calls are chosen to be hostile.
"""

from __future__ import annotations

import asyncio
import json

import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

verifiers = pytest.importorskip("verifiers")

from verifiers.v1.clients import EvalClientConfig, ModelContext  # noqa: E402
from verifiers.v1.task import TaskData  # noqa: E402

from ptc.harness import PTCHarness, PTCHarnessConfig  # noqa: E402
from ptc.runtime import Catalog  # noqa: E402

ENDPOINT = "http://interception.invalid/base"
SECRET = "s3cret"


def _assistant(code: str | None, *, raw_args: str | None = None):
    """One scripted assistant turn. `code=None` means "no tool call", which ends
    the loop; `raw_args` bypasses json encoding so malformed arguments can be
    tested."""
    if code is None and raw_args is None:
        message = {"role": "assistant", "content": "done"}
    else:
        args = raw_args if raw_args is not None else json.dumps({"code": code})
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "run_program", "arguments": args},
            }],
        }
    return {"choices": [{"message": message, "finish_reason": "stop"}]}


def _sse(turn: dict) -> str:
    """Render a scripted turn as the SSE stream the harness reads.

    The arm streams, so the mock must stream too. A mock that kept answering with
    one non-streaming JSON body would leave the whole file green against a
    transport production no longer uses.
    """
    message = turn["choices"][0]["message"]
    events: list[dict] = []
    if message.get("content"):
        events.append({"choices": [{"delta": {"content": message["content"]}}]})
    for index, call in enumerate(message.get("tool_calls") or []):
        events.append({"choices": [{"delta": {"tool_calls": [{
            "index": index, "id": call["id"],
            "function": {
                "name": call["function"]["name"],
                "arguments": call["function"]["arguments"],
            },
        }]}}]})
    if not events:
        events.append({"choices": [{"delta": {}}]})
    rendered = "".join(f"data: {json.dumps(e)}\n\n" for e in events)
    return rendered + "data: [DONE]\n\n"


class Policy:
    """A scripted model. Records every request the harness makes."""

    def __init__(self, *turns):
        self.turns = list(turns)
        self.requests: list[httpx.Request] = []
        self.bodies: list[dict] = []

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            self.bodies.append(json.loads(request.content))
            # Past the script, keep answering with "no tool call" so a loop that
            # over-runs its turn budget fails on the assertion, not on StopIteration.
            turn = self.turns.pop(0) if self.turns else _assistant(None)
            return httpx.Response(
                200, content=_sse(turn).encode(),
                headers={"content-type": "text/event-stream"},
            )
        return httpx.MockTransport(handle)


def _run(policy: Policy, catalog: Catalog, *, max_turns: int = 8, prompt="do it",
         system: str | None = None):
    harness = PTCHarness(
        PTCHarnessConfig(max_turns=max_turns),
        catalog=catalog,
        transport=policy.transport(),
    )
    ctx = ModelContext(model="test-model", client=EvalClientConfig())
    data = TaskData(prompt=prompt, system_prompt=system)
    return asyncio.run(harness.launch(
        ctx, trace=None, runtime=None, endpoint=ENDPOINT, secret=SECRET,
        mcp_urls={}, data=data,
    ))


@pytest.fixture
def calls() -> list:
    return []


@pytest.fixture
def catalog(calls) -> Catalog:
    def note(text):
        calls.append(text)
        return len(calls)

    def double(n):
        return n * 2

    def boom():
        raise ZeroDivisionError("tool exploded")

    return Catalog(tools={"note": note, "double": double, "boom": boom})


# --------------------------------------------------------------- it works

def test_a_program_reaches_the_catalog(catalog, calls):
    policy = Policy(_assistant("note('hello')"), _assistant(None))
    result = _run(policy, catalog)
    assert calls == ["hello"]
    assert result.exit_code == 0
    assert "ok" in result.stdout


def test_one_program_can_chain_several_catalog_calls(catalog, calls):
    """PTC's whole claim. An arm that permits one call per turn is typed-tool
    calling with extra steps, not the interface the paper measures."""
    policy = Policy(_assistant("for w in ['a','b','c']:\n    note(double(w))"),
                    _assistant(None))
    _run(policy, catalog)
    assert calls == ["aa", "bb", "cc"]


def test_the_loop_ends_when_the_model_stops_calling_tools(catalog):
    policy = Policy(_assistant(None))
    result = _run(policy, catalog)
    assert len(policy.requests) == 1
    assert "no tool call; loop ends" in result.stdout


def test_max_turns_bounds_the_loop(catalog, calls):
    """A model that never stops must not run forever."""
    policy = Policy(*[_assistant("note('again')") for _ in range(20)])
    _run(policy, catalog, max_turns=3)
    assert len(policy.requests) == 3
    assert calls == ["again"] * 3


# ------------------------------------------------- the restriction holds here

@pytest.mark.parametrize("escape", [
    "import os\nos.system('id')",
    "from subprocess import run\nrun(['id'])",
    "open('/tmp/pwned','w').write('x')",
    "().__class__.__bases__[0].__subclasses__()",
    "note.__globals__['__builtins__']",
])
def test_an_escape_is_rejected_as_data_and_the_loop_survives(catalog, calls, escape):
    """Each of these is a real escape: the first three scored reward 1.0 against
    the `rlm` harness (docs/spike-verifiers.md), which is why this arm exists.
    The rejection must come back as a tool message the model can read, not as an
    exception — a crash would make the restriction a bug rather than part of the
    interface, and a trained model would never learn the boundary."""
    policy = Policy(_assistant(escape), _assistant("note('fallback')"), _assistant(None))
    result = _run(policy, catalog)
    assert "rejected:" in result.stdout
    # The loop continued and the model could still act legally afterwards.
    assert calls == ["fallback"]
    assert len(policy.requests) == 3


def test_the_rejection_is_visible_to_the_model_not_just_to_the_log(catalog):
    """The tool message has to be in the NEXT request's messages, or the model is
    being punished for something it cannot see."""
    policy = Policy(_assistant("import os"), _assistant(None))
    _run(policy, catalog)
    second = policy.bodies[1]["messages"]
    tool_messages = [m for m in second if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0]["content"].startswith("rejected:")
    assert "not permitted" in tool_messages[0]["content"]


def test_a_tool_that_raises_is_reported_without_killing_the_loop(catalog):
    policy = Policy(_assistant("boom()"), _assistant(None))
    result = _run(policy, catalog)
    assert "error: ZeroDivisionError: tool exploded" in result.stdout
    assert len(policy.requests) == 2


def test_malformed_tool_arguments_do_not_crash_the_loop(catalog):
    """Models emit invalid JSON. An empty program is rejected-or-noop, never a
    traceback out of `launch`."""
    policy = Policy(_assistant(None, raw_args="{not json"), _assistant(None))
    result = _run(policy, catalog)
    assert result.exit_code == 0
    assert len(policy.requests) == 2


# ---------------------------------------------------------- the wire contract

def test_every_model_call_goes_through_the_interception_endpoint(catalog):
    """`Harness.launch`'s in-process permission is conditional on exactly this:
    "as long as every model call goes through `endpoint` + `secret`"."""
    policy = Policy(_assistant("note('x')"), _assistant(None))
    _run(policy, catalog)
    assert policy.requests, "no model call was made"
    for request in policy.requests:
        assert str(request.url) == f"{ENDPOINT}/v1/chat/completions"
        assert request.headers["authorization"] == f"Bearer {SECRET}"


def test_sampling_is_not_forwarded(catalog):
    """The interception server applies ctx.sampling as an override onto the body
    (interception/server.py:596). A harness that also sent its own would diverge
    from every other arm in the comparison."""
    policy = Policy(_assistant(None))
    _run(policy, catalog)
    body = policy.bodies[0]
    assert "temperature" not in body and "top_p" not in body and "max_tokens" not in body
    assert body["model"] == "test-model"


def test_the_system_prompt_names_the_catalog_and_the_absence_of_a_shell(catalog):
    policy = Policy(_assistant(None))
    _run(policy, catalog)
    system = policy.bodies[0]["messages"][0]
    assert system["role"] == "system"
    for name in ("boom", "double", "note"):
        assert name in system["content"]
    assert "no shell" in system["content"]


def test_the_task_system_prompt_is_appended_not_dropped(catalog):
    """APPENDS_SYSTEM_PROMPT is True, so resolve_prompt hands back the task's
    system prompt and the harness must actually emit it."""
    policy = Policy(_assistant(None))
    _run(policy, catalog, system="You are terse.")
    assert "You are terse." in policy.bodies[0]["messages"][0]["content"]


def test_only_one_tool_is_offered(catalog):
    """The catalog lives inside the program. Exposing the catalog as sibling
    tools would make this the bash-arm's interface with different names, and the
    comparison would measure nothing."""
    policy = Policy(_assistant(None))
    _run(policy, catalog)
    tools = policy.bodies[0]["tools"]
    assert [t["function"]["name"] for t in tools] == ["run_program"]


def test_two_harnesses_do_not_share_a_catalog():
    """Regression: `catalog` was a class attribute, so every arm in a run held
    the same dict and a second task could call the first task's tools."""
    a, b = Catalog(tools={"only_a": lambda: 1}), Catalog(tools={"only_b": lambda: 2})
    first = PTCHarness(PTCHarnessConfig(), catalog=a, transport=Policy().transport())
    second = PTCHarness(PTCHarnessConfig(), catalog=b, transport=Policy().transport())
    assert first.catalog.names() == {"only_a"}
    assert second.catalog.names() == {"only_b"}


def test_an_empty_catalog_still_produces_a_valid_system_prompt():
    policy = Policy(_assistant(None))
    _run(policy, Catalog())
    assert "(none)" in policy.bodies[0]["messages"][0]["content"]


def test_the_replayed_conversation_is_a_valid_tool_exchange(catalog):
    """Survivor-driven. Dropping the assistant turn, or the tool_call_id echo,
    left every other test green — MockTransport accepts any message list, but a
    real OpenAI-compatible endpoint rejects a `tool` message that answers no
    preceding `tool_calls`. The arm would then fail only against a live model.
    """
    policy = Policy(_assistant("note('x')"), _assistant(None))
    _run(policy, catalog)
    messages = policy.bodies[1]["messages"]
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "tool"]
    assistant, tool = messages[2], messages[3]
    ids = [c["id"] for c in assistant["tool_calls"]]
    assert ids == ["call_1"]
    assert tool["tool_call_id"] in ids


# ------------------------------------------------------------ the plugin contract

def test_verifiers_can_load_this_arm_by_id():
    """The whole point of `ptc/__init__.py`. `--env.agent.harness.id ptc` resolves
    through `_import_plugin` -> module `ptc` -> the one `Harness` subclass in
    `__all__`. If this fails, the arm is unreachable from a real run no matter how
    green the rest of this file is, and the only way to use it would be the fork or
    the monkeypatch the spike ruled out."""
    from verifiers.v1.utils.loaders import harness_class, load_harness

    assert harness_class("ptc") is PTCHarness
    harness = load_harness(PTCHarnessConfig(id="ptc"))
    assert isinstance(harness, PTCHarness)
    # Loaded through the plugin path, so nothing supplied a catalog: it must still
    # be per-instance and empty rather than None or a shared default.
    assert harness.catalog.names() == set()


def test_the_module_exports_exactly_one_harness():
    """`_plugin_class` rejects a module exporting two `Harness` subclasses. Pin the
    surface so adding a second arm here fails here rather than at load time."""
    import ptc

    harnesses = [
        obj for name in ptc.__all__
        if isinstance(obj := getattr(ptc, name), type) and issubclass(obj, verifiers.v1.harness.Harness)
    ]
    assert harnesses == [PTCHarness]


def test_the_runtime_is_importable_without_verifiers():
    """The reason `PTCHarness` is lazy in `__init__.py`. `runtime.py` is stdlib
    only and `test_ptc.py` must run on a bare interpreter; an eager harness import
    in the package __init__ would make `import ptc.runtime` require httpx,
    pydantic and verifiers. Asserted by inspecting the module's own source rather
    than by uninstalling verifiers, which a test cannot do."""
    import ast
    import pathlib

    source = (pathlib.Path(__file__).parent / "__init__.py").read_text()
    top_level_imports = [
        n for n in ast.parse(source).body if isinstance(n, (ast.Import, ast.ImportFrom))
    ]
    modules = {n.module for n in top_level_imports if isinstance(n, ast.ImportFrom)}
    assert "ptc.harness" not in modules, "the harness must not be imported eagerly"
    assert modules == {"ptc.runtime"}


# ------------------------------------------------------- the MCP-derived catalog

def _served_glossary():
    """A real `glossary` MCP server, launched the way a real rollout launches one.

    Not a mock. The three things worth testing here — that discovery yields callable
    catalog entries, that a synchronous program can call an async tool without
    deadlocking the loop it is bridged to, and that the tool's return value reaches
    the model — are all properties of the real client/server pair, and a stub would
    assert only that the stub behaves as written.
    """
    import verifiers.v1 as vf
    from verifiers.v1.mcp import serve

    from glossary.servers.facts import GlossaryToolset

    return serve(GlossaryToolset(vf.ToolsetConfig()))


async def _run_with_mcp(policy: Policy, url: str, **kw):
    """Awaited, not `asyncio.run`: the caller is already inside the loop that serves
    the MCP server, and the harness bridges its tool calls back to that same loop."""
    # tool_timeout is deliberately short. It is the only thing that makes the
    # sync/async bridge falsifiable: running the program on the event loop instead of
    # in a thread deadlocks, and at the 600s default the mutation would look like a
    # hang rather than a failure.
    harness = PTCHarness(PTCHarnessConfig(tool_timeout=10.0), transport=policy.transport())
    ctx = ModelContext(model="test-model", client=EvalClientConfig())
    data = TaskData(prompt=kw.get("prompt", "look it up"))
    return await (harness.launch(
        ctx, trace=None, runtime=None, endpoint=ENDPOINT, secret=SECRET,
        mcp_urls={"facts": url}, data=data,
    ))


def test_an_mcp_tool_becomes_a_catalog_function_a_program_can_call():
    """End to end against a live MCP server: discovery, the sync/async bridge, and
    the observation channel. If this passes, the arm can score on `glossary`; the
    whole comparison rests on it."""
    from glossary.servers.facts import FACTS

    entity, fact = next(iter(FACTS.items()))
    program = f"print(facts_lookup(name={entity!r}))"

    async def go():
        async with _served_glossary() as url:
            policy = Policy(_assistant(program), _assistant(None))
            return await _run_with_mcp(policy, url), policy

    result, policy = asyncio.run(go())
    # The fact came back through the program's printed output...
    assert fact in result.stdout
    # ...and reached the model, which is the only reason it can answer.
    tool_message = [m for m in policy.bodies[1]["messages"] if m.get("role") == "tool"][0]
    assert fact in tool_message["content"]
    # The catalog was advertised by name, discovered rather than configured.
    assert "facts_lookup" in policy.bodies[0]["messages"][0]["content"]


def test_a_program_that_never_calls_the_tool_learns_nothing():
    """The negative control `glossary` is chosen for: its reward is 1.0 only if the
    tool was actually used. An arm that could answer without calling would make the
    environment unable to discriminate between harnesses, which is the whole reason
    it was picked over gsm8k."""
    async def go():
        async with _served_glossary() as url:
            policy = Policy(_assistant("print('a famous person')"), _assistant(None))
            return await _run_with_mcp(policy, url), policy

    result, policy = asyncio.run(go())
    from glossary.servers.facts import FACTS

    assert next(iter(FACTS.values())) not in result.stdout


def test_print_is_the_observation_channel(catalog):
    """Without capture, `print` writes to the harness process's stdout where the
    model cannot see it, and a program that called a tool would return `ok` with the
    result thrown away."""
    policy = Policy(_assistant("print(double(21))"), _assistant(None))
    result = _run(policy, catalog)
    assert "42" in result.stdout
    tool_message = [m for m in policy.bodies[1]["messages"] if m.get("role") == "tool"][0]
    assert tool_message["content"] == "42"


def test_a_silent_program_says_so_rather_than_claiming_success(catalog, calls):
    """`ok` alone would read as "the tool worked" to a model that printed nothing."""
    policy = Policy(_assistant("note('quiet')"), _assistant(None))
    result = _run(policy, catalog)
    assert calls == ["quiet"]
    assert "printed nothing" in result.stdout


def test_captured_output_does_not_leak_between_programs(catalog):
    """Two programs in one rollout. The second must not inherit the first's output,
    or a model that printed once would keep being told it printed."""
    policy = Policy(_assistant("print('first')"), _assistant("print('second')"),
                    _assistant(None))
    _run(policy, catalog)
    tool_messages = [m["content"] for b in policy.bodies for m in b["messages"]
                     if m.get("role") == "tool"]
    assert tool_messages[-1] == "second"


def test_tool_names_a_program_cannot_call_are_separated_out():
    """`facts_lookup` is callable; a hyphenated server name yields `my-tools_lookup`,
    which no program can name. Unit-tested rather than served, because making a real
    server advertise a malformed name means shipping a broken toolset to test with."""
    from ptc.harness import partition_callable

    ok, bad = partition_callable(["facts_lookup", "my-tools_lookup", "ok2", "1bad"])
    assert ok == ["facts_lookup", "ok2"]
    assert bad == ["my-tools_lookup", "1bad"]


def test_the_endpoint_is_not_double_prefixed(catalog):
    """A real interception endpoint already ends in `/v1`. Appending
    `/v1/chat/completions` to it gives `/v1/v1/chat/completions` and a 404 — which the
    whole rest of this file missed, because `MockTransport` answers any path. Only
    running the arm through `compare.py` surfaced it, so both shapes are pinned here."""
    for endpoint, expected in (
        ("http://host/base", "http://host/base/v1/chat/completions"),
        ("http://host/base/v1", "http://host/base/v1/chat/completions"),
        ("http://host/base/v1/", "http://host/base/v1/chat/completions"),
    ):
        policy = Policy(_assistant(None))
        harness = PTCHarness(PTCHarnessConfig(), catalog=catalog,
                             transport=policy.transport())
        ctx = ModelContext(model="m", client=EvalClientConfig())
        asyncio.run(harness.launch(
            ctx, trace=None, runtime=None, endpoint=endpoint, secret=SECRET,
            mcp_urls={}, data=TaskData(prompt="x"),
        ))
        assert str(policy.requests[0].url) == expected, endpoint


def test_a_hanging_program_comes_back_as_a_rejection_the_model_can_read(catalog, calls):
    """The reward-hacking case from `docs/ptc-runtime-review.md`. A program that never
    returns must not stall the episode: the model is told it blew its budget, the loop
    survives, and it can still act legally afterwards. An episode that never completes
    never scores zero, so a hang would be the cheapest reward hack available."""
    policy = Policy(_assistant("while True:\n    pass"),
                    _assistant("note('after')"), _assistant(None))
    harness = PTCHarness(PTCHarnessConfig(program_timeout=0.4), catalog=catalog,
                         transport=policy.transport())
    ctx = ModelContext(model="m", client=EvalClientConfig())
    result = asyncio.run(harness.launch(
        ctx, trace=None, runtime=None, endpoint=ENDPOINT, secret=SECRET,
        mcp_urls={}, data=TaskData(prompt="go"),
    ))
    assert "rejected:" in result.stdout and "budget" in result.stdout
    assert calls == ["after"], "the loop must survive the timeout"
    tool_messages = [m for b in policy.bodies for m in b["messages"]
                     if m.get("role") == "tool"]
    assert "budget" in tool_messages[0]["content"]


def test_the_program_timeout_is_configurable_and_defaults_to_the_runtime_value():
    from ptc.runtime import TIMEOUT

    assert PTCHarnessConfig().program_timeout == TIMEOUT
    assert PTCHarnessConfig(program_timeout=1.5).program_timeout == 1.5


def test_the_prompt_advertises_argument_names_not_bare_names():
    """`_bridge` is keyword-only by design, so a prompt listing bare names leaves the
    model nothing to guess from -- and it guessed positionally in 26 of the first real
    run's 54 PTC tool failures, with 8 more arriving as the same mistake wearing a
    pydantic `Field required`. The names were available the whole time: `connect_mcp`
    returns the schemas and `_mcp_catalog` discarded them."""
    from ptc.harness import SYSTEM, render_catalog, schema_params

    schemas = [{"type": "function", "function": {"name": "ledger_get", "parameters": {
        "type": "object", "properties": {"id": {"type": "string"}},
        "required": ["id"]}}}]
    assert schema_params(schemas) == {"ledger_get": ["id"]}

    rendered = render_catalog(["ledger_get"], {"ledger_get": ["id"]})
    assert rendered == "ledger_get(id=...)"

    prompt = SYSTEM.format(names=rendered)
    assert "ledger_get(id=...)" in prompt
    assert "KEYWORD" in prompt, "the convention must be stated, not just implied"


def test_required_arguments_render_before_optional_ones():
    """A signature in schema-dict order would read `links_to(depth=..., id=...)` and
    invite the model to fill the optional one first."""
    from ptc.harness import schema_params

    schemas = [{"type": "function", "function": {"name": "links_to", "parameters": {
        "type": "object",
        "properties": {"depth": {"type": "integer"}, "id": {"type": "string"}},
        "required": ["id"]}}}]
    assert schema_params(schemas)["links_to"] == ["id", "depth"]


def test_a_bridged_tool_falls_back_to_the_schema_not_to_kwargs():
    """`_bridge` exposes only `**arguments`, so introspecting it yields nothing. If
    `_callable_params` ever claimed a bridged tool takes no arguments, the prompt would
    advertise `ledger_get()` -- worse than a bare name, because it reads as a promise."""
    from ptc.harness import _bridge, _callable_params, render_catalog

    bridged = _bridge("ledger_get", {}, {}, None, 1.0)
    assert _callable_params(bridged) is None
    assert render_catalog(["ledger_get"], {"ledger_get": None}) == "ledger_get(...)"


def test_the_system_prompt_the_model_receives_carries_the_signatures():
    """The integration half: `render_catalog` can be correct while `launch` still
    formats bare names, which is exactly the state the first real run shipped in. This
    reads the prompt off the wire the model saw, not the helper in isolation."""
    def ledger_get(id):  # noqa: A002 -- mirrors the real catalog's argument name
        return {"id": id}

    policy = Policy(_assistant(None))
    _run(policy, Catalog(tools={"ledger_get": ledger_get}))
    prompt = policy.bodies[0]["messages"][0]["content"]
    assert "ledger_get(id=...)" in prompt


def test_the_ptc_arm_streams_like_the_bash_arm_does():
    """Posting `stream: False` made four tasks fail 45 times with 504s behind a
    relay whose gateway timeout only applies to non-streaming requests, while the
    bash arm streamed through `verifiers` and never hit it. Goes red if the arm
    ever stops streaming."""
    policy = Policy(_assistant("print(1)"), _assistant(None))
    _run(policy, Catalog({}))
    assert policy.bodies, "the harness made no request"
    assert all(b["stream"] is True for b in policy.bodies), \
        [b.get("stream") for b in policy.bodies]
