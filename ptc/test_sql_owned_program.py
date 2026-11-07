"""Inert builder, binding, preflight and retained-runner unit contracts.

No actor/native success is fabricated here. The one real public invocation path
is cancelled before START and returns its own NOT_STARTED completion and ACK.
Process outcomes and missing-proof ownership belong to the canonical actors.
"""
from __future__ import annotations

import asyncio
import builtins
import dataclasses
import gc
import hashlib
import importlib
import importlib.util
import io
import json
import os
import socket
import sqlite3
import subprocess
from types import SimpleNamespace
from typing import Any
import weakref

import pytest

from ptc import sql_isolation as core
from ptc.test_sql_owned_invocation import _profile


def _adapter():
    # New API resolution belongs to the call phase, never collection or skip.
    assert importlib.util.find_spec("ptc.sql_owned_program") is not None, (
        "owned SQL PROGRAM adapter module missing")
    module = importlib.import_module("ptc.sql_owned_program")
    assert callable(getattr(module, "build_owned_sql_program_harness", None)), (
        "owned SQL PROGRAM builder missing")
    return module


def _deps():
    from verifiers.v1.task import TaskData
    from ptc.harness import PTCHarness, PTCHarnessConfig, ProgramInfrastructureError
    from ptc.runtime import Catalog
    from ptc.test_owned_program_runner import Policy, _assistant, _launch
    return SimpleNamespace(
        TaskData=TaskData, Harness=PTCHarness, Config=PTCHarnessConfig,
        Fatal=ProgramInfrastructureError, Catalog=Catalog,
        Policy=Policy, assistant=_assistant, launch=_launch)


def _data(**kwargs):
    TaskData = _deps().TaskData

    class PlainData(TaskData):
        payload: Any = None

    return PlainData(name="owned-unit", prompt="plain fixture", **kwargs)


def _fixture(tmp_path):
    from bench.task import SqlTask
    dep = _deps()
    path = tmp_path / "opaque-owned.db"
    raw = b"opaque first-party fixture, not SQLite\n"
    path.write_bytes(raw)
    profile = _profile(tmp_path)
    return SimpleNamespace(
        dep=dep, data=_data(payload={"nested": ["original"]}),
        config=dep.Config(program_timeout=5.0),
        task=SqlTask("owned-unit", "fixture question", "",
                     "PRIVATE_GOLD_DO_NOT_LEAK", "fixture", str(path),
                     "simple", "derived", "s", "s", "fixture"),
        executor=core.PilotExecutor(profile, state_dir=tmp_path / "never-staged"),
        path=path, digest=hashlib.sha256(raw).hexdigest(), max_rows=7)


def _build(fixture, **updates):
    options = dict(data=fixture.data, task=fixture.task,
                   executor=fixture.executor, db_sha256=fixture.digest,
                   max_rows=fixture.max_rows)
    config = updates.pop("config", fixture.config)
    options.update(updates)
    return _adapter().build_owned_sql_program_harness(config, **options)


def _wire(data):
    return json.dumps(
        data.model_dump(mode="json"), sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(",", ":")).encode("utf-8", "strict")


def _run(coroutine):
    return asyncio.run(asyncio.wait_for(coroutine, 5.0))


def _capture(harness):
    factory = harness.program_runner_factory
    assert callable(factory)
    owners, closes = [], []

    def observed(data, catalog):
        runner = factory(data, catalog)
        owners.append(runner)
        original = runner.aclose

        async def close():
            closes.append(runner)
            return await original()

        runner.aclose = close
        return runner

    harness.program_runner_factory = observed
    return owners, closes


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    attempts = []

    def deny(label):
        def refused(*args, **kwargs):
            attempts.append(label)
            raise AssertionError("adapter unit reached forbidden " + label)
        return refused

    for name in ("_stage_sources", "_stage_database", "_secure_directory",
                 "_spawn_owned_guardian", "_owned_boundary_io", "_run_isolated"):
        monkeypatch.setattr(core, name, deny(name), raising=False)
    monkeypatch.setattr(sqlite3, "connect", deny("SQLite"))
    monkeypatch.setattr(subprocess, "Popen", deny("subprocess"))
    if hasattr(core, "_CreatorPopen"):
        monkeypatch.setattr(core._CreatorPopen, "__init__", deny("creator"))
    monkeypatch.setattr(core.threading.Thread, "start", deny("controller"))
    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, deny("socket." + name))
    monkeypatch.setattr(socket, "getaddrinfo", deny("DNS"))
    monkeypatch.setattr(os, "kill", deny("PID signal"))
    monkeypatch.setattr(os, "killpg", deny("group signal"))
    yield attempts
    assert attempts == [], f"forbidden adapter attempts: {attempts}"


def test_builder_is_ordinary_inert_and_constructs_canonical_catalog_once(
        tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    module = _adapter()
    from ptc import sql_arms
    original = sql_arms.sql_catalog
    catalogs, opened = [], []

    def catalog(*args, **kwargs):
        actual = original(*args, **kwargs)
        catalogs.append(actual)
        return actual

    def no_open(*args, **kwargs):
        opened.append(True)
        raise AssertionError("inert builder performed filesystem IO")

    monkeypatch.setattr(sql_arms, "sql_catalog", catalog)
    if getattr(module, "sql_catalog", None) is original:
        monkeypatch.setattr(module, "sql_catalog", catalog)
    # Resolve imports, profile and executor BEFORE installing zero-open guards.
    with monkeypatch.context() as patch:
        for target, name in (
                (builtins, "open"), (io, "open"), (os, "open"),
                (os, "stat"), (os, "lstat"), (os, "readlink")):
            patch.setattr(target, name, no_open)
        harness = _build(fixture)
    assert opened == []
    assert type(harness) is fixture.dep.Harness
    assert len(catalogs) == 1, "canonical SQL catalog was rebuilt or omitted"
    assert harness.catalog is catalogs[0]
    assert harness.catalog.names() == {"execute_sql", *sql_arms.SQL_PRIMITIVES}
    assert all(harness.catalog.tools[name] is callback
               for name, callback in sql_arms.SQL_PRIMITIVES.items())
    assert not fixture.executor.state_dir.exists()


@pytest.mark.parametrize("fault", (
    "empty-name", "different-name", "task-lookalike",
    "executor-subclass", "config-subclass", "bad-rows",
))
def test_builder_refuses_invalid_original_binding(tmp_path, fault):
    fixture = _fixture(tmp_path)
    build = _adapter().build_owned_sql_program_harness
    options = dict(data=fixture.data, task=fixture.task,
                   executor=fixture.executor, db_sha256=fixture.digest,
                   max_rows=fixture.max_rows)
    config = fixture.config
    if fault in {"empty-name", "different-name"}:
        options["data"] = fixture.data.model_copy(update={
            "name": "" if fault == "empty-name" else "another"})
        if fault == "empty-name":
            options["task"] = dataclasses.replace(fixture.task, name="")
    elif fault == "task-lookalike":
        options["task"] = SimpleNamespace(**dataclasses.asdict(fixture.task))
    elif fault == "executor-subclass":
        class Derived(core.PilotExecutor):
            pass
        options["executor"] = Derived(
            fixture.executor.profile, state_dir=fixture.executor.state_dir)
    elif fault == "config-subclass":
        class Derived(fixture.dep.Config):
            pass
        config = Derived(program_timeout=5.0)
    else:
        options["max_rows"] = True
    with pytest.raises((TypeError, ValueError)):
        build(config, **options)


@pytest.mark.parametrize("value", (float("nan"), float("inf"), "\ud800"))
def test_host_data_requires_finite_strict_utf8_json(tmp_path, value):
    fixture = _fixture(tmp_path)
    fixture.data = fixture.data.model_copy(update={"payload": {"nested": value}})
    build = _adapter().build_owned_sql_program_harness
    with pytest.raises((TypeError, ValueError)):
        build(fixture.config, data=fixture.data, task=fixture.task,
              executor=fixture.executor, db_sha256=fixture.digest, max_rows=7)


@pytest.mark.parametrize("size", (131_072, 131_073))
@pytest.mark.parametrize("character", ("x", "é"), ids=("ascii", "utf8"))
def test_host_data_exact_json_byte_boundary_supports_plain_subclasses(
        tmp_path, size, character):
    fixture = _fixture(tmp_path)
    fixture.data = fixture.data.model_copy(update={"prompt": ""})
    available = size - len(_wire(fixture.data))
    width = len(character.encode("utf-8"))
    fixture.data = fixture.data.model_copy(update={
        "prompt": character * (available // width) + "x" * (available % width)})
    assert len(_wire(fixture.data)) == size
    build = _adapter().build_owned_sql_program_harness
    if size == 131_073:
        with pytest.raises((TypeError, ValueError)):
            build(fixture.config, data=fixture.data, task=fixture.task,
                  executor=fixture.executor, db_sha256=fixture.digest, max_rows=7)
    else:
        assert type(_build(fixture)) is fixture.dep.Harness


def test_image_host_data_is_refused_without_public_or_native_calls(tmp_path):
    fixture = _fixture(tmp_path)
    # Deliberately bypass representation coercion: validation must inspect the
    # live TaskData, not stringify an unsupported image into a plaintext prompt.
    fixture.data = fixture.data.model_copy(update={"image": b"not-an-image"})
    build = _adapter().build_owned_sql_program_harness
    with pytest.raises((TypeError, ValueError)):
        build(fixture.config, data=fixture.data, task=fixture.task,
              executor=fixture.executor, db_sha256=fixture.digest, max_rows=7)


def test_builder_does_not_retain_private_sql_task(tmp_path):
    fixture = _fixture(tmp_path)
    reference = weakref.ref(fixture.task)
    harness = _build(fixture)
    fixture.task = None
    gc.collect()
    assert reference() is None, "adapter retained SqlTask and its private gold"
    assert "PRIVATE_GOLD_DO_NOT_LEAK" not in repr(harness.catalog.tools)


@pytest.mark.parametrize("timeout", (5, 5.0))
def test_valid_preflight_is_once_before_policy_and_closes_one_runner(
        tmp_path, timeout):
    fixture = _fixture(tmp_path)
    fixture.config = fixture.config.model_copy(update={"program_timeout": timeout})
    harness = _build(fixture)
    policy = fixture.dep.Policy(fixture.dep.assistant(None))
    harness.transport = policy.transport()
    owners, closes = _capture(harness)
    validations = []
    factory = harness.program_runner_factory

    def observed(data, catalog):
        runner = factory(data, catalog)
        validate = runner.validate_program_timeout

        def check(value):
            assert policy.requests == []
            validations.append(value)
            return validate(value)

        runner.validate_program_timeout = check
        return runner

    harness.program_runner_factory = observed
    result = _run(fixture.dep.launch(harness, fixture.data))
    assert result.exit_code == 0
    assert validations == [timeout] and len(policy.requests) == 1
    assert len(owners) == 1 and closes == owners
    assert list(owners[0]._jobs) == []


@pytest.mark.parametrize("timeout", (4.0, 8.0, True, float("inf")))
def test_unsupported_timeout_is_premodel_with_exact_factory_close_counts(
        tmp_path, timeout):
    fixture = _fixture(tmp_path)
    fixture.config = fixture.config.model_copy(update={"program_timeout": timeout})
    policy = fixture.dep.Policy(fixture.dep.assistant("must not allocate"))

    async def case():
        owners, closes = [], []
        with pytest.raises((TypeError, ValueError, fixture.dep.Fatal)):
            harness = _build(fixture)
            harness.transport = policy.transport()
            owners, closes = _capture(harness)
            await fixture.dep.launch(harness, fixture.data)
        assert policy.requests == [], "SQL timeout refusal dispatched policy"
        expected = 0 if type(timeout) is bool or timeout == float("inf") else 1
        assert len(owners) == expected and closes == owners
        assert all(not runner._jobs for runner in owners)

    _run(case())


@pytest.mark.parametrize("fault", (
    "data-clone", "nested-data", "data-name", "config",
    "base-extra", "base-missing", "base-replaced",
    "profile", "state-dir", "database",
))
def test_live_binding_drift_refuses_before_first_policy_or_allocation(
        tmp_path, monkeypatch, fault):
    fixture = _fixture(tmp_path)
    harness = _build(fixture)
    policy = fixture.dep.Policy(fixture.dep.assistant("must not allocate"))
    harness.transport = policy.transport()
    allocated = []
    original = core.PilotExecutor.owned_program

    def observed(executor, *args, **kwargs):
        allocated.append(1)
        return original(executor, *args, **kwargs)

    monkeypatch.setattr(core.PilotExecutor, "owned_program", observed)
    data = fixture.data
    if fault == "data-clone":
        data = data.model_copy(deep=True)
    elif fault == "nested-data":
        data.payload["nested"].append("changed")
    elif fault == "data-name":
        # TaskData is frozen; deliberately violate that boundary to probe
        # the adapter's own live-reference guard, not Pydantic assignment.
        object.__setattr__(data, "name", "changed")
    elif fault == "config":
        fixture.config.max_turns += 1
    elif fault == "base-extra":
        harness.catalog.tools["extra"] = lambda: None
    elif fault == "base-missing":
        del harness.catalog.tools["execute_sql"]
    elif fault == "base-replaced":
        harness.catalog.tools["execute_sql"] = lambda *, query: []
    elif fault == "profile":
        profile = fixture.executor.profile
        program = profile.binding.program
        changed = dataclasses.replace(program, sources=(
            dataclasses.replace(program.sources[0], sha256="0" * 64),
            *program.sources[1:]))
        object.__setattr__(fixture.executor, "profile", dataclasses.replace(
            profile, binding=dataclasses.replace(profile.binding, program=changed)))
    elif fault == "state-dir":
        object.__setattr__(fixture.executor, "state_dir", tmp_path / "changed")
    else:
        fixture.path.write_bytes(b"changed DB identity")

    async def case():
        with pytest.raises((TypeError, ValueError, fixture.dep.Fatal)) as caught:
            await fixture.dep.launch(harness, data)
        assert policy.requests == [], "binding drift reached first policy request"
        assert allocated == [], "binding drift allocated an invocation"
        assert "PRIVATE_GOLD_DO_NOT_LEAK" not in str(caught.value)

    _run(case())


@pytest.mark.parametrize("fault", ("compiled-extra", "compiled-missing", "print"))
def test_live_compiled_catalog_membership_and_print_identity(
        tmp_path, monkeypatch, fault):
    fixture = _fixture(tmp_path)
    harness = _build(fixture)
    compiled = fixture.dep.Catalog(tools={
        **harness.catalog.tools, "print": lambda *parts: None})
    runner = harness.program_runner_factory(fixture.data, compiled)
    runner.validate_program_timeout(5.0)
    allocated = []

    def deny(*args, **kwargs):
        allocated.append(1)
        raise AssertionError("compiled drift reached allocation")

    monkeypatch.setattr(core.PilotExecutor, "owned_program", deny)
    if fault == "compiled-extra":
        compiled.tools["extra"] = lambda: None
    elif fault == "compiled-missing":
        del compiled.tools["execute_sql"]
    else:
        compiled.tools["print"] = lambda *parts: None

    async def case():
        try:
            with pytest.raises(fixture.dep.Fatal):
                await runner.run_program("print(1)", timeout=5.0)
            assert allocated == [], "compiled drift allocated an invocation"
        finally:
            assert await runner.aclose() is None

    _run(case())


def test_every_captured_sql_callback_identity_is_rechecked(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    harness = _build(fixture)
    allocated = []

    def deny(*args, **kwargs):
        allocated.append(1)
        raise AssertionError("changed SQL callback reached allocation")

    monkeypatch.setattr(core.PilotExecutor, "owned_program", deny)

    async def case():
        tested = set()
        for name, callback in tuple(harness.catalog.tools.items()):
            compiled = fixture.dep.Catalog(tools={
                **harness.catalog.tools, "print": lambda *parts: None})
            runner = harness.program_runner_factory(fixture.data, compiled)
            runner.validate_program_timeout(5.0)
            compiled.tools[name] = lambda **kwargs: None
            try:
                with pytest.raises(fixture.dep.Fatal):
                    await runner.run_program("print(1)", timeout=5.0)
                tested.add(name)
                assert harness.catalog.tools[name] is callback
            finally:
                await runner.aclose()
        assert tested == harness.catalog.names()
        assert allocated == [], "callback identity drift allocated an invocation"

    _run(case())


@pytest.mark.parametrize("fault", ("nested-data", "config", "database"))
def test_mutation_after_policy_request_one_refuses_before_program_allocation(
        tmp_path, monkeypatch, fault):
    import httpx
    fixture = _fixture(tmp_path)
    harness = _build(fixture)
    policy = fixture.dep.Policy(fixture.dep.assistant("print(1)"),
                                fixture.dep.assistant(None))
    original_transport = policy.transport()
    allocated = []

    def handle(request):
        response = original_transport.handle_request(request)
        if len(policy.requests) == 1:
            if fault == "nested-data":
                fixture.data.payload["nested"].append("post-policy")
            elif fault == "config":
                fixture.config.max_turns += 1
            else:
                # Same bytes and digest, different inode must still be stale.
                replacement = tmp_path / "replacement.db"
                replacement.write_bytes(fixture.path.read_bytes())
                os.replace(replacement, fixture.path)
        return response

    def deny(*args, **kwargs):
        allocated.append(1)
        raise AssertionError("stale pre-program identity allocated invocation")

    monkeypatch.setattr(core.PilotExecutor, "owned_program", deny)
    harness.transport = httpx.MockTransport(handle)
    owners, closes = _capture(harness)

    async def case():
        with pytest.raises(fixture.dep.Fatal):
            await fixture.dep.launch(harness, fixture.data)
        assert len(policy.requests) == 1
        assert allocated == [], "pre-program guard ran after owner allocation"
        assert len(owners) == 1 and closes == owners
        assert not owners[0]._jobs

    _run(case())


@pytest.mark.parametrize("code", ("", "x" * 65_537), ids=("empty", "oversized"))
def test_real_core_request_rejection_is_fatal_with_zero_owners(
        tmp_path, monkeypatch, code):
    fixture = _fixture(tmp_path)
    harness = _build(fixture)
    policy = fixture.dep.Policy(fixture.dep.assistant(code),
                                fixture.dep.assistant(None))
    harness.transport = policy.transport()
    original = core.PilotExecutor.owned_program
    calls, owners = [], []

    def observed(executor, *args, **kwargs):
        calls.append(1)
        owner = original(executor, *args, **kwargs)
        owners.append(owner)
        return owner

    monkeypatch.setattr(core.PilotExecutor, "owned_program", observed)

    async def case():
        with pytest.raises(fixture.dep.Fatal):
            await fixture.dep.launch(harness, fixture.data)
        assert len(policy.requests) == 1, "invalid native input became tool feedback"
        assert calls == [1], "test did not reach the actual core request validator"
        assert owners == [], "invalid core request allocated an owner"

    _run(case())


def test_real_predispatch_abort_is_fatal_and_retains_actual_job_ack(
        tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    harness = _build(fixture)
    policy = fixture.dep.Policy(fixture.dep.assistant("print(1)"),
                                fixture.dep.assistant(None))
    harness.transport = policy.transport()
    runners, runner_closes = _capture(harness)
    original_factory = core.PilotExecutor.owned_program
    original_execute = core.OwnedSqlInvocation.execute
    original_close = core.OwnedSqlInvocation.aclose
    owners, completions, closes, snapshots = [], [], [], []

    def factory(executor, *args, **kwargs):
        owner = original_factory(executor, *args, **kwargs)
        assert type(owner) is core.OwnedSqlInvocation
        owners.append(owner)
        snapshots.append(owner.snapshot())
        owner.request_cancel("runner_closed")
        return owner

    async def execute(owner):
        # Observation delegates to the real public execute. No substituted
        # outcome, abort, completion or cleanup capability.
        jobs = list(runners[0]._jobs)
        assert len(jobs) == 1 and jobs[0].invocation is owner, (
            "job was not registered before first execute await")
        assert all(hasattr(jobs[0], name)
                   for name in ("close_task", "ack", "completion"))
        completion = await original_execute(owner)
        completions.append(completion)
        return completion

    async def close(owner):
        closes.append(owner)
        job, = runners[0]._jobs
        assert job.close_task is asyncio.current_task(), (
            "actual invocation close task was not retained before await")
        return await original_close(owner)

    monkeypatch.setattr(core.PilotExecutor, "owned_program", factory)
    monkeypatch.setattr(core.OwnedSqlInvocation, "execute", execute)
    monkeypatch.setattr(core.OwnedSqlInvocation, "aclose", close)

    async def case():
        with pytest.raises(fixture.dep.Fatal):
            await fixture.dep.launch(harness, fixture.data)
        assert len(policy.requests) == 1, "real abort dispatched another policy request"
        assert len(owners) == len(runners) == 1
        assert closes == owners and runner_closes == runners
        job, = runners[0]._jobs
        assert job.invocation is owners[0]
        assert isinstance(job.close_task, asyncio.Task) and job.close_task.done()
        assert job.completion is completions[0]
        ack = job.completion.cleanup_ack
        assert job.ack is ack and job.close_task.result() is ack
        assert ack.not_started is True and ack.released is True
        assert ack.invocation_id == snapshots[0].invocation_id
        assert ack.request_sha256 == snapshots[0].request_sha256
        assert ack.profile_sha256 == snapshots[0].profile_sha256
        assert job.completion.abort.kind == "cancelled"
        assert all(completion is job.completion for completion in completions)

    _run(case())


@pytest.mark.parametrize("mode", ("body", "normal-close", "close-error"))
def test_first_actual_cancellation_identity_survives_three_launch_cancels(
        monkeypatch, mode):
    dep = _deps()
    first_close_cancels = []
    original_shield = asyncio.shield

    async def observed_shield(awaitable):
        try:
            return await original_shield(awaitable)
        except asyncio.CancelledError as exc:
            first_close_cancels.append(exc)
            raise

    monkeypatch.setattr(asyncio, "shield", observed_shield)

    class InertRunner:
        def __init__(self):
            self.running = asyncio.Event()
            self.closing = asyncio.Event()
            self.release = asyncio.Event()
            self.completed = asyncio.Event()
            self.body_cancel = None
            self.cleanup_error = RuntimeError("inert close failed")
            self.close_task = None
            self.closed = 0

        async def run_program(self, code, *, timeout):
            self.running.set()
            try:
                await asyncio.wait_for(asyncio.Event().wait(), 2.0)
            except asyncio.CancelledError as exc:
                self.body_cancel = exc
                raise

        async def aclose(self):
            self.close_task = asyncio.current_task()
            self.closed += 1
            self.closing.set()
            await asyncio.wait_for(self.release.wait(), 2.0)
            self.completed.set()
            if mode == "close-error":
                raise self.cleanup_error

    async def case():
        runner = InertRunner()
        policy = dep.Policy(dep.assistant(None if mode == "normal-close" else "held"))
        harness = dep.Harness(
            dep.Config(program_timeout=5.0), transport=policy.transport(),
            program_runner_factory=lambda data, catalog: runner)
        caller = asyncio.create_task(dep.launch(harness))
        try:
            if mode != "normal-close":
                await asyncio.wait_for(runner.running.wait(), 1.0)
                assert caller.cancel("first-body")
            await asyncio.wait_for(runner.closing.wait(), 1.0)
            count = 3 if mode == "normal-close" else 2
            for index in range(count):
                assert caller.cancel(f"close-{index}")
                await asyncio.wait({caller}, timeout=0.01)
                assert not caller.done(), "launch escaped held runner close"
                assert not runner.completed.is_set()
            first = (first_close_cancels[0] if mode == "normal-close"
                     else runner.body_cancel)
            assert type(first) is asyncio.CancelledError
            assert len(first_close_cancels) == count
            runner.release.set()
            if mode == "close-error":
                with pytest.raises(asyncio.CancelledError) as caught:
                    await caller
                assert caught.value is first
                failure = caught.value.__cause__
                assert type(failure) is dep.Fatal and "cleanup failed" in str(failure)
                assert failure.__cause__ is runner.cleanup_error
                assert len(failure.__notes__) == 2
                assert all(f"close-{index}" in failure.__notes__[index]
                           for index in range(2))
            else:
                with pytest.raises(asyncio.CancelledError) as caught:
                    await caller
                assert caught.value is first, (
                    "later close cancellation replaced the first actual CancelledError")
            assert runner.completed.is_set() and runner.closed == 1
            assert runner.close_task.done() and len(policy.requests) == 1
        finally:
            runner.release.set()
            if not caller.done():
                caller.cancel()
            await asyncio.gather(caller, return_exceptions=True)
            if runner.close_task is not None:
                await asyncio.gather(runner.close_task, return_exceptions=True)

    _run(case())


@pytest.mark.parametrize("present", (
    ("approved_skill",), ("reuse_case",), ("original_scorer_instrument",),
    ("approved_skill", "reuse_case"),
    ("approved_skill", "original_scorer_instrument"),
    ("reuse_case", "original_scorer_instrument"),
))
def test_live_reuse_builder_host_inputs_are_all_or_none(tmp_path, present):
    from ptc.test_sql_skill_reuse_integration import require_builder

    builder = require_builder()
    fixture = _fixture(tmp_path)
    kwargs = dict(data=fixture.data, task=fixture.task, executor=fixture.executor,
                  db_sha256=fixture.digest, max_rows=fixture.max_rows)
    kwargs.update({name: object() for name in present})
    with pytest.raises((TypeError, ValueError)):
        builder(fixture.config, **kwargs)
