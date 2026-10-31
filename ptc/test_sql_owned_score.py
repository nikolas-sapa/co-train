"""Independent SCORER adapter unit gates, specified before implementation.

Only opaque owned DB bytes and freshly pinned synthetic profiles are used.
Actual core owners are cancelled before START. No usable ExResult, public ACK,
native execution, actor lifetime, SDK scoring or reward is fabricated here.
"""
from __future__ import annotations

import asyncio
import builtins
import dataclasses
import hashlib
import importlib
import importlib.util
import inspect
import io
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
from types import SimpleNamespace

import pytest

from bench.task import SqlTask
from ptc import sql_isolation as core
from ptc.test_sql_owned_invocation import _profile
from train.sql_episodes import InstrumentSettings


GOLD = "PRIVATE_GOLD_DO_NOT_LEAK"
PREDICTION = "PRIVATE_PREDICTION_DO_NOT_LEAK"
TASK_FIELDS = (
    "name", "question", "evidence", "gold_sql", "db_id", "db_path",
    "tier", "tier_source", "shape", "coarse_shape", "source",
)
SETTINGS_FIELDS = (
    "action_cap", "action_max_rows", "scorer_max_rows", "compare",
    "scorer_timeout_s", "program_timeout_s", "wrapper_timeout_s",
    "python_version", "sqlite_version", "source_paths", "source_sha256",
)
INVALID_SETTINGS = (
    ("action_cap", True),
    ("action_max_rows", 0),
    ("scorer_max_rows", True),
    ("scorer_max_rows", 0),
    ("compare", "bag"),
    ("scorer_timeout_s", True),
    ("scorer_timeout_s", 5),
    ("scorer_timeout_s", 0.0),
    ("scorer_timeout_s", 30.0001),
    ("scorer_timeout_s", float("nan")),
    ("scorer_timeout_s", float("inf")),
    ("program_timeout_s", 0.0),
    ("wrapper_timeout_s", float("nan")),
    ("python_version", ""),
    ("sqlite_version", 1),
    ("source_paths", ["ptc/sql_isolation.py"]),
    ("source_paths", ("same", "same")),
    ("source_paths", ("",)),
    ("source_sha256", "Z" * 64),
)


def _api():
    # Missing implementation is an intended call-phase assertion, never a
    # collection error or skip. No future production module is imported above.
    assert importlib.util.find_spec("ptc.sql_owned_score") is not None, (
        "owned SQL SCORER adapter module missing")
    module = importlib.import_module("ptc.sql_owned_score")
    for name in ("build_owned_sql_scorer", "OwnedSqlScorer",
                 "ScoreInfrastructureError"):
        assert hasattr(module, name), "owned SQL SCORER API missing: " + name
    assert callable(module.build_owned_sql_scorer)
    assert issubclass(module.ScoreInfrastructureError, RuntimeError)
    return module


def _fixture(tmp_path):
    path = tmp_path / "opaque-scorer.db"
    raw = b"owned scorer fixture bytes, deliberately not SQLite\n"
    path.write_bytes(raw)
    profile = _profile(tmp_path)
    return SimpleNamespace(
        path=path, raw=raw, digest=hashlib.sha256(raw).hexdigest(),
        task=SqlTask("private-task-name", "private question", "private evidence",
                     GOLD, "fixture", str(path), "simple", "derived",
                     "shape", "coarse", "fixture"),
        executor=core.PilotExecutor(profile, state_dir=tmp_path / "never-staged"),
        instrument=InstrumentSettings(
            action_cap=2, action_max_rows=3, scorer_max_rows=7,
            compare="set", scorer_timeout_s=5.0, program_timeout_s=5.0,
            wrapper_timeout_s=1.0, python_version="fixture-python",
            sqlite_version="fixture-sqlite",
            source_paths=("ptc/sql_isolation.py",), source_sha256="a" * 64))


def _build(fixture, **updates):
    options = dict(task=fixture.task, executor=fixture.executor,
                   db_sha256=fixture.digest, instrument=fixture.instrument)
    options.update(updates)
    return _api().build_owned_sql_scorer(**options)


def _private_error(error):
    assert GOLD not in str(error)
    assert PREDICTION not in str(error)
    assert "private-task-name" not in str(error)
    assert "private question" not in str(error)


def _run(coroutine):
    # Unit safety cap only. Production must await its public execute directly.
    return asyncio.run(asyncio.wait_for(coroutine, 5.0))


def _job(scorer, owner):
    matches = [job for job in scorer._jobs if job.invocation is owner]
    assert len(matches) == 1, "actual SCORER owner not retained before first await"
    job, = matches
    for name in ("snapshot", "close_task", "ack", "completion"):
        assert hasattr(job, name), "SCORER job contract missing: " + name
    return job


@pytest.fixture(autouse=True)
def boundaries(monkeypatch):
    state = SimpleNamespace(forbidden=[], allocations=[], owners=[], admissions=[])
    real_factory = core.PilotExecutor.owned_score
    real_admit = core.PilotExecutor.admit_program

    def deny(label):
        def refused(*args, **kwargs):
            state.forbidden.append(label)
            raise AssertionError("SCORER unit reached forbidden " + label)
        return refused

    for name in ("_stage_sources", "_stage_database", "_secure_directory",
                 "_spawn_owned_guardian", "_owned_boundary_io", "_run_isolated"):
        monkeypatch.setattr(core, name, deny(name), raising=False)
    monkeypatch.setattr(core.PilotExecutor, "score_sql", deny("legacy native score"))
    monkeypatch.setattr(core.PilotExecutor, "run_program", deny("legacy program"))
    monkeypatch.setattr(core.PilotExecutor, "owned_program", deny("PROGRAM owner"))
    monkeypatch.setattr(core.threading.Thread, "start", deny("controller thread"))
    monkeypatch.setattr(sqlite3, "connect", deny("SQLite"))
    monkeypatch.setattr(subprocess, "Popen", deny("Popen"))
    if hasattr(core, "_CreatorPopen"):
        monkeypatch.setattr(core._CreatorPopen, "__init__", deny("creator"))
    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, deny("socket." + name))
    monkeypatch.setattr(socket, "getaddrinfo", deny("DNS"))
    monkeypatch.setattr(os, "kill", deny("PID signal"))
    monkeypatch.setattr(os, "killpg", deny("group signal"))

    def owned(executor, predicted_sql, task, **kwargs):
        state.allocations.append((executor, predicted_sql, task, kwargs))
        owner = real_factory(executor, predicted_sql, task, **kwargs)
        state.owners.append(owner)
        # Safety also under a broken negative gate: no accidental owner can
        # dispatch. This is the real public cancellation API, not fake execute.
        owner.request_cancel("runner_closed")
        return owner

    def admit(executor, **kwargs):
        identity = real_admit(executor, **kwargs)
        state.admissions.append((executor, kwargs, identity))
        return identity

    monkeypatch.setattr(core.PilotExecutor, "owned_score", owned)
    monkeypatch.setattr(core.PilotExecutor, "admit_program", admit)
    yield state
    assert state.forbidden == [], f"forbidden SCORER attempts: {state.forbidden}"


def test_builder_is_inert_concrete_and_creates_zero_owners(
        tmp_path, monkeypatch, boundaries):
    fixture = _fixture(tmp_path)
    api = _api()
    opened = []

    def no_io(*args, **kwargs):
        opened.append(1)
        raise AssertionError("inert SCORER builder performed filesystem IO")

    # All imports/profile/executor construction precede the zero-IO guard.
    with monkeypatch.context() as patch:
        for target, name in (
                (builtins, "open"), (io, "open"), (os, "open"),
                (os, "stat"), (os, "lstat"), (os, "readlink")):
            patch.setattr(target, name, no_io)
        scorer = api.build_owned_sql_scorer(
            task=fixture.task, executor=fixture.executor,
            db_sha256=fixture.digest, instrument=fixture.instrument)
    assert type(scorer) is api.OwnedSqlScorer
    assert callable(scorer.admit) and not inspect.iscoroutinefunction(scorer.admit)
    assert inspect.iscoroutinefunction(scorer.score_sql)
    assert inspect.iscoroutinefunction(scorer.aclose)
    assert list(scorer._jobs) == []
    assert opened == boundaries.allocations == boundaries.admissions == []
    assert not fixture.executor.state_dir.exists()
    assert not fixture.executor.profile.shared_state_dir.exists()
    _run(scorer.aclose())


@pytest.mark.parametrize("fault", (
    "task-lookalike", "task-subclass", "executor-lookalike",
    "executor-subclass", "instrument-lookalike", "instrument-subclass",
))
def test_builder_requires_exact_first_party_binding_types(
        tmp_path, boundaries, fault):
    fixture = _fixture(tmp_path)
    api = _api()
    options = {}
    if fault == "task-lookalike":
        options["task"] = SimpleNamespace(**dataclasses.asdict(fixture.task))
    elif fault == "task-subclass":
        class Derived(SqlTask):
            pass
        options["task"] = Derived(**dataclasses.asdict(fixture.task))
    elif fault == "executor-lookalike":
        options["executor"] = SimpleNamespace(
            profile=fixture.executor.profile, state_dir=fixture.executor.state_dir)
    elif fault == "executor-subclass":
        class Derived(core.PilotExecutor):
            pass
        options["executor"] = Derived(
            fixture.executor.profile, state_dir=fixture.executor.state_dir)
    elif fault == "instrument-lookalike":
        options["instrument"] = SimpleNamespace(
            **dataclasses.asdict(fixture.instrument))
    else:
        class Derived(InstrumentSettings):
            pass
        # Its inherited validator forbids subclasses. Construct a deliberate
        # test representation without accidentally testing that constructor.
        derived = object.__new__(Derived)
        for field in dataclasses.fields(fixture.instrument):
            object.__setattr__(derived, field.name,
                               getattr(fixture.instrument, field.name))
        options["instrument"] = derived
    with pytest.raises((TypeError, ValueError, api.ScoreInfrastructureError)) as caught:
        _build(fixture, **options)
    _private_error(caught.value)
    assert boundaries.allocations == boundaries.admissions == []


@pytest.mark.parametrize("fault", (
    "bad-digest", "empty-digest", "relative-path",
    "nul-path", "unnormalized-path", "nonstring-path",
))
def test_builder_refuses_bad_digest_and_host_database_path(
        tmp_path, boundaries, fault):
    fixture = _fixture(tmp_path)
    api = _api()
    options = {}
    if fault.endswith("digest"):
        options["db_sha256"] = "" if fault == "empty-digest" else "G" * 64
    else:
        path = {
            "relative-path": "relative.db",
            "nul-path": str(fixture.path) + "\x00",
            "unnormalized-path": str(tmp_path) + "/./opaque-scorer.db",
            "nonstring-path": fixture.path,
        }[fault]
        options["task"] = dataclasses.replace(fixture.task, db_path=path)
    with pytest.raises((TypeError, ValueError, api.ScoreInfrastructureError)) as caught:
        _build(fixture, **options)
    _private_error(caught.value)
    assert boundaries.allocations == boundaries.admissions == []


@pytest.mark.parametrize(
    "field,value", INVALID_SETTINGS,
    ids=[f"{field}-{index:02d}"
         for index, (field, _) in enumerate(INVALID_SETTINGS)],
)
def test_builder_revalidates_complete_instrument_and_native_score_rules(
        tmp_path, boundaries, field, value):
    fixture = _fixture(tmp_path)
    api = _api()
    settings = dataclasses.replace(fixture.instrument)
    # Deliberately corrupt an already-constructed frozen record. The builder,
    # not dataclass construction, must enforce the entire original validator.
    object.__setattr__(settings, field, value)
    with pytest.raises((TypeError, ValueError, api.ScoreInfrastructureError)) as caught:
        _build(fixture, instrument=settings)
    _private_error(caught.value)
    assert boundaries.allocations == boundaries.admissions == []


@pytest.mark.parametrize("field,value", (
    ("gold_sql", 1), ("tier", "unsupported"), ("tier_source", "unsupported"),
))
def test_builder_revalidates_original_task_without_leaking_private_values(
        tmp_path, boundaries, field, value):
    fixture = _fixture(tmp_path)
    api = _api()
    task = dataclasses.replace(fixture.task)
    object.__setattr__(task, field, value)
    with pytest.raises((TypeError, ValueError, api.ScoreInfrastructureError)) as caught:
        _build(fixture, task=task)
    _private_error(caught.value)
    assert boundaries.allocations == boundaries.admissions == []


async def _real_abort_probe(fixture, scorer, api, monkeypatch, boundaries,
                            predicted_sql):
    real_execute = core.OwnedSqlInvocation.execute
    real_close = core.OwnedSqlInvocation.aclose
    completions, closes = [], []

    async def execute(owner):
        job = _job(scorer, owner)
        snapshot = job.snapshot
        # The real safety wrapper requests cancellation before returning the
        # inert owner. Capture that actual state, not a fabricated earlier one.
        assert snapshot.state == "ABORT_LATCHED"
        assert snapshot.intent is owner.snapshot().intent
        assert snapshot.intent.reason == "runner_closed"
        assert snapshot.invocation_id == owner.snapshot().invocation_id
        assert snapshot.role == "scorer"
        assert snapshot.request_sha256 == core.request_sha256(owner.request)
        assert snapshot.profile_sha256 == core.execution_profile_sha256(
            fixture.executor.profile)
        completion = await real_execute(owner)
        completions.append(completion)
        return completion

    async def close(owner):
        job = _job(scorer, owner)
        assert job.close_task is asyncio.current_task(), (
            "SCORER invocation close task not retained before first await")
        closes.append(owner)
        return await real_close(owner)

    monkeypatch.setattr(core.OwnedSqlInvocation, "execute", execute)
    monkeypatch.setattr(core.OwnedSqlInvocation, "aclose", close)
    try:
        with pytest.raises(api.ScoreInfrastructureError) as caught:
            await scorer.score_sql(predicted_sql)
        _private_error(caught.value)
        assert len(boundaries.allocations) == len(boundaries.owners) == 1
        executor, prediction, task, kwargs = boundaries.allocations[0]
        assert executor is fixture.executor and prediction == predicted_sql
        assert task == fixture.task
        assert kwargs == {
            "db_sha256": fixture.digest, "instrument": fixture.instrument,
        }
        owner, = boundaries.owners
        assert type(owner) is core.OwnedSqlInvocation
        assert owner.executor is fixture.executor
        assert owner.db_path == fixture.path
        assert type(owner.request) is core.ScoreRequest
        assert owner.request == core.ScoreRequest(
            dataclasses.replace(fixture.task, db_path="/db.sqlite"),
            predicted_sql, fixture.instrument.scorer_timeout_s,
            fixture.instrument.scorer_max_rows, fixture.instrument.compare,
            fixture.digest)
        assert owner.request.task.gold_sql == GOLD
        assert fixture.task.db_path == str(fixture.path)
        job = _job(scorer, owner)
        assert job.completion is completions[0]
        assert job.completion.outcome is None
        assert job.completion.abort.kind == "cancelled", (
            "real predispatch cancellation was not infrastructure-fatal")
        ack = job.completion.cleanup_ack
        assert job.ack is ack
        assert job.close_task.done() and job.close_task.result() is ack
        assert ack.not_started is True and ack.released is True
        assert ack.role == "scorer"
        assert ack.invocation_id == job.snapshot.invocation_id
        assert ack.request_sha256 == job.snapshot.request_sha256
        assert ack.profile_sha256 == job.snapshot.profile_sha256
        assert all(completion is job.completion for completion in completions)
        assert await scorer.aclose() is None
        assert await scorer.aclose() is None
        assert closes == [owner], "repeated SCORER close replayed public owner close"
        assert list(scorer._jobs) == [job], "closed SCORER discarded retained proof"
        assert len(boundaries.admissions) == 2, (
            "score did not repeat fresh public admission")
    finally:
        # Safety never substitutes a public outcome/ACK. If a broken adapter
        # escaped before draining, finish the actual cancelled owner.
        for owner in boundaries.owners:
            if owner.snapshot().state != "HOST_SEALED":
                await real_execute(owner)
                await real_close(owner)


@pytest.mark.parametrize("timeout", (0.25, 5.0, 30.0))
def test_native_scorer_float_timeouts_are_not_program_fixed_five(
        tmp_path, monkeypatch, boundaries, timeout):
    fixture = _fixture(tmp_path)
    fixture.instrument = dataclasses.replace(
        fixture.instrument, scorer_timeout_s=timeout,
        program_timeout_s=8.125, wrapper_timeout_s=17.0,
        compare="multiset" if timeout == 5.0 else "set")
    api = _api()
    scorer = _build(fixture)
    assert scorer.admit() is None
    _run(_real_abort_probe(
        fixture, scorer, api, monkeypatch, boundaries, PREDICTION))


@pytest.mark.parametrize("state", ("not-admitted", "closed"))
def test_score_requires_explicit_admission_and_refuses_after_close(
        tmp_path, boundaries, state):
    fixture = _fixture(tmp_path)
    api = _api()
    scorer = _build(fixture)

    async def case():
        if state == "closed":
            assert scorer.admit() is None
            assert await scorer.aclose() is None
        before = len(boundaries.admissions)
        try:
            with pytest.raises(api.ScoreInfrastructureError) as caught:
                await scorer.score_sql(PREDICTION)
            _private_error(caught.value)
            assert boundaries.allocations == []
            assert len(boundaries.admissions) == before, (
                "unadmitted/closed score attempted implicit admission")
            assert list(scorer._jobs) == []
        finally:
            await scorer.aclose()

    _run(case())


def test_repeated_admit_reuses_original_seal_and_empty_close_is_idempotent(
        tmp_path, boundaries):
    fixture = _fixture(tmp_path)
    api = _api()
    scorer = _build(fixture)
    assert scorer.admit() is None
    assert scorer.admit() is None
    assert len(boundaries.admissions) == 2
    first, second = (entry[2] for entry in boundaries.admissions)
    assert type(first) is core.ProgramDatabaseIdentity and second == first
    assert all(executor is fixture.executor and kwargs == {
        "db_path": str(fixture.path), "db_sha256": fixture.digest,
    } for executor, kwargs, _ in boundaries.admissions)
    assert boundaries.allocations == []

    async def case():
        assert await scorer.aclose() is None
        assert await scorer.aclose() is None
        with pytest.raises(api.ScoreInfrastructureError):
            scorer.admit()
        assert len(boundaries.admissions) == 2

    _run(case())


@pytest.mark.parametrize("fault", ("task", "settings", "profile", "state-dir"))
def test_original_binding_is_sealed_at_construction_not_first_admission(
        tmp_path, boundaries, fault):
    fixture = _fixture(tmp_path)
    api = _api()
    scorer = _build(fixture)
    if fault == "task":
        object.__setattr__(fixture.task, "gold_sql", GOLD + "-changed")
    elif fault == "settings":
        object.__setattr__(fixture.instrument, "source_sha256", "b" * 64)
    elif fault == "profile":
        object.__setattr__(fixture.executor, "profile", dataclasses.replace(
            fixture.executor.profile))
    else:
        object.__setattr__(fixture.executor, "state_dir", tmp_path / "changed-state")
    try:
        with pytest.raises(api.ScoreInfrastructureError) as caught:
            scorer.admit()
        _private_error(caught.value)
        assert boundaries.allocations == []
        assert list(scorer._jobs) == []
    finally:
        _run(scorer.aclose())


def test_explicit_admission_does_not_replace_a_validly_shaped_wrong_db_digest(
        tmp_path, boundaries):
    fixture = _fixture(tmp_path)
    api = _api()
    scorer = _build(fixture, db_sha256="0" * 64)
    try:
        with pytest.raises(api.ScoreInfrastructureError) as caught:
            scorer.admit()
        _private_error(caught.value)
        assert boundaries.allocations == []
        assert list(scorer._jobs) == []
    finally:
        _run(scorer.aclose())


async def _refuse_mutated_score(scorer, api, boundaries):
    try:
        with pytest.raises(api.ScoreInfrastructureError) as caught:
            await scorer.score_sql(PREDICTION)
        _private_error(caught.value)
        assert boundaries.allocations == [], "binding drift allocated SCORER owner"
        assert list(scorer._jobs) == []
    finally:
        await scorer.aclose()


@pytest.mark.parametrize("field", TASK_FIELDS)
def test_each_original_task_field_is_sealed_before_allocation(
        tmp_path, boundaries, field):
    fixture = _fixture(tmp_path)
    api = _api()
    scorer = _build(fixture)
    assert {field.name for field in dataclasses.fields(fixture.task)} == set(TASK_FIELDS)
    scorer.admit()
    value = {"tier": "moderate", "tier_source": "annotated",
             "db_path": str(tmp_path / "changed.db")}.get(
                 field, getattr(fixture.task, field) + "-changed")
    object.__setattr__(fixture.task, field, value)
    _run(_refuse_mutated_score(scorer, api, boundaries))


@pytest.mark.parametrize("field", SETTINGS_FIELDS)
def test_every_instrument_field_including_unused_metadata_is_sealed(
        tmp_path, boundaries, field):
    fixture = _fixture(tmp_path)
    api = _api()
    scorer = _build(fixture)
    assert {field.name for field in dataclasses.fields(fixture.instrument)} == set(
        SETTINGS_FIELDS)
    scorer.admit()
    current = getattr(fixture.instrument, field)
    if field == "compare":
        value = "multiset"
    elif field == "source_paths":
        value = ("ptc/runtime.py",)
    elif field == "source_sha256":
        value = "b" * 64
    elif type(current) in (int, float):
        value = current + 1
    else:
        value = current + "-changed"
    object.__setattr__(fixture.instrument, field, value)
    _run(_refuse_mutated_score(scorer, api, boundaries))


@pytest.mark.parametrize("fault", ("profile-identity", "profile-content", "state-dir"))
def test_executor_profile_and_state_binding_drift_is_prealocation(
        tmp_path, boundaries, fault):
    fixture = _fixture(tmp_path)
    api = _api()
    scorer = _build(fixture)
    scorer.admit()
    profile = fixture.executor.profile
    if fault == "profile-identity":
        object.__setattr__(fixture.executor, "profile", dataclasses.replace(profile))
    elif fault == "profile-content":
        program = profile.binding.program
        changed = dataclasses.replace(program, sources=(
            dataclasses.replace(program.sources[0], sha256="0" * 64),
            *program.sources[1:]))
        # Deliberate in-place mutation tests fingerprint, not only identity.
        object.__setattr__(profile, "binding", dataclasses.replace(
            profile.binding, program=changed))
    else:
        object.__setattr__(fixture.executor, "state_dir", tmp_path / "changed-state")
    _run(_refuse_mutated_score(scorer, api, boundaries))


@pytest.mark.parametrize("fault", (
    "same-bytes-replace", "inplace", "sidecar", "readmit-replace",
))
def test_fresh_database_checks_never_reseal_a_changed_original_identity(
        tmp_path, boundaries, fault):
    fixture = _fixture(tmp_path)
    api = _api()
    scorer = _build(fixture)
    scorer.admit()
    initial = fixture.path.stat()
    if fault in {"same-bytes-replace", "readmit-replace"}:
        replacement = tmp_path / "replacement.db"
        replacement.write_bytes(fixture.raw)
        os.replace(replacement, fixture.path)
    elif fault == "inplace":
        fixture.path.write_bytes(fixture.raw)
        os.utime(fixture.path, ns=(
            initial.st_atime_ns, initial.st_mtime_ns + 1_000_000))
    else:
        Path(str(fixture.path) + "-journal").write_bytes(b"sidecar fixture")
    if fault == "readmit-replace":
        with pytest.raises(api.ScoreInfrastructureError) as caught:
            scorer.admit()
        _private_error(caught.value)
    _run(_refuse_mutated_score(scorer, api, boundaries))
    assert boundaries.allocations == []


@pytest.mark.parametrize("fault", (
    "missing-scorer-member", "source-pin", "observer-after-admit",
))
def test_admission_uses_both_role_closures_without_metadata_repinning(
        tmp_path, boundaries, fault):
    fixture = _fixture(tmp_path)
    api = _api()
    profile = fixture.executor.profile
    if fault != "observer-after-admit":
        role = "scorer" if fault == "missing-scorer-member" else "program"
        record = getattr(profile.binding, role)
        pins = record.sources[1:] if role == "scorer" else (
            dataclasses.replace(record.sources[0], sha256="0" * 64),
            *record.sources[1:])
        profile = dataclasses.replace(profile, binding=dataclasses.replace(
            profile.binding, **{role: dataclasses.replace(record, sources=pins)}))
        fixture.executor = core.PilotExecutor(
            profile, state_dir=fixture.executor.state_dir)
    # A fresh metadata hash is supplied evidence only, never permission to
    # replace the execution profile's expected source closure or observer pin.
    fixture.instrument = dataclasses.replace(
        fixture.instrument, source_sha256=hashlib.sha256(
            (core.installed_source_root() / "ptc/sql_isolation.py").read_bytes()
        ).hexdigest())
    scorer = _build(fixture)
    expected = profile.binding
    if fault == "observer-after-admit":
        scorer.admit()
        profile.observer.binary.write_bytes(b"changed inert observer fixture\n")
        _run(_refuse_mutated_score(scorer, api, boundaries))
    else:
        with pytest.raises(api.ScoreInfrastructureError) as caught:
            scorer.admit()
        _private_error(caught.value)
        _run(scorer.aclose())
    assert fixture.executor.profile.binding is expected
    assert boundaries.allocations == []
    assert not fixture.executor.state_dir.exists()


@pytest.mark.parametrize("prediction", ("", PREDICTION), ids=("empty", "ordinary"))
def test_real_predispatch_abort_retains_request_job_completion_and_one_close(
        tmp_path, monkeypatch, boundaries, prediction):
    fixture = _fixture(tmp_path)
    api = _api()
    scorer = _build(fixture)
    scorer.admit()
    _run(_real_abort_probe(
        fixture, scorer, api, monkeypatch, boundaries, prediction))


@pytest.mark.parametrize("prediction", (None, 1), ids=("none", "integer"))
def test_invalid_prediction_is_infrastructure_fatal_without_an_owner(
        tmp_path, boundaries, prediction):
    fixture = _fixture(tmp_path)
    api = _api()
    scorer = _build(fixture)
    scorer.admit()

    async def case():
        try:
            with pytest.raises(api.ScoreInfrastructureError) as caught:
                await scorer.score_sql(prediction)
            _private_error(caught.value)
            assert boundaries.owners == []
            assert list(scorer._jobs) == []
        finally:
            assert await scorer.aclose() is None

    _run(case())


@pytest.mark.parametrize("field,value", (
    ("released", False), ("role", "program"),
    ("request_sha256", "0" * 64), ("profile_sha256", "0" * 64),
))
def test_mutated_real_owner_ack_is_not_accepted_or_upgraded_on_adapter_close(
        tmp_path, monkeypatch, boundaries, field, value):
    fixture = _fixture(tmp_path)
    api = _api()
    scorer = _build(fixture)
    scorer.admit()
    real_close = core.OwnedSqlInvocation.aclose
    real_execute = core.OwnedSqlInvocation.execute
    changed, closes = [], []

    async def close(owner):
        assert _job(scorer, owner).close_task is asyncio.current_task()
        closes.append(owner)
        ack = await real_close(owner)
        if not any(actual is ack for actual, _ in changed):
            changed.append((ack, getattr(ack, field)))
        # Negative-only corruption of the actual owner-produced record. No
        # usable ACK is issued or reconstructed by the test.
        object.__setattr__(ack, field, value)
        return ack

    monkeypatch.setattr(core.OwnedSqlInvocation, "aclose", close)

    async def case():
        try:
            with pytest.raises(api.ScoreInfrastructureError) as caught:
                await scorer.score_sql(PREDICTION)
            _private_error(caught.value)
            assert len(boundaries.owners) == len(changed) == 1
            owner, = boundaries.owners
            job = _job(scorer, owner)
            assert job.ack is None, "malformed cleanup ACK was accepted as retained proof"
            with pytest.raises(api.ScoreInfrastructureError):
                await scorer.aclose()
            assert closes == [owner], "malformed ACK caused public close replay"
        finally:
            for ack, original in changed:
                object.__setattr__(ack, field, original)
            # Restore then delegate to real public execute for safety. Do not
            # assert a successful adapter close after infrastructure failure.
            for owner in boundaries.owners:
                completion = await real_execute(owner)
                if changed:
                    assert completion.cleanup_ack is changed[0][0]
                assert completion.cleanup_ack.not_started is True
                if owner not in closes:
                    await real_close(owner)

    _run(case())


def test_retained_actual_close_failure_remains_fatal_without_public_close_replay(
        tmp_path, monkeypatch, boundaries):
    fixture = _fixture(tmp_path)
    api = _api()
    scorer = _build(fixture)
    scorer.admit()
    real_close = core.OwnedSqlInvocation.aclose
    real_execute = core.OwnedSqlInvocation.execute
    closes = []

    async def close(owner):
        assert _job(scorer, owner).close_task is asyncio.current_task()
        closes.append(owner)
        await real_close(owner)
        raise RuntimeError(GOLD)

    monkeypatch.setattr(core.OwnedSqlInvocation, "aclose", close)

    async def case():
        try:
            with pytest.raises(api.ScoreInfrastructureError) as caught:
                await scorer.score_sql(PREDICTION)
            _private_error(caught.value)
            owner, = boundaries.owners
            job = _job(scorer, owner)
            assert job.close_task.done() and job.ack is None
            with pytest.raises(api.ScoreInfrastructureError) as caught:
                await scorer.aclose()
            _private_error(caught.value)
            assert closes == [owner], "failed retained close was replayed"
        finally:
            for owner in boundaries.owners:
                completion = await real_execute(owner)
                assert completion.cleanup_ack.not_started is True
                if owner not in closes:
                    await real_close(owner)

    _run(case())


def test_foreign_real_owner_ack_cannot_replace_matching_cleanup_metadata(
        tmp_path, monkeypatch, boundaries):
    """Corrupt real NOT_STARTED records, never manufacture a usable ACK."""
    fixture = _fixture(tmp_path)
    api = _api()
    scorer = _build(fixture)
    scorer.admit()
    real_execute = core.OwnedSqlInvocation.execute
    real_close = core.OwnedSqlInvocation.aclose
    delegated, changed = [], []

    async def case():
        foreign = fixture.executor.owned_score(
            PREDICTION, fixture.task, db_sha256=fixture.digest,
            instrument=fixture.instrument)
        foreign_completion = await real_execute(foreign)
        foreign_ack = foreign_completion.cleanup_ack
        foreign_id = foreign_ack.invocation_id

        async def close(owner):
            assert owner is not foreign
            job = _job(scorer, owner)
            assert job.close_task is asyncio.current_task()
            original_ack = await real_close(owner)
            delegated.append(owner)
            completion = owner._completion
            changed.append((completion, original_ack))
            # Match every public binding field while retaining the foreign
            # owner's actual private capability. Negative-only corruption.
            object.__setattr__(foreign_ack, "invocation_id", owner.invocation_id)
            object.__setattr__(completion, "cleanup_ack", foreign_ack)
            assert (
                foreign_ack.invocation_id == job.snapshot.invocation_id
                and foreign_ack.role == job.snapshot.role
                and foreign_ack.request_sha256 == job.snapshot.request_sha256
                and foreign_ack.profile_sha256 == job.snapshot.profile_sha256
                and foreign_ack._authority.owner is foreign
                and foreign_ack._authority.owner is not owner)
            return foreign_ack

        monkeypatch.setattr(core.OwnedSqlInvocation, "aclose", close)
        try:
            with pytest.raises(api.ScoreInfrastructureError) as caught:
                await scorer.score_sql(PREDICTION)
            _private_error(caught.value)
            assert str(caught.value) == "owned SQL scorer cleanup failed"
            owner, = delegated
            job = _job(scorer, owner)
            assert job.ack is None
            with pytest.raises(api.ScoreInfrastructureError):
                await scorer.aclose()
            assert delegated == [owner], "foreign ACK caused public close replay"
        finally:
            # Restore actual records before independent safety. This cannot
            # retrospectively turn the captured adapter failure into success.
            object.__setattr__(foreign_ack, "invocation_id", foreign_id)
            for completion, original_ack in changed:
                object.__setattr__(completion, "cleanup_ack", original_ack)
            for actual in boundaries.owners:
                await real_execute(actual)
                if actual not in delegated:
                    await real_close(actual)

    _run(case())


def test_shutdown_starts_every_real_owner_close_before_joining_the_first(
        tmp_path, monkeypatch, boundaries):
    """Real NOT_STARTED owners with observational delay, not unknown proof."""
    fixture = _fixture(tmp_path)
    api = _api()
    scorer = _build(fixture)
    scorer.admit()
    real_execute = core.OwnedSqlInvocation.execute
    real_close = core.OwnedSqlInvocation.aclose

    async def case():
        release_body = asyncio.Event()
        release_close = asyncio.Event()
        entered_body = [asyncio.Event(), asyncio.Event()]
        entered_close = [asyncio.Event(), asyncio.Event()]
        closes = []

        def index(owner):
            return next(i for i, actual in enumerate(boundaries.owners)
                        if actual is owner)

        async def execute(owner):
            job = _job(scorer, owner)
            completion = await real_execute(owner)
            if asyncio.current_task() is not job.close_task:
                entered_body[index(owner)].set()
                await asyncio.wait_for(release_body.wait(), 2.0)
            return completion

        async def close(owner):
            job = _job(scorer, owner)
            assert job.close_task is asyncio.current_task()
            closes.append(owner)
            entered_close[index(owner)].set()
            await asyncio.wait_for(release_close.wait(), 2.0)
            return await real_close(owner)

        monkeypatch.setattr(core.OwnedSqlInvocation, "execute", execute)
        monkeypatch.setattr(core.OwnedSqlInvocation, "aclose", close)
        calls = [asyncio.create_task(scorer.score_sql(prediction))
                 for prediction in ("first", "second")]
        shutdown = None
        try:
            await asyncio.wait_for(asyncio.gather(
                *(event.wait() for event in entered_body)), 1.0)
            assert len(boundaries.owners) == len(scorer._jobs) == 2
            assert boundaries.owners[0] is not boundaries.owners[1]
            shutdown = asyncio.create_task(scorer.aclose())
            await asyncio.wait_for(entered_close[0].wait(), 0.5)
            await asyncio.wait_for(entered_close[1].wait(), 0.5)
            assert not shutdown.done(), "shutdown escaped held actual close tasks"
            assert all(isinstance(job.close_task, asyncio.Task)
                       for job in scorer._jobs)
            before = len(boundaries.allocations)
            with pytest.raises(api.ScoreInfrastructureError):
                await scorer.score_sql("closed adapter")
            assert len(boundaries.allocations) == before == 2
            release_close.set()
            assert await shutdown is None
            release_body.set()
            results = await asyncio.gather(*calls, return_exceptions=True)
            assert all(isinstance(result, api.ScoreInfrastructureError)
                       for result in results), "real abort became fabricated score"
            assert len(closes) == 2
            assert all(sum(actual is owner for actual in closes) == 1
                       for owner in boundaries.owners)
            for owner in boundaries.owners:
                job = _job(scorer, owner)
                assert job.ack is job.completion.cleanup_ack
                assert job.close_task.result() is job.ack
                assert job.ack.not_started is True
            assert await scorer.aclose() is None
            assert len(closes) == 2
        finally:
            release_close.set()
            release_body.set()
            await asyncio.gather(*calls, return_exceptions=True)
            if shutdown is not None:
                await asyncio.gather(shutdown, return_exceptions=True)
            for owner in boundaries.owners:
                if owner.snapshot().state != "HOST_SEALED":
                    await real_execute(owner)
                    await real_close(owner)

    _run(case())
