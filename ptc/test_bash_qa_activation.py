"""Unit tests for `cotrain_bash_qa` — the serialized-config activation route.

`ptc/bash_qa.py` proved the paired composition; this file proves the flat
canonical plugin ID plus the runner that builds the binding, pairs task and
harness, runs through `run_bash_qa`, and restores the agent afterwards
(`spec/bash-qa-activation.md`).

The product module is the flat root file `cotrain_bash_qa.py`, imported inside
test bodies: a missing or incomplete implementation fails, never skips. The
only stubbed seam is `run_bash_qa` itself (patched at BOTH import sites) where
construct/pairing/lifecycle is under test without touching its private permit;
when the real `run_bash_qa` is used, `_qa_rewrite` assertions run INSIDE the
stubbed `BashHarness.launch` delegate while the route is active.
"""

from __future__ import annotations

import asyncio
import copy
import gc
import json
import os
import subprocess
import sys
import warnings
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ptc.bash_qa as bash_qa  # noqa: E402

from verifiers.v1.agent import Agent  # noqa: E402
from verifiers.v1.configs.agent import AgentConfig  # noqa: E402
from verifiers.v1.configs.retries import RetryConfig  # noqa: E402
from verifiers.v1.errors import TaskError  # noqa: E402
from verifiers.v1.harness import Harness  # noqa: E402
from verifiers.v1.harnesses.bash.harness import (  # noqa: E402
    BashHarness,
    BashHarnessConfig,
    CompactionConfig,
)
from verifiers.v1.runtimes import (  # noqa: E402
    PrimeConfig,
    ProgramResult,
    SubprocessConfig,
)
from verifiers.v1.task import Task, TaskData  # noqa: E402
from verifiers.v1.utils.loaders import (  # noqa: E402
    harness_class,
    harness_config_type,
    import_harness,
    load_harness,
)

from ptc.sql_qa import QaChannel  # noqa: E402

# Shared real-type builders; the delegate/probe pattern is theirs too.
from ptc.test_bash_qa import (  # noqa: E402
    INTERCEPT_URL,
    _ctx,
    _report_events,
    _report_request,
    _runtime,
    _stubbed_run,
    _task_type,
    _trace,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ID = "cotrain_bash_qa"


def _mod():
    """Import the product module inside the test call: missing code fails
    loudly, never skips."""
    import cotrain_bash_qa

    return cotrain_bash_qa


def _canonical_cfg(mod, **overrides):
    data = {"id": CANONICAL_ID, "edit": False, "search": False}
    data.update(overrides)
    return mod.ReportingBashConfig(**data)


def _agent_config_dict(**overrides):
    """The serialized AgentConfig form the spike proved GREEN: canonical flat
    ID, subprocess runtime, bounded turns, zero retries."""
    data = {
        "model": "fixture-model",
        "harness": {"id": CANONICAL_ID, "edit": False, "search": False},
        "runtime": {"type": "subprocess"},
        "max_turns": 4,
        "retries": {"max_retries": 0},
    }
    data.update(overrides)
    return data


def _configured_agent(mod, **overrides):
    """An Agent whose harness came through the real loader path: unbound
    `ReportingBashHarness`, canonical config on `agent.config.harness`."""
    return Agent(AgentConfig.model_validate(
        _agent_config_dict(**overrides)))


def _builder(bash_qa, calls, task=None):
    """A valid `make_task`: records the binding handed in, returns one mixin
    task paired to it (default) or a caller-supplied object."""

    def make_task(binding):
        calls.append(binding)
        if task is not None:
            return task
        return _task_type(bash_qa)(
            TaskData(prompt="go"), qa_binding=binding)

    return make_task


def _stub_runner(monkeypatch, mod, body):
    """Stub `run_bash_qa` at BOTH plausible import sites so the runner's own
    code is under test regardless of how the module binds the name."""
    calls = []

    async def stub(agent, task):
        calls.append({"agent": agent, "task": task,
                      "harness": agent.harness})
        return await body(agent, task)

    monkeypatch.setattr(bash_qa, "run_bash_qa", stub, raising=False)
    monkeypatch.setattr(mod, "run_bash_qa", stub, raising=False)
    return calls


def _good_factory(calls):
    def factory(data):
        calls.append(data)
        return QaChannel()

    return factory


# ---------------------------------------------------------------------------
# Flat plugin resolution and the serialized config surface.
# ---------------------------------------------------------------------------

def test_flat_id_resolves_one_harness_and_config():
    """The real SDK plugin path: flat ID resolves the exact classes through
    `__all__`-contract and generic ancestry; the dotted ID fails at
    `find_spec`, and `__all__` carries exactly one Harness subclass."""
    mod = _mod()

    module = import_harness(CANONICAL_ID)
    exported = [
        obj for name in module.__all__
        if isinstance(obj := getattr(module, name, None), type)
        and issubclass(obj, Harness) and obj is not Harness
    ]
    assert exported == [mod.ReportingBashHarness]
    assert harness_class(CANONICAL_ID) is mod.ReportingBashHarness
    assert harness_config_type(CANONICAL_ID) is mod.ReportingBashConfig

    # Dotted plugin IDs die inside `_import_plugin` before any fallback.
    with pytest.raises(ModuleNotFoundError):
        import_harness("ptc.bash_qa")


def test_agent_config_json_roundtrip_preserves_canonical_fields():
    """Canonical ID + every public field survive AgentConfig validate -> dump
    -> revalidate; zero serialized factory/binding/private-marker keys."""
    mod = _mod()

    config = AgentConfig.model_validate(_agent_config_dict())
    assert type(config.harness) is mod.ReportingBashConfig
    assert config.harness.id == CANONICAL_ID

    dump = config.model_dump_json()
    for key in ("_qa_required", "qa_factory", "qa_binding",
                "binding", "factory"):
        assert f'"{key}"' not in dump

    restored = AgentConfig.model_validate_json(dump)
    assert type(restored.harness) is mod.ReportingBashConfig
    assert restored.harness.model_dump(mode="json") == \
        config.harness.model_dump(mode="json")
    assert restored.model_dump(mode="json") == \
        config.model_dump(mode="json")

    schema = mod.ReportingBashConfig.model_json_schema()
    assert schema == mod.ReportingBashConfig.model_json_schema()
    for key in ("_qa_required", "qa_factory", "qa_binding",
                "binding", "factory"):
        assert key not in schema["properties"]


def test_canonical_config_is_strict_typed():
    """Wrong ID, smuggled keys and wrong types all refuse at validation --
    inherited extra=forbid is the contract, nothing is silently dropped."""
    mod = _mod()

    with pytest.raises(Exception):
        mod.ReportingBashConfig.model_validate(
            {"id": "bash", "edit": False, "search": False})
    for smuggled in (
        {"qa_factory": "m:fn"},
        {"qa_binding": {}},
        {"binding": "x"},
        {"api_key": "sk-1"},
        {"channel": {}},
        {"unexpected": 1},
    ):
        with pytest.raises(Exception):
            mod.ReportingBashConfig.model_validate(
                {"id": CANONICAL_ID, "edit": False, "search": False,
                 **smuggled})
    with pytest.raises(Exception):
        mod.ReportingBashConfig.model_validate(
            {"id": CANONICAL_ID, "edit": "not-a-boolean", "search": False})
    with pytest.raises(Exception):
        mod.ReportingBashConfig.model_validate_json(
            json.dumps({"id": CANONICAL_ID, "edit": False, "search": False,
                        "sneak": "key"}))
    with pytest.raises(Exception):
        mod.ReportingBashConfig.model_validate(
            {"id": 12345, "edit": False, "search": False})


def test_harness_states_unbound_partial_and_forged(tmp_path):
    """Unbound construction is allowed for loader use but both setup and
    launch refuse naming `run_configured_bash_qa` (no disabled Bash
    fallback); each partial pairing refuses at construction; a forged
    unvalidated copy is refused too."""
    mod = _mod()
    cfg = _canonical_cfg(mod)
    harness = mod.ReportingBashHarness(cfg)
    assert type(harness) is mod.ReportingBashHarness
    runtime = _runtime(tmp_path / "rt")
    trace = SimpleNamespace(id="t")

    with pytest.raises(Exception, match="run_configured_bash_qa"):
        asyncio.run(harness.setup(runtime))
    with pytest.raises(Exception, match="run_configured_bash_qa"):
        asyncio.run(harness.launch(
            _ctx(), trace, runtime, "http://e", "s", {},
            TaskData(prompt="go"), tool_interception_url=INTERCEPT_URL))

    def factory(data):
        return QaChannel()

    with pytest.raises(Exception):
        mod.ReportingBashHarness(cfg, qa_factory=factory)
    with pytest.raises(Exception):
        mod.ReportingBashHarness(cfg, qa_binding=bash_qa.BashQaBinding())

    # Forged identity through unvalidated copies: wrong ID is refused at the
    # harness boundary, not silently re-canonicalized.
    forged = cfg.model_copy(update={"id": "bash"})
    with pytest.raises(Exception):
        mod.ReportingBashHarness(forged)


def test_marked_and_cloned_configs_fail_closed(tmp_path):
    """Shallow, deep and JSON reconstructions cannot smuggle a live launch: a
    marked config without dependencies refuses (clone path); JSON rebuild
    yields an unbound harness whose launch still refuses."""
    mod = _mod()
    cfg = _canonical_cfg(mod)
    marked = cfg.model_copy()
    marked._qa_required = True

    for clone in (marked, marked.model_copy(), copy.deepcopy(marked)):
        with pytest.raises(Exception):
            mod.ReportingBashHarness(clone)

    # JSON has no private marker: reconstruction is unbound, and its launch
    # refuses rather than delegating a disabled Bash launch.
    restored_cfg = mod.ReportingBashConfig.model_validate_json(
        cfg.model_dump_json())
    harness = load_harness(restored_cfg)
    assert type(harness) is mod.ReportingBashHarness
    with pytest.raises(Exception, match="run_configured_bash_qa"):
        asyncio.run(harness.launch(
            _ctx(), SimpleNamespace(id="t"),
            _runtime(tmp_path / "rt"),
            "http://e", "s", {}, TaskData(prompt="go"),
            tool_interception_url=INTERCEPT_URL))


# ---------------------------------------------------------------------------
# Runner admission: canonical identity, builder/factory callbacks.
# ---------------------------------------------------------------------------

def test_runner_rejects_noncanonical_compositions(tmp_path, monkeypatch):
    """Wrong agent type, wrong harness type, a bound harness, mismatched
    public config and a forged agent-config ID all refuse before the builder,
    the factory or the run ever execute; the original harness is untouched."""
    mod = _mod()
    run_calls = _stub_runner(
        monkeypatch, mod, lambda a, t: asyncio.sleep(0, result=None))
    make_calls, factory_calls = [], []

    async def refuse(agent):
        with pytest.raises(Exception):
            await mod.run_configured_bash_qa(
                agent, _builder(bash_qa, make_calls),
                qa_factory=_good_factory(factory_calls))

    # Not an Agent at all.
    asyncio.run(refuse(object()))

    # Plain Bash harness.
    plain = Agent(AgentConfig.model_validate(_agent_config_dict(
        harness={"id": "bash"})))
    originals = {id(plain): plain.harness}
    asyncio.run(refuse(plain))

    # Parent-class bound QA harness, not the canonical reporting one.
    parent = Agent(AgentConfig.model_validate(_agent_config_dict()))
    parent.harness = bash_qa.QaBashHarness(
        bash_qa.QaBashHarnessConfig(id="x", edit=False, search=False),
        qa_factory=lambda d: QaChannel(),
        qa_binding=bash_qa.BashQaBinding())
    originals[id(parent)] = parent.harness
    asyncio.run(refuse(parent))

    # A BOUND reporting harness: the runner owns binding, refuses pre-bound.
    bound_agent = _configured_agent(mod)
    bound_agent.harness = mod.ReportingBashHarness(
        _canonical_cfg(mod),
        qa_factory=lambda d: QaChannel(),
        qa_binding=bash_qa.BashQaBinding())
    originals[id(bound_agent)] = bound_agent.harness
    asyncio.run(refuse(bound_agent))

    # Public config mismatch between agent.config.harness and harness.config.
    mismatch = _configured_agent(mod)
    mismatch.config.harness = mod.ReportingBashConfig(
        id=CANONICAL_ID, edit=False, search=False, env={"X": "1"})
    originals[id(mismatch)] = mismatch.harness
    asyncio.run(refuse(mismatch))

    # Forged agent-config ID (unvalidated copy) on the serialized side.
    forged = _configured_agent(mod)
    forged.config.harness = forged.config.harness.model_copy(
        update={"id": "bash"})
    originals[id(forged)] = forged.harness
    asyncio.run(refuse(forged))

    for agent in (plain, parent, bound_agent, mismatch, forged):
        assert agent.harness is originals[id(agent)], (
            f"{type(agent.harness).__name__}: original harness not preserved")
    assert make_calls == []
    assert factory_calls == []
    assert run_calls == []


def test_runner_invokes_bound_composition_once(tmp_path, monkeypatch):
    """The happy unit path through the stubbed run: exactly one fresh
    BashQaBinding to the builder, the builder's returned task handed to the
    run unchanged, a ReportingBashHarness bound during the run, the stub's
    result returned, the exact original harness restored, and the factory
    never preflight-called (it belongs to real launch only)."""
    mod = _mod()
    agent = _configured_agent(mod)
    original = agent.harness
    sentinel = object()
    run_calls = _stub_runner(
        monkeypatch, mod,
        lambda a, t: asyncio.sleep(0, result=sentinel))
    make_calls, factory_calls = [], []

    result = asyncio.run(mod.run_configured_bash_qa(
        agent, partial(_builder(bash_qa, make_calls)),
        qa_factory=partial(_good_factory(factory_calls))))

    assert result is sentinel
    call, = run_calls
    assert call["agent"] is agent
    assert isinstance(call["task"], bash_qa.BashQaTaskMixin)
    assert isinstance(call["task"], Task)
    assert call["harness"] is not original
    assert type(call["harness"]) is mod.ReportingBashHarness
    binding, = make_calls
    assert type(binding) is bash_qa.BashQaBinding
    assert factory_calls == []
    assert agent.harness is original


def test_builder_and_factory_admission(tmp_path, monkeypatch):
    """Every callback shape outside the contract refuses before assignment:
    noncallable, async coroutine function, async-generator function, native
    coroutine/awaitable/async-generator returns, non-Task, non-mixin and a
    task paired to a different binding; plus a noncallable/async factory."""
    mod = _mod()
    run_calls = _stub_runner(
        monkeypatch, mod, lambda a, t: asyncio.sleep(0, result=None))
    make_calls, factory_calls = [], []

    async def refuse(builder, factory=None):
        with pytest.raises(Exception):
            await mod.run_configured_bash_qa(
                agent, builder,
                qa_factory=factory or _good_factory(factory_calls))

    agent = _configured_agent(mod)
    original = agent.harness
    wrong_binding = bash_qa.BashQaBinding()

    async def async_builder(binding):
        return _task_type(bash_qa)(
            TaskData(prompt="go"), qa_binding=binding)

    async def async_gen(binding):
        yield binding

    async def coro_body():
        return None

    def coro_returning(binding):
        make_calls.append(binding)
        return coro_body()

    def agen_returning(binding):
        make_calls.append(binding)
        return async_gen(binding)

    for builder in (
        object(),
        async_builder,
        async_gen,
        coro_returning,
        agen_returning,
        _builder(bash_qa, make_calls, task=object()),
        _builder(bash_qa, make_calls,
                 task=Task(TaskData(prompt="go"))),
        _builder(bash_qa, make_calls,
                 task=_task_type(bash_qa)(
                     TaskData(prompt="go"), qa_binding=wrong_binding)),
    ):
        asyncio.run(refuse(builder))
        assert agent.harness is original

    # A native coroutine return must be CLOSED before raising: zero
    # "never awaited" warnings is part of the contract, not a nicety.
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        asyncio.run(refuse(coro_returning))
        gc.collect()
    leaked = [w for w in seen
              if issubclass(w.category, RuntimeWarning)
              and "await" in str(w.message).lower()]
    assert leaked == []

    # Factory admission: noncallable and async both refuse before the builder
    # is ever invoked.
    before = len(make_calls)
    async def async_factory(data):
        return QaChannel()

    for factory in (object(), async_factory):
        asyncio.run(refuse(_builder(bash_qa, make_calls), factory=factory))
    assert make_calls[before:] == []
    assert factory_calls == []
    assert run_calls == []
    assert agent.harness is original


@pytest.mark.parametrize("name", ["make_task", "qa_factory"])
@pytest.mark.parametrize("async_generator", [False, True])
@pytest.mark.parametrize("wrapped", [False, True])
def test_async_callable_objects_refuse_before_invocation(
    monkeypatch, name, async_generator, wrapped
):
    mod = _mod()
    agent = _configured_agent(mod)
    original = agent.harness
    builders, factories = [], []
    run_calls = _stub_runner(
        monkeypatch, mod, lambda a, t: asyncio.sleep(0, result=None)
    )

    class AsyncCallable:
        async def __call__(self, value):
            return value

    class AsyncGeneratorCallable:
        async def __call__(self, value):
            yield value

    callback = AsyncGeneratorCallable() if async_generator else AsyncCallable()
    if wrapped:
        callback = partial(callback)
    builder = callback if name == "make_task" else _builder(bash_qa, builders)
    factory = callback if name == "qa_factory" else _good_factory(factories)
    with pytest.raises(TypeError, match=f"{name} must be a synchronous callable"):
        asyncio.run(mod.run_configured_bash_qa(
            agent, builder, qa_factory=factory
        ))
    assert builders == factories == run_calls == []
    assert agent.harness is original


def test_runner_rechecks_snapshot_after_callbacks(tmp_path, monkeypatch):
    """A callback that mutates the agent's serialized config, the aliased
    harness config, or the harness object itself is refused at the
    pre-assignment recheck; the original harness object is restored."""
    mod = _mod()
    run_calls = _stub_runner(
        monkeypatch, mod, lambda a, t: asyncio.sleep(0, result=None))
    factory_calls = []

    def sabotaged(mutator):
        def builder(binding):
            mutator()
            return _task_type(bash_qa)(
                TaskData(prompt="go"), qa_binding=binding)
        return builder

    for mutator in (
        lambda: setattr(agent.config, "harness",
                        BashHarnessConfig(id="bash")),
        lambda: setattr(agent.harness.config, "edit", True),
        lambda: setattr(agent.harness, "config", _canonical_cfg(mod)),
        lambda: setattr(agent, "harness",
                        BashHarness(BashHarnessConfig(id="bash"))),
    ):
        agent = _configured_agent(mod)
        original = agent.harness
        with pytest.raises(Exception):
            asyncio.run(mod.run_configured_bash_qa(
                agent, sabotaged(mutator),
                qa_factory=_good_factory(factory_calls)))
        assert agent.harness is original

    assert factory_calls == []
    assert run_calls == []


# ---------------------------------------------------------------------------
# Runner lifetime and exclusivity.
# ---------------------------------------------------------------------------

def test_runner_restores_original_on_every_exit(tmp_path, monkeypatch):
    """Success, run failure, builder failure and cancellation each restore
    the exact original harness object and release the claim: a follow-up
    activation on the same agent still works."""
    mod = _mod()
    agent = _configured_agent(mod)
    original = agent.harness
    factory_calls = []

    class Boom(Exception):
        pass

    # 1. Success.
    run_calls = _stub_runner(
        monkeypatch, mod, lambda a, t: asyncio.sleep(0, result="ok"))
    assert asyncio.run(mod.run_configured_bash_qa(
        agent, _builder(bash_qa, []),
        qa_factory=_good_factory(factory_calls))) == "ok"
    assert agent.harness is original
    assert len(run_calls) == 1

    # 2. Run raises.
    async def raising(agent, task):
        raise Boom("run failed")
    monkeypatch.setattr(bash_qa, "run_bash_qa", raising, raising=False)
    monkeypatch.setattr(mod, "run_bash_qa", raising, raising=False)
    with pytest.raises(Boom):
        asyncio.run(mod.run_configured_bash_qa(
            agent, _builder(bash_qa, []),
            qa_factory=_good_factory(factory_calls)))
    assert agent.harness is original

    # 3. Builder raises before assignment.
    def bad_builder(binding):
        raise Boom("builder failed")

    with pytest.raises(Boom):
        asyncio.run(mod.run_configured_bash_qa(
            agent, bad_builder,
            qa_factory=_good_factory(factory_calls)))
    assert agent.harness is original

    # 4. Cancellation mid-run.
    entered = asyncio.Event()
    release = asyncio.Event()

    async def parked(agent, task):
        entered.set()
        await asyncio.wait_for(release.wait(), timeout=10.0)

    monkeypatch.setattr(bash_qa, "run_bash_qa", parked, raising=False)
    monkeypatch.setattr(mod, "run_bash_qa", parked, raising=False)

    async def cancel_case():
        running = asyncio.create_task(mod.run_configured_bash_qa(
            agent, _builder(bash_qa, []),
            qa_factory=_good_factory(factory_calls)))
        await asyncio.wait_for(entered.wait(), timeout=10.0)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running

    asyncio.run(cancel_case())
    assert agent.harness is original

    # 5. The claim was released: a fresh activation succeeds.
    run_calls = _stub_runner(
        monkeypatch, mod, lambda a, t: asyncio.sleep(0, result="again"))
    assert asyncio.run(mod.run_configured_bash_qa(
        agent, _builder(bash_qa, []),
        qa_factory=_good_factory(factory_calls))) == "again"
    assert agent.harness is original


def test_two_overlapping_runners_one_agent_refuses_one(tmp_path, monkeypatch):
    """The agent claim is exclusive: while the first runner is parked inside
    the stubbed run, a second activation on the same agent refuses; the first
    completes with its own binding. Two distinct agents overlap freely."""
    mod = _mod()
    agent = _configured_agent(mod)
    original = agent.harness
    entered = asyncio.Event()
    release = asyncio.Event()
    run_calls = []

    async def parked(agent, task):
        run_calls.append(agent)
        entered.set()
        await asyncio.wait_for(release.wait(), timeout=10.0)

    monkeypatch.setattr(bash_qa, "run_bash_qa", parked, raising=False)
    monkeypatch.setattr(mod, "run_bash_qa", parked, raising=False)
    factory_calls = []
    refused = []

    async def second():
        try:
            await mod.run_configured_bash_qa(
                agent, _builder(bash_qa, []),
                qa_factory=_good_factory(factory_calls))
        except Exception as err:
            refused.append(err)
        release.set()

    async def go():
        first = asyncio.create_task(mod.run_configured_bash_qa(
            agent, _builder(bash_qa, []),
            qa_factory=_good_factory(factory_calls)))
        await asyncio.wait_for(entered.wait(), timeout=10.0)
        await second()
        await asyncio.wait_for(first, timeout=10.0)

    asyncio.run(go())
    refusal, = refused
    assert isinstance(refusal, Exception)
    assert run_calls == [agent]
    assert agent.harness is original

    # Distinct agents: real overlap, zero interference.
    other = _configured_agent(mod)
    other_original = other.harness
    barrier = asyncio.Barrier(2)
    both = []

    async def gated(agent, task):
        both.append(agent)
        await asyncio.wait_for(barrier.wait(), timeout=10.0)

    monkeypatch.setattr(bash_qa, "run_bash_qa", gated, raising=False)
    monkeypatch.setattr(mod, "run_bash_qa", gated, raising=False)

    async def overlap():
        await asyncio.wait_for(asyncio.gather(
            mod.run_configured_bash_qa(
                agent, _builder(bash_qa, []),
                qa_factory=_good_factory(factory_calls)),
            mod.run_configured_bash_qa(
                other, _builder(bash_qa, []),
                qa_factory=_good_factory(factory_calls)),
        ), timeout=20.0)

    asyncio.run(overlap())
    assert set(map(id, both)) == {id(agent), id(other)}
    assert agent.harness is original
    assert other.harness is other_original


# ---------------------------------------------------------------------------
# Unbound/bare-run refusals and the preserved unsupported-settings matrix.
# ---------------------------------------------------------------------------

def test_bare_agent_run_never_falls_back(tmp_path, monkeypatch):
    """A bound composition run through bare `agent.run` hits the same entry
    permit refusal as always: the run errors (raised TaskError or an errored
    Trace — the framework decides), zero factory calls, zero policy actions."""
    mod = _mod()
    binding = bash_qa.BashQaBinding()
    factory_calls = []
    agent = _configured_agent(mod)
    agent.harness = mod.ReportingBashHarness(
        _canonical_cfg(mod),
        qa_factory=_good_factory(factory_calls),
        qa_binding=binding)
    task = _task_type(bash_qa)(
        TaskData(prompt="go"), qa_binding=binding)

    async def bare():
        try:
            trace = await asyncio.wait_for(agent.run(task), timeout=30.0)
        except TaskError as err:
            assert "run_bash_qa" in str(err)
            return
        assert not trace.ok, (
            "a bare agent.run must not produce a clean rollout")
        assert trace.last_error is not None
        blob = repr(trace.last_error).lower()
        assert "run_bash_qa" in blob or "qa" in blob, (
            f"expected the entry-point refusal, got {trace.last_error!r}")

    asyncio.run(bare())
    assert factory_calls == []


def test_unsupported_settings_survive_activation(tmp_path, monkeypatch):
    """The existing run_bash_qa admission matrix still bites under activation:
    non-subprocess runtime, non-string prompt, skills, compaction, edit,
    search, MCP toolsets, unbounded turns and retries refuse with zero policy
    actions, zero factory calls and the original harness restored."""
    mod = _mod()
    reached, factory_calls = [], []

    async def never(task, **kwargs):
        reached.append(task)

    def refuse(agent, builder=None, match=None):
        agent.run = never
        builder = _builder(bash_qa, []) if builder is None else builder
        with pytest.raises((ValueError, TypeError), match=match):
            asyncio.run(mod.run_configured_bash_qa(
                agent, builder, qa_factory=_good_factory(factory_calls)))

    original_map = {}

    for kwargs, label in (
        ({"max_turns": None}, "unbounded turns"),
        ({"max_turns": 0}, "zero turns"),
        ({"retries": {"max_retries": 1}}, "retries"),
        ({"harness": {"id": CANONICAL_ID, "edit": True,
                      "search": False}}, "edit tool"),
        ({"harness": {"id": CANONICAL_ID, "edit": False,
                      "search": True}}, "search tool"),
    ):
        agent = _configured_agent(mod, **kwargs)
        original_map[id(agent)] = agent.harness
        refuse(agent)
        assert agent.harness is original_map[id(agent)], label

    # Non-subprocess runtime: mutate the validated config, then run.
    agent = Agent(AgentConfig.model_validate(_agent_config_dict())
                  .model_copy(update={"runtime": PrimeConfig()}))
    original_map[id(agent)] = agent.harness
    refuse(agent)
    assert agent.harness is original_map[id(agent)]

    # Non-string prompt and task-carried skills refuse on the task side.
    for data, reason in (
        (TaskData(prompt=None), "string opening prompt"),
        (TaskData(prompt=[]), "string opening prompt"),
        (TaskData(prompt="go", skills=[{"runtime": "/s"}]), "skills"),
    ):
        agent = _configured_agent(mod)
        original_map[id(agent)] = agent.harness
        refuse(
            agent,
            builder=lambda binding, data=data: _task_type(bash_qa)(
                data, qa_binding=binding
            ),
            match=reason,
        )
        assert agent.harness is original_map[id(agent)]

    # An MCP-toolset task refuses: toolsets() returns a live set.
    class McpTask(bash_qa.BashQaTaskMixin, Task):
        @classmethod
        def toolsets(cls, config):
            return [SimpleNamespace()]

    agent = _configured_agent(mod)
    original_map[id(agent)] = agent.harness
    refuse(
        agent,
        builder=lambda binding: McpTask(
            TaskData(prompt="go"), qa_binding=binding
        ),
        match="MCP toolsets",
    )
    assert agent.harness is original_map[id(agent)]

    assert reached == []
    assert factory_calls == []


def test_unsupported_config_refused_at_construction():
    """Skills and compaction on the canonical config refuse inside the
    harness constructor chain — before any runner is even involved."""
    mod = _mod()
    for overrides in (
        {"skills": [{"runtime": "/s"}]},
        {"compaction": CompactionConfig()},
    ):
        with pytest.raises(Exception):
            mod.ReportingBashHarness(
                _canonical_cfg(mod, **overrides),
                qa_factory=lambda d: QaChannel(),
                qa_binding=bash_qa.BashQaBinding())


# ---------------------------------------------------------------------------
# Disabled ordinary-Bash path: zero QA footprint, proven in a child.
# ---------------------------------------------------------------------------

def test_ordinary_bash_config_never_imports_qa_modules():
    """A fresh isolated interpreter loading an ordinary Bash config through
    the real Agent path must not import the new plugin or either QA module.
    In-process cannot prove this — another test may have imported them."""
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from verifiers.v1.agent import Agent\n"
        "from verifiers.v1.configs.agent import AgentConfig\n"
        "cfg = AgentConfig.model_validate({\n"
        "    'model': 'fixture-model',\n"
        "    'harness': {'id': 'bash'},\n"
        "    'runtime': {'type': 'subprocess'},\n"
        "    'max_turns': 3,\n"
        "    'retries': {'max_retries': 0},\n"
        "})\n"
        "agent = Agent(cfg)\n"
        "for name in ('cotrain_bash_qa', 'ptc.bash_qa', 'ptc.sql_qa'):\n"
        "    assert name not in sys.modules, (f'{name} leaked: '\n"
        "        + str([m for m in sys.modules if 'qa' in m]))\n"
        "from verifiers.v1.harnesses.bash.harness import BashHarness\n"
        "assert type(agent.harness) is BashHarness\n"
        "print('INERT-OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script],
        capture_output=True, text=True, timeout=120,
        cwd=str(REPO_ROOT), env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    assert proc.returncode == 0, proc.stderr
    assert "INERT-OK" in proc.stdout
