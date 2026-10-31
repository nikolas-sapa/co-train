"""Offline, test-first owned-invocation contracts. Not process qualification.

No backend or public method is replaced with a canned result. These tests cover
allocation, admission refusal, cancellation before dispatch, and the frame codec.
They deliberately do not stand in for the sixteen real-process race cases.

Record spelling selected here (the spec gives semantics, not every field name):
  CancelIntent(invocation_id: UUID, reason, requested_ns, deadline_ns)
  CancelReceipt.status / .intent
  InvocationSnapshot.state / .invocation_id / .role / .request_sha256 /
      .profile_sha256 / .intent / .incomplete
  InvocationCompletion.outcome / .abort / .cleanup_ack
  OutcomeAbort.invocation_id / .role / .kind / .detail_code
  CleanupCompleteAck.invocation_id / .role / .request_sha256 / .profile_sha256 /
      .not_started / .released / .cleanup_trigger_ns / .cleanup_deadline_ns /
      .completed_ns / .terminal_ack_sha256

Two pure production-helper contracts, not fake-backend injection points:
  _encode_cancel_frame(intent: CancelIntent) -> bytes
  _decode_cancel_frame(data: bytes, *, invocation_id: UUID, now_ns: int)
      -> tuple[int, int]  # original requested_ns, deadline_ns; no new budget
The decoder raises ValueError for invalid complete/acquired frames. Acquisition
timeouts, actual readers and delivery are NOT tested by the pure codec cases.

The only backend injection seams mentioned here are denial sentinels:
  _spawn_owned_guardian(*args, **kwargs): must not be called in these cases
  _owned_boundary_io(profile, job): must not be called in these cases
No argument/return shape for a successful process bridge is invented here.
"""
import asyncio
import dataclasses
import hashlib
import inspect
import os
import socket
import sqlite3
import struct
import subprocess
import threading
import time
import uuid

import pytest

from ptc import sql_isolation as m


CAP_NS = 12_000_000_000
FRAME = struct.Struct(">8s16sQQ")
INVOCATION_ID = uuid.UUID("a1907e40-f26a-478b-9503-376147398f1a")
REQUESTED_NS = 1_000_000_000_000
DEADLINE_NS = REQUESTED_NS + CAP_NS
UINT64_MAX = (1 << 64) - 1
ROLES = ("program", "scorer")


def _symbol(name):
    # Resolve new symbols in the call phase: missing implementation is RED,
    # not an import/collection error or a silently skipped acceptance gate.
    assert hasattr(m, name), f"owned invocation contract missing: {name}"
    return getattr(m, name)


def _owned_factory(executor, role):
    name = "owned_program" if role == "program" else "owned_score"
    assert hasattr(executor, name), f"public owned invocation API missing: {name}"
    return getattr(executor, name)


@pytest.fixture
def loop():
    # Create asyncio's private anonymous self-pipe before network guards.
    event_loop = asyncio.new_event_loop()
    yield event_loop
    pending = asyncio.all_tasks(event_loop)
    for task in pending:
        task.cancel()
    if pending:
        _, still_pending = event_loop.run_until_complete(
            asyncio.wait(pending, timeout=0.1))
    else:
        still_pending = set()
    event_loop.close()
    assert not still_pending, "offline public call retained pending host tasks"


@pytest.fixture(autouse=True)
def offline_only(loop, monkeypatch):
    calls = []

    def deny(label):
        def forbidden(*args, **kwargs):
            calls.append(label)
            raise AssertionError(f"offline owned test reached forbidden IO: {label}")
        return forbidden

    # Guards fail even if production swallows an exception into a typed abort.
    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, deny("socket." + name))
    monkeypatch.setattr(socket, "getaddrinfo", deny("getaddrinfo"))
    monkeypatch.setattr(subprocess, "Popen", deny("Popen"))
    if hasattr(m, "_CreatorPopen"):
        monkeypatch.setattr(m._CreatorPopen, "__init__", deny("_CreatorPopen"))
    monkeypatch.setattr(sqlite3, "connect", deny("sqlite3.connect"))
    monkeypatch.setattr(os, "killpg", deny("process-group signal"))
    monkeypatch.setattr(os, "kill", deny("PID-derived signal"))
    for name in ("_stage_sources", "_stage_database", "_secure_directory"):
        monkeypatch.setattr(m, name, deny(name))
    monkeypatch.setattr(
        m, "_spawn_owned_guardian", deny("_spawn_owned_guardian"), raising=False)
    monkeypatch.setattr(
        m, "_owned_boundary_io", deny("_owned_boundary_io"), raising=False)
    yield calls
    assert calls == [], f"forbidden IO attempted: {calls}"


def _profile(tmp_path):
    """Pin the installed required closure afresh. Observer bytes stay inert."""
    root = m.installed_source_root()
    observer = tmp_path / "observer-never-executed"
    observer.write_bytes(b"first-party inert observer fixture\n")

    def pins(names):
        return tuple(m.SourcePin(name, hashlib.sha256(
            (root / name).read_bytes()).hexdigest()) for name in names)

    return m.make_execution_profile(
        daemon_socket=tmp_path / "daemon-never-opened.sock",
        observer=m.MemoryObserver(
            binary=observer,
            binary_sha256=hashlib.sha256(observer.read_bytes()).hexdigest()),
        program_sources=pins(m._PROGRAM_PATHS),
        scorer_sources=pins(m._SCORER_PATHS),
        controller_sources=pins(("ptc/sql_isolation.py",)))


def _inputs(tmp_path, role):
    db = tmp_path / "not-a-database"
    db.write_bytes(b"inert bytes, never open with SQLite\n")
    db_sha256 = hashlib.sha256(db.read_bytes()).hexdigest()
    if role == "program":
        args = ("print(1)",)
        kwargs = dict(db_path=str(db), db_sha256=db_sha256, max_rows=1)
        request = m.ProgramRequest("print(1)", 1, db_sha256)
    else:
        from bench.task import SqlTask
        from train.sql_episodes import InstrumentSettings
        task = SqlTask(
            "owned-fixture", "q", "", "SELECT 1", "db", str(db),
            "simple", "derived", "s", "s", "fixture")
        instrument = InstrumentSettings(
            action_cap=1, action_max_rows=1, scorer_max_rows=1, compare="set",
            scorer_timeout_s=1.0, program_timeout_s=5.0,
            wrapper_timeout_s=1.0, python_version="fixture",
            sqlite_version="fixture", source_paths=("ptc/sql_isolation.py",),
            source_sha256="a" * 64)
        args = ("SELECT 1", task)
        kwargs = dict(db_sha256=db_sha256, instrument=instrument)
        request = m.ScoreRequest(
            dataclasses.replace(task, db_path="/db.sqlite"),
            "SELECT 1", 1.0, 1, "set", db_sha256)
    return args, kwargs, request


def _case(tmp_path, role, *, profile=None):
    if profile is None:
        profile = _profile(tmp_path)
    args, kwargs, request = _inputs(tmp_path, role)
    executor = m.PilotExecutor(profile, state_dir=tmp_path / "not-staged")
    invocation = _owned_factory(executor, role)(*args, **kwargs)
    assert isinstance(invocation, _symbol("OwnedSqlInvocation"))
    return invocation, profile, request


def _finish(loop, *coroutines):
    """Finite caller wait; unlike wait_for, cancellation cannot extend timeout."""
    tasks = [loop.create_task(coroutine) for coroutine in coroutines]
    _, pending = loop.run_until_complete(asyncio.wait(tasks, timeout=1.0))
    assert not pending, "not-started/refused invocation failed to finish within 1s"
    return [task.result() for task in tasks]


def _assert_snapshot(snapshot, profile, request, role):
    assert isinstance(snapshot, _symbol("InvocationSnapshot"))
    assert type(snapshot.invocation_id) is uuid.UUID
    assert snapshot.role == role
    assert snapshot.request_sha256 == m.request_sha256(request)
    assert snapshot.profile_sha256 == m.execution_profile_sha256(profile)


def _assert_not_started_ack(ack, snapshot, intent=None):
    assert isinstance(ack, _symbol("CleanupCompleteAck"))
    assert ack.invocation_id == snapshot.invocation_id
    assert ack.role == snapshot.role
    assert ack.request_sha256 == snapshot.request_sha256
    assert ack.profile_sha256 == snapshot.profile_sha256
    assert ack.not_started is True
    assert ack.released is True
    assert ack.terminal_ack_sha256 is None, "no fabricated terminal ACK before START"
    assert type(ack.completed_ns) is int
    assert ack.completed_ns <= time.monotonic_ns()
    if intent is not None:
        assert ack.cleanup_trigger_ns == intent.requested_ns
        assert ack.cleanup_deadline_ns <= intent.deadline_ns
        assert intent.requested_ns <= ack.completed_ns <= ack.cleanup_deadline_ns
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        ack.released = False


@pytest.mark.parametrize("role", ROLES)
def test_owned_factory_is_inert_and_preserves_call_shape(
        tmp_path, monkeypatch, role):
    profile = _profile(tmp_path)
    args, kwargs, request = _inputs(tmp_path, role)
    executor = m.PilotExecutor(profile, state_dir=tmp_path / "not-staged")
    factory = _owned_factory(executor, role)
    legacy = executor.run_program if role == "program" else executor.score_sql
    assert inspect.signature(factory).parameters == inspect.signature(legacy).parameters
    admission_calls = []

    def no_admission(*args, **kwargs):
        admission_calls.append(1)
        raise AssertionError("factory performed source/profile admission IO")

    with monkeypatch.context() as patch:
        patch.setattr(m, "build_execution_binding", no_admission)
        patch.setattr(m, "_read_owned", no_admission)
        invocation = factory(*args, **kwargs)
        snapshot = invocation.snapshot()
        receipt = invocation.request_cancel("caller_cancelled")
    assert admission_calls == []
    _assert_snapshot(snapshot, profile, request, role)
    assert snapshot.state == "ALLOCATED"
    assert snapshot.intent is None and not snapshot.incomplete
    assert receipt.status == "accepted"
    assert receipt.intent.invocation_id == snapshot.invocation_id
    assert not executor.state_dir.exists()
    assert not profile.shared_state_dir.exists()


@pytest.mark.parametrize("role", ROLES)
def test_owned_factory_validates_request_without_dispatch(tmp_path, role):
    profile = _profile(tmp_path)
    args, kwargs, _ = _inputs(tmp_path, role)
    executor = m.PilotExecutor(profile, state_dir=tmp_path / "not-staged")
    factory = _owned_factory(executor, role)
    with pytest.raises((TypeError, ValueError)):
        factory(None, *args[1:], **kwargs)
    assert not executor.state_dir.exists()
    assert not profile.shared_state_dir.exists()


@pytest.mark.parametrize("role", ROLES)
def test_predispatch_cancel_returns_bound_not_started_ack(tmp_path, loop, role):
    invocation, profile, request = _case(tmp_path, role)
    before = invocation.snapshot()
    start_ns = time.monotonic_ns()
    receipt = invocation.request_cancel("caller_cancelled")
    end_ns = time.monotonic_ns()
    intent = receipt.intent
    assert isinstance(receipt, _symbol("CancelReceipt"))
    assert isinstance(intent, _symbol("CancelIntent"))
    assert receipt.status == "accepted"
    assert intent.reason == "caller_cancelled"
    assert intent.invocation_id == before.invocation_id
    assert start_ns <= intent.requested_ns <= end_ns
    assert intent.deadline_ns - intent.requested_ns == CAP_NS

    completion, = _finish(loop, invocation.execute())
    assert isinstance(completion, _symbol("InvocationCompletion"))
    assert completion.outcome is None, "accepted cancellation exposed usable outcome"
    assert isinstance(completion.abort, _symbol("OutcomeAbort"))
    assert completion.abort.invocation_id == before.invocation_id
    assert completion.abort.role == role
    assert completion.abort.kind == "cancelled"
    assert type(completion.abort.detail_code) is str and completion.abort.detail_code
    _assert_not_started_ack(completion.cleanup_ack, before, intent)
    after = invocation.snapshot()
    _assert_snapshot(after, profile, request, role)
    assert after.state == "HOST_SEALED" and not after.incomplete
    assert after.invocation_id == before.invocation_id
    assert after.intent is intent
    close_ack, = _finish(loop, invocation.aclose())
    assert close_ack is completion.cleanup_ack
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        intent.deadline_ns += 1
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        completion.abort = None
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        receipt.status = "already_completed"
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        after.state = "RUNNING"
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        completion.abort.role = "wrong"
    with pytest.raises((TypeError, ValueError)):
        dataclasses.replace(completion, abort=None)


@pytest.mark.parametrize("role", ROLES)
def test_three_predispatch_intents_share_identity_and_deadline(tmp_path, loop, role):
    invocation, _, _ = _case(tmp_path, role)
    receipts = [
        invocation.request_cancel("caller_cancelled"),
        invocation.request_cancel("runner_closed"),
        invocation.request_cancel("caller_cancelled"),
    ]
    assert [receipt.status for receipt in receipts] == ["accepted", "repeated", "repeated"]
    first = receipts[0].intent
    assert all(receipt.intent is first for receipt in receipts)
    assert first.reason == "caller_cancelled"
    assert first.deadline_ns == first.requested_ns + CAP_NS
    assert invocation.snapshot().intent is first
    a, b, ack = _finish(
        loop, invocation.execute(), invocation.execute(), invocation.aclose())
    assert a is b, "repeated execute did not join retained completion"
    assert ack is a.cleanup_ack
    _assert_not_started_ack(ack, invocation.snapshot(), first)
    again, = _finish(loop, invocation.execute())
    assert again is a


@pytest.mark.parametrize("role", ROLES)
def test_postseal_cancel_is_already_completed_and_writes_nothing(
        tmp_path, loop, monkeypatch, role):
    invocation, _, _ = _case(tmp_path, role)
    invocation.request_cancel("caller_cancelled")
    completion, = _finish(loop, invocation.execute())
    writes = []

    def no_write(*args, **kwargs):
        writes.append(1)
        raise AssertionError("notification write after host seal")

    with monkeypatch.context() as patch:
        patch.setattr(os, "write", no_write)
        receipts = [invocation.request_cancel(reason) for reason in
                    ("caller_cancelled", "runner_closed", "caller_cancelled")]
    assert writes == []
    assert all(receipt.status == "already_completed" for receipt in receipts)
    assert all(receipt.intent is None for receipt in receipts)
    retained, ack = _finish(loop, invocation.execute(), invocation.aclose())
    assert retained is completion and ack is completion.cleanup_ack


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("reason", ("", "timeout", None, True), ids=(
    "empty", "unsupported", "none", "bool"))
def test_invalid_cancel_reason_does_not_latch(tmp_path, loop, role, reason):
    invocation, _, _ = _case(tmp_path, role)
    with pytest.raises((TypeError, ValueError)):
        invocation.request_cancel(reason)
    assert invocation.snapshot().intent is None
    invocation.request_cancel("runner_closed")
    completion, = _finish(loop, invocation.execute())
    assert completion.abort.kind == "cancelled"


@pytest.mark.parametrize("role", ROLES)
def test_execute_rechecks_source_admission_before_staging(tmp_path, loop, role):
    profile = _profile(tmp_path)
    # Syntactically valid profile, deliberately stale source SHA. No source file
    # is changed, no profile/binding validator or public API is substituted.
    first, *rest = profile.binding.program.sources
    wrong = "0" * 64 if first.sha256 != "0" * 64 else "1" * 64
    program = dataclasses.replace(
        profile.binding.program,
        sources=(dataclasses.replace(first, sha256=wrong), *rest))
    stale = dataclasses.replace(
        profile, binding=dataclasses.replace(profile.binding, program=program))
    invocation, _, request = _case(tmp_path, role, profile=stale)
    snapshot = invocation.snapshot()
    _assert_snapshot(snapshot, stale, request, role)
    completion, = _finish(loop, invocation.execute())
    assert completion.outcome is None
    assert completion.abort.kind == "infrastructure"
    assert completion.abort.role == role
    assert completion.abort.invocation_id == snapshot.invocation_id
    assert completion.abort.detail_code == "binding"
    _assert_not_started_ack(completion.cleanup_ack, snapshot)
    assert not (tmp_path / "not-staged").exists()
    assert not stale.shared_state_dir.exists()
    ack, = _finish(loop, invocation.aclose())
    assert ack is completion.cleanup_ack


@pytest.mark.parametrize("role", ROLES)
def test_ack_cannot_be_reconstructed_from_public_record_fields(tmp_path, loop, role):
    invocation, _, _ = _case(tmp_path, role)
    invocation.request_cancel("runner_closed")
    completion, = _finish(loop, invocation.execute())
    ack = completion.cleanup_ack
    # Actual owner-produced ACK first; no test-issued ACK/capability.
    public = {field.name: getattr(ack, field.name)
              for field in dataclasses.fields(ack) if not field.name.startswith("_")}
    with pytest.raises((TypeError, ValueError)):
        type(ack)(**public)


def _intent():
    return _symbol("CancelIntent")(
        invocation_id=INVOCATION_ID, reason="caller_cancelled",
        requested_ns=REQUESTED_NS, deadline_ns=DEADLINE_NS)


def _decode(data, *, now_ns=REQUESTED_NS):
    return _symbol("_decode_cancel_frame")(
        data, invocation_id=INVOCATION_ID, now_ns=now_ns)


def _wire(*, magic=b"SQLCNL01", invocation_id=INVOCATION_ID,
          requested_ns=REQUESTED_NS, deadline_ns=DEADLINE_NS):
    # Independent byte oracle, not production logic copied into the fixture.
    return FRAME.pack(magic, invocation_id.bytes, requested_ns, deadline_ns)


def test_cancel_frame_is_exact_40_byte_uuid_bound_wire():
    intent = _intent()
    actual = _symbol("_encode_cancel_frame")(intent)
    assert type(actual) is bytes
    assert FRAME.size == len(actual) == 40
    assert actual == _wire()
    assert _decode(actual) == (REQUESTED_NS, DEADLINE_NS)


@pytest.mark.parametrize("size", range(40), ids=[f"short-{n:02d}" for n in range(40)])
def test_cancel_frame_rejects_every_short_length(size):
    decode = _symbol("_decode_cancel_frame")
    with pytest.raises(ValueError):
        decode(_wire()[:size], invocation_id=INVOCATION_ID, now_ns=REQUESTED_NS)


@pytest.mark.parametrize("fault", (
    "oversize-41", "wrong-magic", "wrong-uuid", "nil-uuid", "future",
    "deadline-short", "deadline-long", "deadline-before-request", "overflow",
))
def test_cancel_frame_rejects_invalid_identity_and_arithmetic(fault):
    decode = _symbol("_decode_cancel_frame")
    raw, now_ns = _wire(), REQUESTED_NS
    if fault == "oversize-41":
        raw += b"x"
    elif fault == "wrong-magic":
        raw = _wire(magic=b"SQLCNL02")
    elif fault == "wrong-uuid":
        raw = _wire(invocation_id=uuid.UUID("0829a573-3a84-4ecd-8bda-849ace4e9093"))
    elif fault == "nil-uuid":
        raw = _wire(invocation_id=uuid.UUID(int=0))
    elif fault == "future":
        now_ns = REQUESTED_NS - 1
    elif fault == "deadline-short":
        raw = _wire(deadline_ns=DEADLINE_NS - 1)
    elif fault == "deadline-long":
        raw = _wire(deadline_ns=DEADLINE_NS + 1)
    elif fault == "deadline-before-request":
        raw = _wire(deadline_ns=REQUESTED_NS - 1)
    elif fault == "overflow":
        requested = UINT64_MAX - CAP_NS + 1
        raw = _wire(requested_ns=requested, deadline_ns=0)
        now_ns = UINT64_MAX
    with pytest.raises(ValueError):
        decode(raw, invocation_id=INVOCATION_ID, now_ns=now_ns)


@pytest.mark.parametrize("delay_ns", (0, 1, CAP_NS - 1, CAP_NS, CAP_NS + 1),
                         ids=("immediate", "delayed", "last-ns", "at-cap", "expired"))
def test_valid_delayed_frame_never_restarts_budget(delay_ns):
    assert _decode(_wire(), now_ns=REQUESTED_NS + delay_ns) == (
        REQUESTED_NS, DEADLINE_NS)


@pytest.mark.parametrize("role", ROLES)
def test_public_intent_encodes_the_original_identity_and_cap(tmp_path, loop, role):
    invocation, _, _ = _case(tmp_path, role)
    intent = invocation.request_cancel("caller_cancelled").intent
    raw = _symbol("_encode_cancel_frame")(intent)
    assert raw == FRAME.pack(
        b"SQLCNL01", intent.invocation_id.bytes, intent.requested_ns, intent.deadline_ns)
    assert _symbol("_decode_cancel_frame")(
        raw, invocation_id=intent.invocation_id,
        now_ns=time.monotonic_ns()) == (intent.requested_ns, intent.deadline_ns)
    completion, = _finish(loop, invocation.execute())
    assert completion.abort.kind == "cancelled"


def test_existing_role_limits_and_admission_bounds_unchanged(tmp_path):
    from ptc import runtime
    assert runtime.TIMEOUT == 5.0
    assert inspect.signature(runtime.run).parameters["timeout"].default == 5.0
    profile = _profile(tmp_path)
    for role, ceiling, stdout in (("program", 10_000, 1_048_576),
                                  ("scorer", 30_000, 65_536)):
        limits = m.limits_for(role)
        assert dataclasses.asdict(limits) == dict(
            memory_bytes=268_435_456, swap_bytes=0, pids=1,
            tmp_bytes=16_777_216, shm_bytes=1_048_576, nofile=64,
            deadline_ms=ceiling, stdout_bytes=stdout,
            stderr_bytes=65_536, input_bytes=8_388_608)
    assert (profile.admission_bytes, profile.reserve_bytes,
            profile.max_sample_age_ms, profile.api_timeout_ms) == (
                469_762_048, 201_326_592, 4_000, 3_000)


@pytest.fixture
def cleanup_monitor(tmp_path):
    """Actual pipe and sole-reader thread; no guardian or native boundary."""
    cancel_read, cancel_write = os.pipe()
    control_read, control_write = os.pipe()
    now = time.monotonic()
    context = m._OwnedContext(tmp_path, control_read, cancel_read, {
        "nonce": INVOCATION_ID.hex, "deadline": now + 2,
        "cleanup_trigger": now, "cleanup_deadline": now + 2,
    })
    context.begin_cleanup()
    context.monitor.start()
    try:
        assert context.ready.wait(0.2), "monitor startup exceeded 200ms"
        yield context, cancel_write
    finally:
        context.stop.set()
        context.monitor.join(timeout=0.2)
        assert not context.monitor.is_alive(), "fixture monitor failed to join"
        with m._OWNED_CONTEXT_LOCK:
            registered = m._OWNED_CONTEXTS.pop(INVOCATION_ID.hex, None) is context
            m._OWNED_CONTROLS.pop(control_read, None)
        if registered:
            os.close(cancel_read)
        for fd in (cancel_write, control_read, control_write):
            os.close(fd)


def test_cleanup_monitor_retains_malformed_frame_failure(cleanup_monitor):
    context, writer = cleanup_monitor
    os.write(writer, b"x" * 41)
    context.monitor.join(timeout=0.2)
    assert context.error is not None, "oversize frame not latched"
    context.checkpoint()  # Trusted cleanup must not be repeatedly interrupted.
    with pytest.raises(m._Failure, match="protocol"):
        context.retire()


def test_cleanup_monitor_rejects_delayed_extra_byte(
        cleanup_monitor, monkeypatch):
    context, writer = cleanup_monitor
    acquired = threading.Event()
    original = m._acquire_cancel_frame

    def observed(*args, **kwargs):
        result = original(*args, **kwargs)
        acquired.set()
        return result

    monkeypatch.setattr(m, "_acquire_cancel_frame", observed)
    now = time.monotonic_ns()
    intent = m.CancelIntent(INVOCATION_ID, "caller_cancelled", now, now + CAP_NS)
    os.write(writer, m._encode_cancel_frame(intent))
    assert acquired.wait(0.2), "initial valid frame acquisition exceeded 200ms"
    os.write(writer, b"x")  # Deliberately after the original acquisition returned.
    context.monitor.join(timeout=0.2)
    assert context.error is not None, "delayed extra byte escaped sole reader"
    with pytest.raises(m._Failure, match="protocol"):
        context.retire()


@pytest.mark.parametrize("new_error", (False, True), ids=("accounted", "new-fault"))
def test_cleanup_monitor_distinguishes_accounted_protocol_fault(
        cleanup_monitor, new_error):
    # Unit accounting branch only, not proof of guardian publication/cleanup.
    context, writer = cleanup_monitor
    os.write(writer, b"x" * 41)
    context.monitor.join(timeout=0.2)
    assert context.error is not None
    context.accounted_error = context.error
    if new_error:
        context.error = m._Failure("protocol", "new unaccounted monitor failure")
        with pytest.raises(m._Failure, match="protocol"):
            context.retire()
    else:
        context.retire()


@pytest.mark.parametrize("mode", (
    "live-replace", "strict-replace", "live-inplace",
    "live-open-replace", "strict-open-replace", "live-hardlink"))
def test_live_journal_read_distinguishes_atomic_replacement(
        tmp_path, monkeypatch, mode):
    invocation, profile, _ = _case(tmp_path, "program")
    path = tmp_path / "journal.json"
    m._write_owned(path, b'{"marker":"old"}\n')
    initial = path.stat()
    original_read = os.read
    original_open = os.open
    hits = []

    def open_then_replace(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        current = os.fstat(fd)
        if (not hits and (current.st_dev, current.st_ino) ==
                (initial.st_dev, initial.st_ino)):
            hits.append(1)
            if mode == "live-hardlink":
                os.link(path, tmp_path / "alias.json")
            else:
                m._write_owned(path, b'{"marker":"new"}\n')
        return fd

    def replace_during_read(fd, size):
        data = original_read(fd, size)
        if data and not hits and os.fstat(fd).st_ino == initial.st_ino:
            hits.append(1)
            if mode == "live-inplace":
                with path.open("r+b") as stream:
                    stream.write(b'{"marker":"new"}\n')
                os.utime(path, ns=(initial.st_atime_ns, initial.st_mtime_ns + 1_000_000))
            else:
                m._write_owned(path, b'{"marker":"new"}\n')
        return data

    if mode.endswith("open-replace") or mode == "live-hardlink":
        monkeypatch.setattr(os, "open", open_then_replace)
    else:
        monkeypatch.setattr(os, "read", replace_during_read)
    if mode.startswith("strict-"):
        with pytest.raises(ValueError):
            m._read_owned(path)
    else:
        read_fd, write_fd = os.pipe()
        seen = []

        class ReachedSnapshot(Exception):
            pass

        def observe(snapshot):
            seen.append(snapshot["marker"])
            raise ReachedSnapshot()

        invocation._journal = {"deadline": time.monotonic() + 1}
        invocation._latch_cleanup = observe
        try:
            with os.fdopen(read_fd, "rb", buffering=0) as stdout:
                class Process:
                    pass
                process = Process()
                process.stdout = stdout
                if mode in ("live-inplace", "live-hardlink"):
                    with pytest.raises(ValueError):
                        invocation._terminal(process, profile, tmp_path)
                    assert seen == []
                else:
                    with pytest.raises(ReachedSnapshot):
                        invocation._terminal(process, profile, tmp_path)
                    assert seen == ["new"], "live reader consumed an unlinked snapshot"
        finally:
            os.close(write_fd)
    assert hits == [1]
