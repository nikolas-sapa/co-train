"""Original-loop guards with synthetic HTTP/runner fixtures, not native proof."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from verifiers.v1.clients import EvalClientConfig, ModelContext
from verifiers.v1.task import TaskData

from ptc import sql_isolation as core
from ptc.harness import (
    PTCHarness, PTCHarnessConfig, ProgramInfrastructureError, _close_program_runner,
)
from ptc.runtime import Catalog
from ptc.sql_owned_program import build_owned_sql_program_harness
from ptc.sql_owned_score import build_owned_sql_scorer
from ptc.test_sql_owned_program import _fixture
from train.sql_episodes import InstrumentSettings


def _run(coroutine):
    return asyncio.run(asyncio.wait_for(coroutine, 5))


def _rig(*, reference=False, fault=None):
    state = SimpleNamespace(requests=[], actions=[], closed=0, drift=False,
                            close_started=asyncio.Event(), close_release=None)

    def authority():
        if state.drift:
            raise ValueError("synthetic authority failure")

    class Runner:
        async def run_program(self, code, *, timeout):
            state.actions.append(code)
            if fault in ("action", "multi"):
                state.drift = True
            return "synthetic observation"

        async def aclose(self):
            state.close_started.set()
            if state.close_release is not None:
                await state.close_release.wait()
            state.closed += 1

    runner = Runner()
    if reference:
        runner.reference_descriptor = lambda: dict(
            skill_id="synthetic", promotion_sha256="a" * 64, scope="synthetic",
            instruction="Select this approved skill by ID and promotion digest.")
        runner.validate_launch = lambda: None

        async def run_reference(skill_id, promotion_sha256, *, timeout):
            return await runner.run_program(skill_id, timeout=timeout)
        runner.run_reference = run_reference

    def respond(request):
        state.requests.append(json.loads(request.content))
        if fault in ("response", "replace", "remove"):
            state.drift = fault == "response"
            if fault == "replace":
                harness.host_authority = lambda: None
            elif fault == "remove":
                harness.host_authority = None
        if len(state.requests) > 1 or fault in ("response", "replace", "remove"):
            delta = {"content": "SELECT 1"}
        else:
            arguments = ({"skill_id": "synthetic", "promotion_sha256": "a" * 64}
                         if reference else {"code": "print(1)"})
            count = 2 if fault == "multi" else 1
            delta = {"tool_calls": [
                {"index": i, "id": str(i), "type": "function",
                 "function": {"name": "run_program",
                              "arguments": json.dumps(arguments)}} for i in range(count)]}
        raw = "data: " + json.dumps({"choices": [{"delta": delta}]}) + "\n\n"
        return httpx.Response(200, content=(raw + "data: [DONE]\n\n").encode(),
                              headers={"content-type": "text/event-stream"})

    harness = PTCHarness(
        PTCHarnessConfig(max_turns=3, program_timeout=5),
        transport=httpx.MockTransport(respond), catalog=Catalog(),
        program_runner_factory=lambda data, catalog: runner,
        host_authority=authority)
    state.harness = harness

    async def launch():
        return await harness.launch(
            ModelContext("synthetic", EvalClientConfig()), None, None,
            "http://synthetic.invalid/v1", "synthetic", {},
            TaskData(name="synthetic", prompt="question"))
    state.launch = launch
    return state


@pytest.mark.parametrize("reference", [False, True])
@pytest.mark.parametrize("fault,requests,actions", [
    ("initial", 0, 0), ("action", 1, 1), ("multi", 1, 1),
    ("response", 1, 0),
])
def test_host_authority_request_action_response_guards(reference, fault, requests, actions):
    async def case():
        state = _rig(reference=reference, fault=fault)
        state.drift = fault == "initial"
        with pytest.raises(ProgramInfrastructureError):
            await state.launch()
        assert len(state.requests) == requests
        assert len(state.actions) == actions, "per-action authority guard lost"
        assert state.closed == (0 if fault == "initial" else 1)
        assert all(not message.get("content", "").startswith("error:")
                   for body in state.requests for message in body["messages"]
                   if message["role"] == "tool")
    _run(case())


@pytest.mark.parametrize("fault", ["replace", "remove"])
def test_host_authority_identity_and_return(fault):
    async def case():
        state = _rig(fault=fault)
        with pytest.raises(ProgramInfrastructureError):
            await state.launch()
        assert len(state.requests) == 1 and state.actions == [] and state.closed == 1
    _run(case())


def test_host_authority_invalid_callbacks():
    async def asynchronous():
        pass

    def generator():
        yield None

    class AsyncCallable:
        async def __call__(self):
            pass

    for callback in (asynchronous, generator, AsyncCallable()):
        with pytest.raises(TypeError):
            PTCHarness(PTCHarnessConfig(), host_authority=callback)

    async def case():
        state = _rig()
        state.harness.host_authority = lambda: 1
        with pytest.raises(ProgramInfrastructureError):
            await state.launch()
        assert state.requests == [] and state.actions == []
    _run(case())


def test_bind_existing_identity(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    actual = PTCHarness(fixture.config)
    callback = lambda: None
    before = actual.config

    def no_constructor(*args, **kwargs):
        raise AssertionError("replacement harness construction")
    monkeypatch.setattr(PTCHarness, "__init__", no_constructor)
    bound = build_owned_sql_program_harness(
        fixture.config, data=fixture.data, task=fixture.task,
        executor=fixture.executor, db_sha256=fixture.digest, max_rows=7,
        existing_harness=actual, host_authority=callback)
    assert bound is actual and bound.config is before
    compiled = Catalog(tools={**bound.catalog.tools, "print": print})
    runner = bound.program_runner_factory(fixture.data, compiled)
    assert runner._binding.harness is actual
    assert runner._binding.host_authority is callback
    bound.host_authority = None
    with pytest.raises(ProgramInfrastructureError):
        runner._check()


@pytest.mark.parametrize("fault", [
    "subclass", "config", "launched", "bound", "catalog", "factory",
    "qa", "callback", "transport", "invalid_callback",
])
def test_bind_rejects_dirty_harness(tmp_path, fault):
    fixture = _fixture(tmp_path)

    class Subclass(PTCHarness):
        pass

    actual = (Subclass if fault == "subclass" else PTCHarness)(fixture.config)
    if fault == "config":
        actual.config = fixture.config.model_copy()
    elif fault in ("launched", "bound"):
        setattr(actual, "_launch_started" if fault == "launched" else "_owned_bound", True)
    elif fault == "catalog":
        actual.catalog.tools["unexpected"] = lambda: None
    elif fault in ("factory", "qa", "callback"):
        setattr(actual, {"factory": "program_runner_factory", "qa": "qa_factory",
                         "callback": "host_authority"}[fault], lambda: None)
    elif fault == "transport":
        actual.transport = httpx.MockTransport(lambda request: httpx.Response(200))
    before = dict(vars(actual))
    with pytest.raises((ValueError, TypeError)):
        build_owned_sql_program_harness(
            fixture.config, data=fixture.data, task=fixture.task,
            executor=fixture.executor, db_sha256=fixture.digest, max_rows=7,
            existing_harness=actual,
            host_authority=(lambda: (yield None)) if fault == "invalid_callback" else None)
    assert vars(actual) == before


def test_default_builder_and_failed_launch_lifecycle(tmp_path):
    fixture = _fixture(tmp_path)
    bound = build_owned_sql_program_harness(
        fixture.config, data=fixture.data, task=fixture.task,
        executor=fixture.executor, db_sha256=fixture.digest, max_rows=7)
    assert type(bound) is PTCHarness and bound.config is fixture.config

    async def case():
        state = _rig(fault="initial")
        state.drift = True
        with pytest.raises(ProgramInfrastructureError):
            await state.launch()
        assert state.harness._launch_started is True
        state.drift = False
        await state.launch()
        assert len(state.requests) == 2, "ordinary harness reuse changed"
    _run(case())


def test_cancellation_joins_cleanup():
    """Synthetic runner only, not original invocation or native lifecycle proof."""
    async def case():
        state = _rig()
        state.close_release = asyncio.Event()
        task = asyncio.create_task(state.launch())
        await state.close_started.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and state.closed == 0
        state.close_release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert state.closed == 1
    _run(case())


@pytest.mark.parametrize("role", ["program", "scorer"])
def test_original_owner_predispatch_cancellation_joins_cleanup(tmp_path, monkeypatch, role):
    """Synthetic inputs, real pre-START owner/ACK, no started native actor proof."""
    fixture = _fixture(tmp_path)
    if role == "program":
        harness = build_owned_sql_program_harness(
            fixture.config, data=fixture.data, task=fixture.task,
            executor=fixture.executor, db_sha256=fixture.digest, max_rows=7)
        compiled = Catalog(tools={**harness.catalog.tools, "print": print})
        adapter = harness.program_runner_factory(fixture.data, compiled)
        adapter.validate_program_timeout(5)
    else:
        instrument = InstrumentSettings(
            2, 7, 7, "set", 5.0, 5.0, 5.0,
            "synthetic-python", "synthetic-sqlite", (), "a" * 64)
        adapter = build_owned_sql_scorer(
            task=fixture.task, executor=fixture.executor,
            db_sha256=fixture.digest, instrument=instrument)
        adapter.admit()

    factory_name, real_factory = {
        "program": ("owned_program", core.PilotExecutor.owned_program),
        "scorer": ("owned_score", core.PilotExecutor.owned_score),
    }[role]
    real_execute = core.OwnedSqlInvocation.execute
    real_close = core.OwnedSqlInvocation.aclose
    owners, completions, closes, forbidden = [], [], [], []

    def allocate(executor, *args, **kwargs):
        assert executor is fixture.executor
        owner = real_factory(executor, *args, **kwargs)
        assert type(owner) is core.OwnedSqlInvocation
        owners.append(owner)
        owner.request_cancel("runner_closed")
        return owner

    def deny(*args, **kwargs):
        forbidden.append(True)
        raise AssertionError("predispatch cancellation reached native dispatch")

    for name in ("_stage_sources", "_stage_database", "_secure_directory",
                 "_spawn_owned_guardian", "_owned_boundary_io", "_run_isolated"):
        monkeypatch.setattr(core, name, deny)
    monkeypatch.setattr(core.PilotExecutor, factory_name, allocate)

    async def case():
        close_started, close_release = asyncio.Event(), asyncio.Event()

        async def execute(owner):
            job, = adapter._jobs
            assert job.invocation is owner and job.snapshot.role == role
            assert owner.snapshot().state == (
                "HOST_SEALED" if completions else "ABORT_LATCHED")
            completion = await real_execute(owner)
            if completions:
                assert completion is completions[0]
            else:
                completions.append(completion)
            return completion

        async def close(owner):
            job, = adapter._jobs
            assert job.invocation is owner
            assert job.close_task is asyncio.current_task()
            closes.append(owner)
            close_started.set()
            await close_release.wait()
            return await real_close(owner)

        monkeypatch.setattr(core.OwnedSqlInvocation, "execute", execute)
        monkeypatch.setattr(core.OwnedSqlInvocation, "aclose", close)
        operation = (adapter.run_program("print(1)", timeout=5)
                     if role == "program" else adapter.score_sql("SELECT 1"))
        caller = asyncio.create_task(operation)
        try:
            await close_started.wait()
            owner, = owners
            job, = adapter._jobs
            assert job.completion is completions[0]
            for index in range(3):
                assert caller.cancel("held-close-" + str(index))
                await asyncio.sleep(0)
                assert not caller.done() and not job.close_task.done()
                assert job.ack is None
            close_release.set()
            with pytest.raises(asyncio.CancelledError):
                await caller
            ack = job.ack
            assert type(ack) is core.CleanupCompleteAck
            assert ack is job.completion.cleanup_ack is owner._completion.cleanup_ack
            assert ack is owner._authority.ack and ack._authority.owner is owner
            assert job.close_task.done() and job.close_task.result() is ack
            assert ack.not_started is True and ack.released is True
            assert ack.role == role and ack.invocation_id == job.snapshot.invocation_id
            assert ack.request_sha256 == job.snapshot.request_sha256
            assert ack.profile_sha256 == job.snapshot.profile_sha256
            assert job.completion.abort.kind == "cancelled"
            assert job.completion.outcome is None
            assert owner.snapshot().state == "HOST_SEALED"
            assert len(owners) == len(completions) == len(closes) == 1
            await _close_program_runner(adapter)
            await _close_program_runner(adapter)
            assert closes == [owner] and adapter._jobs == [job]
            assert forbidden == []
        finally:
            close_release.set()
            if not caller.done():
                caller.cancel()
            await asyncio.gather(caller, return_exceptions=True)
    _run(case())
