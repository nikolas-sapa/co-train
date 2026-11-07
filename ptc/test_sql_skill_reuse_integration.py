"""Registered-guardian SQLite dispatch fixture, not native qualification.

Bootstrap image identity and v2 promotion identity are synthetic fixture inputs.
SQLite execution, wire/grant validation, ownership and SDK scoring are not faked.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest


INSTRUCTION = "Select this approved skill by ID and promotion digest."
OLD_SKILL_SOURCES = ("train/sql_skills.py", "train/sql_skill_eval.py")
ADDED_SKILL_SOURCES = (
    "ptc/sql_owned_program.py", "train/sql_skill_pilot.py",
    "train/sql_pilot_api.py", "train/sql_pilot_assets.py",
)
_PLUGIN_ID = "live_registered_skill_fixture"
_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1"}


def capability(module, name):
    value = getattr(module, name, None)
    assert callable(value), f"live reuse capability missing: {module.__name__}.{name}"
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def descriptor(**updates):
    value = dict(skill_id="fixture-count", promotion_sha256="a" * 64,
                 scope='{"coarse_shape":"aggregate","shape":"select-count","source":"fixture"}',
                 instruction=INSTRUCTION)
    value.update(updates)
    return value


# Adapted from the lifecycle fixture protocol, deliberately without its SQLite
# prohibition or its static result table. Loaded only by actual fixture children.
_ACTORS = r'''
import copy, hashlib, json, os, platform, select, socket, sqlite3, struct
import subprocess, sys, threading, time, types
from pathlib import Path

MODE, JOB, END, FAULT = sys.argv[1], Path(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
SCRIPT = str(Path(__file__).resolve())
sys.path.insert(0, str(JOB / ("program" if MODE == "role" else "controller")))
from ptc import sql_isolation as m
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}

def remaining():
    return max(0.001, END - time.monotonic())

def line(fd, maximum):
    raw = bytearray()
    while not raw.endswith(b"\n"):
        assert time.monotonic() < END, "fixture reader deadline"
        assert select.select([fd], [], [], remaining())[0], "fixture reader deadline"
        part = os.read(fd, 1)
        assert part, "fixture EOF"
        raw.extend(part)
        assert len(raw) <= maximum, "fixture byte cap"
    return bytes(raw)

def record(fd, **value):
    raw = json.dumps(value, separators=(",", ":")).encode() + b"\n"
    assert len(raw) < 4096 and os.write(fd, raw) == len(raw)

def role():
    diagnostic = int(sys.argv[5])
    profile = m.execution_profile_from_bytes((JOB / "profile.json").read_bytes())
    journal = json.loads((JOB / "journal.json").read_bytes())
    binding = profile.binding.program
    m.validate_source_pins(binding.sources, source_root=JOB / "program")
    digest = hashlib.sha256((JOB / "db.sqlite").read_bytes()).hexdigest()
    assert digest == journal["db_sha256"]
    assert line(0, 16) == b"START\n"
    def output(raw):
        sys.stdout.buffer.write(struct.pack(">BxxxI", 1, len(raw)) + raw)
        sys.stdout.buffer.flush()
    # Synthetic image-version identity, never claimed to describe this Python.
    boot = m.BootstrapPayload(dict(profile.environment)["PYTHON_VERSION"],
                              sqlite3.sqlite_version, binding.sources, digest)
    output(m.READY + m.encode_wire_message("program", "bootstrap", boot))
    request = m.decode_wire_message(
        line(0, m.limits_for("program").input_bytes), role="program",
        kind="request", request_sha256=journal["request_sha256"]).payload
    assert type(request) is m.ProgramRequest
    assert m.request_sha256(request) == journal["request_sha256"]
    assert request.db_sha256 == digest
    from ptc.sql_arms import run_ptc_program
    if FAULT == "removed-execution":
        record(diagnostic, kind="CANDIDATE_REMOVED",
               request_sha256=m.request_sha256(request))
        raise RuntimeError("declared removed candidate execution")
    native = run_ptc_program(request.program, str(JOB / "db.sqlite"),
                             max_rows=request.max_rows)
    record(diagnostic, kind="EXECUTED", program_sha256=hashlib.sha256(
        request.program.encode("utf-8")).hexdigest(), python=platform.python_version(),
        sqlite=sqlite3.sqlite_version, observation=native.observation,
        request_sha256=m.request_sha256(request), db_sha256=digest)
    result = m.encode_wire_message("program", "result",
        m.ProgramResponse(native.observation, native.rejected),
        request_sha256=("0"*64 if FAULT == "result-digest" else journal["request_sha256"]))
    output(result)
    class Input:
        def readline(self, maximum):
            raw = line(0, maximum)
            if FAULT == "grant-digest":
                grant = m.decode_wire_message(raw, role="program", kind="exit_grant",
                                              request_sha256=journal["request_sha256"])
                return m.encode_wire_message("program", "exit_grant", m.ExitGrant("0"*64),
                                             request_sha256=journal["request_sha256"])
            return raw
    original = sys.stdin
    sys.stdin = types.SimpleNamespace(buffer=Input())
    try:
        m._worker_wait_for_exit_grant("program", journal["request_sha256"], result, request)
        record(diagnostic, kind="GRANT_ACCEPTED")
    except ValueError as exc:
        if FAULT == "grant-digest" and str(exc) == "exit grant result mismatch":
            record(diagnostic, kind="GRANT_REJECTED", reason=str(exc),
                   request_sha256=journal["request_sha256"])
        raise
    finally:
        sys.stdin = original

def guardian():
    control, cancel, diagnostic, safety = map(int, sys.argv[5:9])
    stopped, done = threading.Event(), threading.Event()
    lock = threading.RLock()
    children, threads, daemons = [], [], []
    state = types.SimpleNamespace(role=None, registry=[], started=False,
                                  deleted=False, attached=None, owned=None)
    original_init, original_wait = m._CreatorPopen.__init__, m._CreatorPopen.wait
    thread_start = threading.Thread.start
    def constructor(process, *args, _registry, **kwargs):
        with lock:
            assert not stopped.is_set(), "fixture creator retired"
            children.append((process, _registry))
            original_init(process, *args, _registry=_registry, **kwargs)
    def start(thread):
        with lock:
            assert not stopped.is_set(), "fixture thread creator retired"
            threads.append(thread)
            return thread_start(thread)
    m._CreatorPopen.__init__ = constructor
    threading.Thread.start = start

    class Attached:
        def __init__(self, process):
            self.process, self.timeout = process, 0.1
            self.lock = threading.RLock()
            os.set_blocking(process.stdin.fileno(), False)
            os.set_blocking(process.stdout.fileno(), False)
        def settimeout(self, value):
            self.timeout = value
        def send(self, raw):
            with self.lock:
                fd = self.process.stdin.fileno()
                if not select.select([], [fd], [], min(0.01, self.timeout))[1]:
                    raise socket.timeout()
                return os.write(fd, raw)
        def sendall(self, raw):
            raw = memoryview(raw)
            while raw:
                assert time.monotonic() < END
                try:
                    raw = raw[self.send(raw):]
                except (socket.timeout, BlockingIOError):
                    pass
        def recv(self, maximum):
            with self.lock:
                fd = self.process.stdout.fileno()
                if not select.select([fd], [], [], min(0.01, self.timeout))[0]:
                    raise socket.timeout()
                raw = os.read(fd, maximum)
            if not raw:
                self.process.wait(timeout=remaining())
            return raw
        def close(self):
            with self.lock:
                for stream in (self.process.stdin, self.process.stdout):
                    if not stream.closed:
                        stream.close()

    class Daemon:
        def __init__(self):
            self.active, self.workers = set(), set()
            self.lock = threading.RLock()
            self.shutdown_supervision = None
            daemons.append(self)
        def call(self, method, path, *args, **kwargs):
            token, worker = object(), threading.current_thread()
            with self.lock:
                assert not stopped.is_set()
                self.active.add(token)
                self.workers.add(worker)
            try:
                return self.operation(method, path, *args, **kwargs)
            finally:
                with self.lock:
                    self.active.remove(token)
                    self.workers.remove(worker)
        def operation(self, method, path, *args, **kwargs):
            journal = state.owned.journal
            if path.startswith("/images/sha256:"):
                assert method == "GET"
                return dict(Os="linux", Architecture="arm64",
                    Id="sha256:"+m.IMAGE_CONFIG_SHA256,
                    RepoDigests=["fixture@sha256:"+m.IMAGE_MANIFEST_SHA256])
            if path == "/info":
                return {"MemTotal": 1073741824}
            if path == "/containers/json":
                return ([{"Id": "c"*64, "State": "running"}]
                        if state.role is not None and state.role.poll() is None else [])
            if "/stats?" in path:
                return {"memory_stats": {"usage": 1024}}
            if path.startswith("/containers/create?"):
                assert method == "POST" and state.role is None
                assert args[0] == journal["config"]
                state.role = m._CreatorPopen(
                    [sys.executable, "-I", "-B", SCRIPT, "role", str(JOB),
                     str(END), FAULT, str(diagnostic)], _registry=state.registry,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, pass_fds=(diagnostic,),
                    close_fds=True, env=ENV, bufsize=0)
                return {"Id": "c"*64}
            assert path.startswith("/containers/"+"c"*64), path
            process = state.role
            assert process is not None
            if path.endswith("/start"):
                assert method == "POST" and not state.started
                os.write(process.stdin.fileno(), b"START\n")
                state.started = True
                return None
            if "/kill?" in path:
                assert method == "POST"
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=remaining())
                return None
            if method == "DELETE":
                assert process.poll() is not None and process._creator_waited
                state.deleted = True
                return None
            assert method == "GET" and path.endswith("/json")
            if state.deleted:
                raise m._HTTPFailure(404)
            alive = process.poll() is None
            if not alive:
                process.wait(timeout=remaining())
            config = copy.deepcopy(journal["config"])
            host = config.pop("HostConfig")
            host["Runtime"] = "runc"
            return dict(Id="c"*64, Name="/"+journal["name"],
                Image="sha256:"+m.IMAGE_MANIFEST_SHA256, Config=config, HostConfig=host,
                State=dict(Running=alive, Paused=False, Restarting=False,
                    Pid=process.pid if alive else 0, OOMKilled=False,
                    ExitCode=0 if alive else process.returncode,
                    Status=("running" if state.started else "created") if alive else "exited"),
                Mounts=[dict(Type="bind", Source=x["Source"], Destination=x["Target"],
                    RW=False, Propagation="rprivate") for x in host["Mounts"]])
        def attach(self, cid):
            assert cid == "c"*64
            state.attached = Attached(state.role)
            return state.attached

    class Bridge:
        def daemon(self, profile):
            return Daemon()
        def vm_command(self, profile):
            return ([sys.executable, "-I", "-B", "-c",
                     "print('MemTotal: 1048576 kB\\nMemAvailable: 1048576 kB')"], ENV)
    def boundary(profile, job):
        assert job == JOB and state.owned is None
        state.owned = m._OWNED_CONTEXTS[job.name]
        return Bridge()
    m._owned_boundary_io = boundary
    if FAULT in ("removed-execution", "result-digest"):
        stream_result = m._stream_result
        def refused_result(*args):
            try:
                return stream_result(*args)
            except m._Failure as exc:
                if (FAULT == "removed-execution" and isinstance(exc, m._RPCUncertain)
                        and str(exc) == "guest exited without coordinated exit grant"):
                    record(diagnostic, kind="MISSING_CANDIDATE_REJECTED",
                           reason=str(exc), request_sha256=state.owned.journal["request_sha256"])
                elif (FAULT == "result-digest" and exc.reason == "protocol"
                      and str(exc) == "invalid result frame"
                      and isinstance(exc.__cause__, ValueError)):
                    record(diagnostic, kind="RESULT_REJECTED", reason=str(exc),
                           request_sha256=state.owned.journal["request_sha256"])
                raise
        m._stream_result = refused_result
    if FAULT == "withheld-proof":
        cleanup_evidence = m._owned_cleanup_evidence
        def withheld(*args):
            cleanup_evidence(*args)
            record(diagnostic, kind="PROOF_WITHHELD", canonical_evidence=True,
                   request_sha256=state.owned.journal["request_sha256"])
            raise m._Failure("cleanup", "declared withheld canonical cleanup proof")
        m._owned_cleanup_evidence = withheld

    def evidence():
        return [dict(pid=p.pid, role=p is state.role, waited=p._creator_waited,
                     ambiguous=p._creator_ambiguous, returncode=p.returncode,
                     registered=p in registry) for p, registry in children]
    cleanup_lock = threading.Lock()
    def safe():
        with cleanup_lock:
            with lock:
                stopped.set()
            owned = state.owned
            if owned is not None:
                owned.stop.set()
            for thread in tuple(threads):
                receiver = getattr(getattr(thread, "_target", None), "__self__", None)
                if isinstance(receiver, m._Observer):
                    receiver.stop.set()
            for process, registry in tuple(children):
                assert process.pid is not None and not process._creator_ambiguous
                if process.poll() is None:
                    process.kill()
                original_wait(process, timeout=remaining())
            if owned is not None:
                for pool in tuple(owned.executors):
                    pool.shutdown(wait=False, cancel_futures=False)
            for thread in tuple(threads):
                if thread.ident is not None:
                    thread.join(timeout=remaining())
                assert not thread.is_alive(), "independent nested thread join missing"
            if state.attached is not None:
                state.attached.close()
            assert all(not daemon.active and not daemon.workers for daemon in daemons)
            rows = evidence()
            assert all(row["waited"] and not row["ambiguous"] for row in rows)
            record(diagnostic, kind="SAFE", independent=True, children=rows,
                   threads_joined=len(threads), active_rpc=0, workers=0)

    def watchdog():
        while not done.wait(0.01):
            if select.select([safety], [], [], 0)[0] or time.monotonic() >= END-1:
                try:
                    safe()
                except BaseException as exc:
                    record(diagnostic, kind="UNSAFE", error=type(exc).__name__)
                    return
                os._exit(88)
    supervisor = threading.Thread(target=watchdog, name="fixture-nested-safety", daemon=False)
    thread_start(supervisor)
    try:
        m._owned_guardian(JOB, control, cancel, False)
        rows = evidence()
        assert len([row for row in rows if row["role"]]) == 1
        assert all(row["waited"] and row["registered"] and not row["ambiguous"] for row in rows)
        assert all(not thread.is_alive() for thread in threads)
        assert all(not daemon.active and not daemon.workers for daemon in daemons)
        record(diagnostic, kind="PRODUCT_RESOURCES", children=rows,
               threads_joined=len(threads), active_rpc=0, workers=0, deleted=state.deleted)
        safe()
        done.set()
        supervisor.join(timeout=remaining())
        assert not supervisor.is_alive()
    except BaseException as exc:
        record(diagnostic, kind="GUARDIAN_ERROR", error=type(exc).__name__)
        # Safety owns nested work; failure cannot escape by abandoning threads.
        supervisor.join(timeout=remaining())
        assert not supervisor.is_alive(), "nested SAFE not established"

if MODE == "role":
    role()
else:
    guardian()
'''


class RegisteredGuardian:
    def __init__(self, root, monkeypatch, *, fault="none"):
        from ptc import sql_isolation as core

        self.core, self.fault = core, fault
        self.script = root / "registered-actors.py"
        self.script.write_text(_ACTORS)
        self.slots = []
        self.lock = threading.RLock()
        self.stopping = False
        monkeypatch.setattr(core, "_spawn_owned_guardian", self.spawn)

    def spawn(self, owner, job, control_fd, cancel_fd, lock_fd, log, emergency=False):
        with self.lock:
            assert not self.stopping and not emergency
            diagnostic_r, diagnostic_w = os.pipe()
            safety_r, safety_w = os.pipe()
            slot = SimpleNamespace(owner=owner, job=job, messages=[], child=None,
                                   diagnostic=diagnostic_r, safety=safety_w,
                                   reader=None, safe=threading.Event(), error=None,
                                   reaps=[], end=time.monotonic() + 24)
            self.slots.append(slot)

            def read():
                raw = bytearray()
                try:
                    while time.monotonic() < slot.end:
                        if not select.select([diagnostic_r], [], [], 0.1)[0]:
                            continue
                        part = os.read(diagnostic_r, 4096)
                        if not part:
                            return
                        raw.extend(part)
                        assert len(raw) <= 16384
                        while b"\n" in raw:
                            item, _, rest = raw.partition(b"\n")
                            raw[:] = rest
                            value = json.loads(item)
                            slot.messages.append(value)
                            if value["kind"] == "SAFE":
                                assert value["independent"] is True
                                assert all(row["waited"] and not row["ambiguous"]
                                           for row in value["children"])
                                slot.safe.set()
                except BaseException as exc:
                    slot.error = exc

            slot.reader = threading.Thread(target=read, name="fixture-diagnostics", daemon=False)
            slot.reader.start()
            try:
                slot.child = owner._spawn(
                    [sys.executable, "-I", "-B", str(self.script), "guardian",
                     str(job), str(slot.end), self.fault, str(control_fd),
                     str(cancel_fd), str(diagnostic_w), str(safety_r)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=log,
                    pass_fds=(control_fd, cancel_fd, lock_fd, diagnostic_w, safety_r),
                    close_fds=True, env=_ENV)
                original_wait = slot.child.wait

                def wait(timeout=None):
                    value = original_wait(timeout=timeout)
                    if not slot.reaps:
                        slot.reaps.append((slot.child.pid, value))
                    return value

                slot.child.wait = wait
                return slot.child
            finally:
                os.close(diagnostic_w)
                os.close(safety_r)

    def close(self):
        with self.lock:
            self.stopping = True
        for slot in self.slots:
            if not slot.safe.is_set():
                os.write(slot.safety, b"S")
            assert slot.safe.wait(max(0.001, slot.end-time.monotonic())), (
                "independent nested SAFE missing")
            assert slot.child is not None
            slot.child.wait(timeout=max(0.001, slot.end-time.monotonic()))
            slot.reader.join(timeout=max(0.001, slot.end-time.monotonic()))
            assert not slot.reader.is_alive() and slot.error is None
            for fd in (slot.diagnostic, slot.safety):
                os.close(fd)

    def assert_product(self, runner, code):
        assert len(self.slots) == len(runner._jobs) == 1
        slot, = self.slots
        job, = runner._jobs
        owner = slot.owner
        assert owner is job.invocation and type(owner) is self.core.OwnedSqlInvocation
        ack = job.ack
        assert ack is job.completion.cleanup_ack is owner._completion.cleanup_ack
        assert ack._authority.owner is owner and ack._authority.ack is ack
        assert ack.not_started is False and ack.released is True
        assert ack.child_waits is True and ack.thread_joins is True
        assert tuple(ack.guardian_reaps) == ((slot.child.pid, 0),)
        assert slot.reaps == [(slot.child.pid, 0)]
        assert owner._thread is not None and not owner._thread.is_alive()
        executed = [row for row in slot.messages if row["kind"] == "EXECUTED"]
        row, = executed
        assert row["program_sha256"] == hashlib.sha256(code.encode("utf-8")).hexdigest()
        assert row["request_sha256"] == owner.request_digest
        assert row["db_sha256"] == owner.request.db_sha256
        assert row["python"] and row["sqlite"]
        assert len([row for row in slot.messages if row["kind"] == "GRANT_ACCEPTED"]) == 1
        resource, = [row for row in slot.messages if row["kind"] == "PRODUCT_RESOURCES"]
        assert resource["deleted"] is True
        assert resource["active_rpc"] == resource["workers"] == 0
        roles = [row for row in resource["children"] if row["role"]]
        cli = [row for row in resource["children"] if not row["role"]]
        assert len(roles) == 1 and len(cli) >= 1
        assert all(row["waited"] and row["registered"] for row in roles + cli)
        shared = owner.executor.profile.shared_state_dir
        assert len(list(shared.glob("FINALIZATION-PENDING-*.json"))) == 1
        assert len(list(shared.glob("FINALIZATION-COMMITTED-*.json"))) == 1
        assert not list(shared.glob("UNRESOLVED*"))
        assert not (shared / "active.json").exists()


def make_host(root, *, enabled=True, program=None):
    from ptc import sql_isolation as core
    from ptc.harness import PTCHarnessConfig
    from ptc.test_sql_owned_invocation import _profile
    from train import sql_skill_eval as evaluator
    from train import sql_skills as skills
    from train.sql_skill_pilot import ApprovedSkill
    from train.sql_pilot_assets import envelope_bytes
    from train.test_sql_skills import world, promote, proposed, task_at, ids

    root.mkdir(parents=True, exist_ok=True)
    host = SimpleNamespace(root=root, enabled=enabled, runners=[], closes=[],
                           events=[], scores=[], tasks=[], records=[], traces=[])
    host.task = task_at(root, "private_reuse_canary", 11)
    host.task = dataclasses.replace(
        host.task, gold_sql=host.task.gold_sql + " /* private_gold_canary */")
    host.executor = core.PilotExecutor(_profile(root), state_dir=root / "owned-state")
    host.digest = hashlib.sha256(Path(host.task.db_path).read_bytes()).hexdigest()
    host.case = evaluator.SkillCase("reuse", host.task, ids("live", "reuse"),
                                    expected_db_sha256=host.digest)
    host.instrument = evaluator._current_binding(host.task, host.executor).instrument
    host.config = PTCHarnessConfig(max_turns=host.instrument.action_cap, program_timeout=5)
    host.approved = None
    if enabled:
        state = world(root / "qualification", skills, evaluator)
        if program is not None:
            state.candidate = proposed(skills, state.task, state.capture, program)
        promotion, captures = promote(skills, evaluator, state)
        assert promotion is not None and len(captures) == 4
        assert all(item.result.valid and item.result.score == 1 for item in captures)
        # Declared synthetic v2 identity. These were real host-SQLite captures,
        # not isolated PROGRAM/SCORER qualification or authenticated approvals.
        promotion = dataclasses.replace(
            promotion, schema_version=2,
            binding=evaluator._current_binding(host.task, host.executor))
        candidate_raw = skills.encode_candidate(state.candidate)
        promotion_raw = skills.encode_promotion(promotion)
        host.candidate_path = root / "candidate.json"
        host.promotion_path = root / "promotion.json"
        host.approval_path = root / "private-approval-canary.json"
        host.candidate_path.write_bytes(candidate_raw)
        host.promotion_path.write_bytes(promotion_raw)
        approval_raw = envelope_bytes("sql_pilot_host_approval", {
            "promotion_sha256": hashlib.sha256(promotion_raw).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate_raw).hexdigest(),
            "ids": dataclasses.asdict(promotion.ids),
        })
        host.approval_path.write_bytes(approval_raw)
        host.approved = ApprovedSkill(
            skills.decode_candidate(host.candidate_path.read_bytes()),
            skills.decode_promotion(host.promotion_path.read_bytes()),
            hashlib.sha256(promotion_raw).hexdigest(), host.approval_path,
            hashlib.sha256(approval_raw).hexdigest())
    return host


def require_builder():
    from ptc import sql_owned_program

    builder = sql_owned_program.build_owned_sql_program_harness
    for name in ("approved_skill", "reuse_case", "original_scorer_instrument"):
        assert name in inspect.signature(builder).parameters, (
            f"live reuse builder capability missing: {name}")
    return builder


def build_host(host, data, *, future=True):
    from ptc import sql_owned_program

    kwargs = dict(data=data, task=host.task, executor=host.executor,
                  db_sha256=host.digest,
                  max_rows=getattr(host, "action_max_rows", host.instrument.action_max_rows))
    builder = sql_owned_program.build_owned_sql_program_harness
    if future:
        builder = require_builder()
        kwargs.update(approved_skill=host.approved, reuse_case=host.case,
                      original_scorer_instrument=host.instrument)
    harness = builder(host.config, **kwargs)
    original_factory = harness.program_runner_factory

    def factory(actual_data, compiled):
        runner = original_factory(actual_data, compiled)
        assert type(runner) is sql_owned_program._Runner
        host.runners.append(runner)
        close = runner.aclose

        async def observed_close():
            host.closes.append(runner)
            return await close()

        runner.aclose = observed_close
        return runner

    harness.program_runner_factory = factory
    return harness


_PLUGIN = '''
from contextvars import ContextVar
from types import SimpleNamespace
from typing import Literal
from verifiers.v1.configs.taskset import TasksetConfig
from verifiers.v1.env import Env
from verifiers.v1.envs.single_agent import SingleAgentEnvConfig
from verifiers.v1.harness import Harness
from verifiers.v1.task import Task, TaskData
from verifiers.v1.taskset import Taskset
from bench.score import execution_accuracy, extract_sql
from ptc.harness import PTCHarness, PTCHarnessConfig
from ptc.test_sql_skill_reuse_integration import build_host

__all__ = ["Config", "Adapter", "SetConfig", "FixtureSet", "EnvConfig", "FixtureEnv"]
ACTIVE = ContextVar("live_registered_skill_fixture", default=None)

class Config(PTCHarnessConfig):
    id: Literal["live_registered_skill_fixture"] = "live_registered_skill_fixture"

class Adapter(PTCHarness, Harness[Config]):
    async def setup(self, runtime):
        record = ACTIVE.get()
        assert record.adapter is self and record.live
        record.setup = True
    async def launch(self, ctx, trace, runtime, endpoint, secret, mcp_urls, data):
        record = ACTIVE.get()
        host, task = record.host, record.task
        assert record.live and record.setup and record.adapter is self
        assert data is task.data
        assert trace.task.type == type(task).__name__
        assert trace.task.data is task.data
        assert trace.task.key == task.key
        assert trace.task.hash == task.hash
        assert record.scorer.__self__ is task
        assert record.scorer.__func__ is OriginalTask.score
        assert record.instrument is task.instrument is host.instrument
        assert record.sql_task is task.sql_task is host.task
        native = build_host(host, data, future=host.enabled)
        record.native = native
        return await native.launch(ctx, trace, runtime, endpoint, secret, mcp_urls, data)

class OriginalTask(Task):
    async def setup(self, trace, runtime):
        ACTIVE.get().host.events.append(("setup", self))
        await super().setup(trace, runtime)
    async def finalize(self, trace, runtime):
        ACTIVE.get().host.events.append(("finalize", self))
        await super().finalize(trace, runtime)
    async def score(self, trace, runtime=None):
        record = ACTIVE.get()
        host, instrument = record.host, self.instrument
        assert record.task is self
        assert trace.task.type == type(self).__name__
        assert trace.task.data is self.data
        assert trace.task.key == self.key
        assert trace.task.hash == self.hash
        assert record.scorer.__self__ is self and record.scorer.__func__ is OriginalTask.score
        assert record.instrument is instrument is host.instrument
        assert self.sql_task is record.sql_task is host.task
        host.events.append(("score", self))
        result = execution_accuracy(extract_sql(trace.last_reply or ""), self.sql_task,
            timeout_s=instrument.scorer_timeout_s, max_rows=instrument.scorer_max_rows,
            compare=instrument.compare)
        host.scores.append((self, record.scorer, instrument, result))
        assert result.valid is True
        trace.record_reward("execution_accuracy", result.score)

class SetConfig(TasksetConfig):
    id: Literal["live_registered_skill_fixture"] = "live_registered_skill_fixture"

class FixtureSet(Taskset[OriginalTask, SetConfig]):
    def load(self):
        host = ACTIVE.get()
        task = OriginalTask(TaskData(name=host.task.name, prompt=host.task.question),
                            self.config.task)
        task.sql_task, task.instrument = host.task, host.instrument
        host.tasks.append(task)
        yield task

class EnvConfig(SingleAgentEnvConfig):
    id: Literal["live_registered_skill_fixture"] = "live_registered_skill_fixture"

class FixtureEnv(Env[EnvConfig]):
    async def run(self, task, agents):
        host = ACTIVE.get()
        adapter = agents.agent.harness
        assert type(adapter) is Adapter
        record = SimpleNamespace(host=host, task=task, adapter=adapter, live=True,
            setup=False, scorer=task.score, instrument=task.instrument, sql_task=task.sql_task)
        host.records.append(record)
        token = ACTIVE.set(record)
        try:
            trace = await agents.agent.run(task)
            host.traces.append(trace)
        finally:
            record.live = False
            ACTIVE.reset(token)
'''


@pytest.fixture
def sdk_framework(monkeypatch, tmp_path):
    importlib.import_module("verifiers.v1.cli.eval.runner")
    from ptc.test_bash_qa_eval_integration import framework

    yield from framework.__wrapped__(monkeypatch, tmp_path)


def sdk_config(state, host):
    from verifiers.v1.configs.cli.eval import EvalConfig

    state.config = EvalConfig.model_validate_json(json.dumps({
        "model": "fixture-model",
        "client": {"type": "train", "api_key_var": "PROBE_UNUSED_API_KEY"},
        "env": {"id": _PLUGIN_ID, "taskset": {"id": _PLUGIN_ID},
                "interception": {"type": "server"},
                "agent": {"harness": {"id": _PLUGIN_ID, "program_timeout": 5.0},
                          "runtime": {"type": "subprocess"},
                          "max_turns": host.instrument.action_cap,
                          "timeout": {"setup": 3.0, "rollout": 25.0,
                                      "finalize": 2.0, "scoring": 3.0},
                          "retries": {"max_retries": 0}},
                "retries": {"max_retries": 0}},
        "num_tasks": 1, "num_rollouts": 1, "max_concurrent": 1,
        "push": False, "resume": False, "clean": False, "rich": None,
        "output_dir": str(state.root / "eval-output"), "run": {"dir": "run"},
    }))
    return state.config


def forbid_live_replay(monkeypatch):
    from train import sql_capture, sql_skill_eval, sql_skill_pilot

    calls = []

    def refused(*args, **kwargs):
        calls.append(1)
        raise AssertionError("live action invoked full capture/qualification path")

    for module, names in (
        (sql_skill_eval, ("reuse_promoted", "_execute", "promote_candidate")),
        (sql_capture, ("rescore_capture",)),
        (sql_skill_pilot, ("reuse_approved_files",)),
    ):
        for name in names:
            if hasattr(module, name):
                monkeypatch.setattr(module, name, refused)
    return calls


def sdk_positive(monkeypatch, state, *, enabled, mode="success", usage_present=True):
    from verifiers.v1.cli.eval.runner import run_eval
    from ptc.test_bash_qa_activation_integration import ScriptedClient, _text_step
    from ptc.test_bash_qa_eval_integration import _rows
    from train.test_sql_skills import PROGRAM
    from ptc.metrics import summarize

    if enabled:
        require_builder()
    host = make_host(state.root / "private", enabled=enabled)
    if mode == "one-turn":
        assert enabled is False, "one-turn probe must not weaken enabled instrument admission"
        host.config.max_turns = 1
    guardian = RegisteredGuardian(state.root, monkeypatch)
    (state.root / (_PLUGIN_ID + ".py")).write_text(_PLUGIN)
    monkeypatch.syspath_prepend(str(state.root))
    module = importlib.import_module(_PLUGIN_ID)
    config = sdk_config(state, host)
    args = (dict(skill_id=host.approved.candidate.skill_id,
                 promotion_sha256=host.approved.promotion_sha256)
            if enabled else {"code": PROGRAM})
    if mode == "rejected":
        args["skill_id"] = "unknown-reference"
    query = host.task.gold_sql.split(" /*")[0]

    class ObservedClient(ScriptedClient):
        async def get_response(self, *args, **kwargs):
            response = await super().get_response(*args, **kwargs)
            if not usage_present:
                raw = dict(response.raw)
                raw.pop("usage", None)
                object.__setattr__(response, "raw", raw)
                object.__setattr__(response, "usage", None)
            return response

    state.policy = policy = ObservedClient([
        {"call_id": "approved", "name": "run_program", "arguments": args},
        _text_step(query),
    ])
    replay = forbid_live_replay(monkeypatch)

    async def case():
        token = module.ACTIVE.set(host)
        try:
            episode, = await run_eval(config)
            assert episode.ok and len(episode.traces) == 1
            trace, = episode.traces
            assert trace is host.traces[0]
            assert trace.task.type == type(host.tasks[0]).__name__
            assert trace.task.data is host.tasks[0].data
            assert trace.task.key == host.tasks[0].key
            assert trace.task.hash == host.tasks[0].hash
            assert trace.ok and trace.reward == (0.0 if mode == "one-turn" else 1.0)
            task, scorer, instrument, result = host.scores[0]
            assert task is host.tasks[0] and instrument is host.instrument
            assert scorer.__self__ is task and scorer.__func__ is module.OriginalTask.score
            assert result.valid is True and result.score == (0 if mode == "one-turn" else 1)
            assert host.events == [("setup", task), ("finalize", task), ("score", task)]
            assert len(host.scores) == len(host.records) == len(host.runners) == 1
            assert host.records[0].instrument is instrument
            assert host.records[0].live is False and host.closes == host.runners
            assert policy.calls == (1 if mode == "one-turn" else 2)
            if mode != "one-turn":
                content = policy.bodies[1]["messages"][-1]["content"]
                if mode == "rejected":
                    assert content.startswith("rejected:")
                else:
                    assert content == "FINAL_SQL:" + query
            assert replay == []
            for body in policy.bodies:
                assert body["stream_options"]["include_usage"] is True
                assert [item["function"]["name"] for item in body["tools"]] == ["run_program"]
                advertised = json.dumps([body["messages"][0], body["tools"]])
                assert PROGRAM not in advertised
                assert json.dumps(PROGRAM)[1:-1] not in advertised
                wire = json.dumps(body)
                assert str(host.task.db_path) not in wire
                assert "private_gold_canary" not in wire
                if enabled:
                    assert str(host.approval_path) not in wire
            row, = _rows(config)
            assert row["ok"] and row["task"]["hash"] == task.hash
            assert row["traces"][0]["rewards"]["execution_accuracy"]["score"] == result.score
            metric = summarize([episode], "ptc", "registered-fixture",
                               turn_budget=host.config.max_turns)
            assert metric.tool_calls == 1
            assert metric.tool_failures == int(mode == "rejected")
            assert metric.n_budget_exhausted == int(mode == "one-turn")
            assert metric.usage_reported is usage_present
            if usage_present:
                assert metric.prompt_tokens == metric.completion_tokens == policy.calls
            else:
                assert metric.cost_total is None and metric.cost_per_solved is None
                assert getattr(trace.usage, "cost", None) is None
            # No price supplied by this fixture: reported usage is not a bill.
            assert metric.cost_total is None
            host.trace, host.episode, host.metric = trace, episode, metric
            return host
        finally:
            module.ACTIVE.reset(token)
            guardian.close()
    result = asyncio.run(asyncio.wait_for(case(), 29))
    if mode == "rejected":
        assert guardian.slots == [] and host.runners[0]._jobs == []
    else:
        guardian.assert_product(host.runners[0], PROGRAM)
    return result


def test_live_reuse_sdk_owned_direct_baseline_control(monkeypatch, sdk_framework):
    sdk_positive(monkeypatch, sdk_framework, enabled=False)


def test_live_reuse_sdk_original_scorer_positive(monkeypatch, sdk_framework):
    sdk_positive(monkeypatch, sdk_framework, enabled=True)


@pytest.mark.parametrize("mode", ("success", "rejected", "one-turn"))
def test_live_reuse_original_sdk_accounting(monkeypatch, sdk_framework, mode):
    host = sdk_positive(
        monkeypatch, sdk_framework, enabled=mode != "one-turn", mode=mode)
    assert host.trace is host.episode.traces[0] is host.traces[0]
    assert host.metric.tool_calls == 1


@pytest.mark.parametrize("usage_present", (True, False))
def test_live_reuse_original_sdk_usage_not_synthetic_zero(
        monkeypatch, sdk_framework, usage_present):
    host = sdk_positive(
        monkeypatch, sdk_framework, enabled=True, usage_present=usage_present)
    assert host.metric.usage_reported is usage_present
    assert host.metric.cost_total is None and host.metric.cost_per_solved is None


_NEGATIVE_HOST = r'''
import asyncio, json, os, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import pytest
from verifiers.v1.task import TaskData
from ptc.harness import ProgramInfrastructureError
from ptc.test_sql_skill_reuse_integration import make_host, build_host, RegisteredGuardian
from ptc.test_owned_program_runner import Policy, _assistant, _launch
from train.test_sql_skills import PROGRAM

root, fault = Path(sys.argv[2]), sys.argv[3]
patch = pytest.MonkeyPatch()
host = make_host(root / "private", enabled=False)
bridge = RegisteredGuardian(root, patch, fault=fault)
policy = Policy(_assistant(PROGRAM), _assistant(None))
loop = asyncio.new_event_loop()
error = None
success = False
pending = False
observed = False
poisoned = {}
task = None

def unresolved():
    if len(bridge.slots) != 1 or len(host.runners) != 1:
        return None
    slot, = bridge.slots
    owner = slot.owner
    assert type(owner) is bridge.core.OwnedSqlInvocation
    journal = json.loads((slot.job / "journal.json").read_bytes())
    shared = owner.executor.profile.shared_state_dir
    marker = shared / ("UNRESOLVED-" + journal["nonce"] + ".json")
    active = shared / "active.json"
    if journal["state"] != "UNRESOLVED" or not marker.exists() or not active.exists():
        return None
    assert journal["request_sha256"] == owner.request_digest
    block = json.loads(marker.read_bytes())
    reservation = json.loads(active.read_bytes())
    assert block["nonce"] == reservation["nonce"] == journal["nonce"]
    assert block["job"] == reservation["job"] == str(slot.job)
    assert owner._completion is None and owner._authority.ack is None
    job, = host.runners[0]._jobs
    assert job.invocation is owner and job.completion is None and job.ack is None
    assert not list(shared.glob("FINALIZATION-COMMITTED-*.json"))
    return {marker: marker.read_bytes(), active: active.read_bytes()}

def refusal():
    if len(bridge.slots) != 1:
        return False
    slot, = bridge.slots
    rows = [row for row in slot.messages
            if row.get("request_sha256") == slot.owner.request_digest]
    if fault == "removed-execution":
        return (any(row["kind"] == "CANDIDATE_REMOVED" for row in rows)
                and any(row["kind"] == "MISSING_CANDIDATE_REJECTED"
                        and row["reason"] == "guest exited without coordinated exit grant"
                        for row in rows)
                and not any(row["kind"] == "EXECUTED" for row in rows))
    if fault == "grant-digest":
        return any(row["kind"] == "GRANT_REJECTED"
                   and row["reason"] == "exit grant result mismatch" for row in rows)
    if fault == "result-digest":
        return any(row["kind"] == "RESULT_REJECTED"
                   and row["reason"] == "invalid result frame" for row in rows)
    if fault == "withheld-proof":
        return any(row["kind"] == "PROOF_WITHHELD"
                   and row["canonical_evidence"] is True for row in rows)
    return False

try:
    public = TaskData(name=host.task.name, prompt=host.task.question)
    harness = build_host(host, public, future=False)
    harness.transport = policy.transport()
    async def run():
        global success, error, pending, observed, poisoned, task
        task = asyncio.create_task(_launch(harness, public))
        end = time.monotonic() + 15
        while time.monotonic() < end:
            if task.done():
                try:
                    await task
                    success = True
                except ProgramInfrastructureError as exc:
                    error = type(exc).__name__
                    assert fault == "result-digest"
                    slot, = bridge.slots
                    completion = slot.owner._completion
                    assert completion is not None and completion.abort is not None
                    assert completion.abort.kind == "infrastructure"
                    observed = refusal()
                assert not success, "protocol fault became product success"
                if observed:
                    break
            if fault != "result-digest" and refusal():
                poisoned = unresolved()
                if poisoned is not None:
                    pending = True
                    observed = True
                    break
            await asyncio.sleep(0.01)
        assert observed, "specific protocol fault evidence absent within 15 seconds"
        # Independent safety starts at observed refusal, not public completion.
        bridge.close()
        assert len(policy.requests) == 1
    loop.run_until_complete(run())
except BaseException as exc:
    error = type(exc).__name__
    failed = True
else:
    failed = False
finally:
    # Independent fixture safety only, never _seal, _issue or a public ACK.
    if not bridge.stopping:
        bridge.close()
    for slot in bridge.slots:
        owner = slot.owner
        owner._retained.set()
        if owner._thread is not None:
            owner._thread.join(timeout=3)
            assert not owner._thread.is_alive()
        for resource in tuple(owner._resources):
            try:
                if isinstance(resource, int):
                    os.close(resource)
                elif callable(getattr(resource, "close", None)):
                    resource.close()
            except OSError:
                pass
    messages = [row for slot in bridge.slots for row in slot.messages]
    if observed and fault != "result-digest":
        assert pending and task is not None and not task.done()
        assert refusal() and unresolved() == poisoned
        assert all(path.read_bytes() == raw for path, raw in poisoned.items())
    assert len(bridge.slots) == 1
    assert all(slot.safe.is_set() and slot.reaps and not slot.reader.is_alive()
               and slot.error is None for slot in bridge.slots)
    sys.stdout.write(json.dumps(dict(success=success, pending=pending, error=error,
        failed=failed, safe=True, observed=observed,
        unresolved=bool(poisoned), requests=len(policy.requests),
        executions=sum(row["kind"] == "EXECUTED" for row in messages))) + "\n")
    sys.stdout.flush()
    os._exit(1 if failed else 0)
'''


@pytest.mark.parametrize("fault", (
    "removed-execution", "result-digest", "grant-digest", "withheld-proof",
))
def test_live_reuse_protocol_fault_cannot_be_success(tmp_path, fault):
    from ptc import sql_isolation as core

    script = tmp_path / "negative-host.py"
    script.write_text(_NEGATIVE_HOST)
    registry = []
    child = core._CreatorPopen(
        [sys.executable, "-I", "-B", str(script),
         str(Path(__file__).resolve().parents[1]), str(tmp_path), fault],
        _registry=registry, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True, env=_ENV)
    stdout, stderr = child.communicate(timeout=29)
    child.wait(timeout=1)
    assert child._creator_waited and registry == [child]
    assert child.returncode == 0, stderr.decode("utf-8", "replace")
    result = json.loads(stdout)
    assert result["safe"] is True and result["failed"] is False
    assert result["observed"] is True
    assert result["pending"] is (fault != "result-digest")
    assert result["unresolved"] is (fault != "result-digest")
    if fault == "result-digest":
        assert result["error"] == "ProgramInfrastructureError"
    assert result["success"] is False and result["requests"] == 1
    assert result["executions"] == (0 if fault == "removed-execution" else 1)


def _public(host):
    from verifiers.v1.task import TaskData

    return TaskData(name=host.task.name, prompt=host.task.question)


def _reference(host):
    return dict(skill_id=host.approved.candidate.skill_id,
                promotion_sha256=host.approved.promotion_sha256)


def _turn(host, kind):
    from ptc.test_owned_program_runner import _assistant

    if kind == "final":
        return _assistant(None)
    if kind == "direct":
        return _assistant("print('direct canary')")
    return _assistant(None, raw_args=json.dumps(_reference(host)))


def _source_copy(host, monkeypatch):
    from train import sql_skill_eval as evaluator, sql_skills as skills

    root = host.root / "selected-copy"
    for name in skills.SOURCE_PATHS:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((evaluator._ROOT / name).read_bytes())
    monkeypatch.setattr(evaluator, "_ROOT", root)
    return root / skills.SOURCE_PATHS[-1]


def _drift(host, kind, source):
    if kind == "approval":
        host.approval_path.write_bytes(host.approval_path.read_bytes() + b"\n")
    elif kind == "db":
        import sqlite3
        with sqlite3.connect(host.task.db_path) as connection:
            connection.execute('INSERT INTO "private_reuse_canary" VALUES (99)')
    else:
        source.write_bytes(source.read_bytes() + b"\n# test-owned drift\n")


def _policy_transport(policy, callback):
    import httpx

    original = policy.transport()

    def handle(request):
        response = original.handle_request(request)
        callback(len(policy.requests))
        return response

    return httpx.MockTransport(handle)


def _fatal_launch(host, harness, public, policy, *, requests, executions):
    from ptc.harness import ProgramInfrastructureError
    from ptc.test_owned_program_runner import _launch

    async def case():
        with pytest.raises(ProgramInfrastructureError):
            await _launch(harness, public)
        assert len(policy.requests) == requests
        assert sum(len(runner._jobs) for runner in host.runners) == executions
        assert host.scores == []
        assert host.closes == host.runners and len(host.runners) == 1
    asyncio.run(asyncio.wait_for(case(), 29))


@pytest.mark.parametrize("drift", ("approval", "db", "source"))
@pytest.mark.parametrize("response", ("direct", "reference", "final"))
def test_live_launch_first_response_authority_matrix(tmp_path, monkeypatch, drift, response):
    from ptc.test_owned_program_runner import Policy

    require_builder()
    host = make_host(tmp_path)
    source = _source_copy(host, monkeypatch)
    public = _public(host)
    harness = build_host(host, public)
    policy = Policy(_turn(host, response), _turn(host, "final"))
    harness.transport = _policy_transport(
        policy, lambda index: _drift(host, drift, source) if index == 1 else None)
    _fatal_launch(host, harness, public, policy, requests=1, executions=0)


@pytest.mark.parametrize("drift", ("approval", "db", "source"))
def test_live_launch_preflight_authority_matrix(tmp_path, monkeypatch, drift):
    from ptc.test_owned_program_runner import Policy

    require_builder()
    host = make_host(tmp_path)
    source = _source_copy(host, monkeypatch)
    public = _public(host)
    harness = build_host(host, public)
    policy = Policy(_turn(host, "reference"))
    harness.transport = policy.transport()
    _drift(host, drift, source)
    _fatal_launch(host, harness, public, policy, requests=0, executions=0)


@pytest.mark.parametrize("drift", ("approval", "db", "source"))
def test_live_launch_second_final_response_authority_matrix(tmp_path, monkeypatch, drift):
    from ptc.test_owned_program_runner import Policy

    require_builder()
    host = make_host(tmp_path)
    source = _source_copy(host, monkeypatch)
    public = _public(host)
    harness = build_host(host, public)
    policy = Policy(_turn(host, "reference"), _turn(host, "final"))
    harness.transport = _policy_transport(
        policy, lambda index: _drift(host, drift, source) if index == 2 else None)
    guardian = RegisteredGuardian(tmp_path, monkeypatch)
    try:
        _fatal_launch(host, harness, public, policy, requests=2, executions=1)
    finally:
        guardian.close()
    assert len([row for row in guardian.slots[0].messages if row["kind"] == "EXECUTED"]) == 1
    guardian.assert_product(host.runners[0], host.approved.candidate.program)


def _instrument_preflight(tmp_path, field):
    from ptc.test_owned_program_runner import Policy

    require_builder()
    host = make_host(tmp_path)
    if field == "action_cap":
        host.config.max_turns += 1
    elif field == "action_max_rows":
        host.action_max_rows = host.instrument.action_max_rows + 1
    elif field == "program_timeout":
        host.config.program_timeout = 4.999
    else:
        replacement = ("multiset" if host.instrument.compare == "set" else "set") if (
            field == "compare") else getattr(host.instrument, field) + 1
        host.instrument = dataclasses.replace(host.instrument, **{field: replacement})
    public = _public(host)
    harness = build_host(host, public)
    policy = Policy(_turn(host, "reference"))
    harness.transport = policy.transport()
    _fatal_launch(host, harness, public, policy, requests=0, executions=0)


def test_live_preflight_actual_harness_action_cap_mismatch(tmp_path):
    _instrument_preflight(tmp_path, "action_cap")


def test_live_preflight_action_rows_mismatch(tmp_path):
    _instrument_preflight(tmp_path, "action_max_rows")


def test_live_preflight_original_scorer_rows_mismatch(tmp_path):
    _instrument_preflight(tmp_path, "scorer_max_rows")


def test_live_preflight_original_scorer_mode_mismatch(tmp_path):
    _instrument_preflight(tmp_path, "compare")


def test_live_preflight_original_scorer_timeout_mismatch(tmp_path):
    _instrument_preflight(tmp_path, "scorer_timeout_s")


def test_live_preflight_program_timeout_remains_exactly_five(tmp_path):
    _instrument_preflight(tmp_path, "program_timeout")


@pytest.mark.parametrize("mutation", (
    "missing-approval", "whole-approval-pin", "approval-ids", "candidate-bytes",
    "promotion-pin", "promotion-source", "routing-scope", "case-role", "case-task",
    "db-digest", "public-data", "harness-config", "executor-profile",
    "catalog-callback", "selected-source", "v1-unbound",
))
def test_live_reuse_authority_mutations_never_allocate(tmp_path, monkeypatch, mutation):
    from ptc.harness import ProgramInfrastructureError
    from ptc.test_owned_program_runner import Policy, _launch
    from train import sql_skills as skills
    from train.sql_pilot_assets import envelope_bytes

    require_builder()
    host = make_host(tmp_path)
    selected = _source_copy(host, monkeypatch)
    public = _public(host)
    harness = build_host(host, public)
    policy = Policy(_turn(host, "reference"), _turn(host, "final"))
    harness.transport = policy.transport()
    approved = host.approved
    if mutation == "missing-approval":
        host.approval_path.rename(host.root / "retained-approval.json")
    elif mutation == "whole-approval-pin":
        _drift(host, "approval", selected)
    elif mutation == "approval-ids":
        payload = dict(
            candidate_sha256=hashlib.sha256(skills.encode_candidate(approved.candidate)).hexdigest(),
            promotion_sha256=approved.promotion_sha256,
            ids=dataclasses.asdict(approved.promotion.ids))
        payload["ids"]["episode_id"] = "wrong-approval"
        raw = envelope_bytes("sql_pilot_host_approval", payload)
        host.approval_path.write_bytes(raw)
        object.__setattr__(approved, "approval_sha256", hashlib.sha256(raw).hexdigest())
    elif mutation == "candidate-bytes":
        object.__setattr__(approved.candidate, "program", approved.candidate.program + "\nprint(0)")
    elif mutation == "promotion-pin":
        object.__setattr__(approved, "promotion_sha256", "b"*64)
    elif mutation == "promotion-source":
        object.__setattr__(approved.promotion, "source",
                           dataclasses.replace(approved.promotion.source, capture_sha256="c"*64))
    elif mutation == "routing-scope":
        object.__setattr__(host.task, "shape", "different-scope")
    elif mutation == "case-role":
        object.__setattr__(host.case, "role", "qualification")
    elif mutation == "case-task":
        object.__setattr__(host.case, "task", dataclasses.replace(host.task, name="other-task"))
    elif mutation == "db-digest":
        _drift(host, "db", selected)
    elif mutation == "public-data":
        object.__setattr__(public, "prompt", "changed public prompt")
    elif mutation == "harness-config":
        host.config.max_turns += 1
    elif mutation == "executor-profile":
        object.__setattr__(host.executor, "profile", dataclasses.replace(host.executor.profile))
    elif mutation == "catalog-callback":
        harness.catalog.tools["execute_sql"] = lambda **kwargs: []
    elif mutation == "selected-source":
        _drift(host, "source", selected)
    elif mutation == "v1-unbound":
        object.__setattr__(approved.promotion, "schema_version", 1)
        object.__setattr__(approved.promotion.binding, "execution_binding", None)

    async def case():
        with pytest.raises(ProgramInfrastructureError):
            await _launch(harness, public)
        assert policy.requests == [], "invalid host authority reached policy"
        assert sum(len(runner._jobs) for runner in host.runners) == 0
        assert host.scores == [] and host.closes == host.runners
    asyncio.run(asyncio.wait_for(case(), 5))


def test_live_reuse_launch_local_sqlite_and_cross_task_refusal(tmp_path, monkeypatch):
    from ptc.test_owned_program_runner import Policy, _launch
    from train.test_sql_skills import PROGRAM

    require_builder()
    program = PROGRAM.replace(
        'print("FINAL_SQL:SELECT COUNT(*) FROM " + quoted)',
        'count = execute_sql(query="SELECT COUNT(*) AS n FROM " + quoted)[0]["n"]\n'
        '    print("FINAL_SQL:SELECT COUNT(*) FROM " + quoted + " /* rows=" + str(count) + " */")')
    assert program != PROGRAM
    first = make_host(tmp_path / "first", program=program)
    second = make_host(tmp_path / "second", program=program)
    # Distinct data snapshots, same approved program, no global task authority.
    import sqlite3
    with sqlite3.connect(second.task.db_path) as connection:
        connection.execute('INSERT INTO "private_reuse_canary" VALUES (77)')
    second.digest = hashlib.sha256(Path(second.task.db_path).read_bytes()).hexdigest()
    second.case = dataclasses.replace(second.case, expected_db_sha256=second.digest)
    assert first.digest != second.digest
    guardian = RegisteredGuardian(tmp_path, monkeypatch)
    try:
        async def case():
            async def launch(host):
                public = _public(host)
                harness = build_host(host, public)
                policy = Policy(_turn(host, "reference"), _turn(host, "final"))
                harness.transport = policy.transport()
                await _launch(harness, public)
                assert len(policy.requests) == 2 and host.closes == host.runners
                assert str(host.task.db_path) not in json.dumps(policy.bodies)
                return host.runners[0]._jobs[0].completion.outcome.observation
            observed = await asyncio.gather(launch(first), launch(second))
            assert observed == [
                "FINAL_SQL:" + first.task.gold_sql.split(" /*")[0] + " /* rows=11 */",
                "FINAL_SQL:" + second.task.gold_sql.split(" /*")[0] + " /* rows=12 */",
            ]
            for host, total in ((first, 11), (second, 12)):
                with sqlite3.connect(host.task.db_path) as connection:
                    assert connection.execute(host.task.gold_sql).fetchone() == (total,)
            # Bind another task's case to this launch. IDs alone cannot authorize it.
            from ptc.harness import ProgramInfrastructureError
            first.case = second.case
            public = _public(first)
            harness = build_host(first, public)
            policy = Policy(_turn(first, "reference"))
            harness.transport = policy.transport()
            with pytest.raises(ProgramInfrastructureError):
                await _launch(harness, public)
            assert policy.requests == [] and len(guardian.slots) == 2
        asyncio.run(asyncio.wait_for(case(), 29))
    finally:
        guardian.close()
