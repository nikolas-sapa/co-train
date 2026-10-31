"""Unit tests for `cotrain_ptc_qa` — the serialized-config PTC activation route.

`ptc/test_harness_qa.py` proved the opt-in report channel inside the real
`PTCHarness.launch`; this file proves the flat canonical plugin ID plus the
runner that claims the Agent, binds a scoped activation record, drives
`agent.run` once on the ORIGINAL task object, and restores everything
afterwards (`spec/ptc-qa-activation.md`).

The product module is the flat root file `cotrain_ptc_qa.py`, imported inside
test bodies: missing code fails, never skips. The only stubbed seams are the
declared unit boundaries — the instance `agent.run` driver (a real
task/harness lifecycle without a rollout) and `PTCHarness.launch` for
isolated factory/guard cases; the delegate may call `self.qa_factory(data)`
and return a `ProgramResult` but claims nothing about old PTC execution. The
claim, ContextVar record, bound guards and channel objects are real. The
delegate bypasses the old loop/launch claim/report callback; the real SDK
integration suite exercises those boundaries.
"""

from __future__ import annotations

import asyncio
import contextvars
import copy
import gc
import sys
import threading
import warnings
from dataclasses import replace
from functools import partial
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verifiers.v1.agent import Agent  # noqa: E402
from verifiers.v1.clients import EvalClientConfig  # noqa: E402
from verifiers.v1.configs.agent import AgentConfig  # noqa: E402
from verifiers.v1.harness import Harness  # noqa: E402
from verifiers.v1.runtimes import PrimeConfig, ProgramResult  # noqa: E402
from verifiers.v1.task import Task, TaskData, TaskTimeout  # noqa: E402
from verifiers.v1.types import UserMessage  # noqa: E402
from verifiers.v1.utils.decorators import intercept  # noqa: E402
from verifiers.v1.utils.loaders import (  # noqa: E402
    harness_class, harness_config_type, import_harness, load_harness,
)

from ptc.harness import PTCHarness, PTCHarnessConfig  # noqa: E402
from ptc.runtime import Catalog  # noqa: E402
from ptc.sql_qa import QaChannel, ReportRejected, report_ack  # noqa: E402
from ptc.test_bash_qa import _ctx, _runtime, _trace  # noqa: E402
from ptc.test_harness import ENDPOINT, SECRET  # noqa: E402

CANONICAL_ID = "cotrain_ptc_qa"
OWNER_ATTR = "_cotrain_ptc_qa_owner"
GUARD = "cotrain_ptc_qa activation refused"


def _mod():
    """Lazy product import: missing code fails, never skips."""
    import cotrain_ptc_qa
    return cotrain_ptc_qa


def _harness_dict(**overrides):
    data = {"id": CANONICAL_ID, "max_turns": 4, "program_timeout": 2.0}
    data.update(overrides)
    return data


def _canonical_cfg(mod, **overrides):
    return mod.ReportingPTCConfig(**_harness_dict(**overrides))


def _agent_config_dict(**overrides):
    """Spec-required serialized AgentConfig: canonical flat ID, subprocess
    runtime, bounded turns, explicit finite timeouts, zero retries, train
    client on an unused probe key."""
    data = {
        "model": "fixture-model",
        "client": {"type": "train", "api_key_var": "PROBE_UNUSED_API_KEY"},
        "harness": _harness_dict(),
        "runtime": {"type": "subprocess"},
        "max_turns": 4,
        "retries": {"max_retries": 0},
        "timeout": {
            "setup": 5.0, "rollout": 15.0, "finalize": 5.0, "scoring": 5.0,
        },
    }
    data.update(overrides)
    return data


def _configured_agent(mod, **overrides):
    """A real Agent through the loader path: unbound ReportingPTCHarness."""
    return Agent(AgentConfig.model_validate(_agent_config_dict(**overrides)))


def _good_factory(calls, created=None):
    def factory(data):
        calls.append(data)
        channel = QaChannel()
        if created is not None:
            created.append(channel)
        return channel
    return factory


def _stub_run(agent, body):
    """Replace `agent.run` at the unit boundary with a driver."""
    calls = []

    async def run(task, **kwargs):
        calls.append(task)
        return await body(task)

    agent.run = run
    return calls


def _record(bound):
    """The activation record reachable through the binding seam."""
    binding = bound._binding
    return binding._record


def _delegate(seen, *, factory_calls=1, report=None):
    """A `PTCHarness.launch` stub — the declared isolated delegate seam."""

    async def delegate(self, ctx, trace, runtime, endpoint, secret,
                       mcp_urls, data):
        seen.append({"ctx": ctx, "trace": trace, "runtime": runtime,
                     "mcp_urls": mcp_urls, "data": data})
        for _ in range(factory_calls):
            channel = self.qa_factory(data)
        if report is not None:
            channel.submit("ptc", kind=report[0], detail=report[1])
        return ProgramResult(exit_code=0, stdout="", stderr="")

    return delegate


def _lifecycle(agent, runtime, captured, task):
    """The unit driver: real task/harness lifecycle, no rollout."""

    async def body(task):
        trace = _trace(task, agent)
        captured["trace"] = trace
        await task.setup(trace, runtime)
        bound = agent.harness
        captured["bound"] = bound
        assert _record(bound).active is True
        await bound.setup(runtime)
        await bound.launch(
            agent.ctx, trace, runtime, ENDPOINT, SECRET, {}, task.data)
        await task.finalize(trace, runtime)
        return trace

    return body


def _activated(tmp_path, mod, agent, task, monkeypatch, *, delegate=None):
    """Unit fixture: stub the PTC delegate and the instance run driver."""
    runtime = _runtime(tmp_path / "rt")
    seen = []
    monkeypatch.setattr(PTCHarness, "launch", delegate or _delegate(seen))
    captured = {}
    run_calls = _stub_run(agent, _lifecycle(agent, runtime, captured, task))
    return runtime, seen, captured, run_calls


def _refuses(mod, agent, task, match, calls):
    """Fixed generic guard error, zero run/factory calls, owned claim released."""
    reached = []

    async def never(task, **kwargs):
        reached.append(task)
        raise RuntimeError("agent.run must not be reached")

    original = agent.harness
    original_owner = getattr(agent, OWNER_ATTR, None)
    agent.run = never
    with pytest.raises(ValueError, match=GUARD):
        asyncio.run(mod.run_configured_ptc_qa(
            agent, task, qa_factory=_good_factory(calls)))
    assert reached == []
    assert calls == []
    assert agent.harness is original
    assert getattr(agent, OWNER_ATTR, None) is original_owner


# --------------------------------------------------------------------------
# Flat plugin resolution and the serialized config surface.
# --------------------------------------------------------------------------

def test_flat_id_resolves_one_harness_and_config():
    """Flat ID resolves exactly one Harness/Config via __all__ + generic
    ancestry; the dotted ID dies at find_spec; the binding seam exists."""
    mod = _mod()

    module = import_harness(CANONICAL_ID)
    exported = [
        obj for name in module.__all__
        if isinstance(obj := getattr(module, name, None), type)
        and issubclass(obj, Harness) and obj is not Harness
    ]
    assert exported == [mod.ReportingPTCHarness]
    assert module.__all__ == ["ReportingPTCHarness"]
    assert harness_class(CANONICAL_ID) is mod.ReportingPTCHarness
    assert harness_config_type(CANONICAL_ID) is mod.ReportingPTCConfig
    assert callable(getattr(mod, "_bind_harness", None))
    with pytest.raises(ModuleNotFoundError):
        import_harness("ptc.harness")

    # The root ptc export is unchanged: activation surfaces stay private.
    import ptc
    assert not hasattr(ptc, "ReportingPTCHarness")
    assert not hasattr(ptc, "run_configured_ptc_qa")


def test_canonical_config_defaults_schema_and_roundtrip():
    """ID is the only serialized change: inherited fields, defaults and
    schema match PTCHarnessConfig; AgentConfig JSON round-trips clean."""
    mod = _mod()

    base = PTCHarnessConfig()
    canon = mod.ReportingPTCConfig()
    assert canon.id == CANONICAL_ID
    assert canon.model_dump() == {**base.model_dump(), "id": CANONICAL_ID}
    assert (canon.model_json_schema()["properties"].keys()
            == base.model_json_schema()["properties"].keys())

    config = AgentConfig.model_validate(_agent_config_dict())
    assert type(config.harness) is mod.ReportingPTCConfig
    assert config.harness.id == CANONICAL_ID
    assert config.client.type == "train"
    assert config.client.api_key_var == "PROBE_UNUSED_API_KEY"

    dump = config.model_dump_json()
    for key in ("_qa_required", "qa_factory", "qa_binding", "_binding",
                "binding", "factory", "channel", "record", "snapshot",
                "owner"):
        assert f'"{key}"' not in dump
        assert key not in canon.model_json_schema()["properties"]

    restored = AgentConfig.model_validate_json(dump)
    assert type(restored.harness) is mod.ReportingPTCConfig
    assert restored.model_dump(mode="json") == config.model_dump(mode="json")


def test_canonical_config_is_strict_typed():
    """Wrong ID, smuggled activation keys and wrong types refuse at
    validation — the inherited extra policy is the contract."""
    mod = _mod()
    with pytest.raises(ValidationError):
        mod.ReportingPTCConfig.model_validate(_harness_dict(id="ptc"))
    with pytest.raises(ValidationError):
        mod.ReportingPTCConfig.model_validate(_harness_dict(id=12345))
    for smuggled in ({"qa_factory": "m:fn"}, {"qa_binding": {}},
                    {"binding": "x"}, {"channel": {}}, {"record": {}},
                    {"snapshot": {}}, {"edit": False}, {"search": False},
                    {"unexpected": 1}, {"max_turns": "not-an-int"}):
        with pytest.raises(ValidationError):
            mod.ReportingPTCConfig.model_validate(_harness_dict(**smuggled))
    with pytest.raises(ValidationError):
        mod.ReportingPTCConfig.model_validate_json(
            '{"id": "cotrain_ptc_qa", "sneak": "key"}')


def test_harness_states_unbound_injection_forged_marked(tmp_path):
    """Unbound setup/launch refuse naming run_configured_ptc_qa; public
    injection kwargs, forged IDs and pre-marked configs refuse; JSON
    reconstruction stays unbound."""
    mod = _mod()
    cfg = _canonical_cfg(mod)
    agent = _configured_agent(mod)
    task = Task(TaskData(prompt="go"))
    runtime = _runtime(tmp_path / "rt")
    trace = _trace(task, agent)

    harness = mod.ReportingPTCHarness(cfg)
    assert type(harness) is mod.ReportingPTCHarness
    with pytest.raises(RuntimeError, match="run_configured_ptc_qa"):
        asyncio.run(harness.setup(runtime))
    with pytest.raises(RuntimeError, match="run_configured_ptc_qa"):
        asyncio.run(harness.launch(
            agent.ctx, trace, runtime, ENDPOINT, SECRET, {}, task.data))

    for kwarg in ({"qa_factory": _good_factory([])}, {"catalog": Catalog()},
                  {"transport": object()}):
        with pytest.raises(TypeError):
            mod.ReportingPTCHarness(cfg, **kwarg)
    with pytest.raises(TypeError, match=GUARD):
        mod.ReportingPTCHarness(cfg.model_copy(update={"id": "ptc"}))
    with pytest.raises(TypeError, match=GUARD):
        mod.ReportingPTCHarness(PTCHarnessConfig(id=CANONICAL_ID))

    marked = _canonical_cfg(mod)
    marked._qa_required = True
    for clone in (marked, marked.model_copy(), copy.deepcopy(marked)):
        with pytest.raises(RuntimeError, match=GUARD):
            mod.ReportingPTCHarness(clone)

    restored_cfg = mod.ReportingPTCConfig.model_validate_json(
        cfg.model_dump_json())
    rebuilt = load_harness(restored_cfg)
    assert type(rebuilt) is mod.ReportingPTCHarness
    with pytest.raises(RuntimeError, match="run_configured_ptc_qa"):
        asyncio.run(rebuilt.launch(
            _ctx(), trace, runtime, ENDPOINT, SECRET, {}, task.data))


# --------------------------------------------------------------------------
# Runner admission: identity, freshness, declared and live fields.
# --------------------------------------------------------------------------

def test_runner_rejects_noncanonical_identities(tmp_path, monkeypatch):
    """Non-Agent, Agent subclass, plain PTC harness, wrong config type,
    forged IDs, pre-marked config, public-field mismatch and a pre-bound
    harness refuse — each on a baseline satisfying every other
    precondition."""
    mod = _mod()
    calls = []
    task = Task(TaskData(prompt="go"))

    with pytest.raises(ValueError, match=GUARD):
        asyncio.run(mod.run_configured_ptc_qa(
            object(), task, qa_factory=_good_factory(calls)))

    class SubAgent(Agent):
        pass

    _refuses(mod, SubAgent(AgentConfig.model_validate(
        _agent_config_dict())), task, "Agent|exact", calls)

    agent = _configured_agent(mod)
    agent.harness = PTCHarness(PTCHarnessConfig(id=CANONICAL_ID))
    _refuses(mod, agent, task, "ReportingPTCHarness|canonical|unbound",
             calls)

    agent = _configured_agent(mod)
    agent.harness.config = PTCHarnessConfig(id=CANONICAL_ID)
    _refuses(mod, agent, task, "ReportingPTCConfig|canonical|type", calls)

    agent = _configured_agent(mod)
    agent.harness.config = agent.harness.config.model_copy(
        update={"id": "ptc"})
    _refuses(mod, agent, task, "id|cotrain_ptc_qa|canonical", calls)
    agent = _configured_agent(mod)
    agent.config.harness = agent.config.harness.model_copy(
        update={"id": "ptc"})
    _refuses(mod, agent, task, "id|cotrain_ptc_qa|canonical", calls)

    agent = _configured_agent(mod)
    agent.harness.config._qa_required = True
    _refuses(mod, agent, task, "mark|bound|canonical", calls)

    agent = _configured_agent(mod)
    agent.config.harness = mod.ReportingPTCConfig(
        id=CANONICAL_ID, max_turns=9, program_timeout=2.0)
    _refuses(mod, agent, task, "match|equal|agree|declared|canonical",
             calls)

    # A genuinely bound harness, captured from a real activation, refuses.
    agent = _configured_agent(mod)
    _activated(tmp_path, mod, agent, task, monkeypatch)
    seen_bound = []

    async def grab(task, **kwargs):
        seen_bound.append(agent.harness)
        return _trace(task, agent)

    agent.run = grab
    asyncio.run(mod.run_configured_ptc_qa(
        agent, task, qa_factory=_good_factory([])))
    bound, = seen_bound
    agent.harness = bound
    _refuses(mod, agent, task, "bound|mark|binding", calls)


def test_runner_rejects_unfresh_agents(tmp_path):
    """Closed, entered, server-borrowing, gated and already-claimed agents
    refuse before discovery; injected interception is admitted, pinned."""
    mod = _mod()
    calls = []
    task = Task(TaskData(prompt="go"))

    for mutate, match in (
        (lambda a: setattr(a, "_closed", True), "closed|fresh"),
        (lambda a: setattr(a, "_entered", True), "entered|fresh"),
        (lambda a: setattr(a, "_server", object()), "server|borrowed"),
        (lambda a: setattr(a, "_gate", asyncio.Semaphore(1)),
         "gate|borrowed|server"),
        (lambda a: setattr(a, OWNER_ATTR, object()),
         "claim|owner|in-flight|already"),
    ):
        agent = _configured_agent(mod)
        mutate(agent)
        _refuses(mod, agent, task, match, calls)

    agent = _configured_agent(mod)
    agent.interception = object()
    seen = []

    async def done(task, **kwargs):
        seen.append(task)
        return _trace(task, agent)

    agent.run = done
    asyncio.run(mod.run_configured_ptc_qa(
        agent, task, qa_factory=_good_factory(calls)))
    assert len(seen) == 1
    assert calls == []


@pytest.mark.parametrize("case,match", [
    # Declared-side: one bad serialized setting each.
    ({"max_turns": None}, "max_turns|turn"),
    ({"retries": {"max_retries": 1}}, "retr"),
    ({"timeout": {"rollout": 15.0, "finalize": 5.0, "scoring": 5.0}},
     "timeout|setup"),
    ({"timeout": {"setup": 5.0, "rollout": None, "finalize": 5.0,
                  "scoring": 5.0}}, "timeout|rollout"),
    ({"harness": _harness_dict(program_timeout=float("inf"))},
     "program_timeout|finite"),
    ({"harness": _harness_dict(skills=[{"runtime": "/x"}])}, "skill"),
    ({"runtime": {"type": "prime"}}, "subprocess|runtime"),
    ({"model": "   "}, "model"),
    ({"client": None}, "client"),
    # Live-side: one invalid or declared-vs-live-mismatched field each.
    (lambda a: setattr(a, "runtime_config", PrimeConfig()),
     "subprocess|runtime"),
    (lambda a: setattr(a, "limits", replace(a.limits, max_turns=None)),
     "max_turns|turn|limit"),
    (lambda a: setattr(a, "limits", replace(a.limits, max_turns=5)),
     "max_turns|turn|limit|agree|declared|match"),
    (lambda a: setattr(a, "timeout",
                       a.timeout.model_copy(update={"setup": None})),
     "timeout|setup"),
    (lambda a: setattr(a, "timeout",
                       a.timeout.model_copy(update={"scoring": 0.0})),
     "timeout|scoring"),
    (lambda a: setattr(a, "ctx", replace(a.ctx, model="")), "model"),
    (lambda a: setattr(a, "ctx", replace(a.ctx, model="other-model")),
     "model|agree|declared|match"),
    (lambda a: setattr(a, "ctx", replace(
        a.ctx, client=EvalClientConfig(api_key_var="X"))),
     "client|agree|declared|match"),
    (lambda a: setattr(a, "config",
                       a.config.model_copy(
                           update={"retries": a.config.retries.model_copy(
                               update={"max_retries": 1})})),
     "retr"),
    (lambda a: setattr(a.harness, "config",
                       a.harness.config.model_copy(update={"max_turns": 9})),
     "max_turns|config|match|agree|canonical"),
    (lambda a: setattr(a.config, "harness",
                       a.config.harness.model_copy(
                           update={"program_timeout": 9.0})),
     "config|match|agree|canonical|declared"),
    (lambda a: setattr(a.harness, "config", a.harness.config.model_copy(
        update={"env": {**a.harness.config.env, "K": "v"}})),
     "config|match|agree|canonical|env"),
])
def test_runner_field_admission(tmp_path, case, match):
    """Each invalid declared setting or live field/mismatch refuses
    individually with the fixed generic guard error and zero run/factory calls."""
    mod = _mod()
    if callable(case):
        agent = _configured_agent(mod)
        case(agent)
    else:
        agent = _configured_agent(mod, **case)
    _refuses(mod, agent, Task(TaskData(prompt="go")), match, [])


@pytest.mark.parametrize("field", [
    "max_turns", "max_input_tokens", "max_output_tokens", "max_total_tokens",
])
@pytest.mark.parametrize("value", [
    True, 1.5, "4", float("nan"), float("inf"), -1, 0,
])
def test_limits_require_actual_positive_ints(tmp_path, field, value):
    """Turn/token budgets are actual ints: bool, float, string, NaN, inf and
    nonpositive refuse."""
    mod = _mod()
    agent = _configured_agent(mod)
    agent.limits = replace(agent.limits, **{field: value})
    _refuses(mod, agent, Task(TaskData(prompt="go")),
             "limit|turn|token|int|finite", [])


@pytest.mark.parametrize("field", ["setup", "rollout", "finalize", "scoring"])
@pytest.mark.parametrize("value", [
    None, True, "5", float("nan"), float("inf"), -1, 0,
])
def test_stage_timeouts_require_explicit_finite_positive(tmp_path, field,
                                                         value):
    """Every stage timeout is an explicit positive finite number."""
    mod = _mod()
    agent = _configured_agent(mod)
    invalid = agent.timeout.model_copy(update={field: value})
    agent.timeout = agent.config.timeout = invalid
    _refuses(mod, agent, Task(TaskData(prompt="go")),
             "timeout|finite|positive", [])


def test_admitted_positive_token_limits_reach_the_run(tmp_path):
    """Positive actual-int token limits declared in JSON are admitted."""
    mod = _mod()
    agent = _configured_agent(mod, max_input_tokens=128,
                              max_output_tokens=64, max_total_tokens=256)
    seen = []

    async def done(task, **kwargs):
        seen.append(task)
        return _trace(task, agent)

    agent.run = done
    asyncio.run(mod.run_configured_ptc_qa(
        agent, Task(TaskData(prompt="go")),
        qa_factory=_good_factory([])))
    assert len(seen) == 1


# --------------------------------------------------------------------------
# Task and callback admission.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("data,match", [
    (TaskData(prompt=None), "prompt"),
    (TaskData(prompt=[UserMessage(content="hi")]), "prompt"),
    (TaskData(prompt="go").model_copy(update={"prompt": 123}), "prompt"),
    (TaskData(prompt="go").model_copy(update={"system_prompt": 123}),
     "system_prompt|prompt"),
    (TaskData(prompt="go", skills=[Path("/x")]), "skill"),
    (TaskData(prompt="go", timeout=TaskTimeout(agent=5.0)), "timeout"),
    (TaskData(prompt="go", image="img:1"), "container|image"),
])
def test_task_data_admission(tmp_path, data, match):
    """Non-string/missing prompts, forged fields, skills, timeout overrides
    and container requirements refuse before the run."""
    mod = _mod()
    _refuses(mod, _configured_agent(mod), Task(data), match, [])


def test_task_kinds_and_declarations_refuse_without_invocation(tmp_path):
    """A container Task, non-Task objects, custom/inherited toolsets and a
    discovered @intercept hook all refuse with ZERO invocations."""
    mod = _mod()
    calls = []

    class ContainerTask(Task):
        NEEDS_CONTAINER = True

    _refuses(mod, _configured_agent(mod), ContainerTask(
        TaskData(prompt="go")), "container", calls)
    with pytest.raises(ValueError, match=GUARD):
        asyncio.run(mod.run_configured_ptc_qa(
            _configured_agent(mod), object(),
            qa_factory=_good_factory(calls)))

    class ToolsetTask(Task):
        invoked = 0

        @classmethod
        def toolsets(cls, config):
            cls.invoked += 1
            return []

    class InheritedToolsetTask(ToolsetTask):
        pass

    for cls in (ToolsetTask, InheritedToolsetTask):
        _refuses(mod, _configured_agent(mod), cls(TaskData(prompt="go")),
                 "toolset|MCP", calls)
    assert ToolsetTask.invoked == 0, "declarations must never be invoked"

    class InterceptTask(Task):
        invoked = 0

        @intercept
        def _rewrite(self, request):
            InterceptTask.invoked += 1
            return request

    _refuses(mod, _configured_agent(mod), InterceptTask(
        TaskData(prompt="go")), "intercept|hook", calls)
    assert InterceptTask.invoked == 0


def test_claim_precedes_task_discovery(tmp_path):
    """The Agent is claimed before any discovery work that can execute
    Python: a pre-claimed agent refuses without touching a task attribute."""
    mod = _mod()
    agent = _configured_agent(mod)
    setattr(agent, OWNER_ATTR, object())
    calls = []

    class PoisonTask(Task):
        touched: list = []

        def __getattribute__(self, name):
            if name != "touched":
                object.__getattribute__(self, "touched").append(name)
            return object.__getattribute__(self, name)

    task = PoisonTask(TaskData(prompt="go"))
    task.touched.clear()

    with pytest.raises(ValueError, match=GUARD):
        asyncio.run(mod.run_configured_ptc_qa(
            agent, task, qa_factory=_good_factory(calls)))
    assert task.touched == []
    assert calls == []


@pytest.mark.parametrize("shape", [
    "object", "async_fn", "async_gen", "async_call", "async_gen_call", "gen_call",
    "partial_async", "partial_async_call",
])
def test_factory_admission_before_invocation(tmp_path, shape):
    """Async fns, async gens, async __call__ objects and their partials
    refuse BEFORE invocation with zero run calls."""
    mod = _mod()
    reached = []

    async def async_factory(data):
        return QaChannel()

    async def async_gen(data):
        yield QaChannel()

    class AsyncCallable:
        async def __call__(self, data):
            return QaChannel()

    class AsyncGenCallable:
        async def __call__(self, data):
            yield QaChannel()

    class GenCallable:
        def __call__(self, data):
            yield QaChannel()

    factory = {
        "object": object(), "async_fn": async_factory,
        "async_gen": async_gen, "async_call": AsyncCallable(),
        "async_gen_call": AsyncGenCallable(),
        "gen_call": GenCallable(),
        "partial_async": partial(async_factory),
        "partial_async_call": partial(AsyncCallable()),
    }[shape]

    agent = _configured_agent(mod)
    original = agent.harness

    async def never(task, **kwargs):
        reached.append(task)

    agent.run = never
    with pytest.raises(TypeError, match=GUARD):
        asyncio.run(mod.run_configured_ptc_qa(
            agent, Task(TaskData(prompt="go")), qa_factory=factory))
    assert reached == []
    assert agent.harness is original
    assert getattr(agent, OWNER_ATTR, None) is None


def test_factory_return_shapes_and_single_shot(tmp_path, monkeypatch):
    """Inside the launch boundary the guarded factory refuses a non-channel,
    a QaChannel subclass, an awaitable, an async generator and a second
    call; a native coroutine is CLOSED before refusal (zero unawaited
    warnings); a factory that raises propagates its own error."""
    mod = _mod()

    class SubChannel(QaChannel):
        pass

    class Boom(Exception):
        pass

    async def coro_body():
        return QaChannel()

    async def agen():
        yield QaChannel()

    class Awaitable:
        def __await__(self):
            yield
            return QaChannel()

    for index, (factory, expected) in enumerate((
        (lambda d: "not a channel", TypeError),
        (lambda d: SubChannel(), TypeError),
        (lambda d: Awaitable(), TypeError),
        (lambda d: agen(), TypeError),
        (lambda d: coro_body(), TypeError),
        (lambda d: (_ for _ in ()).throw(Boom()), Boom),
    )):
        agent = _configured_agent(mod)
        _, seen, _, _ = _activated(
            tmp_path / str(index), mod, agent, Task(TaskData(prompt="go")),
            monkeypatch)
        with pytest.raises(expected):
            asyncio.run(mod.run_configured_ptc_qa(
                agent, Task(TaskData(prompt="go")), qa_factory=factory))
        assert len(seen) == 1, "the refusal is inside the delegate"

    # The owned native coroutine is closed: zero never-awaited warnings.
    agent = _configured_agent(mod)
    _activated(tmp_path / "coro", mod, agent, Task(TaskData(prompt="go")),
               monkeypatch)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(TypeError, match=GUARD):
            asyncio.run(mod.run_configured_ptc_qa(
                agent, Task(TaskData(prompt="go")),
                qa_factory=lambda d: coro_body()))
        gc.collect()
    leaked = [w for w in caught if issubclass(w.category, RuntimeWarning)
              and "await" in str(w.message).lower()]
    assert leaked == []

    # A second self.qa_factory(data) call refuses — factory ran once.
    agent = _configured_agent(mod)
    received = []
    _activated(tmp_path / "twice", mod, agent, Task(TaskData(prompt="go")),
               monkeypatch, delegate=_delegate([], factory_calls=2))
    with pytest.raises(ValueError, match=GUARD):
        asyncio.run(mod.run_configured_ptc_qa(
            agent, Task(TaskData(prompt="go")),
            qa_factory=_good_factory(received)))
    assert len(received) == 1


# --------------------------------------------------------------------------
# Happy path and cleanup.
# --------------------------------------------------------------------------

def test_runner_ordinary_task_full_lifecycle(tmp_path, monkeypatch):
    """The happy unit path: ORIGINAL subclassed task reaches agent.run
    unchanged exactly once; bound harness is exact ReportingPTCHarness with
    empty catalog, no transport, MCP/resume off; factory called once on the
    exact TaskData through the real guarded wrapper; a real report lands;
    original harness/config restored, owner released, record revoked."""
    mod = _mod()

    class CustomTask(Task):
        def __init__(self, data):
            super().__init__(data)
            self.custom = {"k": 1}
            self.setup_calls, self.finalize_calls = [], []

        async def setup(self, trace, runtime):
            self.setup_calls.append(trace)

        async def finalize(self, trace, runtime):
            self.finalize_calls.append(trace)

    agent = _configured_agent(mod)
    original = agent.harness
    config_dump = agent.config.model_dump(mode="json")
    task = CustomTask(TaskData(prompt="go"))
    received, created, seen = [], [], []
    runtime = _runtime(tmp_path / "rt")
    monkeypatch.setattr(
        PTCHarness, "launch", _delegate(seen, report=("other", "d1")))
    captured = {}
    run_calls = _stub_run(agent, _lifecycle(agent, runtime, captured, task))

    result = asyncio.run(mod.run_configured_ptc_qa(
        agent, task, qa_factory=_good_factory(received, created)))

    trace = captured["trace"]
    bound = captured["bound"]
    assert result is trace
    assert run_calls == [task]
    assert task.setup_calls == [trace]
    assert task.finalize_calls == [trace]
    assert task.custom == {"k": 1}
    assert type(bound) is mod.ReportingPTCHarness
    assert bound is not original
    assert bound._binding is not None
    assert bound.transport is None
    assert bound.catalog.names() == set()
    assert bound.SUPPORTS_MCP is False
    assert bound.SUPPORTS_RESUME is False
    assert bound.NEEDS_CONTAINER is False
    assert len(received) == 1 and received[0] is task.data
    entry, = seen
    assert entry["ctx"] is agent.ctx
    assert entry["runtime"] is runtime
    assert entry["trace"].task.data is task.data
    assert entry["data"] is task.data
    assert entry["mcp_urls"] == {}
    channel, = created
    reports = [e for e in channel.events if e["type"] == "report"]
    assert len(reports) == 1
    assert reports[0]["arm"] == "ptc"
    assert reports[0]["provenance"] == "catalog_callback"
    assert reports[0]["detail"] == "d1"
    assert agent.harness is original
    assert agent.config.model_dump(mode="json") == config_dump
    assert getattr(agent, OWNER_ATTR, None) is None
    assert _record(bound).active is False
    assert report_ack() == (
        "report received (unverified allegation; outcome unchanged)")


def test_runner_restores_on_raise_cancel_and_returned_trace(
        tmp_path, monkeypatch):
    """Run exception, cancellation and a returned trace all revoke the
    record, release the owner and restore the exact original harness; a
    fresh activation still works."""
    mod = _mod()
    agent = _configured_agent(mod)
    original = agent.harness
    task = Task(TaskData(prompt="go"))
    calls = []

    class Boom(Exception):
        pass

    captured = {}

    async def boom(task, **kwargs):
        captured["bound"] = agent.harness
        raise Boom("run failed")

    agent.run = boom
    with pytest.raises(Boom):
        asyncio.run(mod.run_configured_ptc_qa(
            agent, task, qa_factory=_good_factory(calls)))
    assert agent.harness is original
    assert getattr(agent, OWNER_ATTR, None) is None
    assert _record(captured["bound"]).active is False

    entered, release = asyncio.Event(), asyncio.Event()
    captured2 = {}

    async def parked(task, **kwargs):
        captured2["bound"] = agent.harness
        entered.set()
        await asyncio.wait_for(release.wait(), timeout=10.0)

    agent.run = parked

    async def cancel_case():
        running = asyncio.create_task(mod.run_configured_ptc_qa(
            agent, task, qa_factory=_good_factory(calls)))
        await asyncio.wait_for(entered.wait(), timeout=10.0)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running

    asyncio.run(cancel_case())
    assert agent.harness is original
    assert getattr(agent, OWNER_ATTR, None) is None
    assert _record(captured2["bound"]).active is False

    # A returned trace comes back verbatim; a fresh activation works.
    _, seen, captured3, _ = _activated(
        tmp_path / "ok", mod, agent, task, monkeypatch)
    result = asyncio.run(mod.run_configured_ptc_qa(
        agent, task, qa_factory=_good_factory(calls)))
    assert result is captured3["trace"]
    assert agent.harness is original


def test_sequential_runs_distinct_channels(tmp_path, monkeypatch):
    """Two sequential activations produce two DISTINCT channels with one
    own report each — no channel or record state leaks between runs."""
    mod = _mod()
    agent = _configured_agent(mod)
    original = agent.harness
    task = Task(TaskData(prompt="go"))
    received, channels, seen = [], [], []
    monkeypatch.setattr(
        PTCHarness, "launch", _delegate(seen, report=("other", "d")))

    for round_ in range(2):
        runtime = _runtime(tmp_path / f"rt{round_}")
        captured = {}
        _stub_run(agent, _lifecycle(agent, runtime, captured, task))
        asyncio.run(mod.run_configured_ptc_qa(
            agent, task, qa_factory=_good_factory(received, channels)))

    first, second = channels
    assert first is not second
    assert len(received) == 2
    assert received[0] is task.data and received[1] is task.data
    for channel in (first, second):
        reports = [e for e in channel.events if e["type"] == "report"]
        assert len(reports) == 1
        assert reports[0]["arm"] == "ptc"
        assert reports[0]["provenance"] == "catalog_callback"
    assert agent.harness is original


def test_report_bound_and_survives_later_error(tmp_path, monkeypatch):
    """The ninth ptc report is rejected through the real channel (8
    accepted, bounded overflow); accepted reports survive a later program
    error."""
    mod = _mod()
    agent = _configured_agent(mod)
    original = agent.harness
    task = Task(TaskData(prompt="go"))
    created, rejected = [], []
    runtime = _runtime(tmp_path / "rt")

    class ProgramBoom(Exception):
        pass

    async def delegate(self, ctx, trace, runtime, endpoint, secret,
                       mcp_urls, data):
        channel = self.qa_factory(data)
        for i in range(9):
            try:
                channel.submit("ptc", kind="other", detail=f"d{i}")
            except ReportRejected as exc:
                rejected.append(exc)
        raise ProgramBoom("program failed after reporting")

    monkeypatch.setattr(PTCHarness, "launch", delegate)
    captured = {}
    _stub_run(agent, _lifecycle(agent, runtime, captured, task))
    with pytest.raises(ProgramBoom):
        asyncio.run(mod.run_configured_ptc_qa(
            agent, task, qa_factory=_good_factory([], created)))

    assert len(rejected) == 1
    channel, = created
    reports = [e for e in channel.events if e["type"] == "report"]
    overflow = [e for e in channel.events if e["type"] == "overflow"]
    assert len(reports) == 8, "exactly eight reports accepted"
    assert len(overflow) == 1, "the overflow is a bounded rejected event"
    assert agent.harness is original
    assert getattr(agent, OWNER_ATTR, None) is None


# --------------------------------------------------------------------------
# One-shot lifecycle, snapshot mutations and stale contexts.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("case", [
    "repeat_setup", "inherited_setup", "pre_setup_launch", "wrong_runtime",
    "foreign_trace", "foreign_data", "mcp_urls", "copied", "repeat_launch",
    "sneaky_hook",
])
def test_launch_lifecycle_refusals(tmp_path, monkeypatch, case):
    """Every record-transition violation refuses inside the guarded
    setup/launch — repeated setup (direct or via inherited context), launch
    before setup, wrong runtime/trace/data, non-empty MCP URLs, a copied
    harness, a repeated launch, a hook planted during Task setup — with no
    extra activations."""
    mod = _mod()
    agent = _configured_agent(mod)
    original = agent.harness

    class SneakyTask(Task):
        def _rewrite(self, request):
            return request

        async def setup(self, trace, runtime):
            SneakyTask._rewrite.intercept = True

    task = (SneakyTask(TaskData(prompt="go")) if case == "sneaky_hook"
            else Task(TaskData(prompt="go")))
    received, seen = [], []
    runtime = _runtime(tmp_path / "rt")
    monkeypatch.setattr(PTCHarness, "launch", _delegate(seen))
    captured = {}
    launch_args = dict(endpoint=ENDPOINT, secret=SECRET, mcp_urls={})

    async def body(task):
        trace = _trace(task, agent)
        bound = agent.harness
        captured["bound"] = bound

        if case == "pre_setup_launch":
            with pytest.raises(ValueError, match=GUARD):
                await bound.launch(agent.ctx, trace, runtime, **launch_args,
                                   data=task.data)
            return trace

        await task.setup(trace, runtime)
        if case == "sneaky_hook":
            # Toolsets/interceptor exclusions are rechecked AFTER Task setup.
            with pytest.raises(ValueError, match=GUARD):
                await bound.setup(runtime)
            return trace
        if case == "copied":
            # Exercise the copy identity guard while setup is still unconsumed.
            with pytest.raises(ValueError, match=GUARD):
                await copy.copy(bound).setup(runtime)
            with pytest.raises(TypeError, match="lock"):
                copy.deepcopy(bound)
            return trace
        await bound.setup(runtime)

        if case == "repeat_setup":
            with pytest.raises(ValueError, match=GUARD):
                await bound.setup(runtime)
            return trace
        if case == "inherited_setup":
            with pytest.raises(ValueError, match=GUARD):
                await asyncio.create_task(bound.setup(runtime))
            return trace
        if case == "wrong_runtime":
            with pytest.raises(ValueError, match=GUARD):
                await bound.launch(agent.ctx, trace,
                                   _runtime(tmp_path / "rt2"),
                                   **launch_args, data=task.data)
            return trace
        if case == "foreign_trace":
            with pytest.raises(ValueError, match=GUARD):
                await bound.launch(
                    agent.ctx, _trace(Task(TaskData(prompt="go")), agent),
                    runtime, **launch_args, data=task.data)
            return trace
        if case == "foreign_data":
            with pytest.raises(ValueError, match=GUARD):
                await bound.launch(agent.ctx, trace, runtime, **launch_args,
                                   data=TaskData(prompt="go"))
            return trace
        if case == "mcp_urls":
            with pytest.raises(ValueError, match=GUARD):
                await bound.launch(agent.ctx, trace, runtime, ENDPOINT,
                                   SECRET, {"m": "http://x"}, task.data)
            return trace
        await bound.launch(agent.ctx, trace, runtime, **launch_args,
                           data=task.data)
        if case == "repeat_launch":
            with pytest.raises(ValueError, match=GUARD):
                await bound.launch(agent.ctx, trace, runtime, **launch_args,
                                   data=task.data)
        await task.finalize(trace, runtime)
        return trace

    run_calls = _stub_run(agent, body)
    asyncio.run(mod.run_configured_ptc_qa(
        agent, task, qa_factory=_good_factory(received)))
    assert len(run_calls) == 1
    expected = 1 if case == "repeat_launch" else 0
    assert len(seen) == len(received) == expected
    assert agent.harness is original
    assert getattr(agent, OWNER_ATTR, None) is None
    assert _record(captured["bound"]).active is False


def test_stale_and_revoked_contexts_refuse(tmp_path, monkeypatch):
    """After the run the record is a revoked tombstone: setup/launch on the
    bound harness refuse outside the context and under an inherited
    (copied) ContextVar state — zero extra activations."""
    mod = _mod()
    agent = _configured_agent(mod)
    task = Task(TaskData(prompt="go"))
    runtime = _runtime(tmp_path / "rt")
    monkeypatch.setattr(PTCHarness, "launch", _delegate([]))
    captured, saved_ctx = {}, []

    async def body(task):
        trace = _trace(task, agent)
        captured["trace"] = trace
        await task.setup(trace, runtime)
        bound = agent.harness
        captured["bound"] = bound
        saved_ctx.append(contextvars.copy_context())
        await bound.setup(runtime)
        await bound.launch(
            agent.ctx, trace, runtime, ENDPOINT, SECRET, {}, task.data)
        await task.finalize(trace, runtime)
        return trace

    _stub_run(agent, body)
    asyncio.run(mod.run_configured_ptc_qa(
        agent, task, qa_factory=_good_factory([])))
    bound = captured["bound"]
    assert _record(bound).active is False

    with pytest.raises(ValueError, match=GUARD):
        asyncio.run(bound.setup(runtime))
    with pytest.raises(ValueError, match=GUARD):
        asyncio.run(bound.launch(
            agent.ctx, captured["trace"], runtime, ENDPOINT, SECRET, {},
            task.data))
    with pytest.raises(ValueError, match=GUARD):
        saved_ctx[0].run(asyncio.run, bound.setup(runtime))


def _mutations():
    def cfg_copy(field_cfg, **kw):
        return field_cfg.model_copy(update=kw)
    return {
        "bound_config": lambda a, t: setattr(
            a.harness, "config", cfg_copy(a.harness.config, max_turns=9)),
        "declared_config": lambda a, t: setattr(
            a.config, "harness", cfg_copy(a.config.harness, max_turns=9)),
        "nested_env": lambda a, t: a.harness.config.env.__setitem__("K", "v"),
        "runtime_config": lambda a, t: setattr(
            a, "runtime_config", PrimeConfig()),
        "limits": lambda a, t: setattr(
            a, "limits", replace(a.limits, max_turns=9)),
        "limits_equal_float": lambda a, t: object.__setattr__(
            a.limits, "max_turns", float(a.limits.max_turns)),
        "client_ref": lambda a, t: object.__setattr__(
            a.ctx, "client", a.ctx.client.model_copy()),
        "sampling_ref": lambda a, t: object.__setattr__(
            a.ctx, "sampling", a.ctx.sampling.model_copy()),
        "declared_runtime_ref": lambda a, t: setattr(
            a.config, "runtime", a.config.runtime.model_copy()),
        "declared_timeout_ref": lambda a, t: setattr(
            a.config, "timeout", a.config.timeout.model_copy()),
        "declared_client_ref": lambda a, t: setattr(
            a.config, "client", a.config.client.model_copy()),
        "declared_marker": lambda a, t: object.__setattr__(
            a.config.harness, "_qa_required", True),
        "protected_factory": lambda a, t: setattr(
            a.harness, "qa_factory", lambda data: QaChannel()),
        "timeout": lambda a, t: setattr(
            a, "timeout", a.timeout.model_copy(update={"rollout": 1.0})),
        "ctx": lambda a, t: setattr(
            a, "ctx", replace(a.ctx, model="other-model")),
        "harness_ref": lambda a, t: setattr(
            a, "harness", PTCHarness(PTCHarnessConfig())),
        "catalog": lambda a, t: setattr(
            a.harness, "catalog", Catalog(tools={"f": lambda: 1})),
        "transport": lambda a, t: setattr(a.harness, "transport", object()),
        "interception": lambda a, t: setattr(a, "interception", object()),
        "task_data": lambda a, t: setattr(t, "data", TaskData(prompt="go")),
    }


@pytest.mark.parametrize("stage", ["pre_setup", "pre_launch", "in_factory"])
@pytest.mark.parametrize("mutator", sorted(_mutations()))
def test_snapshot_mutation_refusals(tmp_path, monkeypatch, stage, mutator):
    """Mutating any admitted config field, live reference or nested value —
    before setup, before launch, or inside the caller factory — is refused
    at that boundary with a generic error; factory invoked at most once,
    zero subsequent policy calls."""
    mod = _mod()
    mutate = _mutations()[mutator]
    agent = _configured_agent(mod)
    original = agent.harness
    task = Task(TaskData(prompt="go"))
    received, seen = [], []
    runtime = _runtime(tmp_path / "rt")
    monkeypatch.setattr(PTCHarness, "launch", _delegate(seen))
    factory = _good_factory(received)
    if stage == "in_factory":
        def factory(data):
            received.append(data)
            mutate(agent, task)
            return QaChannel()

    async def body(task):
        trace = _trace(task, agent)
        bound = agent.harness
        await task.setup(trace, runtime)
        if stage == "pre_setup":
            mutate(agent, task)
            with pytest.raises(ValueError, match=GUARD):
                await bound.setup(runtime)
            return trace
        await bound.setup(runtime)
        if stage == "pre_launch":
            mutate(agent, task)
            with pytest.raises(ValueError, match=GUARD):
                await bound.launch(agent.ctx, trace, runtime, ENDPOINT,
                                   SECRET, {}, task.data)
            return trace
        await bound.launch(
            agent.ctx, trace, runtime, ENDPOINT, SECRET, {}, task.data)
        await task.finalize(trace, runtime)
        return trace

    _stub_run(agent, body)
    if stage == "in_factory":
        with pytest.raises(ValueError, match=GUARD):
            asyncio.run(mod.run_configured_ptc_qa(
                agent, task, qa_factory=factory))
        assert len(received) == 1, "the factory ran at most once"
    else:
        asyncio.run(mod.run_configured_ptc_qa(
            agent, task, qa_factory=factory))
        assert received == []
    assert len(seen) <= 1
    assert agent.harness is original
    assert getattr(agent, OWNER_ATTR, None) is None


# --------------------------------------------------------------------------
# Concurrency: claim exclusivity.
# --------------------------------------------------------------------------

def test_same_agent_overlap_one_winner(tmp_path):
    """Two overlapping activations on one Agent admit exactly one: the
    first parks inside the run holding the claim; the second refuses."""
    mod = _mod()
    agent = _configured_agent(mod)
    original = agent.harness
    task = Task(TaskData(prompt="go"))
    entered, release = asyncio.Event(), asyncio.Event()
    ran = []

    async def parked(task, **kwargs):
        ran.append(task)
        entered.set()
        await asyncio.wait_for(release.wait(), timeout=10.0)
        return _trace(task, agent)

    agent.run = parked

    async def go():
        first = asyncio.create_task(mod.run_configured_ptc_qa(
            agent, task, qa_factory=_good_factory([])))
        await asyncio.wait_for(entered.wait(), timeout=10.0)
        with pytest.raises(ValueError, match=GUARD):
            await mod.run_configured_ptc_qa(
                agent, task, qa_factory=_good_factory([]))
        release.set()
        await asyncio.wait_for(first, timeout=10.0)

    asyncio.run(go())
    assert len(ran) == 1
    assert agent.harness is original
    assert getattr(agent, OWNER_ATTR, None) is None


def test_distinct_agents_barrier_overlap(tmp_path):
    """Two distinct Agents overlap freely: an asyncio barrier parks both
    drivers until both are in-flight; both succeed."""
    mod = _mod()
    agents = [_configured_agent(mod), _configured_agent(mod)]
    originals = [a.harness for a in agents]
    tasks = [Task(TaskData(prompt=f"go-{i}")) for i in range(2)]
    barrier = asyncio.Barrier(2)
    ran = []

    def make_driver(agent):
        async def drive(task, **kwargs):
            await asyncio.wait_for(barrier.wait(), timeout=10.0)
            ran.append(agent)
            return _trace(task, agent)
        return drive

    for a in agents:
        a.run = make_driver(a)

    async def go():
        return await asyncio.wait_for(asyncio.gather(
            mod.run_configured_ptc_qa(
                agents[0], tasks[0], qa_factory=_good_factory([])),
            mod.run_configured_ptc_qa(
                agents[1], tasks[1], qa_factory=_good_factory([])),
        ), timeout=20.0)

    asyncio.run(go())
    assert set(map(id, ran)) == {id(agents[0]), id(agents[1])}
    for agent, original in zip(agents, originals):
        assert agent.harness is original
        assert getattr(agent, OWNER_ATTR, None) is None


def test_two_thread_claim_exclusive(tmp_path):
    """Two OS threads each run a full asyncio.run activation on the SAME
    agent: the short global claim lock admits exactly one — event-based
    sync, no polling, no runtime, no network."""
    mod = _mod()
    agent = _configured_agent(mod)
    original = agent.harness
    task = Task(TaskData(prompt="go"))
    proceed = threading.Event()
    outcomes = []

    async def drive(task, **kwargs):
        await asyncio.to_thread(proceed.wait, 10.0)
        return _trace(task, agent)

    agent.run = drive

    def worker():
        try:
            asyncio.run(mod.run_configured_ptc_qa(
                agent, task, qa_factory=_good_factory([])))
            outcomes.append("ok")
        except Exception as err:
            outcomes.append(err)
        finally:
            proceed.set()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30.0)
    assert not any(t.is_alive() for t in threads), "the test must not hang"
    oks = [o for o in outcomes if o == "ok"]
    errs = [o for o in outcomes if isinstance(o, BaseException)]
    assert len(oks) == 1 and len(errs) == 1
    assert isinstance(errs[0], ValueError) and str(errs[0]) == GUARD
    assert agent.harness is original
    assert getattr(agent, OWNER_ATTR, None) is None


# --------------------------------------------------------------------------
# Fail-closed serialization and generic guard errors.
# --------------------------------------------------------------------------

def test_bound_config_copy_loses_activation_fails_closed(
        tmp_path, monkeypatch):
    """The bound config carries private intent: reconstructing
    ReportingPTCHarness from a copy loses the factory and refuses."""
    mod = _mod()
    agent = _configured_agent(mod)
    task = Task(TaskData(prompt="go"))
    _, _, captured, _ = _activated(tmp_path, mod, agent, task, monkeypatch)
    asyncio.run(mod.run_configured_ptc_qa(
        agent, task, qa_factory=_good_factory([])))
    bound = captured["bound"]

    for clone in (copy.copy(bound.config), bound.config.model_copy(),
                  copy.deepcopy(bound.config)):
        with pytest.raises(RuntimeError, match=GUARD):
            mod.ReportingPTCHarness(clone)


def test_guard_errors_stay_generic(tmp_path, monkeypatch):
    """Guard refusals leak no private sentinels and no admitted nested
    values (config env value, task prompt). Ordinary SDK/caller exceptions
    make no such promise and are not asserted on."""
    mod = _mod()
    agent = _configured_agent(mod)
    task = Task(TaskData(prompt="XYZZYPROMPT"))
    runtime = _runtime(tmp_path / "rt")
    monkeypatch.setattr(PTCHarness, "launch", _delegate([]))

    def factory(data):
        agent.harness.config.env["SECRET"] = "xyzzy-sentinel-value"
        return QaChannel()

    captured = {}
    _stub_run(agent, _lifecycle(agent, runtime, captured, task))
    with pytest.raises(ValueError, match=GUARD) as raised:
        asyncio.run(mod.run_configured_ptc_qa(
            agent, task, qa_factory=factory))
    blob = str(raised.value)
    assert "xyzzy-sentinel-value" not in blob
    assert "XYZZYPROMPT" not in blob
